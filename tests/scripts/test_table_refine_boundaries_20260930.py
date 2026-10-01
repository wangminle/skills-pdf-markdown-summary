#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
table_refine 高频函数边界测试（20260930 测试投入决策）

背景：design/4-analysis 的 BUG 归属统计中，table_refine.py 以 21 条 BUG
居文件榜首，其中 refine_clip_to_table_band（BUG-010/011/012/016/018）
与 expand_table_clip_to_text_bounds（BUG-026/034/035/039/040）各 5 条，
历史呈「修一个、破一个」模式。本文件为两个函数补对称反例边界测试：

refine_clip_to_table_band：
- 强/弱行分类、行距桥接上限（BUG-018 的对称两面：可桥接 / 超上限断开）
- 编号小节标题不得并入行带（BUG-011/039 回归面）
- 正文句终止行带、稀疏标签桥接（BUG-016）、弱行表最少行数门槛
- 题注侧守卫与退化输入

expand_table_clip_to_text_bounds：
- 基础安全补边与 reference_clip 上限（BUG-026）
- 连接行恢复（BUG-034）与正文尾句/题注行不得回拉（BUG-035/040）
- above/below 方向对称
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "skills", "pdf-markdown-summary", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import fitz

from lib.table_refine import (
    expand_table_clip_to_text_bounds,
    refine_clip_to_table_band,
)


def L(x0, y0, x1, y1, text, size=9.0):
    return (fitz.Rect(x0, y0, x1, y1), size, text)


def strong_row(y, clip_x=(110.0, 470.0)):
    """三单元格强表格行（110-180 / 250-320 / 400-470）。"""
    return [
        L(clip_x[0], y, 180.0, y + 9.0, "Cell A1"),
        L(250.0, y, 320.0, y + 9.0, "12.5"),
        L(400.0, y, clip_x[1], y + 9.0, "OCR"),
    ]


CLIP = lambda y1=700.0: fitz.Rect(100.0, 100.0, 500.0, y1)
CAPTION_ABOVE = fitz.Rect(200.0, 85.0, 400.0, 97.0)


# ============================================================================
# refine_clip_to_table_band
# ============================================================================

class TestRefineClipToTableBand:
    def test_degenerate_inputs(self):
        clip = CLIP()
        assert refine_clip_to_table_band(clip, CAPTION_ABOVE, [], "below") == (clip, False)
        zero = fitz.Rect(100.0, 100.0, 100.0, 700.0)
        out, changed = refine_clip_to_table_band(zero, CAPTION_ABOVE, [], "below")
        assert not changed and out == zero

    def test_below_strong_band_tightens_far_edge(self):
        clip = CLIP()
        lines = []
        for y in (110.0, 122.0, 134.0, 146.0):
            lines.extend(strong_row(y))
        out, changed = refine_clip_to_table_band(
            clip, CAPTION_ABOVE, lines, "below", typical_line_h=10.0)
        assert changed
        assert out.y1 == pytest.approx(146.0 + 9.0 + 6.0)  # 末行底 + pad
        assert (out.x0, out.y0, out.x1) == (clip.x0, clip.y0, clip.x1)

    def test_above_symmetric(self):
        clip = fitz.Rect(100.0, 100.0, 500.0, 700.0)
        caption_below = fitz.Rect(200.0, 705.0, 400.0, 717.0)
        lines = []
        for y in (595.0, 610.0, 625.0, 640.0):
            lines.extend(strong_row(y))
        out, changed = refine_clip_to_table_band(
            clip, caption_below, lines, "above", typical_line_h=10.0)
        assert changed
        assert out.y0 == pytest.approx(595.0 - 6.0)
        assert out.y1 == clip.y1

    def test_numbered_section_row_not_absorbed(self):
        """BUG-011/039 回归面：'7.1 Conclusion' 编号小节不得并入行带。"""
        clip = CLIP()
        lines = []
        for y in (110.0, 122.0, 134.0):
            lines.extend(strong_row(y))
        lines.append(L(110.0, 146.0, 200.0, 155.0, "7.1 Conclusion"))
        out, changed = refine_clip_to_table_band(
            clip, CAPTION_ABOVE, lines, "below", typical_line_h=10.0)
        assert changed
        assert out.y1 == pytest.approx(134.0 + 9.0 + 6.0)

    def test_sentence_body_terminates_band(self):
        clip = CLIP()
        lines = []
        for y in (110.0, 122.0, 134.0):
            lines.extend(strong_row(y))
        lines.append(L(110.0, 146.0, 480.0, 155.0,
                       "This is a long body sentence that clearly does not belong "
                       " to the table and must terminate the band right here."))
        out, changed = refine_clip_to_table_band(
            clip, CAPTION_ABOVE, lines, "below", typical_line_h=10.0)
        assert changed
        assert out.y1 == pytest.approx(134.0 + 9.0 + 6.0)

    def test_moderate_gap_between_strong_groups_bridged(self):
        """BUG-018 对称面 A：强-强分组间距 ≤ max_bridge_gap(80) 应桥接。"""
        clip = CLIP()
        lines = []
        for y in (110.0, 122.0):
            lines.extend(strong_row(y))
        for y in (171.0, 183.0):  # 与上行底 131 相距 40pt
            lines.extend(strong_row(y))
        out, changed = refine_clip_to_table_band(
            clip, CAPTION_ABOVE, lines, "below", typical_line_h=10.0)
        assert changed
        assert out.y1 == pytest.approx(183.0 + 9.0 + 6.0)

    def test_excessive_gap_breaks_band(self):
        """BUG-018 对称面 B：间距 > max_bridge_gap(80) 必须断开。"""
        clip = CLIP()
        lines = []
        for y in (110.0, 122.0):
            lines.extend(strong_row(y))
        for y in (231.0, 243.0):  # 与上行底 131 相距 100pt
            lines.extend(strong_row(y))
        out, changed = refine_clip_to_table_band(
            clip, CAPTION_ABOVE, lines, "below", typical_line_h=10.0)
        assert changed
        assert out.y1 == pytest.approx(122.0 + 9.0 + 6.0)

    def test_sparse_label_bridged_with_future_evidence(self):
        """BUG-016 回归面：窄短分组标签（不判 weak）由后续强行证据桥接。"""
        clip = CLIP()
        lines = []
        for y in (110.0, 122.0):
            lines.extend(strong_row(y))
        # 宽 40pt < clip 12% → classify 为 none，只能走 sparse label 通道
        lines.append(L(150.0, 134.0, 190.0, 143.0, "Top"))
        for y in (146.0, 158.0):
            lines.extend(strong_row(y))
        out, changed = refine_clip_to_table_band(
            clip, CAPTION_ABOVE, lines, "below", typical_line_h=10.0)
        assert changed
        assert out.y1 == pytest.approx(158.0 + 9.0 + 6.0)

    def test_weak_only_table_needs_three_rows(self):
        """弱行表（无强行）：2 行不够，3 行成形。"""
        def weak_row(y):
            return L(150.0, y, 260.0, y + 9.0, "OCR 98.5")
        clip = CLIP()
        two = [weak_row(110.0), weak_row(122.0)]
        out, changed = refine_clip_to_table_band(
            clip, CAPTION_ABOVE, two, "below", typical_line_h=10.0)
        assert not changed and out == clip
        three = two + [weak_row(134.0)]
        out, changed = refine_clip_to_table_band(
            clip, CAPTION_ABOVE, three, "below", typical_line_h=10.0)
        assert changed
        assert out.y1 == pytest.approx(134.0 + 9.0 + 6.0)

    def test_single_strong_row_no_change(self):
        clip = CLIP()
        out, changed = refine_clip_to_table_band(
            clip, CAPTION_ABOVE, strong_row(110.0), "below", typical_line_h=10.0)
        assert not changed and out == clip

    def test_caption_side_guard(self):
        """行带底边不得越过题注：new_y1 <= caption.y1 时放弃收紧。"""
        clip = CLIP()
        caption_low = fitz.Rect(200.0, 200.0, 400.0, 212.0)
        lines = []
        for y in (110.0, 122.0):
            lines.extend(strong_row(y))
        out, changed = refine_clip_to_table_band(
            clip, caption_low, lines, "below", typical_line_h=10.0)
        assert not changed and out == clip


# ============================================================================
# expand_table_clip_to_text_bounds
# ============================================================================

REF_CLIP = fitz.Rect(50.0, 50.0, 550.0, 750.0)


def in_clip_table_lines():
    """clip(100,100,500,150) 内的三行两列短单元格：使 looks_like_table_text 为真。"""
    lines = []
    for y in (110.0, 122.0, 134.0):
        lines.append(L(110.0, y, 180.0, y + 9.0, "A1"))
        lines.append(L(250.0, y, 320.0, y + 9.0, "B2"))
    return lines


class TestExpandTableClipToTextBounds:
    def _call(self, clip, lines, direction="below", caption=None, ref=None):
        return expand_table_clip_to_text_bounds(
            clip, ref or REF_CLIP, caption or CAPTION_ABOVE, lines, direction)

    def test_degenerate_inputs(self):
        clip = fitz.Rect(100.0, 100.0, 500.0, 150.0)
        assert self._call(clip, []) == clip
        zero = fitz.Rect(100.0, 100.0, 100.0, 150.0)
        assert self._call(zero, in_clip_table_lines()) == zero

    def test_connected_row_below_recovered(self):
        """BUG-034 回归面：紧贴底边的表格行被恢复，y1 = 行底 + pad(2.5)。"""
        clip = fitz.Rect(100.0, 100.0, 500.0, 150.0)
        lines = in_clip_table_lines()
        lines.append(L(110.0, 152.0, 260.0, 161.0, "Data 123 456"))
        out = self._call(clip, lines)
        assert out.y1 == pytest.approx(161.0 + 2.5)

    def test_far_nontable_line_stays_out(self):
        """超出 connected_row_gap 的远处孤立短行不得回拉，框保持不动。"""
        clip = fitz.Rect(100.0, 100.0, 500.0, 150.0)
        lines = in_clip_table_lines()
        lines.append(L(110.0, 230.0, 170.0, 239.0, "Appendix"))
        out = self._call(clip, lines)
        assert out == clip

    def test_body_sentence_below_not_pulled(self):
        """BUG-035/040 回归面：远端整句正文不得回拉进框。"""
        clip = fitz.Rect(100.0, 100.0, 500.0, 150.0)
        lines = in_clip_table_lines()
        lines.append(L(110.0, 152.0, 470.0, 162.0,
                       "This trailing body sentence belongs to the paragraph after "
                       "the table and must never be pulled back into the clip."))
        out = self._call(clip, lines)
        assert out.y1 == pytest.approx(150.0)

    def test_caption_like_line_never_pulled(self):
        clip = fitz.Rect(100.0, 100.0, 500.0, 150.0)
        lines = in_clip_table_lines()
        lines.append(L(110.0, 152.0, 300.0, 162.0, "Table 5 | Another table caption"))
        out = self._call(clip, lines)
        assert out.y1 == pytest.approx(150.0)

    def test_reference_clip_bounds_expansion(self):
        """BUG-026 回归面：补边不得越过 reference_clip。"""
        clip = fitz.Rect(100.0, 100.0, 500.0, 150.0)
        lines = in_clip_table_lines()
        lines.append(L(110.0, 152.0, 260.0, 161.0, "Data 123 456"))
        out = self._call(clip, lines, ref=fitz.Rect(50.0, 50.0, 550.0, 155.0))
        assert out.y1 == pytest.approx(155.0)

    def test_above_direction_recovers_header_row(self):
        """above 对称面：紧贴顶边的表头行被恢复。"""
        clip = fitz.Rect(100.0, 100.0, 500.0, 150.0)
        caption_below = fitz.Rect(200.0, 205.0, 400.0, 217.0)
        lines = in_clip_table_lines()
        lines.extend([
            L(110.0, 88.0, 180.0, 97.0, "Name"),
            L(250.0, 88.0, 320.0, 97.0, "Value"),
        ])
        out = self._call(clip, lines, direction="above", caption=caption_below)
        assert out.y0 == pytest.approx(88.0 - 2.5)

    def test_above_direction_body_not_pulled(self):
        """above 对称面：上方整句正文不得回拉。"""
        clip = fitz.Rect(100.0, 100.0, 500.0, 150.0)
        caption_below = fitz.Rect(200.0, 205.0, 400.0, 217.0)
        lines = in_clip_table_lines()
        lines.append(L(110.0, 88.0, 470.0, 98.0,
                       "This leading body sentence belongs to the paragraph before "
                       "the table and must never be pulled back into the clip."))
        out = self._call(clip, lines, direction="above", caption=caption_below)
        assert out.y0 == pytest.approx(100.0)


# ============================================================================
# 双向对称（20260930 复核补充）：below 反例经 y 轴镜像映射到 above
# ============================================================================
#
# 复核指出上面多项反例只覆盖 below。这里不手抄第二份期望值：用同一份
# below 坐标场景，按页面 y 轴镜像（Y - y）映射成 above 输入，调用后再镜像
# 回 below 坐标断言——两个方向必须得到同一结果，任何单侧漏改都会变红。

_MIRROR_Y = 800.0


def _mirror_rect(r):
    return fitz.Rect(r.x0, _MIRROR_Y - r.y1, r.x1, _MIRROR_Y - r.y0)


def _mirror_lines(lines):
    return [(_mirror_rect(r), size, text) for r, size, text in lines]


def _band_both(direction, clip, caption, lines):
    """below 坐标场景；above 时镜像输入并把结果镜像回来。"""
    if direction == "below":
        return refine_clip_to_table_band(clip, caption, lines, "below", typical_line_h=10.0)
    out, changed = refine_clip_to_table_band(
        _mirror_rect(clip), _mirror_rect(caption), _mirror_lines(lines),
        "above", typical_line_h=10.0)
    return _mirror_rect(out), changed


def _expand_both(direction, clip, lines, *, caption=None, ref=None):
    cap = caption or CAPTION_ABOVE
    ref = ref or REF_CLIP
    if direction == "below":
        return expand_table_clip_to_text_bounds(clip, ref, cap, lines, "below")
    out = expand_table_clip_to_text_bounds(
        _mirror_rect(clip), _mirror_rect(ref), _mirror_rect(cap),
        _mirror_lines(lines), "above")
    return _mirror_rect(out)


def _rows(*ys):
    lines = []
    for y in ys:
        lines.extend(strong_row(y))
    return lines


@pytest.mark.parametrize("direction", ["below", "above"])
class TestTableBandBothDirections:
    def test_numbered_section_row_not_absorbed(self, direction):
        lines = _rows(110.0, 122.0, 134.0)
        lines.append(L(110.0, 146.0, 200.0, 155.0, "7.1 Conclusion"))
        out, changed = _band_both(direction, CLIP(), CAPTION_ABOVE, lines)
        assert changed
        assert out.y1 == pytest.approx(134.0 + 9.0 + 6.0)

    def test_sentence_body_terminates_band(self, direction):
        lines = _rows(110.0, 122.0, 134.0)
        lines.append(L(110.0, 146.0, 480.0, 155.0,
                       "This is a long body sentence that clearly does not belong "
                       " to the table and must terminate the band right here."))
        out, changed = _band_both(direction, CLIP(), CAPTION_ABOVE, lines)
        assert changed
        assert out.y1 == pytest.approx(134.0 + 9.0 + 6.0)

    def test_moderate_gap_bridged(self, direction):
        lines = _rows(110.0, 122.0, 171.0, 183.0)
        out, changed = _band_both(direction, CLIP(), CAPTION_ABOVE, lines)
        assert changed
        assert out.y1 == pytest.approx(183.0 + 9.0 + 6.0)

    def test_excessive_gap_breaks_band(self, direction):
        lines = _rows(110.0, 122.0, 231.0, 243.0)
        out, changed = _band_both(direction, CLIP(), CAPTION_ABOVE, lines)
        assert changed
        assert out.y1 == pytest.approx(122.0 + 9.0 + 6.0)

    def test_sparse_label_bridged_with_future_evidence(self, direction):
        lines = _rows(110.0, 122.0)
        lines.append(L(150.0, 134.0, 190.0, 143.0, "Top"))
        lines.extend(_rows(146.0, 158.0))
        out, changed = _band_both(direction, CLIP(), CAPTION_ABOVE, lines)
        assert changed
        assert out.y1 == pytest.approx(158.0 + 9.0 + 6.0)

    def test_weak_only_table_needs_three_rows(self, direction):
        def weak_row(y):
            return L(150.0, y, 260.0, y + 9.0, "OCR 98.5")
        clip = CLIP()
        two = [weak_row(110.0), weak_row(122.0)]
        out, changed = _band_both(direction, clip, CAPTION_ABOVE, two)
        assert not changed and out == clip
        out, changed = _band_both(direction, clip, CAPTION_ABOVE, two + [weak_row(134.0)])
        assert changed
        assert out.y1 == pytest.approx(134.0 + 9.0 + 6.0)

    def test_single_strong_row_no_change(self, direction):
        clip = CLIP()
        out, changed = _band_both(direction, clip, CAPTION_ABOVE, strong_row(110.0))
        assert not changed and out == clip

    def test_caption_side_guard(self, direction):
        clip = CLIP()
        caption_low = fitz.Rect(200.0, 200.0, 400.0, 212.0)
        out, changed = _band_both(direction, clip, caption_low, _rows(110.0, 122.0))
        assert not changed and out == clip


@pytest.mark.parametrize("direction", ["below", "above"])
class TestExpandBoundsBothDirections:
    def test_connected_row_recovered(self, direction):
        clip = fitz.Rect(100.0, 100.0, 500.0, 150.0)
        lines = in_clip_table_lines()
        lines.append(L(110.0, 152.0, 260.0, 161.0, "Data 123 456"))
        out = _expand_both(direction, clip, lines)
        assert out.y1 == pytest.approx(161.0 + 2.5)

    def test_far_nontable_line_stays_out(self, direction):
        clip = fitz.Rect(100.0, 100.0, 500.0, 150.0)
        lines = in_clip_table_lines()
        lines.append(L(110.0, 230.0, 170.0, 239.0, "Appendix"))
        assert _expand_both(direction, clip, lines) == clip

    def test_body_sentence_not_pulled(self, direction):
        clip = fitz.Rect(100.0, 100.0, 500.0, 150.0)
        lines = in_clip_table_lines()
        lines.append(L(110.0, 152.0, 470.0, 162.0,
                       "This trailing body sentence belongs to the paragraph after "
                       "the table and must never be pulled back into the clip."))
        assert _expand_both(direction, clip, lines).y1 == pytest.approx(150.0)

    def test_caption_like_line_never_pulled(self, direction):
        clip = fitz.Rect(100.0, 100.0, 500.0, 150.0)
        lines = in_clip_table_lines()
        lines.append(L(110.0, 152.0, 300.0, 162.0, "Table 5 | Another table caption"))
        assert _expand_both(direction, clip, lines).y1 == pytest.approx(150.0)

    def test_reference_clip_bounds_expansion(self, direction):
        clip = fitz.Rect(100.0, 100.0, 500.0, 150.0)
        lines = in_clip_table_lines()
        lines.append(L(110.0, 152.0, 260.0, 161.0, "Data 123 456"))
        out = _expand_both(direction, clip, lines, ref=fitz.Rect(50.0, 50.0, 550.0, 155.0))
        assert out.y1 == pytest.approx(155.0)
