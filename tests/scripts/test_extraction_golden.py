#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QA-01 Golden Index.json 对比测试

核心回归集（8 份 PDF，与 tests/basic-benchmark/ 下两个回测组一一对应）：
1. 1706.03762v7-attention_is_all_you_need.pdf - 5 Figure + 4 Table
2. 2509.17765v1-Qwen3-Omni Technical Report.pdf - 3 Figure + 18 Table
3. DeepSeek_V3_2.pdf - 4 Figure + 1 Table
4. FunAudio-ASR.pdf - 4 Figure + 8 Table
5. gemini_v2_5_report.pdf - 15 Figure + 12 Table
6. gpt-5-system-card.pdf - 31 Figure + 26 Table
7. KearnsNevmyvakaHFTRiskBooks.pdf - 8 Figure + 1 Table
8. DeepSeek_V4.pdf（回测组2）- 15 Figure + 14 Table

Golden 的定位：变更检测器，不是正确性基准。基准由当前输出生成，
会把已知缺陷（如 DeepSeek_V4 Table 6 导出正文）一并冻结；
后续修好这些缺陷时 golden 必然报红，这是预期行为。
基准更新必须单独提交，并在 task-list.md 逐条说明差异原因。

对比策略：
- 忽略不稳定字段：meta.extracted_at, meta.pdf_hash
- 对比稳定字段：
  - items 数量与 ID 集合（spec 期望 + golden 双重口径）
  - (type, id, page, continued) 身份集合
  - final_bbox（≤0.5pt 容差；index.json 坐标 round 1 位小数，容差与此兼容）
  - 输出 PNG 的字节尺寸 + sha256（严格相等；同环境重复渲染已验证哈希稳定）
  - caption 是否非空
  - file 是否存在
- 基准缺失或 golden 用例被跳过一律判失败（禁止「全绿但零覆盖」）

使用方式：
  # 运行 golden 对比测试
  python3 tests/scripts/test_extraction_golden.py

  # 更新 golden 基准（当前提取结果作为新基准；必须单独提交）
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
  - golden 基准 golden_index.json 保留在 tests/basic-benchmark/ 下作为版本化 fixture。
"""

import hashlib
import json
import os
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


def _write_code_fingerprint(batch_dir: Path) -> None:
    """提取完成后在批次目录写入代码指纹文件"""
    payload = {
        "skills_scripts_sha256": _current_code_fingerprint(),
        "generated_at": datetime.now().isoformat(),
    }
    batch_dir.mkdir(parents=True, exist_ok=True)
    with open(batch_dir / FINGERPRINT_FILENAME, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _read_code_fingerprint(batch_dir: Path) -> Optional[str]:
    """读取批次目录的代码指纹；文件缺失或损坏返回 None"""
    fp_path = batch_dir / FINGERPRINT_FILENAME
    if not fp_path.exists():
        return None
    try:
        with open(fp_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload.get("skills_scripts_sha256")
    except (json.JSONDecodeError, OSError):
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
    - 批次目录必须带 _code_fingerprint.json，且指纹与当前 skills 代码一致；
      指纹缺失或不符的批次直接跳过。

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
    # 从新到旧逐一校验指纹
    for _, index_path in sorted(candidates, reverse=True):
        batch_dir = index_path.parent.parent  # <batch>/<stem>/images/index.json -> <batch>
        fingerprint = _read_code_fingerprint(batch_dir)
        if fingerprint is None or fingerprint != _current_code_fingerprint():
            continue
        return index_path.parent, index_path
    return None


# ============================================================================
# 核心回归集配置
# ============================================================================

@dataclass
class GoldenSpec:
    """Golden 规格定义"""
    benchmark_group: str         # benchmark 子目录（如 回测组1）
    pdf_file: str                # PDF 文件名
    expected_figures: int        # 期望的 Figure 数量
    expected_tables: int       # 期望的 Table 数量
    expected_ids: Dict[str, Set[str]] = field(default_factory=dict)  # 期望的 ID 集合


# 核心回归集定义（8 份，覆盖 回测组1 七份 + 回测组2 DeepSeek_V4）
CORE_REGRESSION_SET: List[GoldenSpec] = [
    GoldenSpec(
        benchmark_group="回测组1",
        pdf_file="1706.03762v7-attention_is_all_you_need.pdf",
        expected_figures=5,
        expected_tables=4,
        expected_ids={
            "figures": {"1", "2", "3", "4", "5"},
            "tables": {"1", "2", "3", "4"},
        }
    ),
    GoldenSpec(
        benchmark_group="回测组1",
        pdf_file="2509.17765v1-Qwen3-Omni Technical Report.pdf",
        expected_figures=3,
        expected_tables=18,
        expected_ids={
            "figures": {"1", "2", "3"},
            "tables": {str(i) for i in range(1, 19)},
        }
    ),
    GoldenSpec(
        benchmark_group="回测组1",
        pdf_file="DeepSeek_V3_2.pdf",
        expected_figures=4,
        expected_tables=1,
        expected_ids={
            "figures": {"1", "2", "3", "4"},
            "tables": {"1"},
        }
    ),
    GoldenSpec(
        benchmark_group="回测组1",
        pdf_file="FunAudio-ASR.pdf",
        expected_figures=4,
        expected_tables=8,
        expected_ids={
            "figures": {"1", "2", "3", "4"},
            "tables": {"1", "2", "3", "4", "5", "6", "7", "8"},
        }
    ),
    GoldenSpec(
        benchmark_group="回测组1",
        pdf_file="gemini_v2_5_report.pdf",
        expected_figures=15,
        expected_tables=12,
        expected_ids={
            # 当前提取结果缺 Figure 9（变更检测器如实冻结现状）
            "figures": {"1", "2", "3", "4", "5", "6", "7", "8",
                        "10", "11", "12", "13", "14", "15", "16"},
            "tables": {str(i) for i in range(1, 13)},
        }
    ),
    GoldenSpec(
        benchmark_group="回测组1",
        pdf_file="gpt-5-system-card.pdf",
        expected_figures=31,
        expected_tables=26,
        expected_ids={
            "figures": {str(i) for i in range(1, 32)},
            "tables": {str(i) for i in range(1, 27)},
        }
    ),
    GoldenSpec(
        benchmark_group="回测组1",
        pdf_file="KearnsNevmyvakaHFTRiskBooks.pdf",
        expected_figures=8,
        expected_tables=1,
        expected_ids={
            "figures": {str(i) for i in range(1, 9)},
            "tables": {"1"},
        }
    ),
    GoldenSpec(
        benchmark_group="回测组2",
        pdf_file="DeepSeek_V4.pdf",
        expected_figures=15,
        expected_tables=14,
        expected_ids={
            "figures": {str(i) for i in range(1, 16)},
            "tables": {str(i) for i in range(1, 15)},
        }
    ),
]


# ============================================================================
# 数据类定义
# ============================================================================

@dataclass
class ItemSignature:
    """图表条目签名（用于对比）。

    身份键为 (type, id, page, continued)，hash/eq 只用这四项；
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

    def identity(self) -> Tuple[str, str, int, bool]:
        """身份键（集合比对与负载配对都用它）"""
        return (self.type, self.id, self.page, self.continued)

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
    signatures: Dict[Tuple[str, str, int, bool], ItemSignature] = {}

    items = index_data.get("items", [])
    for item in items:
        sig = ItemSignature(
            type=item.get("type", "unknown"),
            id=str(item.get("id", "")),
            page=item.get("page", 0),
            continued=item.get("continued", False),
            final_bbox=item.get("final_bbox"),
        )
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
# 测试运行器
# ============================================================================

def _resolve_golden_paths(spec: GoldenSpec) -> Tuple[Path, Path, Path, Path]:
    """Resolve PDF path, images dir, index.json and golden_index.json.

    - PDF 与 golden_index.json 位于 tests/basic-benchmark/ 下（版本化 fixture）。
    - images/index.json 等提取产物优先复用 tests/results/ 已有批次中的产物；
      没有已提取产物时，路径指向本次运行的新批次目录（懒创建）。
    """
    stem = Path(spec.pdf_file).stem
    benchmark_root = TESTS_DIR / spec.benchmark_group
    pdf_path = benchmark_root / spec.pdf_file
    golden_path = benchmark_root / stem / "images" / "golden_index.json"
    existing = _find_existing_index(stem)
    if existing is not None:
        images_dir, index_path = existing
    else:
        images_dir = _get_batch_dir() / stem / "images"
        index_path = images_dir / "index.json"
    return pdf_path, images_dir, index_path, golden_path


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
                    # 注意：不保存 extracted_at 和 pdf_hash
                },
                "items": golden_items,
            }

            golden_path.parent.mkdir(parents=True, exist_ok=True)
            with open(golden_path, 'w', encoding='utf-8') as f:
                json.dump(golden_to_save, f, ensure_ascii=False, indent=2)

            result = ComparisonResult(
                pdf_name=spec.pdf_file,
                passed=True,
                messages=[f"已更新 golden 基准: {golden_path}"]
            )
            results.append(result)
            if verbose:
                print(f"  {result.messages[0]}")
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

        # 执行对比
        result = compare_with_golden(spec, golden_data, current_data, images_dir)
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

    result = compare_with_golden(spec, golden_data, current_data, images_dir)
    assert result.passed, "\n".join(result.messages)


@pytest.mark.golden
def test_golden_baseline_coverage() -> None:
    """meta 断言（A0-2）：禁止「全绿但零覆盖」。

    - tests/basic-benchmark/ 下两个回测组的每份 PDF 都必须纳入 CORE_REGRESSION_SET；
    - 每份 PDF 都必须存在 golden_index.json 基准；
    - 收集到的 golden 对比用例数必须与 benchmark PDF 数一致。
    """
    pdfs = sorted(TESTS_DIR.glob("*/*.pdf"))
    assert pdfs, f"未扫描到任何 benchmark PDF: {TESTS_DIR}"

    spec_files = {spec.pdf_file for spec in CORE_REGRESSION_SET}
    uncovered = [p.name for p in pdfs if p.name not in spec_files]
    assert not uncovered, (
        f"benchmark PDF 未纳入 CORE_REGRESSION_SET（扫描覆盖两个回测组）: {uncovered}"
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
        help="更新 golden 基准文件（使用当前 index.json 作为新基准）"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式输出结果"
    )

    args = parser.parse_args(argv)

    print("\n" + "#"*60)
    print("# QA-01 Golden Index.json 对比测试")
    print("# 核心回归集: 8 份 benchmark PDF（回测组1 七份 + 回测组2 DeepSeek_V4）")
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
