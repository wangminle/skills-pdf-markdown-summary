#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QA-01 Golden Index.json 对比测试

核心回归集（8 份 PDF，扁平存放于 tests/basic-benchmark/*.pdf）：
1. 1706.03762v7-attention_is_all_you_need.pdf - 5 Figure + 4 Table
2. 2509.17765v1-Qwen3-Omni Technical Report.pdf - 3 Figure + 18 Table
3. 2607.24653v2-Kimi-K3.pdf - caption 索引约 16 Figure + 5 Table（以提取结果为准）
4. FunAudio-ASR.pdf - 4 Figure + 8 Table
5. gemini_v2_5_report.pdf - 16 Figure + 15 Table fragments (12 IDs)
6. gpt-5-system-card.pdf - 31 Figure + 26 Table
7. KearnsNevmyvakaHFTRiskBooks.pdf - 8 Figure + 1 Table
8. DeepSeek_V41_Tech_Report.pdf - 12 Figure + 5 Table

Golden 的定位：变更检测器，不是正确性基准。基准由当前输出生成，
会把已知缺陷（如历史版本中的表格截图误含正文）一并冻结；
后续修好这些缺陷时 golden 必然报红，这是预期行为。
基准更新必须在 task-list.md 逐条说明差异原因。基准位于已忽略的
tests/results/ 中，仅作本地变更检测，不纳入版本控制。

对比策略：
- 忽略不稳定字段：meta.extracted_at, meta.pdf_hash
- 对比稳定字段：
  - items 数量与 ID 集合（spec 期望 + golden 双重口径）
  - (type, id, page, continued) 身份集合
  - final_bbox（≤0.5pt 容差；index.json 坐标 round 1 位小数，容差与此兼容）
  - 输出 PNG 的字节尺寸 + sha256（严格相等；同一渲染环境内重复渲染哈希稳定，
    跨环境不保证，因此基准按渲染环境分文件，见下）
  - caption 是否非空
  - file 是否存在
- 基准缺失或 golden 用例被跳过一律判失败（禁止「全绿但零覆盖」）

使用方式：
  # 运行 golden 对比测试
  python3 tests/scripts/test_extraction_golden.py

  # 更新本地 golden 基准（当前提取结果作为新基准；只写本渲染环境的基准文件）
  python3 tests/scripts/test_extraction_golden.py --update-golden

  # 详细输出
  python3 tests/scripts/test_extraction_golden.py -v

  # pytest 入口（golden 默认纳入普通运行）
  python3 -m pytest tests/scripts/test_extraction_golden.py -q
  python3 -m pytest tests/scripts/ -q -m "not golden"   # 排除 golden 用例

产物位置：
  - 提取产物写入 tests/results/<yyyymmdd-xxx>/<pdf-name>/（批次目录为日期+序号），
    其下按 images/、txt/ 分层；批次目录下写 _code_fingerprint.json
    （skills/scripts 全部 .py 的内容汇总 sha256 + 生成时间）。
  - 复用规则：已有批次的 index.json 仅在指纹与当前 skills 代码一致时复用；
    指纹缺失或不符（即 skills/ 代码有变动）自动触发重新提取到新批次，
    防止「改了裁剪逻辑却比对旧产物」的假绿。
  - 环境变量 PDF_GOLDEN_REEXTRACT=1 可强制不复用、全部重新提取。
  - golden 基准按渲染环境分文件（BUG-166）：golden_index.<环境标识>.json，环境标识为
    「平台-CPU架构-pymupdf版本」，如 golden_index.darwin-arm64-pymupdf1.28.0.json。
    PNG 像素由 MuPDF 在具体平台上栅格化，同页同框在 macOS 与 Windows 上只差个别行
    几个字节，字节数与 sha256 却不同；基准只存这两项，所以不能跨环境共用。
    查找时优先本环境基准；没有则回退到旧版无后缀基准 golden_index.json（2026-10-24
    在 Windows 重建，保留不覆盖）。--update-golden 只写本环境基准文件，并报告它与其他
    基准、与本环境上一版基准的差异，供台账逐条说明。
    基准不纳入版本控制（tests/results/ 已整体 gitignore），也不校验代码指纹（与
    index.json 不同）：代码变更后仍应读取旧批次的 golden 作为对比基准。
    按批次从新到旧查找，同名文件取最新批次。clone 后需先运行 --update-golden 生成本地
    基准。basic-benchmark 仅保留 PDF（纯只读输入）。
"""

import hashlib
import json
import os
import platform
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any

import pytest

# 项目根目录：tests/scripts/ -> 向上三级
PROJECT_ROOT = Path(__file__).parent.parent.parent
TESTS_DIR = PROJECT_ROOT / "tests" / "basic-benchmark"
RESULTS_DIR = PROJECT_ROOT / "tests" / "results"

# A0-2: final_bbox 比较容差（PDF 点）。index.json 坐标 round 到 1 位小数，
# 容差取 0.5pt，既能容忍小数取舍，又能检出任何有意义的框位移动。
BBOX_TOLERANCE_PT = 0.5

# 批次复用的代码指纹文件名（写在批次目录下）
FINGERPRINT_FILENAME = "_code_fingerprint.json"

# 旧版基准文件名（不区分渲染环境；本环境没有基准时回退使用，保留不覆盖）
LEGACY_GOLDEN_FILENAME = "golden_index.json"

# 强制重新提取开关：设为 1 时不再复用任何已有批次产物
REEXTRACT_ENV = "PDF_GOLDEN_REEXTRACT"

# 提取器代码目录（指纹覆盖此目录下全部 .py，排除 __pycache__）
SKILLS_SCRIPTS_DIR = (
    PROJECT_ROOT / "skills" / "pdf-markdown-summary" / "scripts"
)


def _compute_code_fingerprint() -> str:
    """计算 skills 提取器代码指纹：scripts/ 下全部 .py 内容汇总为单个 sha256。

    汇总时混入相对路径，防止两个文件内容互换而哈希不变。
    """
    hasher = hashlib.sha256()
    for path in sorted(SKILLS_SCRIPTS_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        hasher.update(str(path.relative_to(SKILLS_SCRIPTS_DIR)).encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


# 当前代码指纹（懒计算，运行内只算一次）
_CURRENT_FINGERPRINT: Optional[str] = None


def _current_code_fingerprint() -> str:
    global _CURRENT_FINGERPRINT
    if _CURRENT_FINGERPRINT is None:
        _CURRENT_FINGERPRINT = _compute_code_fingerprint()
    return _CURRENT_FINGERPRINT


def _write_code_fingerprint(stem_dir: Path) -> None:
    """提取完成后在该 PDF 的产物目录记录源码指纹与完整渲染环境。"""
    payload = {
        "skills_scripts_sha256": _current_code_fingerprint(),
        "render_environment": render_environment(),
        "generated_at": datetime.now().isoformat(),
    }
    stem_dir.mkdir(parents=True, exist_ok=True)
    with open(stem_dir / FINGERPRINT_FILENAME, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _read_code_fingerprint(stem_dir: Path) -> Optional[str]:
    """仅返回同渲染环境的源码指纹；旧格式或损坏的缓存不可复用。"""
    fp_path = stem_dir / FINGERPRINT_FILENAME
    if not fp_path.exists():
        return None
    try:
        with open(fp_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, dict) and payload.get("render_environment") == render_environment():
            fingerprint = payload.get("skills_scripts_sha256")
            if isinstance(fingerprint, str):
                return fingerprint
    except (ValueError, OSError):
        return None
    return None


def _compute_batch_dir() -> Path:
    """计算新提取应写入的批次目录：tests/results/<yyyymmdd-xxx>。

    扫描 tests/results/ 下当天已有批次目录，取最大序号 +1；
    同一次运行内只计算一次（见 _get_batch_dir），所有用例复用同一批次目录。
    """
    today = datetime.now().strftime("%Y%m%d")
    max_seq = 0
    if RESULTS_DIR.exists():
        for entry in RESULTS_DIR.iterdir():
            m = re.fullmatch(r"(\d{8})-(\d{3})", entry.name)
            if m and m.group(1) == today:
                max_seq = max(max_seq, int(m.group(2)))
    return RESULTS_DIR / f"{today}-{max_seq + 1:03d}"


# 模块级批次目录缓存（懒计算，只有确实需要新提取时才取值）
_BATCH_DIR: Optional[Path] = None


def _get_batch_dir() -> Path:
    """获取本次运行的新提取批次目录（懒计算，运行内复用）"""
    global _BATCH_DIR
    if _BATCH_DIR is None:
        _BATCH_DIR = _compute_batch_dir()
    return _BATCH_DIR


def _find_existing_index(stem: str) -> Optional[Tuple[Path, Path]]:
    """在 tests/results/ 各批次中查找可复用的 <stem>/images/index.json。

    复用条件（防止「改了 skills/ 却比对旧产物」的假绿）：
    - 环境变量 PDF_GOLDEN_REEXTRACT=1 时不复用任何批次（强制重新提取）；
    - 产物目录的 _code_fingerprint.json 必须同时匹配当前源码与完整渲染环境；
      信息缺失或不符的产物直接跳过。

    按批次从新到旧检查，找到则返回 (images_dir, index_path)，否则返回 None。
    """
    if os.environ.get(REEXTRACT_ENV) == "1":
        return None
    if not RESULTS_DIR.exists():
        return None
    candidates: List[Tuple[str, Path]] = []
    for entry in RESULTS_DIR.iterdir():
        if not re.fullmatch(r"\d{8}-\d{3}", entry.name):
            continue
        index_path = entry / stem / "images" / "index.json"
        if index_path.exists():
            candidates.append((entry.name, index_path))
    # 从新到旧逐一校验指纹（指纹按 PDF 目录记录，见 _write_code_fingerprint）
    for _, index_path in sorted(candidates, reverse=True):
        stem_dir = index_path.parent.parent  # <batch>/<stem>/images/index.json -> <batch>/<stem>
        fingerprint = _read_code_fingerprint(stem_dir)
        if fingerprint is None or fingerprint != _current_code_fingerprint():
            continue
        return index_path.parent, index_path
    return None


def render_environment() -> Dict[str, str]:
    """当前渲染环境：平台、CPU 架构、PyMuPDF 与 MuPDF 版本。

    输出 PNG 的像素由 MuPDF 在具体平台与 CPU 架构上栅格化得到，同页同框在不同
    环境只差个别行几个字节，字节数与 sha256 却不同（BUG-166）。基准只存这两项，
    所以必须按环境分开保存与比较。
    """
    import fitz  # PyMuPDF：提取器必装，缺失时提取本身也跑不了

    return {
        "platform": sys.platform,
        "machine": platform.machine(),
        "pymupdf": str(getattr(fitz, "VersionBind", "")),
        "mupdf": str(getattr(fitz, "VersionFitz", "")),
    }


def legacy_render_environment_key(environment: Optional[Dict[str, str]] = None) -> str:
    """不含 MuPDF 的旧渲染环境标识，用于读取既有基准。"""
    env = environment if environment is not None else render_environment()
    return f"{env['platform']}-{env['machine']}-pymupdf{env['pymupdf']}"


def render_environment_key(environment: Optional[Dict[str, str]] = None) -> str:
    """完整渲染环境标识：平台-CPU架构-pymupdf版本-mupdf版本。"""
    env = environment if environment is not None else render_environment()
    return f"{legacy_render_environment_key(env)}-mupdf{env['mupdf']}"


def golden_filename_for(environment_key: str) -> str:
    """某渲染环境的基准文件名。"""
    return f"golden_index.{environment_key}.json"


def _environment_key_of_filename(filename: str) -> Optional[str]:
    """由基准文件名还原渲染环境标识；旧版无后缀基准返回空串，不是基准返回 None。"""
    if filename == LEGACY_GOLDEN_FILENAME:
        return ""
    prefix, suffix = "golden_index.", ".json"
    if filename.startswith(prefix) and filename.endswith(suffix) and len(filename) > len(prefix) + len(suffix):
        return filename[len(prefix):-len(suffix)]
    return None


def _find_golden_variants(stem: str) -> Dict[str, Path]:
    """某 PDF 现有的全部基准：键为渲染环境标识（旧版无后缀基准为空串）。

    值为该环境最新批次里的基准路径。别的环境的基准不参与本环境比较，只用于
    更新基准时的差异报告，以及「本环境基准是否过期」的诊断。
    """
    variants: Dict[str, Path] = {}
    if not RESULTS_DIR.exists():
        return variants
    for entry in sorted(RESULTS_DIR.iterdir(), reverse=True):
        if not re.fullmatch(r"\d{8}-\d{3}", entry.name):
            continue
        images_dir = entry / stem / "images"
        if not images_dir.is_dir():
            continue
        for path in images_dir.glob("golden_index*.json"):
            key = _environment_key_of_filename(path.name)
            if key is not None:
                variants.setdefault(key, path)
    return variants


def _find_golden_index(stem: str) -> Optional[Path]:
    """在 tests/results/ 各批次中查找该 PDF 的 golden 基准。

    优先返回完整渲染环境的基准（golden_index.<环境标识>.json）；本环境还没有
    基准时，先回退到同平台/架构/PyMuPDF 的旧环境键基准，再回退旧版无后缀基准
    golden_index.json。别的环境的基准不借用：它们的 PNG 字节数与 sha256 在本环境
    不可能复现，拿来比较只会得到无法处理的失败。旧文件只读，不自动改名或改写。

    golden 基准是本地变更检测基准，不纳入版本控制（tests/results/ 已整体
    gitignore），也不校验代码指纹（与 index.json 不同）：代码变更后仍应读取
    旧批次的 golden 作为对比基准。同类文件取最新批次。
    """
    variants = _find_golden_variants(stem)
    current = variants.get(render_environment_key())
    if current is not None:
        return current
    legacy_key = variants.get(legacy_render_environment_key())
    if legacy_key is not None:
        legacy_data = load_index_json(legacy_key)
        environment = (
            (legacy_data.get("meta") or {}).get("render_environment")
            if isinstance(legacy_data, dict) else None
        )
        has_known_conflict = isinstance(environment, dict) and any(
            environment.get(field) and str(environment[field]) != local
            for field, local in render_environment().items()
        )
        if not has_known_conflict or variants.get("") is None:
            return legacy_key
    return variants.get("")


def recorded_environment_key(golden_data: Dict[str, Any]) -> Optional[str]:
    """基准文件内记录的渲染环境标识；旧版基准没有记录，返回 None。"""
    environment = (golden_data.get("meta") or {}).get("render_environment")
    if isinstance(environment, dict) and environment.get("key"):
        return str(environment["key"])
    return None


# ============================================================================
# 核心回归集配置
# ============================================================================

@dataclass
class GoldenSpec:
    """Golden 规格定义"""
    pdf_file: str                # PDF 文件名（位于 tests/basic-benchmark/ 根下）
    expected_figures: int        # 期望的 Figure 数量
    expected_tables: int         # 期望的 Table 数量
    expected_ids: Dict[str, Set[str]] = field(default_factory=dict)  # 期望的 ID 集合
    # 已废弃：旧 benchmark 子目录布局已移除，golden 基准迁至 tests/results/
    benchmark_group: str = ""


# 核心回归集定义（8 份，扁平存放于 tests/basic-benchmark/*.pdf）
CORE_REGRESSION_SET: List[GoldenSpec] = [
    GoldenSpec(
        pdf_file="1706.03762v7-attention_is_all_you_need.pdf",
        expected_figures=5,
        expected_tables=4,
        expected_ids={
            "figures": {"1", "2", "3", "4", "5"},
            "tables": {"1", "2", "3", "4"},
        }
    ),
    GoldenSpec(
        pdf_file="2509.17765v1-Qwen3-Omni Technical Report.pdf",
        expected_figures=3,
        expected_tables=18,
        expected_ids={
            "figures": {"1", "2", "3"},
            "tables": {str(i) for i in range(1, 19)},
        }
    ),
    GoldenSpec(
        pdf_file="2607.24653v2-Kimi-K3.pdf",
        # 数量/ID 以首次 --update-golden 冻结的提取结果为准；占位先按 caption 索引上界
        expected_figures=16,
        expected_tables=5,
        expected_ids={
            "figures": {str(i) for i in range(1, 17)},
            "tables": {str(i) for i in range(1, 6)},
        }
    ),
    GoldenSpec(
        pdf_file="FunAudio-ASR.pdf",
        expected_figures=4,
        expected_tables=8,
        expected_ids={
            "figures": {"1", "2", "3", "4"},
            "tables": {"1", "2", "3", "4", "5", "6", "7", "8"},
        }
    ),
    GoldenSpec(
        pdf_file="gemini_v2_5_report.pdf",
        expected_figures=16,
        expected_tables=15,  # Table 11 跨4页，12个ID共15个表格片段
        expected_ids={
            "figures": {str(i) for i in range(1,17)},
            "tables": {str(i) for i in range(1, 13)},
        }
    ),
    GoldenSpec(
        pdf_file="gpt-5-system-card.pdf",
        expected_figures=31,
        expected_tables=26,
        expected_ids={
            "figures": {str(i) for i in range(1, 32)},
            "tables": {str(i) for i in range(1, 27)},
        }
    ),
    GoldenSpec(
        pdf_file="KearnsNevmyvakaHFTRiskBooks.pdf",
        expected_figures=8,
        expected_tables=1,
        expected_ids={
            "figures": {str(i) for i in range(1, 9)},
            "tables": {"1"},
        }
    ),
    GoldenSpec(
        pdf_file="DeepSeek_V41_Tech_Report.pdf",
        expected_figures=12,
        expected_tables=5,
        expected_ids={
            "figures": {str(i) for i in range(1, 13)},
            "tables": {str(i) for i in range(1, 6)},
        }
    ),
]


# ============================================================================
# 数据类定义
# ============================================================================

@dataclass
class ItemSignature:
    """图表条目签名（用于对比）。

    身份键为 (type, id, page, continued, occurrence)，hash/eq 只用这五项；
    occurrence 是同一四元组在 items 中的出现序号，用于区分重复条目。
    final_bbox / file_size / file_sha256 是比对负载，不参与 hash/eq：
    bbox 用 ≤0.5pt 容差逐元素比较（容差比较无法放进 __eq__），
    文件尺寸与 sha256 严格相等。
    """
    type: str      # "figure" | "table"
    id: str        # 标识符
    page: int      # 页码
    continued: bool  # 是否续页
    final_bbox: Optional[List[float]] = None   # [x0, y0, x1, y1]（PDF 点）
    file_size: Optional[int] = None            # 输出 PNG 字节尺寸
    file_sha256: Optional[str] = None          # 输出 PNG sha256
    occurrence: int = 0                        # 同身份四元组内的出现序号

    def identity(self) -> Tuple[str, str, int, bool, int]:
        """身份键（集合比对与负载配对都用它）"""
        return (self.type, self.id, self.page, self.continued, self.occurrence)

    def __hash__(self):
        return hash(self.identity())

    def __eq__(self, other):
        if not isinstance(other, ItemSignature):
            return False
        return self.identity() == other.identity()


@dataclass
class ComparisonResult:
    """对比结果"""
    pdf_name: str
    passed: bool
    messages: List[str] = field(default_factory=list)

    # 详细统计
    expected_count: int = 0
    actual_count: int = 0
    missing_items: List[ItemSignature] = field(default_factory=list)
    extra_items: List[ItemSignature] = field(default_factory=list)
    page_mismatches: List[Tuple[str, str, int, int]] = field(default_factory=list)  # (type, id, expected_page, actual_page)
    bbox_mismatches: List[str] = field(default_factory=list)   # bbox 差异描述
    file_mismatches: List[str] = field(default_factory=list)   # 文件尺寸/哈希差异描述


# ============================================================================
# 核心对比函数
# ============================================================================

def _file_sha256(path: Path) -> str:
    """分块计算文件 sha256"""
    hasher = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_index_json(index_path: Path) -> Optional[Dict[str, Any]]:
    """加载 index.json"""
    if not index_path.exists():
        return None

    try:
        with open(index_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON 解析失败: {index_path}: {e}")
        return None


def extract_item_signatures(
    index_data: Dict[str, Any],
    images_dir: Optional[Path] = None,
    from_golden: bool = False,
) -> Dict[Tuple[str, str, int, bool], ItemSignature]:
    """从 index.json 提取所有条目签名，key 为身份键。

    Args:
        index_data: index.json（或 golden_index.json）数据
        images_dir: 当前提取产物的 images 目录（用于实测 PNG 尺寸/哈希）；
            from_golden=True 时忽略（golden 不存 PNG，尺寸/哈希取自基准记录字段）
        from_golden: 是否解析 golden 基准（尺寸/哈希读 golden_file_* 字段）
    """
    signatures: Dict[Tuple[str, str, int, bool, int], ItemSignature] = {}
    seen: Dict[Tuple[str, str, int, bool], int] = {}

    items = index_data.get("items", [])
    for item in items:
        sig = ItemSignature(
            type=item.get("type", "unknown"),
            id=str(item.get("id", "")),
            page=item.get("page", 0),
            continued=item.get("continued", False),
            final_bbox=item.get("final_bbox"),
        )
        # 同 (type,id,page,continued) 可能出现多条（如同页多次续表）；
        # 不编号会让后出现的那条静默覆盖前一条，数量变化检测不出来。
        base = (sig.type, sig.id, sig.page, sig.continued)
        sig.occurrence = seen.get(base, 0)
        seen[base] = sig.occurrence + 1
        if from_golden:
            # golden 基准在 --update-golden 时记录的尺寸/哈希
            sig.file_size = item.get("golden_file_size_bytes")
            sig.file_sha256 = item.get("golden_file_sha256")
        elif images_dir is not None:
            file_name = item.get("file", "")
            file_path = images_dir / file_name if file_name else None
            if file_path is not None and file_path.exists():
                sig.file_size = file_path.stat().st_size
                sig.file_sha256 = _file_sha256(file_path)
        signatures[sig.identity()] = sig

    return signatures


def extract_id_sets(index_data: Dict[str, Any]) -> Dict[str, Set[str]]:
    """提取 Figure 和 Table 的 ID 集合"""
    figures: Set[str] = set()
    tables: Set[str] = set()

    items = index_data.get("items", [])
    for item in items:
        item_type = item.get("type", "")
        item_id = str(item.get("id", ""))

        if item_type == "figure":
            figures.add(item_id)
        elif item_type == "table":
            tables.add(item_id)

    return {"figures": figures, "tables": tables}


def count_by_type(index_data: Dict[str, Any]) -> Tuple[int, int]:
    """统计 Figure 和 Table 数量"""
    figures = 0
    tables = 0

    items = index_data.get("items", [])
    for item in items:
        item_type = item.get("type", "")
        if item_type == "figure":
            figures += 1
        elif item_type == "table":
            tables += 1

    return figures, tables


def check_files_exist(index_data: Dict[str, Any], images_dir: Path) -> List[str]:
    """检查所有引用的文件是否存在"""
    missing_files = []

    items = index_data.get("items", [])
    for item in items:
        file_name = item.get("file", "")
        if file_name:
            file_path = images_dir / file_name
            if not file_path.exists():
                missing_files.append(file_name)

    return missing_files


def _compare_bbox(
    expected: Optional[List[float]],
    actual: Optional[List[float]],
    label: str,
) -> Optional[str]:
    """比较 final_bbox（≤0.5pt 容差），不一致返回描述文本，一致返回 None"""
    if expected is None or actual is None:
        return f"{label}: final_bbox 缺失（golden={expected}, 当前={actual}）"
    if len(expected) != 4 or len(actual) != 4:
        return f"{label}: final_bbox 长度异常（golden={expected}, 当前={actual}）"
    diffs = [abs(e - a) for e, a in zip(expected, actual)]
    if any(d > BBOX_TOLERANCE_PT for d in diffs):
        return (
            f"{label}: final_bbox 偏移超过 {BBOX_TOLERANCE_PT}pt "
            f"（golden={expected}, 当前={actual}, 最大偏差={max(diffs):.2f}pt）"
        )
    return None


def compare_with_golden(
    spec: GoldenSpec,
    golden_data: Optional[Dict[str, Any]],
    current_data: Dict[str, Any],
    images_dir: Path,
) -> ComparisonResult:
    """
    对比当前提取结果与 golden 基准

    如果没有 golden 数据，则只与 spec 中的期望值对比
    """
    result = ComparisonResult(pdf_name=spec.pdf_file, passed=True)

    # 1. 数量对比
    actual_figures, actual_tables = count_by_type(current_data)
    result.expected_count = spec.expected_figures + spec.expected_tables
    result.actual_count = actual_figures + actual_tables

    if actual_figures != spec.expected_figures:
        result.passed = False
        result.messages.append(
            f"Figure 数量不匹配: 期望 {spec.expected_figures}，实际 {actual_figures}"
        )

    if actual_tables != spec.expected_tables:
        result.passed = False
        result.messages.append(
            f"Table 数量不匹配: 期望 {spec.expected_tables}，实际 {actual_tables}"
        )

    # 2. ID 集合对比
    actual_ids = extract_id_sets(current_data)

    missing_figures = spec.expected_ids.get("figures", set()) - actual_ids["figures"]
    extra_figures = actual_ids["figures"] - spec.expected_ids.get("figures", set())

    if missing_figures:
        result.passed = False
        result.messages.append(f"缺失 Figure IDs: {sorted(missing_figures)}")

    if extra_figures:
        result.passed = False
        result.messages.append(f"额外 Figure IDs: {sorted(extra_figures)}")

    missing_tables = spec.expected_ids.get("tables", set()) - actual_ids["tables"]
    extra_tables = actual_ids["tables"] - spec.expected_ids.get("tables", set())

    if missing_tables:
        result.passed = False
        result.messages.append(f"缺失 Table IDs: {sorted(missing_tables)}")

    if extra_tables:
        result.passed = False
        result.messages.append(f"额外 Table IDs: {sorted(extra_tables)}")

    # 3. 文件存在性检查
    missing_files = check_files_exist(current_data, images_dir)
    if missing_files:
        result.passed = False
        result.messages.append(f"缺失文件: {missing_files[:5]}{'...' if len(missing_files) > 5 else ''}")

    # 4. Caption 非空检查
    items = current_data.get("items", [])
    empty_captions = [
        f"{item.get('type', 'unknown')}_{item.get('id', '?')}"
        for item in items
        if not item.get("caption", "").strip()
    ]
    if empty_captions:
        result.passed = False
        result.messages.append(f"空 Caption 条目: {empty_captions[:5]}{'...' if len(empty_captions) > 5 else ''}")

    # 5. 与 Golden 对比（如果有）
    if golden_data:
        golden_sigs = extract_item_signatures(golden_data, from_golden=True)
        current_sigs = extract_item_signatures(current_data, images_dir=images_dir)

        missing = set(golden_sigs) - set(current_sigs)
        extra = set(current_sigs) - set(golden_sigs)

        if missing:
            result.passed = False
            result.missing_items = [golden_sigs[k] for k in missing]
            result.messages.append(
                f"相比 Golden 缺失 {len(missing)} 项: "
                f"{[(s.type, s.id, s.page) for s in result.missing_items[:3]]}..."
            )

        if extra:
            result.passed = False
            result.extra_items = [current_sigs[k] for k in extra]
            result.messages.append(
                f"相比 Golden 多出 {len(extra)} 项: "
                f"{[(s.type, s.id, s.page) for s in result.extra_items[:3]]}..."
            )

        # 6. 逐条负载对比：final_bbox（≤0.5pt 容差）+ PNG 尺寸/sha256（严格相等）
        for key in sorted(set(golden_sigs) & set(current_sigs)):
            g = golden_sigs[key]
            c = current_sigs[key]
            label = f"{g.type} {g.id} (page {g.page})"

            # golden 基准必须带 A0-2 新字段，否则视为过期基准
            if g.final_bbox is None or g.file_size is None or g.file_sha256 is None:
                result.passed = False
                result.file_mismatches.append(
                    f"{label}: golden 基准缺少 final_bbox/文件尺寸/哈希字段，"
                    f"请用 --update-golden 重新生成"
                )
                continue

            bbox_msg = _compare_bbox(g.final_bbox, c.final_bbox, label)
            if bbox_msg:
                result.passed = False
                result.bbox_mismatches.append(bbox_msg)

            if c.file_size is None or c.file_sha256 is None:
                result.passed = False
                result.file_mismatches.append(f"{label}: 当前输出 PNG 缺失或不可读")
                continue

            if c.file_size != g.file_size:
                result.passed = False
                result.file_mismatches.append(
                    f"{label}: PNG 尺寸不一致（golden={g.file_size}B, 当前={c.file_size}B）"
                )
            elif c.file_sha256 != g.file_sha256:
                result.passed = False
                result.file_mismatches.append(
                    f"{label}: PNG sha256 不一致（golden={g.file_sha256[:12]}..., "
                    f"当前={c.file_sha256[:12]}...）"
                )

        if result.bbox_mismatches:
            result.messages.append(
                f"final_bbox 差异 {len(result.bbox_mismatches)} 项: "
                f"{result.bbox_mismatches[:3]}..."
            )
        if result.file_mismatches:
            result.messages.append(
                f"文件尺寸/哈希差异 {len(result.file_mismatches)} 项: "
                f"{result.file_mismatches[:3]}..."
            )

    if result.passed:
        result.messages.insert(0, "通过所有检查")

    return result


# ============================================================================
# 多环境基准：自检、差异统计与失败诊断
# ============================================================================

def _batch_name_of(golden_path: Path) -> str:
    """基准所在批次目录名：<batch>/<stem>/images/golden_index*.json"""
    return golden_path.parent.parent.parent.name


def baseline_problems(golden_path: Path, golden_data: Dict[str, Any]) -> List[str]:
    """验证文件名与元数据，并拒绝与本机渲染环境明确冲突的旧键基准。

    把别的平台的基准改个名冒充本环境基准，会在本环境留下永远对不上的 PNG 哈希，
    还抹掉了基准的真实来源；这种文件必须显式拒绝。
    """
    filename_key = _environment_key_of_filename(golden_path.name)
    recorded = recorded_environment_key(golden_data)
    if (recorded or "") != filename_key:
        filename_label = filename_key or "旧版无后缀文件名"
        return [
            f"基准渲染环境标识不一致（文件名={filename_label}，文件内记录={recorded}）："
            f"基准文件可能被改名或混入，请保留旧版无环境记录文件，或在目标环境重新 "
            f"--update-golden: {golden_path}"
        ]
    environment = (golden_data.get("meta") or {}).get("render_environment")
    if isinstance(environment, dict):
        for field, local in render_environment().items():
            value = environment.get(field)
            if value and str(value) != local:
                return [
                    f"基准渲染环境标识不一致（{field}：文件内={value}，本机={local}）："
                    f"请在目标环境重新 --update-golden: {golden_path}"
                ]
    return []


def diff_golden_baselines(reference: Dict[str, Any], other: Dict[str, Any]) -> Dict[str, int]:
    """两份基准的精确差异计数；不同于正式比较，bbox 在这里不使用容差。"""
    reference_sigs = extract_item_signatures(reference, from_golden=True)
    other_sigs = extract_item_signatures(other, from_golden=True)
    bbox_diffs = 0
    png_diffs = 0
    for key in set(reference_sigs) & set(other_sigs):
        ref, oth = reference_sigs[key], other_sigs[key]
        if ref.final_bbox != oth.final_bbox:
            bbox_diffs += 1
        if (ref.file_size, ref.file_sha256) != (oth.file_size, oth.file_sha256):
            png_diffs += 1
    return {
        "identity": len(set(reference_sigs) ^ set(other_sigs)),
        "final_bbox": bbox_diffs,
        "png": png_diffs,
    }


def _format_baseline_diff(label: str, batch: str, diff: Dict[str, int]) -> str:
    # 标签以英文（环境标识）开头时，中文「与」后留一个空格
    spacer = " " if label[:1].isascii() else ""
    return (
        f"与{spacer}{label}（批次 {batch}）对比：条目差异 {diff['identity']}、"
        f"final_bbox 差异 {diff['final_bbox']}、PNG 字节差异 {diff['png']}"
    )


def _baseline_diff_notes(stem: str, environment_key: str, new_golden: Dict[str, Any]) -> List[str]:
    """新基准与既有基准的差异：其他环境（含旧版）各比一份，外加本环境的上一版。

    基准更新后要在 task-list.md 逐条说明差异原因，这里把差异先数出来。
    """
    latest_by_key = _find_golden_variants(stem)
    targets: List[Tuple[str, Path]] = [
        ("旧版基准" if not key else f"{key} 环境基准", path)
        for key, path in sorted(latest_by_key.items()) if key != environment_key
    ]
    previous = latest_by_key.get(environment_key)
    if previous is not None:
        targets.append(("本环境上一版基准", previous))

    notes: List[str] = []
    for label, path in targets:
        batch = _batch_name_of(path)
        data = load_index_json(path)
        if data is None:
            notes.append(f"与{label}（批次 {batch}）对比：基准无法读取")
            continue
        notes.append(_format_baseline_diff(label, batch, diff_golden_baselines(new_golden, data)))
    return notes


def _stale_baseline_hint(
    stem: str,
    golden_path: Path,
    current_data: Dict[str, Any],
    images_dir: Path,
) -> Optional[str]:
    """本环境基准比别的环境的基准旧，而当前产物的条目与框位与那份更新的基准一致。

    两台机器共用同一个 tests/results/ 时，一边为某次修复更新了基准，另一边的
    基准不会跟着变。此时另一边看到的是条目或 final_bbox 差异，很容易误判成
    代码回归。只生成提示，不改变判定：基准过期同样要显式更新并说明原因。
    """
    batch = _batch_name_of(golden_path)
    current = extract_item_signatures(current_data, images_dir=images_dir)
    for key, path in sorted(_find_golden_variants(stem).items()):
        other_batch = _batch_name_of(path)
        if path == golden_path or other_batch <= batch:
            continue
        other = load_index_json(path)
        if other is None:
            continue
        other_sigs = extract_item_signatures(other, from_golden=True)
        if set(other_sigs) != set(current):
            continue
        if all(not _compare_bbox(other_sigs[k].final_bbox, current[k].final_bbox, "") for k in current):
            label = "旧版" if not key else f"{key} 环境"
            return (
                f"本环境基准（批次 {batch}）早于{label}基准（批次 {other_batch}），"
                f"而当前产物的条目与 final_bbox 与后者一致：本环境基准可能过期。"
                f"先核对台账中批次 {other_batch} 的更新说明，确认后再 --update-golden。"
            )
    return None


def comparison_hints(
    stem: str,
    golden_path: Path,
    golden_data: Dict[str, Any],
    current_data: Dict[str, Any],
    images_dir: Path,
    result: ComparisonResult,
) -> List[str]:
    """比较失败后的补充说明：只解释原因与处理办法，不改变判定。"""
    hints: List[str] = []
    recorded = recorded_environment_key(golden_data)
    if recorded != render_environment_key() and result.file_mismatches:
        origin = recorded or "未记录渲染环境的旧版基准"
        hints.append(
            f"基准环境为 {origin}，当前完整渲染环境为 {render_environment_key()}。"
            f"若只有 PNG 尺寸/哈希不一致而条目与 final_bbox 一致，可能是跨渲染环境的"
            f"像素舍入差异：运行 --update-golden 生成本环境基准，旧基准不会被覆盖。"
        )
    if result.missing_items or result.extra_items or result.bbox_mismatches:
        stale = _stale_baseline_hint(stem, golden_path, current_data, images_dir)
        if stale:
            hints.append(stale)
    return hints


# ============================================================================
# 测试运行器
# ============================================================================

def _resolve_golden_paths(spec: GoldenSpec) -> Tuple[Path, Path, Path, Path]:
    """Resolve PDF path, images dir, index.json and golden_index.json.

    - PDF 扁平存放于 tests/basic-benchmark/<pdf_file>（纯只读输入）。
    - images/index.json 等提取产物优先复用 tests/results/ 已有批次中的产物；
      没有已提取产物时，路径指向本次运行的新批次目录（懒创建）。
    - golden 基准存放于 tests/results/ 各批次中（本地基准，不纳入
      版本控制——tests/results/ 已整体 gitignore）；按渲染环境分文件，读取时优先
      本环境基准、没有则回退旧版基准，取最新批次（_find_golden_index，不校验
      指纹）。更新时由 run_golden_tests 创建单独批次，与被比较的 index.json 分离；
      新 clone 需先运行 --update-golden 生成基准。
    """
    stem = Path(spec.pdf_file).stem
    pdf_path = TESTS_DIR / spec.pdf_file
    existing = _find_existing_index(stem)
    if existing is not None:
        images_dir, index_path = existing
    else:
        images_dir = _get_batch_dir() / stem / "images"
        index_path = images_dir / "index.json"
    golden_path = _find_golden_index(stem) or (images_dir / LEGACY_GOLDEN_FILENAME)
    return pdf_path, images_dir, index_path, golden_path


def golden_is_self_comparison(index_path: Path, golden_path: Path) -> bool:
    """判断基准是否就出自被比对象所在的那次运行（同批次）。

    `_find_golden_index` 取「最新含基准的批次」，而 `_find_existing_index`
    取「最新含 index.json 的批次」。`--update-golden` 会把基准写进它自己
    刚提取出来的批次，于是两者落在同一批次目录——此时无论产物对不对，
    比较都必然全绿（假绿）。

    比父目录而非比文件：文件名本就不同（index.json / golden_index.json），
    比文件永远为 False，判不到自比状态。

    这类状态必须显式失败：真实防回归需要「另一次运行的产物 vs 基准」。
    """
    try:
        return index_path.resolve().parent == golden_path.resolve().parent
    except OSError:
        return False


def ensure_extracted_index(spec: GoldenSpec, verbose: bool = False) -> Tuple[bool, str]:
    """Run extraction when index.json is missing.

    提取产物写入 tests/results/<yyyymmdd-xxx>/<pdf-name>/ 下，
    按 images/、txt/ 分层；已有批次中存在 index.json 则复用，不重复提取。
    """
    stem = Path(spec.pdf_file).stem
    pdf_path, images_dir, index_path, _ = _resolve_golden_paths(spec)
    if index_path.exists():
        return True, ""
    if not pdf_path.exists():
        return False, f"PDF 不存在: {pdf_path}"

    import subprocess

    images_dir.mkdir(parents=True, exist_ok=True)
    txt_dir = _get_batch_dir() / stem / "txt"
    txt_dir.mkdir(parents=True, exist_ok=True)
    script = PROJECT_ROOT / "skills" / "pdf-markdown-summary" / "scripts" / "extract_pdf_assets.py"
    cmd = [
        sys.executable,
        str(script),
        "--pdf", str(pdf_path),
        "--out-dir", str(images_dir),
        "--index-json", str(index_path),
        "--out-text", str(txt_dir / f"{stem}.txt"),
        "--preset", "robust",
    ]
    if verbose:
        print(f"  运行提取: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return False, f"提取失败 (exit {result.returncode}): {detail[:300]}"
    if not index_path.exists():
        return False, f"提取完成但 index.json 未生成: {index_path}"
    # 提取完成后记录代码指纹（测试侧落盘，不改 skills/）
    _write_code_fingerprint(index_path.parent.parent)
    return True, ""


def run_golden_tests(
    verbose: bool = False,
    update_golden: bool = False,
) -> Tuple[int, int, List[ComparisonResult]]:
    """
    运行 Golden 对比测试

    Args:
        verbose: 显示详细输出
        update_golden: 更新 golden 基准文件

    Returns:
        (passed_count, failed_count, results)
    """
    results: List[ComparisonResult] = []
    # 一次更新操作中的所有 PDF 共用一个独立基准批次。
    update_batch_dir: Optional[Path] = None

    for spec in CORE_REGRESSION_SET:
        pdf_path, images_dir, index_path, golden_path = _resolve_golden_paths(spec)

        if verbose:
            print(f"\n{'='*60}")
            print(f"测试: {spec.pdf_file}")
            print(f"PDF: {pdf_path}")
            print(f"输出: {images_dir}")
            print('='*60)

        ok, extract_msg = ensure_extracted_index(spec, verbose=verbose)
        if not ok:
            result = ComparisonResult(
                pdf_name=spec.pdf_file,
                passed=False,
                messages=[extract_msg],
            )
            results.append(result)
            if verbose:
                print(f"  {extract_msg}")
            continue

        # 检查 index.json 是否存在
        if not index_path.exists():
            result = ComparisonResult(
                pdf_name=spec.pdf_file,
                passed=False,
                messages=[f"index.json 不存在: {index_path}"]
            )
            results.append(result)
            if verbose:
                print(f"  {result.messages[0]}")
            continue

        # 加载当前 index.json
        current_data = load_index_json(index_path)
        if current_data is None:
            result = ComparisonResult(
                pdf_name=spec.pdf_file,
                passed=False,
                messages=["无法加载 index.json"]
            )
            results.append(result)
            continue

        # 加载 golden 基准（如果存在）
        golden_data = load_index_json(golden_path) if golden_path.exists() else None

        # 如果要更新 golden
        if update_golden:
            environment = render_environment()
            environment_key = render_environment_key(environment)
            # 创建精简的 golden 数据（移除不稳定字段），
            # 并为每条资产记录输出 PNG 的字节尺寸与 sha256（A0-2）
            golden_items: List[Dict[str, Any]] = []
            for item in current_data.get("items", []):
                item_copy = dict(item)
                file_name = item.get("file", "")
                file_path = images_dir / file_name if file_name else None
                if file_path is not None and file_path.exists():
                    item_copy["golden_file_size_bytes"] = file_path.stat().st_size
                    item_copy["golden_file_sha256"] = _file_sha256(file_path)
                golden_items.append(item_copy)

            golden_to_save = {
                "version": current_data.get("version", "2.0"),
                "meta": {
                    "pdf": current_data.get("meta", {}).get("pdf", spec.pdf_file),
                    "pages": current_data.get("meta", {}).get("pages", 0),
                    "preset": current_data.get("meta", {}).get("preset", "robust"),
                    # 记录基准产自哪个渲染环境；PNG 字节只在同一环境内可复现
                    "render_environment": {"key": environment_key, **environment},
                    # 注意：不保存 extracted_at 和 pdf_hash
                },
                "items": golden_items,
            }

            # 基准必须与生成它的 index.json 分批保存，否则比较会变成自比假绿。
            # 批次目录只计算一次，保证同次更新的所有 PDF 归于同一批次。
            stem = Path(spec.pdf_file).stem
            if update_batch_dir is None:
                update_batch_dir = _compute_batch_dir()
            # 只写本环境的基准文件；旧版无后缀基准与其他环境的基准原样保留。
            # 与既有基准的差异在写盘前统计：本环境的上一版写盘后就会被新文件取代。
            diff_notes = _baseline_diff_notes(stem, environment_key, golden_to_save)
            golden_write_path = (
                update_batch_dir / stem / "images" / golden_filename_for(environment_key)
            )
            golden_write_path.parent.mkdir(parents=True, exist_ok=True)
            with open(golden_write_path, 'w', encoding='utf-8') as f:
                json.dump(golden_to_save, f, ensure_ascii=False, indent=2)

            result = ComparisonResult(
                pdf_name=spec.pdf_file,
                passed=True,
                messages=[
                    f"已更新本环境 golden 基准（{environment_key}）: {golden_write_path}",
                    *diff_notes,
                ],
            )
            results.append(result)
            if verbose:
                for msg in result.messages:
                    print(f"  {msg}")
            continue

        # 基准缺失即失败（禁止空跑；与 pytest 入口的断言同口径）
        if golden_data is None:
            result = ComparisonResult(
                pdf_name=spec.pdf_file,
                passed=False,
                messages=[
                    f"golden 基准缺失（禁止空跑）: {golden_path}，"
                    f"请运行 --update-golden 生成"
                ]
            )
            results.append(result)
            if verbose:
                print(f"  {result.messages[0]}")
            continue

        if golden_is_self_comparison(index_path, golden_path):
            result = ComparisonResult(
                pdf_name=spec.pdf_file,
                passed=False,
                messages=[f"golden 基准与被比产物同批次，禁止自比假绿: {index_path}"],
            )
            results.append(result)
            if verbose:
                print(f"  {result.messages[0]}")
            continue

        # 基准自检：文件名的环境标识与文件内记录不符的基准不能用来比较
        problems = baseline_problems(golden_path, golden_data)
        if problems:
            result = ComparisonResult(
                pdf_name=spec.pdf_file, passed=False, messages=problems
            )
            results.append(result)
            if verbose:
                print(f"  {result.messages[0]}")
            continue

        # 执行对比
        result = compare_with_golden(spec, golden_data, current_data, images_dir)
        if not result.passed:
            result.messages.extend(comparison_hints(
                Path(spec.pdf_file).stem, golden_path, golden_data,
                current_data, images_dir, result,
            ))
        results.append(result)

        if verbose:
            for msg in result.messages:
                print(f"  {msg}")

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)

    return passed, failed, results


def print_diff_summary(results: List[ComparisonResult]) -> None:
    """打印差异摘要"""
    print("\n" + "="*60)
    print("差异摘要")
    print("="*60)

    for result in results:
        if not result.passed:
            print(f"\n{result.pdf_name}")
            print(f"   期望: {result.expected_count} 项，实际: {result.actual_count} 项")

            if result.missing_items:
                print(f"   缺失:")
                for sig in result.missing_items[:5]:
                    print(f"     - {sig.type} {sig.id} (page {sig.page})")
                if len(result.missing_items) > 5:
                    print(f"     ... 共 {len(result.missing_items)} 项")

            if result.extra_items:
                print(f"   多出:")
                for sig in result.extra_items[:5]:
                    print(f"     + {sig.type} {sig.id} (page {sig.page})")
                if len(result.extra_items) > 5:
                    print(f"     ... 共 {len(result.extra_items)} 项")

            if result.bbox_mismatches:
                print(f"   final_bbox 差异:")
                for msg in result.bbox_mismatches[:5]:
                    print(f"     ~ {msg}")
                if len(result.bbox_mismatches) > 5:
                    print(f"     ... 共 {len(result.bbox_mismatches)} 项")

            if result.file_mismatches:
                print(f"   文件尺寸/哈希差异:")
                for msg in result.file_mismatches[:5]:
                    print(f"     # {msg}")
                if len(result.file_mismatches) > 5:
                    print(f"     ... 共 {len(result.file_mismatches)} 项")


# ============================================================================
# pytest 入口
# ============================================================================

@pytest.mark.golden
@pytest.mark.parametrize(
    "spec",
    CORE_REGRESSION_SET,
    ids=lambda spec: Path(spec.pdf_file).stem,
)
def test_golden_index_comparison(spec: GoldenSpec) -> None:
    """对核心回归集 8 份 PDF 逐一对比（基准缺失即失败，禁止空跑）。

    复用 tests/results/ 已有批次的提取产物；同一次运行内所有用例共享
    模块级批次目录，不会每个用例重跑提取。
    默认不触发 --update-golden（更新基准请用 main() 独立入口）。
    """
    ok, extract_msg = ensure_extracted_index(spec)
    assert ok, extract_msg

    _, images_dir, index_path, golden_path = _resolve_golden_paths(spec)

    # 基准缺失即红（A0-2：禁止「全绿但零覆盖」）
    assert golden_path.exists(), (
        f"golden 基准缺失（禁止空跑）: {golden_path}，"
        f"请运行 --update-golden 生成"
    )

    current_data = load_index_json(index_path)
    assert current_data is not None, f"无法加载 index.json: {index_path}"

    golden_data = load_index_json(golden_path)
    assert golden_data is not None, f"无法加载 golden 基准: {golden_path}"

    # 基准与被比对象同目录时比较必然全绿（假绿），必须显式失败。
    assert not golden_is_self_comparison(index_path, golden_path), (
        f"golden 基准与被比产物位于同一目录，比较无意义（假绿）: {index_path}。"
        f"请将基准与产物放在不同批次后重跑。"
    )

    # 文件名的环境标识与文件内记录不符的基准不能用来比较（改名冒充、同步混入）
    problems = baseline_problems(golden_path, golden_data)
    assert not problems, "\n".join(problems)

    result = compare_with_golden(spec, golden_data, current_data, images_dir)
    if not result.passed:
        result.messages.extend(comparison_hints(
            Path(spec.pdf_file).stem, golden_path, golden_data,
            current_data, images_dir, result,
        ))
    assert result.passed, "\n".join(result.messages)


@pytest.mark.golden
def test_golden_baseline_coverage() -> None:
    """meta 断言（A0-2）：禁止「全绿但零覆盖」。

    - tests/basic-benchmark/ 根目录下每份 PDF 都必须纳入 CORE_REGRESSION_SET；
    - 每份 PDF 都必须存在本环境基准，或允许回退的旧环境键/旧版无后缀基准；
    - 收集到的 golden 对比用例数必须与 benchmark PDF 数一致。
    """
    # 优先扁平根目录；兼容旧子目录布局
    pdfs = sorted(TESTS_DIR.glob("*.pdf"))
    if not pdfs:
        pdfs = sorted(TESTS_DIR.glob("*/*.pdf"))
    assert pdfs, f"未扫描到任何 benchmark PDF: {TESTS_DIR}"

    spec_files = {spec.pdf_file for spec in CORE_REGRESSION_SET}
    uncovered = [p.name for p in pdfs if p.name not in spec_files]
    assert not uncovered, (
        f"benchmark PDF 未纳入 CORE_REGRESSION_SET: {uncovered}"
    )

    missing = [
        spec.pdf_file for spec in CORE_REGRESSION_SET
        if not _resolve_golden_paths(spec)[3].exists()
    ]
    assert not missing, (
        f"缺少 golden 基准（禁止空跑）: {missing}，请运行 --update-golden 生成"
    )

    assert len(CORE_REGRESSION_SET) == len(pdfs), (
        f"golden 用例数 {len(CORE_REGRESSION_SET)} 与 benchmark PDF 数 {len(pdfs)} 不一致"
    )


# ============================================================================
# 主函数
# ============================================================================

def main(argv: Optional[List[str]] = None) -> int:
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description="QA-01 Golden Index.json 对比测试"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="显示详细测试输出"
    )
    parser.add_argument(
        "--update-golden",
        action="store_true",
        help="更新 golden 基准文件（使用当前 index.json 作为新基准；只写本渲染环境的基准文件）"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式输出结果"
    )

    args = parser.parse_args(argv)

    print("\n" + "#"*60)
    print("# QA-01 Golden Index.json 对比测试")
    print("# 核心回归集: 8 份 benchmark PDF（tests/basic-benchmark/*.pdf）")
    print("#"*60)

    passed, failed, results = run_golden_tests(
        verbose=args.verbose,
        update_golden=args.update_golden,
    )

    print("\n" + "="*60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("="*60)

    if args.json:
        output = {
            "passed": passed,
            "failed": failed,
            "results": [
                {
                    "pdf": r.pdf_name,
                    "passed": r.passed,
                    "expected_count": r.expected_count,
                    "actual_count": r.actual_count,
                    "messages": r.messages,
                }
                for r in results
            ]
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))

    # 显示失败的测试
    if failed > 0 and not args.verbose:
        print_diff_summary(results)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
