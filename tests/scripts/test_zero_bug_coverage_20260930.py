#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
零 BUG 功能覆盖抽查（20260930 测试投入决策）

背景：design/4-analysis 统计显示 266 个零 BUG 功能模块中，103 个在
tests/scripts/ + tests/eval/ 测试语料中零提及。「零 BUG」只代表没出过人命
关天的事故，不代表行为被锁定。本文件抽查其中 5 个纯函数/契约模块，用
特征化测试（characterization test）把当前行为固定下来：

- F03.013 共享矩形运算：create_rect / intersect_rects / union_rects
- F06.004 宽松图表题注前缀检测：is_caption_text
- F06.005 文本列峰值表结构辅助：estimate_column_peaks
- F06.006 横纵规则线密度辅助：line_density
- F06.007 宽正文行比例辅助：paragraph_ratio
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "skills", "pdf-markdown-summary", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import fitz

from lib.pdf_backend import create_rect, intersect_rects, union_rects
from lib.extract_helpers import (
    estimate_column_peaks,
    is_caption_text,
    line_density,
    paragraph_ratio,
)
from lib.models import DrawItem


def L(x0, y0, x1, y1, text, size=9.0):
    return (fitz.Rect(x0, y0, x1, y1), size, text)


# ============================================================================
# F03.013 共享矩形运算
# ============================================================================

class TestRectOps:
    def test_create_rect_coordinates(self):
        r = create_rect(1.0, 2.0, 3.0, 4.0)
        assert (r.x0, r.y0, r.x1, r.y1) == (1.0, 2.0, 3.0, 4.0)

    def test_intersect_overlap(self):
        r = intersect_rects(create_rect(0, 0, 10, 10), create_rect(5, 5, 15, 15))
        assert (r.x0, r.y0, r.x1, r.y1) == (5.0, 5.0, 10.0, 10.0)

    def test_intersect_disjoint_is_empty(self):
        r = intersect_rects(create_rect(0, 0, 10, 10), create_rect(20, 20, 30, 30))
        assert r.is_empty or r.width <= 0 or r.height <= 0

    def test_union_bounds(self):
        r = union_rects(create_rect(0, 0, 10, 10), create_rect(20, 5, 30, 25))
        assert (r.x0, r.y0, r.x1, r.y1) == (0.0, 0.0, 30.0, 25.0)


# ============================================================================
# F06.004 宽松题注前缀检测
# ============================================================================

class TestIsCaptionText:
    def test_figure_prefixes(self):
        assert is_caption_text("Figure 3: Overview", kind="figure")
        assert is_caption_text("fig. 2 shows", kind="figure")
        assert is_caption_text("图1 系统架构", kind="figure")

    def test_table_prefixes(self):
        assert is_caption_text("Table 2 | Results", kind="table")
        assert is_caption_text("表3 统计数据", kind="table")

    def test_body_text_rejected(self):
        assert not is_caption_text("This is an ordinary body sentence.", kind="figure")
        assert not is_caption_text("The results are shown above.", kind="table")

    def test_kind_mismatch_rejected(self):
        assert not is_caption_text("Table 1: x", kind="figure")
        assert not is_caption_text("Figure 1: x", kind="table")


# ============================================================================
# F06.005 文本列峰值
# ============================================================================

class TestEstimateColumnPeaks:
    def test_empty(self):
        assert estimate_column_peaks(create_rect(0, 0, 500, 500), []) == 0

    def test_single_column(self):
        clip = create_rect(50, 0, 500, 500)
        lines = [L(100, y, 300, y + 9, f"row {i}") for i, y in enumerate(range(0, 50, 10))]
        assert estimate_column_peaks(clip, lines) == 1

    def test_two_column_clusters(self):
        clip = create_rect(50, 0, 500, 500)
        lines = [L(100, y, 200, y + 9, f"left {i}") for i, y in enumerate(range(0, 50, 10))]
        lines += [L(300, y, 400, y + 9, f"right {i}") for i, y in enumerate(range(0, 50, 10))]
        assert estimate_column_peaks(clip, lines) >= 2

    def test_lines_outside_clip_ignored(self):
        clip = create_rect(50, 0, 500, 100)
        lines = [L(100, 200, 300, 209, "outside")]
        assert estimate_column_peaks(clip, lines) == 0


# ============================================================================
# F06.006 规则线密度
# ============================================================================

class TestLineDensity:
    def test_empty(self):
        assert line_density(create_rect(0, 0, 100, 100), []) == 0.0

    def test_counts_intersecting_hv_lines(self):
        clip = create_rect(0, 0, 100, 100)
        # 真实横线矩形带 0.5pt 厚度；零高度矩形 fitz 判 is_empty、不相交
        items = [DrawItem(rect=create_rect(10, y, 90, y + 0.5), orient="H") for y in (10, 20, 30, 40)]
        # 4 条线 / 面积 10000 * 1000 = 0.4
        assert line_density(clip, items) == pytest.approx(0.4)

    def test_non_intersecting_ignored(self):
        clip = create_rect(0, 0, 100, 100)
        items = [DrawItem(rect=create_rect(200, 200, 300, 200), orient="H")]
        assert line_density(clip, items) == 0.0

    def test_non_line_orient_ignored(self):
        clip = create_rect(0, 0, 100, 100)
        items = [DrawItem(rect=create_rect(10, 10, 90, 90), orient="O")]
        assert line_density(clip, items) == 0.0


# ============================================================================
# F06.007 宽正文行比例
# ============================================================================

class TestParagraphRatio:
    def test_empty(self):
        assert paragraph_ratio(create_rect(0, 0, 400, 400), []) == 0.0

    def test_half_wide(self):
        clip = create_rect(0, 0, 400, 400)
        lines = [
            L(10, 10, 310, 19, "wide line one here"),   # 300 ≥ 400*0.5
            L(10, 30, 310, 39, "wide line two here"),
            L(10, 50, 100, 59, "narrow one"),
            L(10, 70, 100, 79, "narrow two"),
        ]
        assert paragraph_ratio(clip, lines) == pytest.approx(0.5)

    def test_short_text_not_counted(self):
        clip = create_rect(0, 0, 400, 400)
        lines = [L(10, 10, 310, 19, "ab")]  # len ≤ 5 不计入总数
        assert paragraph_ratio(clip, lines) == 0.0
