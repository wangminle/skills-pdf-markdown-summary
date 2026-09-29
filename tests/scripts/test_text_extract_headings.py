# -*- coding: utf-8 -*-
"""P2 修复回归测试：中文章节标题被整体降为正文。

问题：looks_like_structural_heading 的编号正则要求编号后出现 A-Z，
非编号标题又要求至少 4 个 ASCII 字母，导致粗体 18pt 的「绪论」
「第一章 绪论」「1 绪论」「研究方法」全部返回 False。

本测试覆盖：
1. 中文编号模式（第X章/第X节、数字编号后直接跟中文、一、（一）等）；
2. 非编号中文粗体标题（CJK 字符计入「字母」计数，2-8 字即可）；
3. 英文行为保持不变（含本轮新加的 font_size >= 11.5 且 >=4 字母门槛）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "skills" / "pdf-markdown-summary" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from lib.text_extract import looks_like_structural_heading


def _check(text: str, *, is_bold: bool, font_size: float) -> bool:
    return looks_like_structural_heading(text, is_bold=is_bold, font_size=font_size)


# ---------------------------------------------------------------------------
# 中文标题：编号模式（任何字号都应识别）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "第一章 绪论",
    "第2章 文献综述",
    "第3节 实验设置",
    "1 绪论",
    "1.1 相关工作",
    "2.3.1 模型细节",
    "一、引言",
    "二、相关工作",
    "（一）研究背景",
    "(二) 研究方法",
])
def test_chinese_numbered_headings_detected_at_any_size(text: str) -> None:
    # 编号标题沿用英文规则：任何字号都保留
    assert _check(text, is_bold=True, font_size=10.0)
    assert _check(text, is_bold=True, font_size=18.0)


# ---------------------------------------------------------------------------
# 中文标题：非编号粗体标题（要求 font_size >= 11.5）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "绪论",
    "研究方法",
    "实验结果与分析",
    "结论与展望",
    "系统总体设计",
])
def test_chinese_unnumbered_bold_headings_detected(text: str) -> None:
    assert _check(text, is_bold=True, font_size=18.0)
    # 大字号边界
    assert _check(text, is_bold=True, font_size=11.5)


@pytest.mark.parametrize("text", [
    "绪论",
    "研究方法",
])
def test_chinese_unnumbered_headings_require_large_font(text: str) -> None:
    # 正文字号的中文粗体短语不应切分 Markdown（保持英文同等门槛）
    assert not _check(text, is_bold=True, font_size=10.5)


def test_chinese_single_char_not_heading() -> None:
    # 单字（图/表等）不算标题
    assert not _check("图", is_bold=True, font_size=18.0)


def test_chinese_year_like_text_not_numbered_heading() -> None:
    # 「2023年」这类年份不应被编号规则误判为标题
    assert not _check("2023年", is_bold=True, font_size=18.0)


# ---------------------------------------------------------------------------
# 英文行为保持不变
# ---------------------------------------------------------------------------

def test_english_unnumbered_heading_still_detected() -> None:
    assert _check("Introduction", is_bold=True, font_size=14.0)
    assert _check("Related Work", is_bold=True, font_size=12.0)


def test_english_unnumbered_heading_requires_four_letters() -> None:
    # 少于 4 个 ASCII 字母的英文短语不算标题
    assert not _check("ABC", is_bold=True, font_size=14.0)


def test_english_unnumbered_heading_requires_large_font() -> None:
    # 正文字号的粗体表头（FEELING ITEMS）不切分 Markdown
    assert not _check("FEELING ITEMS", is_bold=True, font_size=10.0)


def test_english_numbered_heading_any_size() -> None:
    assert _check("1.2 Related Work", is_bold=True, font_size=9.0)
    assert _check("3 Introduction", is_bold=True, font_size=18.0)


def test_page_number_like_text_not_heading() -> None:
    assert not _check("12", is_bold=True, font_size=12.0)
    assert not _check("1.2", is_bold=True, font_size=12.0)


def test_non_bold_never_heading() -> None:
    assert not _check("绪论", is_bold=False, font_size=18.0)
    assert not _check("Introduction", is_bold=False, font_size=14.0)


def test_leading_punctuation_not_heading() -> None:
    assert not _check(") 绪论", is_bold=True, font_size=18.0)
    assert not _check(", Introduction", is_bold=True, font_size=14.0)


# ---------------------------------------------------------------------------
# 罗马数字/字母编号标题（BUG-A，IEEE 会议论文常见格式）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "I. Introduction",
    "II. Related Work",
    "IV. Experiments",
    "V. Conclusion",
    "A. Introduction",
    "B. System Model",
])
def test_roman_alpha_numbered_headings_detected(text: str) -> None:
    # 编号标题沿用阿拉伯数字规则：任何字号都保留；此前这些标题会
    # 走到句点检查（含 ". I"）被当成普通句子误杀
    assert _check(text, is_bold=True, font_size=18.0)
    assert _check(text, is_bold=True, font_size=10.0)


def test_roman_numeral_without_title_not_heading() -> None:
    # 裸编号（无标题文字）不算标题
    assert not _check("IV.", is_bold=True, font_size=18.0)
    assert not _check("A.", is_bold=True, font_size=18.0)


def test_roman_alpha_heading_requires_bold() -> None:
    assert not _check("I. Introduction", is_bold=False, font_size=18.0)


@pytest.mark.parametrize("text", [
    "P. Value",
    "N. Samples",
    "M. Mean",
])
def test_small_bold_table_metric_is_not_alpha_heading(text: str) -> None:
    """统计表头与单字母章节形式相同，正文字号下不应切碎 Markdown。"""
    assert not _check(text, is_bold=True, font_size=9.0)
