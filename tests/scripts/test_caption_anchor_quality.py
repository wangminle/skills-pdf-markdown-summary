#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Caption 锚点与截图质量回归测试。

覆盖两类已暴露问题：
1) build_caption_index 必须给候选项打分，否则 get_best_for_page 无法过滤正文引用。
2) 正文污染检测应能识别明显的整段正文区域，用于阻止误截结果落盘。
"""

import os
import re
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "skills", "pdf-markdown-summary", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import fitz

import lib.refine as refine_module
from lib.caption_detection import (
    build_caption_index,
    is_caption_reference,
    is_likely_reference_context,
)
from lib.direction import score_local_direction
from lib.extract_figures import FIGURE_LINE_RE
from lib.layout_model import adjust_clip_with_layout
from lib.models import DocumentLayoutModel, EnhancedTextUnit, TextBlock
from lib.refine import (
    detect_text_pollution,
    limit_clip_by_neighbor_captions,
    looks_like_table_text,
    refine_clip_to_table_band,
    trim_far_side_text_iterative,
)


def _make_caption_test_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)

    page.insert_text(
        (60, 80),
        "Figure 1 is discussed in the next paragraph and should not be treated as a caption.",
        fontsize=10,
    )

    figure_rect = fitz.Rect(180, 300, 420, 430)
    page.draw_rect(figure_rect, color=(0, 0, 0), width=1.0)
    page.draw_line((180, 365), (420, 365), color=(0, 0, 0), width=1.0)
    page.insert_text((210, 360), "diagram body", fontsize=10)
    page.insert_text((180, 455), "Figure 1: Real diagram caption.", fontsize=10)

    doc.save(path)
    doc.close()


def test_caption_index_scores_candidates() -> None:
    with tempfile.TemporaryDirectory() as td:
        pdf_path = Path(td) / "caption_anchor.pdf"
        _make_caption_test_pdf(pdf_path)

        doc = fitz.open(pdf_path)
        try:
            index = build_caption_index(doc, figure_pattern=FIGURE_LINE_RE, table_pattern=False)
            candidates = index.get_candidates("figure", "1")
            assert len(candidates) == 2, f"应检测到 2 个候选，实际 {len(candidates)}"

            scores = [candidate.score for candidate in candidates]
            assert max(scores) >= 25.0, f"候选项未被有效评分: {scores}"

            best = index.get_best_for_page("figure", "1", 0, min_score=25.0)
            assert best is not None, "应能选出页面内最佳 caption"
            assert best.text.startswith("Figure 1: Real"), f"选错 caption: {best.text}"
        finally:
            doc.close()


def test_caption_index_respects_min_score_for_cross_page_lookup() -> None:
    with tempfile.TemporaryDirectory() as td:
        pdf_path = Path(td) / "caption_anchor.pdf"
        _make_caption_test_pdf(pdf_path)

        doc = fitz.open(pdf_path)
        try:
            index = build_caption_index(doc, figure_pattern=FIGURE_LINE_RE, table_pattern=False)
            assert index.get_best_for_page("figure", "1", 3, min_score=999.0) is None
        finally:
            doc.close()


def test_detect_text_pollution_flags_dense_body_text() -> None:
    clip = fitz.Rect(50, 50, 550, 500)
    text_lines = []
    for i in range(8):
        y0 = 70 + i * 35
        text_lines.append((
            fitz.Rect(60, y0, 540, y0 + 12),
            10.0,
            "This is a long body paragraph line that spans most of the extracted clip width.",
        ))

    polluted, reason = detect_text_pollution(clip, text_lines)
    assert polluted, f"应识别正文污染，实际 reason={reason}"


def test_looks_like_table_text_distinguishes_cells_from_body() -> None:
    clip = fitz.Rect(50, 50, 550, 400)
    table_lines = []
    for row in range(8):
        for col in range(5):
            x0 = 80 + col * 85
            y0 = 80 + row * 24
            table_lines.append((fitz.Rect(x0, y0, x0 + 55, y0 + 10), 8.0, f"{row}.{col}"))

    body_lines = []
    for row in range(8):
        y0 = 80 + row * 24
        body_lines.append((
            fitz.Rect(60, y0, 540, y0 + 10),
            10.0,
            "This is a long body paragraph line that spans nearly the entire clip width.",
        ))

    assert looks_like_table_text(clip, table_lines)
    assert not looks_like_table_text(clip, body_lines)


def test_iterative_far_side_trim_removes_long_body_before_table() -> None:
    clip = fitz.Rect(50, 50, 550, 400)
    text_lines = []
    for row in range(8):
        y0 = 60 + row * 18
        text_lines.append((
            fitz.Rect(60, y0, 540, y0 + 10),
            10.0,
            "This is a long body paragraph line above the table.",
        ))
    for row in range(8):
        y0 = 230 + row * 16
        for col in range(4):
            x0 = 90 + col * 100
            text_lines.append((fitz.Rect(x0, y0, x0 + 60, y0 + 9), 8.0, f"{row}.{col}"))

    trimmed, changed = trim_far_side_text_iterative(
        clip,
        text_lines,
        "above",
        typical_line_h=12,
    )
    assert changed
    assert trimmed.y0 > 190, trimmed
    assert trimmed.y0 < 230, trimmed


def test_table_band_removes_body_and_keeps_full_table() -> None:
    clip = fitz.Rect(50, 50, 550, 400)
    caption = fitz.Rect(80, 405, 520, 425)
    text_lines = []
    for row in range(8):
        y0 = 70 + row * 12
        text_lines.append((
            fitz.Rect(60, y0, 540, y0 + 9),
            10.0,
            "This is a long body paragraph line above the table.",
        ))
    for row in range(10):
        y0 = 210 + row * 14
        for col in range(4):
            x0 = 90 + col * 100
            text_lines.append((fitz.Rect(x0, y0, x0 + 60, y0 + 9), 8.0, f"{row}.{col}"))

    refined, changed = refine_clip_to_table_band(
        clip,
        caption,
        text_lines,
        "above",
        typical_line_h=12,
    )
    assert changed
    assert 200 <= refined.y0 <= 210, refined
    assert refined.y1 == clip.y1


def test_table_band_excludes_narrow_two_part_section_heading() -> None:
    clip = fitz.Rect(50, 50, 550, 400)
    caption = fitz.Rect(80, 405, 520, 425)
    text_lines = [
        (fitz.Rect(70, 150, 100, 160), 10.0, "6.2.3"),
        (fitz.Rect(110, 150, 310, 160), 10.0, "Evaluation on Noise Robustness"),
    ]
    for row in range(8):
        y0 = 190 + row * 18
        for col in range(4):
            x0 = 80 + col * 110
            text_lines.append((fitz.Rect(x0, y0, x0 + 70, y0 + 10), 8.0, f"{row}.{col}"))

    refined, changed = refine_clip_to_table_band(
        clip,
        caption,
        text_lines,
        "above",
        typical_line_h=12,
    )
    assert changed
    assert refined.y0 > 180, refined


def test_table_band_excludes_numbered_section_heading_after_table() -> None:
    clip = fitz.Rect(50, 50, 550, 400)
    caption = fitz.Rect(80, 35, 520, 45)
    text_lines = []
    for row in range(4):
        y0 = 70 + row * 18
        for col in range(3):
            x0 = 80 + col * 140
            text_lines.append((fitz.Rect(x0, y0, x0 + 90, y0 + 10), 8.0, f"{row}.{col}"))
    text_lines.extend([
        (fitz.Rect(70, 180, 100, 192), 12.0, "3.7"),
        (fitz.Rect(110, 180, 220, 192), 12.0, "Hallucinations"),
    ])

    refined, changed = refine_clip_to_table_band(
        clip,
        caption,
        text_lines,
        "below",
        typical_line_h=12,
    )
    assert changed
    assert refined.y1 < 170, refined


def test_table_band_recognizes_compact_single_block_rows() -> None:
    clip = fitz.Rect(50, 50, 550, 430)
    caption = fitz.Rect(180, 35, 420, 45)
    text_lines = []
    for row, text in enumerate([
        "Previous model    GPT-5 model",
        "GPT-4o    gpt-5-main",
        "GPT-4o-mini    gpt-5-main-mini",
        "OpenAI o3    gpt-5-thinking",
        "OpenAI o3-mini    gpt-5-thinking-mini",
        "OpenAI o3 Pro    gpt-5-thinking-pro",
    ]):
        y0 = 70 + row * 18
        text_lines.append((fitz.Rect(175, y0, 420, y0 + 10), 8.0, text))
    for row in range(6):
        y0 = 230 + row * 16
        text_lines.append((
            fitz.Rect(60, y0, 540, y0 + 10),
            10.0,
            "This is a long body paragraph line after the compact table.",
        ))

    refined, changed = refine_clip_to_table_band(
        clip,
        caption,
        text_lines,
        "below",
        typical_line_h=12,
    )
    assert changed
    assert 165 <= refined.y1 <= 180, refined


def test_looks_like_table_text_accepts_short_compact_table() -> None:
    clip = fitz.Rect(50, 50, 550, 180)
    text_lines = []
    for row, text in enumerate([
        "Winner    Loser    Win Rate    95% CI",
        "gpt-5-thinking    OpenAI o3    60.0%    [53.2%, 66.9%]",
        "OpenAI o3    gpt-5-thinking    40.0%    [33.1%, 46.8%]",
        "Overall    50.0%    [45.0%, 55.0%]",
    ]):
        y0 = 70 + row * 20
        text_lines.append((fitz.Rect(80, y0, 520, y0 + 10), 8.0, text))

    assert looks_like_table_text(clip, text_lines)


def test_restore_table_clip_width_recovers_over_narrow_structured_table() -> None:
    restore_width = getattr(refine_module, "restore_table_clip_width", None)
    assert restore_width is not None, "缺少结构化表格的 X 范围恢复函数"

    base_clip = fitz.Rect(26, 100, 569, 500)
    narrow_clip = fitz.Rect(430, 180, 546, 300)
    restored = restore_width(narrow_clip, base_clip, table_band_changed=True)

    assert restored.x0 == base_clip.x0
    assert restored.x1 == base_clip.x1
    assert restored.y0 == narrow_clip.y0
    assert restored.y1 == narrow_clip.y1


def test_table_direction_ignores_adjacent_table_reference_line() -> None:
    caption = fitz.Rect(60, 600, 530, 626)
    page_rect = fitz.Rect(0, 0, 595, 842)
    text_lines = []
    for row in range(8):
        y0 = 420 + row * 18
        for col in range(4):
            x0 = 80 + col * 110
            text_lines.append((fitz.Rect(x0, y0, x0 + 70, y0 + 10), 8.0, f"{row}.{col}"))
    text_lines.append((
        fitz.Rect(62, 629, 356, 640),
        9.0,
        "Table 11 Appendix 8.1 for benchmarks and evaluation details.",
    ))
    text_lines.append((fitz.Rect(524, 780, 533, 789), 8.0, "12"))

    direction, confidence = score_local_direction(
        caption,
        page_rect,
        [],
        [],
        clip_height=520,
        is_table=True,
        text_lines=text_lines,
    )
    assert direction == "above", (direction, confidence)


def test_table_direction_keeps_short_numeric_cells_as_evidence() -> None:
    caption = fitz.Rect(60, 300, 530, 326)
    page_rect = fitz.Rect(0, 0, 595, 842)
    text_lines = []
    for row in range(7):
        y0 = 180 + row * 14
        text_lines.extend([
            (fitz.Rect(90, y0, 150, y0 + 10), 8.0, f"set-{row}"),
            (fitz.Rect(300, y0, 322, y0 + 10), 8.0, f"{row}.12"),
            (fitz.Rect(410, y0, 432, y0 + 10), 8.0, f"{row}.34"),
        ])
    text_lines.append((fitz.Rect(90, 360, 250, 370), 10.0, "Evaluation on Next Benchmark"))
    for row in range(10):
        y0 = 400 + row * 14
        text_lines.extend([
            (fitz.Rect(90, y0, 150, y0 + 10), 8.0, f"next-{row}"),
            (fitz.Rect(300, y0, 322, y0 + 10), 8.0, f"{row}.56"),
            (fitz.Rect(410, y0, 432, y0 + 10), 8.0, f"{row}.78"),
        ])

    direction, confidence = score_local_direction(
        caption,
        page_rect,
        [],
        [],
        clip_height=520,
        is_table=True,
        text_lines=text_lines,
    )
    assert direction == "above", (direction, confidence)


def test_table_direction_prefers_nearest_structured_rows_over_chart_labels() -> None:
    caption = fitz.Rect(220, 350, 375, 362)
    page_rect = fitz.Rect(0, 0, 595, 842)
    text_lines = []
    for row in range(20):
        y0 = 160 + row * 4
        text_lines.append((fitz.Rect(100 + row * 7, y0, 120 + row * 7, y0 + 8), 8.0, f"{row}.0%"))
    for row in range(4):
        y0 = 380 + row * 20
        for col in range(6):
            x0 = 70 + col * 80
            text_lines.append((fitz.Rect(x0, y0, x0 + 55, y0 + 10), 8.0, f"{row}.{col}"))

    direction, confidence = score_local_direction(
        caption,
        page_rect,
        [],
        [],
        clip_height=520,
        is_table=True,
        text_lines=text_lines,
    )
    assert direction == "below", (direction, confidence)
    assert confidence >= 0.6


def test_table_appendix_reference_is_not_caption_context() -> None:
    assert is_likely_reference_context(
        "Table 11 Appendix 8.1 for benchmarks and evaluation details."
    )
    assert is_likely_reference_context(
        "Table 4, we compare the performance of Gemini 2.5 Pro to other models."
    )
    assert is_caption_reference(
        "Table 4, we compare the performance of Gemini 2.5 Pro to other models.",
        {"lines": []},
        re.compile(r"^Table\s+\d+"),
    )


def test_limit_clip_by_neighbor_captions_bounds_same_page_items() -> None:
    clip_above = fitz.Rect(50, 50, 550, 500)
    current_caption = fitz.Rect(80, 505, 520, 525)
    previous_caption = fitz.Rect(80, 260, 520, 285)

    limited_above = limit_clip_by_neighbor_captions(
        clip_above,
        current_caption,
        "above",
        [previous_caption],
        gap=6.0,
    )
    assert limited_above.y0 == previous_caption.y1 + 6.0
    assert limited_above.y1 == clip_above.y1

    clip_below = fitz.Rect(50, 120, 550, 700)
    current_caption = fitz.Rect(80, 90, 520, 110)
    next_caption = fitz.Rect(80, 460, 520, 485)
    limited_below = limit_clip_by_neighbor_captions(
        clip_below,
        current_caption,
        "below",
        [next_caption],
        gap=6.0,
    )
    assert limited_below.y0 == clip_below.y0
    assert limited_below.y1 == next_caption.y0 - 6.0


def test_table_direction_uses_text_structure_above_caption() -> None:
    page_rect = fitz.Rect(0, 0, 600, 800)
    caption = fitz.Rect(120, 400, 480, 420)
    text_lines = []
    for idx in range(10):
        y0 = 250 + idx * 12
        text_lines.append((fitz.Rect(150, y0, 450, y0 + 8), 8.0, f"row {idx} 1.0 2.0 3.0"))
    for idx in range(8):
        y0 = 450 + idx * 18
        text_lines.append((
            fitz.Rect(60, y0, 540, y0 + 10),
            10.0,
            "This is a long body paragraph line below the table caption.",
        ))

    direction, confidence = score_local_direction(
        caption,
        page_rect,
        [],
        [],
        clip_height=520,
        margin_x=20,
        caption_gap=6,
        is_table=True,
        text_lines=text_lines,
    )
    assert direction == "above"
    assert confidence >= 0.6


def test_table_direction_uses_text_structure_below_caption() -> None:
    page_rect = fitz.Rect(0, 0, 600, 800)
    caption = fitz.Rect(120, 180, 480, 200)
    text_lines = []
    for idx in range(8):
        y0 = 40 + idx * 15
        text_lines.append((
            fitz.Rect(60, y0, 540, y0 + 10),
            10.0,
            "This is a long body paragraph line above the table caption.",
        ))
    for idx in range(10):
        y0 = 220 + idx * 12
        text_lines.append((fitz.Rect(150, y0, 450, y0 + 8), 8.0, f"row {idx} 1.0 2.0 3.0"))

    direction, confidence = score_local_direction(
        caption,
        page_rect,
        [],
        [],
        clip_height=520,
        margin_x=20,
        caption_gap=6,
        is_table=True,
        text_lines=text_lines,
    )
    assert direction == "below"
    assert confidence >= 0.6


def test_layout_trims_section_title_from_short_figure() -> None:
    title_rect = fitz.Rect(120, 176, 300, 186)
    title_unit = EnhancedTextUnit(
        bbox=title_rect,
        text="4.1 Pre-training of Audio Encoder",
        page=0,
        font_name="Test",
        font_size=10,
        font_weight="bold",
        font_flags=0,
        color=(0, 0, 0),
        text_type="title_h3",
        confidence=1.0,
        column=-1,
        indent=120,
        block_idx=0,
        line_idx=0,
    )
    model = DocumentLayoutModel(
        page_size=(600, 800),
        num_columns=1,
        margin_left=60,
        margin_right=540,
        margin_top=40,
        margin_bottom=760,
        column_gap=0,
        typical_font_size=10,
        typical_line_height=12,
        typical_line_gap=2,
        text_units={0: [title_unit]},
        text_blocks={0: [TextBlock(title_rect, [title_unit], "title_h3", 0, -1)]},
        vacant_regions={0: []},
    )

    adjusted = adjust_clip_with_layout(
        fitz.Rect(20, 160, 580, 252),
        fitz.Rect(120, 258, 480, 268),
        model,
        0,
        "above",
    )
    assert adjusted.y0 > title_rect.y1, adjusted


def main() -> int:
    tests = [
        test_caption_index_scores_candidates,
        test_caption_index_respects_min_score_for_cross_page_lookup,
        test_detect_text_pollution_flags_dense_body_text,
        test_looks_like_table_text_distinguishes_cells_from_body,
        test_iterative_far_side_trim_removes_long_body_before_table,
        test_table_band_removes_body_and_keeps_full_table,
        test_table_band_excludes_narrow_two_part_section_heading,
        test_table_band_excludes_numbered_section_heading_after_table,
        test_table_band_recognizes_compact_single_block_rows,
        test_looks_like_table_text_accepts_short_compact_table,
        test_restore_table_clip_width_recovers_over_narrow_structured_table,
        test_table_direction_ignores_adjacent_table_reference_line,
        test_table_direction_keeps_short_numeric_cells_as_evidence,
        test_table_direction_prefers_nearest_structured_rows_over_chart_labels,
        test_table_appendix_reference_is_not_caption_context,
        test_limit_clip_by_neighbor_captions_bounds_same_page_items,
        test_table_direction_uses_text_structure_above_caption,
        test_table_direction_uses_text_structure_below_caption,
        test_layout_trims_section_title_from_short_figure,
    ]
    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"FAIL {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {test.__name__}: {e}")
            failed += 1

    print(f"\n测试结果: {passed} 通过, {failed} 失败")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
