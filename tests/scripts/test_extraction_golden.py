#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QA-01 Golden Index.json 对比测试

核心回归集（3份 PDF）：
1. DeepSeek_V3_2.pdf - 4 Figure + 1 Table = 5 items
2. FunAudio-ASR.pdf - 4 Figure + 8 Table = 12 items
3. gpt-5-system-card.pdf - 31 Figure + 26 Table = 57 items

对比策略：
- 忽略不稳定字段：meta.extracted_at, meta.pdf_hash
- 对比稳定字段：
  - items 数量
  - (type, id, page, continued) 集合
  - caption 是否非空
  - file 是否存在

使用方式：
  # 运行 golden 对比测试
  python3 tests/scripts/test_extraction_golden.py

  # 更新 golden 基准（当前提取结果作为新基准）
  python3 tests/scripts/test_extraction_golden.py --update-golden

  # 详细输出
  python3 tests/scripts/test_extraction_golden.py -v
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any

# 项目根目录：tests/scripts/ -> 向上三级
PROJECT_ROOT = Path(__file__).parent.parent.parent
TESTS_DIR = PROJECT_ROOT / "tests" / "basic-benchmark"


# ============================================================================
# 核心回归集配置
# ============================================================================

@dataclass
class GoldenSpec:
    """Golden 规格定义"""
    pdf_dir: str                   # PDF 所在目录名
    pdf_file: str                  # PDF 文件名
    expected_figures: int          # 期望的 Figure 数量
    expected_tables: int           # 期望的 Table 数量
    expected_ids: Dict[str, Set[str]] = field(default_factory=dict)  # 期望的 ID 集合


# 核心回归集定义
CORE_REGRESSION_SET: List[GoldenSpec] = [
    GoldenSpec(
        pdf_dir="DeepSeek_V3_2",
        pdf_file="DeepSeek_V3_2.pdf",
        expected_figures=4,
        expected_tables=1,
        expected_ids={
            "figures": {"1", "2", "3", "4"},
            "tables": {"1"},
        }
    ),
    GoldenSpec(
        pdf_dir="FunAudio-ASR",
        pdf_file="FunAudio-ASR.pdf",
        expected_figures=4,
        expected_tables=8,
        expected_ids={
            "figures": {"1", "2", "3", "4"},
            "tables": {"1", "2", "3", "4", "5", "6", "7", "8"},
        }
    ),
    GoldenSpec(
        pdf_dir="gpt-5-system-card",
        pdf_file="gpt-5-system-card.pdf",
        expected_figures=31,
        expected_tables=26,
        expected_ids={
            "figures": {str(i) for i in range(1, 32)},
            "tables": {str(i) for i in range(1, 27)},
        }
    ),
]


# ============================================================================
# 数据类定义
# ============================================================================

@dataclass
class ItemSignature:
    """图表条目签名（用于对比）"""
    type: str      # "figure" | "table"
    id: str        # 标识符
    page: int      # 页码
    continued: bool  # 是否续页

    def __hash__(self):
        return hash((self.type, self.id, self.page, self.continued))

    def __eq__(self, other):
        if not isinstance(other, ItemSignature):
            return False
        return (self.type == other.type and
                self.id == other.id and
                self.page == other.page and
                self.continued == other.continued)


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


# ============================================================================
# 核心对比函数
# ============================================================================

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


def extract_item_signatures(index_data: Dict[str, Any]) -> Set[ItemSignature]:
    """从 index.json 提取所有条目签名"""
    signatures = set()

    items = index_data.get("items", [])
    for item in items:
        sig = ItemSignature(
            type=item.get("type", "unknown"),
            id=str(item.get("id", "")),
            page=item.get("page", 0),
            continued=item.get("continued", False),
        )
        signatures.add(sig)

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


def compare_with_golden(
    spec: GoldenSpec,
    golden_data: Optional[Dict[str, Any]],
    current_data: Dict[str, Any],
    images_dir: Path,
) -> ComparisonResult:
    """
    对比当前提取结果与 golden 基准

    如果没有 golden 数据，则与 spec 中的期望值对比
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
        result.messages.append(f"额外 Figure IDs: {sorted(extra_figures)}")

    missing_tables = spec.expected_ids.get("tables", set()) - actual_ids["tables"]
    extra_tables = actual_ids["tables"] - spec.expected_ids.get("tables", set())

    if missing_tables:
        result.passed = False
        result.messages.append(f"缺失 Table IDs: {sorted(missing_tables)}")

    if extra_tables:
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
        result.messages.append(f"空 Caption 条目: {empty_captions[:5]}{'...' if len(empty_captions) > 5 else ''}")

    # 5. 与 Golden 对比（如果有）
    if golden_data:
        golden_sigs = extract_item_signatures(golden_data)
        current_sigs = extract_item_signatures(current_data)

        missing = golden_sigs - current_sigs
        extra = current_sigs - golden_sigs

        if missing:
            result.missing_items = list(missing)
            result.messages.append(
                f"相比 Golden 缺失 {len(missing)} 项: "
                f"{[(s.type, s.id, s.page) for s in list(missing)[:3]]}..."
            )

        if extra:
            result.extra_items = list(extra)
            result.messages.append(
                f"相比 Golden 多出 {len(extra)} 项: "
                f"{[(s.type, s.id, s.page) for s in list(extra)[:3]]}..."
            )

    if result.passed:
        result.messages.insert(0, "通过所有检查")

    return result


# ============================================================================
# 测试运行器
# ============================================================================

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
        pdf_dir = TESTS_DIR / spec.pdf_dir
        images_dir = pdf_dir / "images"
        index_path = images_dir / "index.json"
        golden_path = images_dir / "golden_index.json"

        if verbose:
            print(f"\n{'='*60}")
            print(f"测试: {spec.pdf_file}")
            print(f"目录: {pdf_dir}")
            print('='*60)

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
            # 创建精简的 golden 数据（移除不稳定字段）
            golden_to_save = {
                "version": current_data.get("version", "2.0"),
                "meta": {
                    "pdf": current_data.get("meta", {}).get("pdf", spec.pdf_file),
                    "pages": current_data.get("meta", {}).get("pages", 0),
                    "preset": current_data.get("meta", {}).get("preset", "robust"),
                    # 注意：不保存 extracted_at 和 pdf_hash
                },
                "items": current_data.get("items", []),
            }

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
    print("# 核心回归集: DeepSeek_V3_2, FunAudio-ASR, gpt-5-system-card")
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