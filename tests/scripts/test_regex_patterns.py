#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QA-01 + QA-06 正则表达式与解析函数单元测试

覆盖场景：
1. Figure/Table 常规数字编号（1, 2, 3...）
2. 罗马数字编号（I, II, III, IV, V, VI, VII, VIII, IX, X）
3. Supplementary 前缀（S1, S2, SIV, Supplementary Figure 3...）
4. Extended Data 前缀（Extended Data Figure 1...）
5. 附录表编号（A1, B2...）
6. 中文编号（图1, 表2, 附图3...）
7. 子图标签（1a, 1-a, 1(a), 1A...）
8. 续页标记（(continued), 续, 接上页）
9. QC 引用统计（正文中的图表引用检测）

使用方式：
  python3 tests/scripts/test_regex_patterns.py
"""

import re
import sys
import os
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass

# 项目根目录：tests/scripts/ -> 向上三级
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "skills", "pdf-markdown-summary", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from lib.idents import (
    extract_figure_ident,
    extract_table_ident,
    parse_figure_ident,
    roman_to_int,
    is_roman_numeral,
    count_text_references,
    categorize_idents,
    FIGURE_LINE_RE,
    TABLE_LINE_RE,
)

# 兼容别名（旧代码用 _前缀，新代码去掉 _）
_extract_figure_ident = extract_figure_ident
_extract_table_ident = extract_table_ident
_parse_figure_ident = parse_figure_ident
_roman_to_int = roman_to_int
_is_roman_numeral = is_roman_numeral
_categorize_idents = categorize_idents
main_count_text_references = count_text_references


# ============================================================================
# QC 引用统计正则（用于检测正文中对图表的引用）
# ============================================================================

# 英文 Figure 引用正则
FIGURE_REF_EN_RE = re.compile(
    r"(?:Extended\s+Data\s+)?(?:Supplementary\s+)?(?:Figures?|Figs?\.?)\s*"
    r"(?:S\s*)?(\d+|[IVX]{1,6})\b",
    re.IGNORECASE,
)

# 中文图引用正则
FIGURE_REF_CN_RE = re.compile(
    r"图\s*(\d+)",
)

# 英文 Table 引用正则
TABLE_REF_EN_RE = re.compile(
    r"(?:Extended\s+Data\s+)?(?:Supplementary\s+)?(?:Tables?|Tab\.?)\s*"
    r"(?:S\s*)?([A-Z]?\d+|[IVX]{1,6})\b",
    re.IGNORECASE,
)

# 中文表引用正则
TABLE_REF_CN_RE = re.compile(
    r"表\s*(\d+)",
)

# S 前缀检测辅助正则
S_PREFIX_RE = re.compile(r"\bS\s*(\d+|[IVX]{1,6})", re.IGNORECASE)


# ============================================================================
# 测试数据类
# ============================================================================

@dataclass
class TestCase:
    """测试用例"""
    input_text: str
    expected_ident: str
    description: str = ""


@dataclass
class TestResult:
    """测试结果"""
    name: str
    passed: bool
    message: str = ""


# ============================================================================
# 测试用例集合
# ============================================================================

# Figure 标识符提取测试用例
FIGURE_IDENT_CASES: List[TestCase] = [
    # 常规数字编号
    TestCase("Figure 1: Overview of the system", "1", "常规编号"),
    TestCase("Figure 2", "2", "仅编号"),
    TestCase("Fig. 3 shows the results", "3", "缩写形式"),
    TestCase("Fig 4: Architecture", "4", "无句点缩写"),

    # 子图标签
    TestCase("Figure 1A: First part", "1", "大写子图标签"),
    TestCase("Figure 2a: Second part", "2", "小写子图标签"),
    TestCase("Fig. 3-a: With hyphen", "3", "连字符子图"),
    TestCase("Figure 4(a): With parenthesis", "4", "括号子图"),

    # 罗马数字编号
    TestCase("Figure I: Introduction", "I", "罗马数字 I"),
    TestCase("Figure II: Methods", "II", "罗马数字 II"),
    TestCase("Figure III: Results", "III", "罗马数字 III"),
    TestCase("Figure IV: Discussion", "IV", "罗马数字 IV"),
    TestCase("Figure V: Conclusion", "V", "罗马数字 V"),
    TestCase("Figure VI", "VI", "罗马数字 VI"),
    TestCase("Figure VII", "VII", "罗马数字 VII"),
    TestCase("Figure VIII", "VIII", "罗马数字 VIII"),
    TestCase("Figure IX", "IX", "罗马数字 IX"),
    TestCase("Figure X", "X", "罗马数字 X"),

    # Supplementary 前缀（数字）
    TestCase("Figure S1: Supplementary data", "S1", "S前缀数字"),
    TestCase("Figure S2", "S2", "S前缀数字2"),
    TestCase("Figure S 3: With space", "S3", "S前缀带空格"),
    TestCase("Supplementary Figure 3: Full label", "S3", "完整 Supplementary 标签"),
    TestCase("Supplementary Fig. 4", "S4", "Supplementary 缩写"),

    # Supplementary 前缀（罗马数字）
    TestCase("Figure SIV: Supplementary Roman", "SIV", "S前缀罗马数字"),
    TestCase("Figure S IV: With space", "SIV", "S前缀罗马带空格"),
    TestCase("Supplementary Figure IV", "SIV", "Supplementary 罗马"),
    TestCase("Supplementary Figure III", "SIII", "Supplementary 罗马 III"),

    # 中文编号
    TestCase("图1: 系统架构", "1", "中文图"),
    TestCase("图 2", "2", "中文图带空格"),
    TestCase("附图3", "3", "附图"),
    TestCase("图表4", "4", "图表"),

    # 续页标记
    TestCase("Figure 5 (continued)", "5", "续页标记英文"),
    TestCase("图6 续", "6", "续页标记中文"),
    TestCase("Figure 7 接上页", "7", "接上页标记"),
]

# Table 标识符提取测试用例
TABLE_IDENT_CASES: List[TestCase] = [
    # 常规数字编号
    TestCase("Table 1: Performance metrics", "1", "常规编号"),
    TestCase("Table 2", "2", "仅编号"),
    TestCase("Tab. 3: Results", "3", "缩写形式"),

    # 罗马数字编号
    TestCase("Table I: Introduction", "I", "罗马数字 I"),
    TestCase("Table II: Methods", "II", "罗马数字 II"),
    TestCase("Table III: Results", "III", "罗马数字 III"),
    TestCase("Table IV: Discussion", "IV", "罗马数字 IV"),
    TestCase("Table V", "V", "罗马数字 V"),

    # Supplementary 前缀
    TestCase("Table S1: Supplementary data", "S1", "S前缀数字"),
    TestCase("Table S2", "S2", "S前缀数字2"),
    TestCase("Supplementary Table 2: Full label", "S2", "完整 Supplementary 标签"),
    TestCase("Table SIV", "SIV", "S前缀罗马数字"),
    TestCase("Supplementary Table IV", "SIV", "Supplementary 罗马"),

    # 附录表编号（字母+数字）
    TestCase("Table A1: Appendix table", "A1", "附录表 A1"),
    TestCase("Table B2: Second appendix", "B2", "附录表 B2"),
    TestCase("Table C3", "C3", "附录表 C3"),

    # 中文编号
    TestCase("表1: 性能指标", "1", "中文表"),
    TestCase("表 2", "2", "中文表带空格"),

    # 续页标记
    TestCase("Table 4 (continued)", "4", "续页标记"),
    TestCase("表5 续", "5", "续页标记中文"),
]

# 罗马数字转换测试用例
ROMAN_NUMERAL_CASES: List[Tuple[str, int]] = [
    ("I", 1),
    ("II", 2),
    ("III", 3),
    ("IV", 4),
    ("V", 5),
    ("VI", 6),
    ("VII", 7),
    ("VIII", 8),
    ("IX", 9),
    ("X", 10),
    ("XI", 11),
    ("XII", 12),
    ("XIV", 14),
    ("XV", 15),
    ("XIX", 19),
    ("XX", 20),
]

# _parse_figure_ident 测试用例：(ident, expected_is_supp, expected_numeric)
PARSE_IDENT_CASES: List[Tuple[str, bool, int]] = [
    ("1", False, 1),
    ("2", False, 2),
    ("10", False, 10),
    ("I", False, 1),
    ("IV", False, 4),
    ("X", False, 10),
    ("S1", True, 1),
    ("S2", True, 2),
    ("SIV", True, 4),
    ("SX", True, 10),
    ("SIII", True, 3),
]


# ============================================================================
# 测试函数
# ============================================================================

def test_figure_idents() -> List[TestResult]:
    """测试 Figure 标识符提取"""
    results = []

    for case in FIGURE_IDENT_CASES:
        m = FIGURE_LINE_RE.match(case.input_text)
        if not m:
            results.append(TestResult(
                name=f"Figure: {case.description}",
                passed=False,
                message=f"正则不匹配: '{case.input_text}'"
            ))
            continue

        try:
            got = extract_figure_ident(m)
            if got == case.expected_ident:
                results.append(TestResult(
                    name=f"Figure: {case.description}",
                    passed=True,
                    message=f"'{case.input_text}' -> '{got}'"
                ))
            else:
                results.append(TestResult(
                    name=f"Figure: {case.description}",
                    passed=False,
                    message=f"期望 '{case.expected_ident}'，得到 '{got}'"
                ))
        except Exception as e:
            results.append(TestResult(
                name=f"Figure: {case.description}",
                passed=False,
                message=f"异常: {e}"
            ))

    return results


def test_table_idents() -> List[TestResult]:
    """测试 Table 标识符提取"""
    results = []

    for case in TABLE_IDENT_CASES:
        m = TABLE_LINE_RE.match(case.input_text)
        if not m:
            results.append(TestResult(
                name=f"Table: {case.description}",
                passed=False,
                message=f"正则不匹配: '{case.input_text}'"
            ))
            continue

        try:
            got = extract_table_ident(m)
            if got == case.expected_ident:
                results.append(TestResult(
                    name=f"Table: {case.description}",
                    passed=True,
                    message=f"'{case.input_text}' -> '{got}'"
                ))
            else:
                results.append(TestResult(
                    name=f"Table: {case.description}",
                    passed=False,
                    message=f"期望 '{case.expected_ident}'，得到 '{got}'"
                ))
        except Exception as e:
            results.append(TestResult(
                name=f"Table: {case.description}",
                passed=False,
                message=f"异常: {e}"
            ))

    return results


def test_roman_numerals() -> List[TestResult]:
    """测试罗马数字转换"""
    results = []

    for roman, expected in ROMAN_NUMERAL_CASES:
        try:
            got = roman_to_int(roman)
            if got == expected:
                results.append(TestResult(
                    name=f"Roman: {roman}",
                    passed=True,
                    message=f"'{roman}' -> {got}"
                ))
            else:
                results.append(TestResult(
                    name=f"Roman: {roman}",
                    passed=False,
                    message=f"期望 {expected}，得到 {got}"
                ))
        except Exception as e:
            results.append(TestResult(
                name=f"Roman: {roman}",
                passed=False,
                message=f"异常: {e}"
            ))

    # 测试 is_roman_numeral
    valid_romans = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
    invalid_romans = ["A", "B", "11", "ABC", ""]

    for r in valid_romans:
        if is_roman_numeral(r):
            results.append(TestResult(
                name=f"IsRoman: {r}",
                passed=True,
                message=f"'{r}' 正确识别为罗马数字"
            ))
        else:
            results.append(TestResult(
                name=f"IsRoman: {r}",
                passed=False,
                message=f"'{r}' 应该是罗马数字"
            ))

    for r in invalid_romans:
        if not is_roman_numeral(r):
            results.append(TestResult(
                name=f"NotRoman: {r or '(empty)'}",
                passed=True,
                message=f"'{r}' 正确识别为非罗马数字"
            ))
        else:
            results.append(TestResult(
                name=f"NotRoman: {r or '(empty)'}",
                passed=False,
                message=f"'{r}' 不应该是罗马数字"
            ))

    return results


def test_parse_figure_ident() -> List[TestResult]:
    """测试 parse_figure_ident 函数"""
    results = []

    for ident, expected_is_supp, expected_numeric in PARSE_IDENT_CASES:
        try:
            is_supp, numeric = parse_figure_ident(ident)
            if is_supp == expected_is_supp and numeric == expected_numeric:
                results.append(TestResult(
                    name=f"ParseIdent: {ident}",
                    passed=True,
                    message=f"'{ident}' -> (supp={is_supp}, num={numeric})"
                ))
            else:
                results.append(TestResult(
                    name=f"ParseIdent: {ident}",
                    passed=False,
                    message=f"期望 (supp={expected_is_supp}, num={expected_numeric})，"
                            f"得到 (supp={is_supp}, num={numeric})"
                ))
        except Exception as e:
            results.append(TestResult(
                name=f"ParseIdent: {ident}",
                passed=False,
                message=f"异常: {e}"
            ))

    return results


def _local_count_text_references(text: str) -> Dict[str, Set[str]]:
    """本地参照实现：统计正文中的图表引用"""
    figures: Set[str] = set()
    tables: Set[str] = set()

    for m in FIGURE_REF_EN_RE.finditer(text):
        ident = m.group(1)
        full_match = m.group(0)

        s_match = S_PREFIX_RE.search(full_match)
        if s_match:
            ident = f"S{s_match.group(1).upper()}"
        elif is_roman_numeral(ident):
            ident = ident.upper()

        figures.add(ident)

    for m in FIGURE_REF_CN_RE.finditer(text):
        figures.add(m.group(1))

    for m in TABLE_REF_EN_RE.finditer(text):
        ident = m.group(1)
        full_match = m.group(0)

        s_match = S_PREFIX_RE.search(full_match)
        if s_match:
            ident = f"S{s_match.group(1).upper()}"
        elif is_roman_numeral(ident):
            ident = ident.upper()
        elif ident and ident[0].isalpha() and len(ident) > 1:
            ident = ident.upper()

        tables.add(ident)

    for m in TABLE_REF_CN_RE.finditer(text):
        tables.add(m.group(1))

    return {"figures": figures, "tables": tables}


def test_qc_reference_counting() -> List[TestResult]:
    """测试 QC 引用统计（QA-06 增强版）"""
    results = []

    test_cases = [
        ("常规数字引用",
         "As shown in Figure 1 and Table 2, the results are significant. "
         "Figure 3 demonstrates the improvement.",
         {"1", "3"}, {"2"}),
        ("罗马数字引用",
         "Figure I shows the overview. Table II lists the parameters. "
         "See Figure IV for details.",
         {"I", "IV"}, {"II"}),
        ("罗马数字 V~X",
         "Figure V presents the results. Figure VI shows trends. "
         "Table VIII contains parameters. Figure IX concludes.",
         {"V", "VI", "IX"}, {"VIII"}),
        ("S前缀数字",
         "Supplementary Figure S1 provides additional data. "
         "Table S2 contains the full results. "
         "See Figure S3 for more.",
         {"S1", "S3"}, {"S2"}),
        ("S前缀罗马数字",
         "Figure SIV shows extended analysis. "
         "Supplementary Table SII lists parameters. "
         "See Figure SIII for details.",
         {"SIV", "SIII"}, {"SII"}),
        ("Extended Data 引用",
         "Extended Data Figure 1 shows additional results. "
         "Extended Data Table 2 contains supplementary parameters. "
         "See Extended Data Figure 3.",
         {"1", "3"}, {"2"}),
        ("中文图表引用",
         "如图1所示，本文提出了新方法。表2列出了详细参数。"
         "图3展示了实验结果。",
         {"1", "3"}, {"2"}),
        ("附录表编号",
         "See Table A1 in the appendix. Table B2 provides supplementary data. "
         "Table C3 contains additional metrics.",
         set(), {"A1", "B2", "C3"}),
        ("混合格式引用",
         "Figure 1 and Fig. 2 show the architecture. "
         "See Fig. S1 for additional figures. "
         "Table 1 lists metrics.",
         {"1", "2", "S1"}, {"1"}),
        ("Fig. 缩写形式",
         "Fig. 1 shows results. Fig 2 illustrates the method. "
         "Figs. 3 compares approaches. Fig. 4 shows details.",
         {"1", "2", "3", "4"}, set()),
        ("复杂混合场景",
         "As shown in Figure 1, Figure II, and Figure S1, the approach works. "
         "Table 1, Table III, and Table A1 summarize results. "
         "Extended Data Figure 2 provides details. "
         "Supplementary Figure SIV extends the analysis.",
         {"1", "II", "S1", "2", "SIV"}, {"1", "III", "A1"}),
    ]

    for desc, text, expected_figures, expected_tables in test_cases:
        refs = count_text_references(text)

        if refs["figures"] >= expected_figures:
            results.append(TestResult(
                name=f"QC Figures ({desc})",
                passed=True,
                message=f"正确检测到: {refs['figures']}"
            ))
        else:
            missing = expected_figures - refs["figures"]
            results.append(TestResult(
                name=f"QC Figures ({desc})",
                passed=False,
                message=f"缺失: {missing}，检测到: {refs['figures']}"
            ))

        detected_tables = refs["tables"]
        if expected_tables.issubset(detected_tables):
            results.append(TestResult(
                name=f"QC Tables ({desc})",
                passed=True,
                message=f"正确检测到: {detected_tables}"
            ))
        else:
            missing = expected_tables - detected_tables
            results.append(TestResult(
                name=f"QC Tables ({desc})",
                passed=False,
                message=f"缺失: {missing}，检测到: {detected_tables}"
            ))

    return results


def test_implementation_consistency() -> List[TestResult]:
    """测试主脚本与本地参照实现的一致性"""
    results = []

    test_texts = [
        "Figure 1 shows results. Table 2 lists parameters.",
        "See Figure I and Table II for details.",
        "Supplementary Figure S1 provides data. Table S2 shows metrics.",
        "Figure SIV extends analysis. Extended Data Figure 3 confirms.",
        "如图1所示，表2列出了参数。",
        "Table A1 in appendix. Table B2 contains data.",
    ]

    all_consistent = True
    inconsistent_cases = []

    for text in test_texts:
        main_result = count_text_references(text)
        local_result = _local_count_text_references(text)

        if main_result != local_result:
            all_consistent = False
            inconsistent_cases.append({
                "text": text[:50] + "..." if len(text) > 50 else text,
                "main": main_result,
                "local": local_result,
            })

    if all_consistent:
        results.append(TestResult(
            name="实现一致性检查",
            passed=True,
            message=f"主脚本与本地参照实现完全一致 ({len(test_texts)} 个测试用例)"
        ))
    else:
        details = "; ".join([
            f"'{c['text']}': main={c['main']} vs local={c['local']}"
            for c in inconsistent_cases[:3]
        ])
        results.append(TestResult(
            name="实现一致性检查",
            passed=False,
            message=f"发现 {len(inconsistent_cases)} 处不一致: {details}"
        ))

    return results


def test_qc_categorization() -> List[TestResult]:
    """测试 QA-06 标识符分类功能"""
    results = []

    test_idents = {"1", "2", "I", "IV", "S1", "SIV", "A1", "B2"}

    expected_numeric = {"1", "2"}
    expected_roman = {"I", "IV"}
    expected_supp = {"S1", "SIV"}
    expected_appendix = {"A1", "B2"}

    categorized = categorize_idents(test_idents)

    checks = {
        "numeric": expected_numeric,
        "roman": expected_roman,
        "supplementary": expected_supp,
        "appendix": expected_appendix,
    }

    for category, expected in checks.items():
        actual = categorized.get(category, set())
        if actual == expected:
            results.append(TestResult(
                name=f"QA-06 分类: {category}",
                passed=True,
                message=f"正确分类: {actual}"
            ))
        else:
            results.append(TestResult(
                name=f"QA-06 分类: {category}",
                passed=False,
                message=f"期望 {expected}, 得到 {actual}"
            ))

    return results


def test_edge_cases() -> List[TestResult]:
    """测试边界情况"""
    results = []

    # 空字符串
    m = FIGURE_LINE_RE.match("")
    if m is None:
        results.append(TestResult(
            name="Edge: 空字符串",
            passed=True,
            message="正确不匹配空字符串"
        ))
    else:
        results.append(TestResult(
            name="Edge: 空字符串",
            passed=False,
            message="不应匹配空字符串"
        ))

    # 仅有标签无编号
    m = FIGURE_LINE_RE.match("Figure: Overview")
    if m is None:
        results.append(TestResult(
            name="Edge: 无编号",
            passed=True,
            message="正确不匹配无编号的 Figure"
        ))
    else:
        results.append(TestResult(
            name="Edge: 无编号",
            passed=False,
            message="不应匹配无编号的 Figure"
        ))

    # 非图表文本
    non_figure_texts = [
        "The figure shows...",
        "This table contains...",
        "According to the figure,",
        "In Table, we can see...",
    ]

    for text in non_figure_texts:
        m = FIGURE_LINE_RE.match(text)
        if m is None:
            results.append(TestResult(
                name=f"Edge: 非图注",
                passed=True,
                message=f"正确不匹配: '{text[:30]}...'"
            ))
        else:
            results.append(TestResult(
                name=f"Edge: 非图注",
                passed=False,
                message=f"不应匹配: '{text[:30]}...'"
            ))

    return results


# ============================================================================
# 主测试运行器
# ============================================================================

def run_all_tests(verbose: bool = False) -> Tuple[int, int, List[TestResult]]:
    """运行所有测试"""
    all_results: List[TestResult] = []

    test_suites = [
        ("Figure 标识符提取", test_figure_idents),
        ("Table 标识符提取", test_table_idents),
        ("罗马数字转换", test_roman_numerals),
        ("标识符解析", test_parse_figure_ident),
        ("QC 引用统计 (QA-06)", test_qc_reference_counting),
        ("实现一致性检查 (Bug-5)", test_implementation_consistency),
        ("QA-06 分类功能", test_qc_categorization),
        ("边界情况", test_edge_cases),
    ]

    for suite_name, test_func in test_suites:
        if verbose:
            print(f"\n{'='*60}")
            print(f"测试套件: {suite_name}")
            print('='*60)

        results = test_func()
        all_results.extend(results)

        if verbose:
            for r in results:
                status = "OK" if r.passed else "FAIL"
                print(f"  {status} {r.name}: {r.message}")

    passed = sum(1 for r in all_results if r.passed)
    failed = sum(1 for r in all_results if not r.passed)

    return passed, failed, all_results


def main(argv: Optional[List[str]] = None) -> int:
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description="QA-01 + QA-06 正则表达式与解析函数单元测试"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="显示详细测试输出"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式输出结果"
    )

    args = parser.parse_args(argv)

    print("\n" + "#"*60)
    print("# QA-01 + QA-06 正则表达式与解析函数单元测试")
    print("#"*60)

    passed, failed, results = run_all_tests(verbose=args.verbose)

    print("\n" + "="*60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("="*60)

    if args.json:
        import json as json_mod
        output = {
            "passed": passed,
            "failed": failed,
            "results": [
                {"name": r.name, "passed": r.passed, "message": r.message}
                for r in results
            ]
        }
        print(json_mod.dumps(output, ensure_ascii=False, indent=2))

    # 显示失败的测试
    if failed > 0 and not args.verbose:
        print("\n失败的测试:")
        for r in results:
            if not r.passed:
                print(f"  FAIL {r.name}: {r.message}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())