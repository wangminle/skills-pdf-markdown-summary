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
import pytest

import lib.refine as refine_module
from lib.caption_detection import (
    build_caption_index,
    is_caption_reference,
    is_likely_reference_context,
)
from lib.direction import correct_bare_figure_caption_direction, score_local_direction
from lib.extract_figures import FIGURE_LINE_RE
from lib.layout_model import adjust_clip_with_layout, detect_columns
from lib.models import DocumentLayoutModel, EnhancedTextUnit, TextBlock
from lib.refine import (
    detect_text_pollution,
    expand_clip_to_nearby_figure_title,
    expand_clip_to_nearby_figure_objects,
    expand_clip_to_nearby_table_header,
    expand_table_clip_to_text_bounds,
    limit_clip_by_neighbor_captions,
    limit_clip_by_text_blocks,
    looks_like_table_text,
    pad_figure_clip_near_caption,
    refine_clip_by_objects,
    refine_clip_to_table_band,
    restore_table_tail_after_layout_trim,
    trim_far_side_noise_before_content,
    trim_clip_head_by_text_v2,
    trim_far_side_text_iterative,
    trim_table_far_side_section_heading,
)


def _make_text_block(
    rect: "fitz.Rect",
    text: str,
    block_type: str = "paragraph_group",
    column: int = 0,
) -> TextBlock:
    text_type = block_type if block_type.startswith("title_") else "paragraph"
    unit = EnhancedTextUnit(
        bbox=rect,
        text=text,
        page=0,
        font_name="Test",
        font_size=10.0,
        font_weight="regular",
        font_flags=0,
        color=(0, 0, 0),
        text_type=text_type,
        confidence=1.0,
        column=column,
        indent=rect.x0,
        block_idx=0,
        line_idx=0,
    )
    return TextBlock(rect, [unit], block_type, 0, column)



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
    assert refined.y1 == pytest.approx(clip.y1, abs=0.01)


def test_baseline_clip_stops_before_far_section_title_below_caption() -> None:
    clip = fitz.Rect(26, 98, 586, 618)
    caption = fitz.Rect(108, 71, 504, 92)
    text_blocks = [
        # 真实表格内容，位于 caption 附近，不能作为远端边界。
        fitz.Rect(136, 98, 475, 240),
        # 下一个章节标题，应该把 below 方向 baseline 底部夹到它之前。
        fitz.Rect(108, 371, 163, 383),
        fitz.Rect(108, 418, 505, 592),
    ]

    limited = limit_clip_by_text_blocks(
        clip,
        caption,
        "below",
        text_blocks,
        gap=6,
        min_near_distance=120,
    )

    assert limited.y0 == clip.y0
    assert 360 <= limited.y1 <= 365, limited


def test_baseline_clip_stops_after_far_body_above_caption() -> None:
    clip = fitz.Rect(26, 0, 586, 494)
    caption = fitz.Rect(134, 500, 478, 511)
    text_blocks = [
        fitz.Rect(86, 197, 526, 289),
        fitz.Rect(86, 302, 526, 398),
        # 真实表格标题和内容，位于 caption 附近。
        fitz.Rect(198, 409, 468, 420),
        fitz.Rect(144, 423, 423, 488),
    ]

    limited = limit_clip_by_text_blocks(
        clip,
        caption,
        "above",
        text_blocks,
        gap=6,
        min_near_distance=100,
    )

    assert limited.y1 == clip.y1
    assert 403 <= limited.y0 <= 416, limited


def test_baseline_clip_preserves_near_table_cluster_before_far_body() -> None:
    clip = fitz.Rect(26, 98, 569, 508)
    caption = fitz.Rect(70, 71, 525, 92)
    blocks = [
        _make_text_block(fitz.Rect(160, 104, 435, 114), "Module Architecture", "title_h3", 1),
        _make_text_block(fitz.Rect(160, 120, 413, 141), "Audio Encoder AuT", "paragraph_group", 1),
        _make_text_block(fitz.Rect(160, 142, 375, 152), "Thinker MoE Transformer", "paragraph_group", 1),
        _make_text_block(
            fitz.Rect(70, 225, 525, 301),
            "asynchronous prefilling: when Thinker completes prefilling the current chunk, the next body paragraph starts.",
            "paragraph_group",
            0,
        ),
    ]

    limited = limit_clip_by_text_blocks(
        clip,
        caption,
        "below",
        blocks,
        gap=6,
        min_near_distance=80,
    )

    assert 215 <= limited.y1 <= 220, limited


def test_baseline_clip_preserves_table_header_above_caption() -> None:
    clip = fitz.Rect(26, 0, 586, 494)
    caption = fitz.Rect(134, 500, 478, 511)
    blocks = [
        _make_text_block(
            fitz.Rect(86, 302, 526, 398),
            "(v, t) augmented with various subsets of the order book features described above.",
            "paragraph_group",
            0,
        ),
        _make_text_block(
            fitz.Rect(198, 409, 468, 420),
            "Feature(s) Added Reduction in Trading Cost",
            "title_h3",
            1,
        ),
        _make_text_block(
            fitz.Rect(144, 423, 423, 488),
            "Bid-Ask Spread 7.97% Bid-Ask Volume 8.54%",
            "paragraph_group",
            1,
        ),
    ]

    limited = limit_clip_by_text_blocks(
        clip,
        caption,
        "above",
        blocks,
        gap=6,
        min_near_distance=80,
    )

    assert 400 <= limited.y0 <= 409, limited
    assert limited.y1 == clip.y1


def test_baseline_clip_preserves_wide_numeric_table_blocks() -> None:
    clip = fitz.Rect(26, 0, 586, 326)
    caption = fitz.Rect(70, 332, 526, 412)
    blocks = [
        _make_text_block(
            fitz.Rect(120, 90, 519, 101),
            "Benchmark Metric DeepSeek-V3.1-Terminus DeepSeek-V3.2-Exp",
            "title_h3",
            1,
        ),
        _make_text_block(
            fitz.Rect(120, 109, 479, 166),
            "MMLU-Pro 85.0 85.0 GPQA-Diamond 80.7 79.9 Humanity 21.7 19.8",
            "paragraph_group",
            1,
        ),
        _make_text_block(
            fitz.Rect(120, 182, 479, 258),
            "SimpleQA 96.8 97.1 Codeforces 2046 2121 Aider 76.1 74.5",
            "paragraph_group",
            1,
        ),
    ]

    limited = limit_clip_by_text_blocks(
        clip,
        caption,
        "above",
        blocks,
        gap=6,
        min_near_distance=80,
    )

    assert limited == clip


def test_baseline_clip_preserves_clustered_diagram_labels() -> None:
    clip = fitz.Rect(26, 0, 569, 314)
    caption = fitz.Rect(70, 320, 526, 345)
    blocks = [
        _make_text_block(fitz.Rect(296, 170, 361, 186), "Top-k Selector", "title_h3", 1),
        _make_text_block(fitz.Rect(421, 194, 463, 209), "Lightning", "title_h3", 1),
        _make_text_block(fitz.Rect(425, 207, 459, 222), "Indexer", "title_h3", 1),
    ]

    limited = limit_clip_by_text_blocks(
        clip,
        caption,
        "above",
        blocks,
        gap=6,
        min_near_distance=80,
    )

    assert limited == clip


def test_baseline_clip_preserves_spread_diagram_labels_above_caption() -> None:
    clip = fitz.Rect(26, 0, 569, 303)
    caption = fitz.Rect(71, 309, 526, 352)
    blocks = [
        _make_text_block(fitz.Rect(102, 106, 120, 111), "Query", "title_h3", 1),
        _make_text_block(fitz.Rect(398, 110, 416, 114), "Query", "title_h3", 1),
        _make_text_block(fitz.Rect(131, 135, 446, 149), "Response Response", "title_h3", 1),
        _make_text_block(fitz.Rect(111, 212, 409, 218), "Query Query", "title_h3", 1),
        _make_text_block(fitz.Rect(420, 246, 439, 250), "Response", "title_h3", 1),
    ]

    limited = limit_clip_by_text_blocks(
        clip,
        caption,
        "above",
        blocks,
        gap=6,
        min_near_distance=80,
    )

    assert limited == clip


def test_autocrop_trims_far_side_header_rule_before_figure_content() -> None:
    clip = fitz.Rect(26, 0, 569, 303)
    autocrop = fitz.Rect(64, 39, 532, 303)
    image_rects = []
    vector_rects = [
        fitz.Rect(82, 71, 513, 298),
        fitz.Rect(70, 38, 526, 39),
    ]
    text_lines = [
        (fitz.Rect(102, 106, 120, 111), 5.0, "Query"),
        (fitz.Rect(131, 135, 446, 149), 5.0, "Response Response"),
    ]

    trimmed = trim_far_side_noise_before_content(
        clip,
        autocrop,
        "above",
        image_rects,
        vector_rects,
        text_lines,
        pad=8,
    )

    assert 62 <= trimmed.y0 <= 64, trimmed
    assert trimmed.y1 == autocrop.y1


def test_baseline_expands_to_nearby_chart_title_above_figure() -> None:
    original = fitz.Rect(26, 0, 569, 423)
    limited = fitz.Rect(26, 158.5, 569, 423)
    text_lines = [
        (
            fitz.Rect(68, 56, 527, 64),
            8.0,
            "Gemini 2.5: Pushing the Frontier with Advanced Reasoning.",
        ),
        (fitz.Rect(62, 116, 215, 128), 12.0, "4.1. Gemini Plays Pokemon"),
        (
            fitz.Rect(270, 145, 411, 152.5),
            6.0,
            "Gemini 2.5 Pro Plays Pokemon Progress Timeline",
        ),
        (fitz.Rect(200, 159, 221, 164), 3.8, "Hall of Fame"),
    ]

    expanded = expand_clip_to_nearby_figure_title(
        original,
        limited,
        text_lines,
        "above",
        pad=4,
        max_gap=12,
    )

    assert 140 <= expanded.y0 <= 142, expanded
    assert expanded.y1 == limited.y1


def test_baseline_title_recovery_ignores_page_header_and_section_title() -> None:
    original = fitz.Rect(26, 0, 569, 236)
    limited = fitz.Rect(26, 134, 569, 236)
    text_lines = [
        (
            fitz.Rect(68, 56, 527, 64),
            8.0,
            "Gemini 2.5: Pushing the Frontier with Advanced Reasoning.",
        ),
        (fitz.Rect(62, 116, 215, 128), 12.0, "4.1. Gemini Plays Pokemon"),
    ]

    expanded = expand_clip_to_nearby_figure_title(
        original,
        limited,
        text_lines,
        "above",
        pad=4,
        max_gap=12,
    )

    assert expanded == limited


def test_baseline_title_recovery_ignores_split_numbered_section_heading() -> None:
    original = fitz.Rect(26.0, 224.4, 569.3, 508.0)
    limited = fitz.Rect(26.0, 242.4, 569.3, 508.0)
    text_lines = [
        (fitz.Rect(70.9, 228.4, 83.3, 238.4), 10.0, "2.2"),
        (fitz.Rect(93.3, 228.4, 210.1, 238.4), 10.0, "Audio Transformer (AuT)"),
        (fitz.Rect(470.0, 256.0, 612.0, 266.0), 10.0, "Hi, I'm Qwen, your helpful assistant."),
    ]

    expanded = expand_clip_to_nearby_figure_title(
        original,
        limited,
        text_lines,
        "above",
        pad=4,
        max_gap=12,
    )

    assert expanded == limited


def test_final_title_recovery_ignores_large_section_title() -> None:
    original = fitz.Rect(26.0, 68.8, 586.0, 306.3)
    limited = fitz.Rect(114.5, 93.0, 509.8, 306.3)
    text_lines = [
        (fitz.Rect(108.0, 72.8, 230.8, 84.7), 12.0, "Attention Visualizations"),
        (fitz.Rect(119.6, 156.1, 130.0, 160.5), 4.5, "It"),
    ]

    expanded = expand_clip_to_nearby_figure_title(
        original,
        limited,
        text_lines,
        "above",
        pad=4,
        max_gap=12,
    )

    assert expanded == limited


def test_final_title_recovery_chains_stacked_figure_headings() -> None:
    original = fitz.Rect(26.0, 80.7, 569.3, 189.9)
    limited = fitz.Rect(72.9, 128.4, 523.2, 193.1)
    text_lines = [
        (fitz.Rect(138.1, 84.7, 456.0, 95.9), 10.0, "Frontier Regime Practical Regime"),
        (
            fitz.Rect(93.0, 100.2, 511.4, 122.4),
            10.0,
            "Putnam-2025 with hybrid formal-informal Putnam-200 Pass@8 with minimal tools",
        ),
        (fitz.Rect(79.7, 173.7, 512.0, 180.7), 7.0, "DeepSeek-V4 DeepSeek-V4-Flash-Max"),
    ]

    expanded = expand_clip_to_nearby_figure_title(
        original,
        limited,
        text_lines,
        "above",
        pad=4,
        max_gap=12,
    )

    assert expanded.y0 <= original.y0 + 0.1
    assert expanded.y1 == limited.y1


def test_phase_a_restores_far_side_short_chart_title() -> None:
    clip = fitz.Rect(26.0, 247.7, 586.0, 605.5)
    page = fitz.Rect(0.0, 0.0, 612.0, 792.0)
    caption = fitz.Rect(103.6, 611.5, 508.7, 669.3)
    text_lines = [
        (
            fitz.Rect(86.4, 238.1, 525.6, 249.0),
            10.9,
            "strengths of a learning approach — the policies are all sensible and qualitatively similar.",
        ),
        (
            fitz.Rect(86.4, 251.7, 435.9, 262.6),
            10.9,
            "learning performs significant quantitative optimization on a name-specific basis.",
        ),
        (fitz.Rect(265.8, 275.6, 334.7, 289.3), 10.0, "absolute trainer"),
        (fitz.Rect(405.8, 582.8, 463.6, 596.5), 10.0, "feature index"),
    ]

    trimmed = trim_clip_head_by_text_v2(
        clip,
        page,
        caption,
        "above",
        text_lines,
        width_ratio=0.5,
        font_min=7,
        font_max=16,
        gap=6,
        adjacent_th=24,
        far_text_th=300,
        far_text_para_min_ratio=0.30,
        far_side_min_dist=50,
        far_side_para_min_ratio=0.12,
        typical_line_h=12,
    )

    assert 267 <= trimmed.y0 <= 271, trimmed
    assert trimmed.y1 == clip.y1


def test_phase_b_preserves_near_caption_panel_subcaptions() -> None:
    clip = fitz.Rect(26.0, 82.0, 569.3, 311.9)
    caption = fitz.Rect(62.4, 317.9, 422.4, 329.4)
    vector_rects = [
        fitz.Rect(55.3, 82.0, 541.1, 283.6),
    ]
    text_lines = [
        (fitz.Rect(61.5, 284.2, 294.5, 294.2), 10.0, "(a) The fully autonomous Run 2 milestones as a func-"),
        (fitz.Rect(62.4, 296.2, 236.2, 306.1), 10.0, "tion of the number of individual actions."),
        (fitz.Rect(301.5, 284.1, 532.9, 294.2), 10.0, "(b) Comparison of 2.5 Pro and 2.5 Flash in terms of"),
        (fitz.Rect(302.3, 296.2, 395.3, 306.1), 10.0, "actions to milestones."),
    ]

    refined = refine_clip_by_objects(
        clip,
        caption,
        "above",
        image_rects=[],
        vector_rects=vector_rects,
        object_pad=8.0,
        min_area_ratio=0.015,
        merge_gap=6.0,
        near_edge_only=True,
        use_axis_union=True,
        text_lines=text_lines,
    )

    assert refined.y1 == pytest.approx(clip.y1, abs=0.01)


def test_phase_b_expands_to_nearby_axis_titles_without_full_edge_fallback() -> None:
    clip = fitz.Rect(26.0, 296.1, 586.0, 605.5)
    caption = fitz.Rect(103.6, 611.5, 508.7, 669.3)
    vector_rects = [
        fitz.Rect(181.0, 304.4, 405.0, 574.0),
    ]
    text_lines = [
        (fitz.Rect(405.8, 582.8, 463.6, 596.5), 10.0, "feature index"),
        (fitz.Rect(218.6, 562.0, 270.8, 575.7), 10.0, "policy index"),
        (fitz.Rect(103.6, 623.5, 508.7, 669.3), 10.0, "FIGURE 4: caption text"),
    ]

    refined = refine_clip_by_objects(
        clip,
        caption,
        "above",
        image_rects=[],
        vector_rects=vector_rects,
        object_pad=8.0,
        min_area_ratio=0.015,
        merge_gap=6.0,
        near_edge_only=True,
        use_axis_union=True,
        text_lines=text_lines,
    )

    assert 604 <= refined.y1 <= clip.y1, refined
    assert refined.y1 < clip.y1


def test_phase_b_preserves_near_caption_prompt_text_column() -> None:
    clip = fitz.Rect(26.0, 521.4, 569.3, 714.1)
    caption = fitz.Rect(62.4, 720.1, 534.7, 745.2)
    image_rects = [
        fitz.Rect(61.1, 521.4, 523.1, 655.2),
    ]
    text_lines = [
        (fitz.Rect(68.5, 656.5, 209.3, 667.5), 10.0, "Please convert this image into"),
        (fitz.Rect(68.3, 670.2, 209.5, 681.0), 10.0, "SVG and try to reconstruct the"),
        (fitz.Rect(76.2, 683.6, 201.6, 694.6), 10.0, "spatial arrangement of the"),
        (fitz.Rect(121.0, 697.2, 156.9, 708.1), 10.0, "objects."),
    ]

    refined = refine_clip_by_objects(
        clip,
        caption,
        "above",
        image_rects=image_rects,
        vector_rects=[],
        object_pad=8.0,
        min_area_ratio=0.015,
        merge_gap=6.0,
        near_edge_only=True,
        use_axis_union=True,
        text_lines=text_lines,
    )

    assert refined.y1 == pytest.approx(clip.y1, abs=0.01)


def test_text_trim_ignores_narrow_axis_ticks_near_caption() -> None:
    clip = fitz.Rect(26, 0, 569.3, 236.1)
    page_rect = fitz.Rect(0, 0, 595, 842)
    caption = fitz.Rect(62.4, 242.1, 365.3, 253.6)
    text_lines = [
        (
            fitz.Rect(68.2, 56.0, 526.8, 64.0),
            8.0,
            "Gemini 2.5: Pushing the Frontier with Advanced Reasoning, Multimodality.",
        ),
        (fitz.Rect(101.4, 195.7, 107.1, 203.4), 4.5, "20"),
        (fitz.Rect(104.2, 220.2, 107.1, 227.8), 4.5, "0"),
        (fitz.Rect(88.9, 129.9, 98.1, 195.8), 5.4, "Accuracy / Pass rate (%)"),
        (
            fitz.Rect(62.4, 242.1, 365.3, 253.6),
            10.9,
            "Figure 3 | Impact of Thinking on Gemini models performance.",
        ),
    ]

    trimmed = trim_clip_head_by_text_v2(
        clip,
        page_rect,
        caption,
        "above",
        text_lines,
        width_ratio=0.5,
        font_min=7,
        font_max=16,
        gap=6,
        adjacent_th=24,
        far_text_th=300,
        far_side_min_dist=50,
        far_side_para_min_ratio=0.12,
        typical_line_h=13.74,
    )

    assert trimmed.y1 == clip.y1
    assert 68 <= trimmed.y0 <= 72, trimmed


def test_baseline_clip_stops_at_wide_numeric_body_block() -> None:
    clip = fitz.Rect(26, 100, 569, 500)
    caption = fitz.Rect(70, 71, 525, 92)
    blocks = [
        _make_text_block(
            fitz.Rect(70, 280, 526, 360),
            "Qwen3 has 234 values and 547 parameters in this full width body paragraph.",
            "paragraph_group",
            0,
        ),
    ]

    limited = limit_clip_by_text_blocks(
        clip,
        caption,
        "below",
        blocks,
        gap=6,
        min_near_distance=80,
    )

    assert 270 <= limited.y1 <= 276, limited


def test_baseline_clip_stops_before_far_short_title_followed_by_body() -> None:
    clip = fitz.Rect(26, 521, 569, 842)
    caption = fitz.Rect(70, 493, 524, 515)
    blocks = [
        _make_text_block(fitz.Rect(169, 529, 520, 546), "Best Specialist GPT-4o", "title_h3", 1),
        _make_text_block(fitz.Rect(181, 570, 490, 589), "75.5 74.9", "paragraph_group", 1),
        _make_text_block(fitz.Rect(274, 674, 490, 693), "87.3 86.1", "paragraph_group", 1),
        _make_text_block(
            fitz.Rect(93, 699, 362, 709),
            "Qualitative Results from Qwen3-Omni-30B-A3B-Captioner",
            "title_h3",
            1,
        ),
        _make_text_block(
            fitz.Rect(71, 720, 525, 774),
            "In this section, we illustrate the performance of our finetuned Qwen3 model.",
            "paragraph_group",
            0,
        ),
    ]

    limited = limit_clip_by_text_blocks(
        clip,
        caption,
        "below",
        blocks,
        gap=6,
        min_near_distance=80,
    )

    assert 690 <= limited.y1 <= 695, limited


def test_baseline_clip_stops_after_isolated_far_title_above_caption() -> None:
    clip = fitz.Rect(26, 0, 586, 306)
    caption = fitz.Rect(108, 312, 504, 355)
    blocks = [
        _make_text_block(fitz.Rect(108, 73, 231, 85), "Attention Visualizations", "title_h2", 0),
    ]

    limited = limit_clip_by_text_blocks(
        clip,
        caption,
        "above",
        blocks,
        gap=6,
        min_near_distance=80,
    )

    assert 90 <= limited.y0 <= 92, limited


def test_baseline_clip_ignores_other_column_title_above_caption() -> None:
    clip = fitz.Rect(26, 0, 586, 306)
    caption = fitz.Rect(108, 312, 250, 355)
    blocks = [
        _make_text_block(fitz.Rect(330, 73, 520, 85), "Attention Visualizations", "title_h2", 1),
    ]

    limited = limit_clip_by_text_blocks(
        clip,
        caption,
        "above",
        blocks,
        gap=6,
        min_near_distance=80,
    )

    assert limited == clip


def test_baseline_clip_keeps_original_when_limit_would_be_too_short() -> None:
    clip = fitz.Rect(26, 98, 586, 160)
    caption = fitz.Rect(108, 71, 504, 92)
    text_blocks = [fitz.Rect(108, 120, 500, 132)]

    limited = limit_clip_by_text_blocks(
        clip,
        caption,
        "below",
        text_blocks,
        gap=6,
        min_height=40,
        min_near_distance=20,
    )

    assert limited == clip


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


def test_table_band_keeps_category_row_and_following_data_rows() -> None:
    clip = fitz.Rect(50, 50, 550, 430)
    caption = fitz.Rect(80, 35, 520, 45)
    text_lines = [
        (fitz.Rect(80, 70, 170, 80), 8.0, "Datasets"),
        (fitz.Rect(210, 70, 340, 80), 8.0, "Model"),
        (fitz.Rect(390, 70, 500, 80), 8.0, "Performance"),
        (fitz.Rect(80, 90, 230, 100), 8.0, "Content Consistency"),
        (fitz.Rect(80, 110, 500, 120), 8.0, "Seed-TTS Qwen3-Omni 2.14 3.02 0.91"),
        (fitz.Rect(80, 130, 245, 140), 8.0, "test-zh Qwen3-Omni"),
        (fitz.Rect(390, 130, 500, 140), 8.0, "2.08 3.17 0.92"),
        (fitz.Rect(80, 150, 245, 160), 8.0, "test-en Qwen3-Omni"),
        (fitz.Rect(390, 150, 500, 160), 8.0, "1.96 3.28 0.93"),
    ]
    for row in range(6):
        y0 = 230 + row * 16
        text_lines.append((
            fitz.Rect(60, y0, 540, y0 + 10),
            10.0,
            "Qwen3 is a long body paragraph line after the structured table.",
        ))

    refined, changed = refine_clip_to_table_band(
        clip,
        caption,
        text_lines,
        "below",
        typical_line_h=12,
    )
    assert changed
    assert 164 <= refined.y1 <= 172, refined


def test_table_band_keeps_strong_rows_across_group_spacing() -> None:
    clip = fitz.Rect(50, 50, 550, 220)
    caption = fitz.Rect(80, 35, 520, 45)
    text_lines = []
    for y0 in (70, 90, 130):
        for col in range(3):
            x0 = 80 + col * 140
            text_lines.append((fitz.Rect(x0, y0, x0 + 80, y0 + 10), 8.0, f"{y0}-{col}"))

    refined, changed = refine_clip_to_table_band(
        clip,
        caption,
        text_lines,
        "below",
        typical_line_h=12,
    )
    assert changed
    assert 144 <= refined.y1 <= 146, refined


def test_table_band_stops_before_sentence_like_strong_row_after_gap() -> None:
    clip = fitz.Rect(50, 50, 550, 260)
    caption = fitz.Rect(80, 35, 520, 45)
    text_lines = []
    for y0 in (70, 90, 110):
        for col in range(3):
            x0 = 80 + col * 140
            text_lines.append((fitz.Rect(x0, y0, x0 + 80, y0 + 10), 8.0, f"{y0}-{col}"))
    text_lines.extend([
        (
            fitz.Rect(70, 160, 300, 170),
            10.0,
            "This wide body sentence is split into two horizontal blocks and must not",
        ),
        (
            fitz.Rect(310, 160, 530, 170),
            10.0,
            "be bridged into the structured table after a large vertical gap.",
        ),
    ])

    refined, changed = refine_clip_to_table_band(
        clip,
        caption,
        text_lines,
        "below",
        typical_line_h=12,
    )
    assert changed
    assert 124 <= refined.y1 <= 126, refined


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


def test_column_detection_rejects_unrealistic_large_gap_candidate() -> None:
    units = []
    for i in range(12):
        units.append(EnhancedTextUnit(
            bbox=fitz.Rect(0, 80 + i * 14, 120, 90 + i * 14),
            text=f"Left-like paragraph sample {i}",
            page=0,
            font_name="Test",
            font_size=10.0,
            font_weight="regular",
            font_flags=0,
            color=(0, 0, 0),
            text_type="paragraph",
            confidence=1.0,
            column=-1,
            indent=0,
            block_idx=i,
            line_idx=0,
        ))
        units.append(EnhancedTextUnit(
            bbox=fitz.Rect(430, 80 + i * 14, 560, 90 + i * 14),
            text=f"Right-like paragraph sample {i}",
            page=0,
            font_name="Test",
            font_size=10.0,
            font_weight="regular",
            font_flags=0,
            color=(0, 0, 0),
            text_type="paragraph",
            confidence=1.0,
            column=-1,
            indent=430,
            block_idx=i,
            line_idx=1,
        ))

    num_columns, column_gap, updated = detect_columns({0: units}, 595.3)

    assert num_columns == 1
    assert column_gap == 0
    assert {unit.column for unit in updated[0]} == {-1}


def test_x_refine_ignores_untrusted_wide_gap_layout_columns() -> None:
    clip = fitz.Rect(26.0, 100.0, 569.3, 400.0)
    caption = fitz.Rect(120.0, 410.0, 475.0, 430.0)
    page = fitz.Rect(0.0, 0.0, 595.3, 842.0)
    layout_model = DocumentLayoutModel(
        page_size=(595.3, 842.0),
        num_columns=2,
        margin_left=0.0,
        margin_right=595.3,
        margin_top=50.0,
        margin_bottom=790.0,
        column_gap=327.0,
        typical_font_size=10.0,
        typical_line_height=12.0,
        typical_line_gap=2.0,
        text_units={0: []},
        text_blocks={0: []},
        vacant_regions={0: []},
    )
    image_rects = [fitz.Rect(70.9, 120.0, 524.4, 380.0)]

    refined = refine_module.refine_clip_x_range(
        clip,
        caption,
        "above",
        image_rects,
        [],
        page,
        layout_model=layout_model,
        page_num=0,
        x_margin=15.0,
        min_width_ratio=0.30,
    )

    assert refined.width > 480.0, refined
    assert refined.x1 > 520.0, refined


def test_layout_trim_preserves_structured_table_tail() -> None:
    clip = fitz.Rect(26, 248.8, 566, 498.1)
    caption = fitz.Rect(70, 224, 524, 246)
    far_table_blocks = [
        _make_text_block(fitz.Rect(163, 435, 490, 472), "87.9 91.2 90.0 90.0", "paragraph_group", 1),
        _make_text_block(fitz.Rect(163, 463, 490, 482), "71.9 72.4 70.5 71.4", "paragraph_group", 1),
        _make_text_block(fitz.Rect(163, 473, 490, 492), "30.8 47.3 50.2 51.1", "paragraph_group", 1),
    ]
    layout_model = DocumentLayoutModel(
        page_size=(595, 842),
        num_columns=2,
        margin_left=70,
        margin_right=525,
        margin_top=50,
        margin_bottom=790,
        column_gap=20,
        typical_font_size=10,
        typical_line_height=11,
        typical_line_gap=2,
        text_units={0: []},
        text_blocks={0: far_table_blocks},
        vacant_regions={0: []},
    )
    text_lines = [
        (fitz.Rect(278, 421, 315, 430), 8.8, "Counting"),
        (fitz.Rect(70, 435, 119, 444), 8.8, "CountBench"),
        (fitz.Rect(163, 435, 179, 444), 8.8, "87.9"),
        (fitz.Rect(224, 435, 240, 444), 8.8, "91.2"),
        (fitz.Rect(295, 435, 310, 444), 8.8, "93.6"),
        (fitz.Rect(377, 435, 393, 444), 8.8, "90.0"),
        (fitz.Rect(474, 435, 490, 444), 8.8, "90.0"),
        (fitz.Rect(254, 449, 339, 458), 8.8, "Video Understanding"),
        (fitz.Rect(70, 463, 145, 473), 8.8, "Video-MMEw/o sub"),
        (fitz.Rect(163, 463, 179, 472), 8.8, "71.9"),
        (fitz.Rect(224, 463, 240, 472), 8.8, "72.4"),
        (fitz.Rect(295, 463, 310, 472), 8.8, "73.3"),
        (fitz.Rect(377, 463, 393, 472), 8.8, "70.5"),
        (fitz.Rect(474, 463, 490, 472), 8.8, "71.4"),
        (fitz.Rect(70, 473, 106, 482), 8.8, "LVBench"),
        (fitz.Rect(163, 473, 179, 482), 8.8, "30.8"),
        (fitz.Rect(224, 473, 240, 482), 8.8, "57.9"),
        (fitz.Rect(295, 473, 310, 482), 8.8, "47.3"),
        (fitz.Rect(377, 473, 393, 482), 8.8, "50.2"),
        (fitz.Rect(474, 473, 490, 482), 8.8, "51.1"),
        (fitz.Rect(70, 483, 97, 492), 8.8, "MLVU"),
        (fitz.Rect(163, 483, 179, 492), 8.8, "64.6"),
        (fitz.Rect(224, 483, 240, 492), 8.8, "71.0"),
        (fitz.Rect(295, 483, 310, 492), 8.8, "74.6"),
        (fitz.Rect(377, 483, 393, 492), 8.8, "75.2"),
        (fitz.Rect(474, 483, 490, 492), 8.8, "75.7"),
    ]

    adjusted = adjust_clip_with_layout(clip, caption, layout_model, 0, "below")
    assert 428 <= adjusted.y1 <= 430, adjusted

    restored = restore_table_tail_after_layout_trim(
        clip,
        adjusted,
        text_lines,
        "below",
    )
    assert restored.y1 == clip.y1
    assert restored.x0 == adjusted.x0
    assert restored.x1 == adjusted.x1


def test_table_header_recovery_restores_multiline_header_above_table_body() -> None:
    original = fitz.Rect(26.0, 170.0, 569.3, 500.0)
    limited = fitz.Rect(26.0, 233.8, 569.3, 500.0)
    caption = fitz.Rect(62.0, 510.0, 533.0, 535.0)
    text_lines = [
        (fitz.Rect(80.0, 211.5, 518.0, 221.5), 8.8, "Benchmark Gemini 1.5 Gemini 2.0 Gemini 2.5"),
        (fitz.Rect(160.0, 223.0, 505.0, 233.0), 8.8, "Flash Pro Flash-Lite Flash Pro Flash-Lite Pro"),
        (fitz.Rect(70.0, 236.0, 145.0, 246.0), 8.8, "LiveCodeBench"),
        (fitz.Rect(180.0, 236.0, 198.0, 246.0), 8.8, "65.9"),
        (fitz.Rect(240.0, 236.0, 258.0, 246.0), 8.8, "72.4"),
        (fitz.Rect(300.0, 236.0, 318.0, 246.0), 8.8, "80.1"),
        (fitz.Rect(70.0, 250.0, 130.0, 260.0), 8.8, "HumanEval"),
        (fitz.Rect(180.0, 250.0, 198.0, 260.0), 8.8, "87.2"),
        (fitz.Rect(240.0, 250.0, 258.0, 260.0), 8.8, "91.1"),
        (fitz.Rect(300.0, 250.0, 318.0, 260.0), 8.8, "92.5"),
    ]

    expanded = expand_clip_to_nearby_table_header(
        original,
        limited,
        text_lines,
        caption,
        "above",
    )

    assert 207 <= expanded.y0 <= 209, expanded
    assert expanded.y1 == limited.y1


def test_table_final_text_bounds_recovers_connected_header_band() -> None:
    final_clip = fitz.Rect(57.4, 230.9, 537.9, 420.0)
    reference_clip = fitz.Rect(26.0, 0.0, 569.3, 419.6)
    caption = fitz.Rect(62.0, 425.6, 533.1, 464.2)
    text_lines = [
        (fitz.Rect(142.7, 88.7, 283.4, 98.7), 10.0, "Key Results for Gemini 2.5 Pro"),
        (fitz.Rect(88.9, 101.1, 364.5, 111.1), 10.0, "Area CCL"),
        (fitz.Rect(443.5, 101.1, 505.9, 111.1), 10.0, "CCL reached?"),
        (fitz.Rect(142.7, 126.2, 336.2, 136.2), 10.0, "Based on qualitative assessment, 2.5 Pro"),
        (fitz.Rect(142.7, 138.1, 336.1, 148.1), 10.0, "demonstrates a general trend of increasing"),
        (fitz.Rect(142.7, 150.1, 334.6, 160.1), 10.0, "model capabilities across models 1.5 Pro, 2.0"),
        (fitz.Rect(142.7, 162.1, 313.9, 172.0), 10.0, "and 2.5 Pro: it generates detailed technical"),
        (fitz.Rect(142.7, 174.7, 336.2, 184.6), 10.0, "knowledge of biological, radiological and nu-"),
        (fitz.Rect(142.7, 186.6, 336.1, 196.6), 10.0, "clear domains. However, no current Gem-"),
        (fitz.Rect(142.7, 198.6, 334.6, 208.6), 10.0, "ini model consistently or completely enables"),
        (fitz.Rect(142.7, 210.6, 313.9, 220.5), 10.0, "progress through key bottleneck stages."),
        (fitz.Rect(95.2, 236.4, 105.1, 246.4), 10.0, "biohazard-icon"),
        (fitz.Rect(142.7, 235.1, 335.8, 245.1), 10.0, "Solve rate on autonomous offense suite:"),
        (fitz.Rect(346.5, 235.2, 424.5, 245.1), 10.0, "Autonomy Level 1"),
        (fitz.Rect(443.5, 234.5, 526.9, 245.1), 10.0, "CCL not reached"),
        (fitz.Rect(68.3, 249.4, 131.8, 259.4), 10.0, "Cybersecurity"),
        (fitz.Rect(142.7, 271.4, 334.6, 281.5), 10.0, "On key skills benchmark: 7/8 easy, 14/28"),
        (fitz.Rect(443.5, 270.8, 526.9, 281.5), 10.0, "CCL not reached"),
    ]

    expanded = expand_table_clip_to_text_bounds(
        final_clip,
        reference_clip,
        caption,
        text_lines,
        "above",
    )

    assert expanded.y0 < 90.0, expanded
    assert expanded.y1 == final_clip.y1


def test_table_final_text_bounds_stops_before_body_paragraph() -> None:
    final_clip = fitz.Rect(57.4, 416.9, 537.9, 703.2)
    reference_clip = fitz.Rect(26.0, 381.6, 569.3, 702.8)
    caption = fitz.Rect(62.0, 708.8, 533.1, 747.4)
    text_lines = [
        (fitz.Rect(62.4, 371.9, 534.4, 382.9), 10.9, "In Table 6, we show the performance of Gemini 2.5 models at video understanding."),
        (fitz.Rect(62.4, 385.4, 534.4, 396.4), 10.9, "seen, Gemini 2.5 Pro achieves state-of-the-art performance on key video understanding benchmarks,"),
        (fitz.Rect(62.4, 398.9, 534.4, 410.0), 10.9, "surpassing recent models like GPT 4.1 under comparable testing conditions."),
        (fitz.Rect(211.1, 433.7, 254.0, 442.1), 8.4, "Gemini 2.5"),
        (fitz.Rect(62.4, 433.7, 532.9, 447.3), 8.4, "Capability Benchmark Gemini 2.5 o3 o4-mini Claude 4"),
        (fitz.Rect(125.0, 465.0, 220.0, 473.0), 8.4, "LiveCodeBench"),
        (fitz.Rect(421.0, 465.0, 445.0, 473.0), 8.4, "69.0%"),
        (fitz.Rect(501.0, 465.0, 525.0, 473.0), 8.4, "70.5%"),
    ]

    expanded = expand_table_clip_to_text_bounds(
        final_clip,
        reference_clip,
        caption,
        text_lines,
        "above",
    )

    assert expanded.y0 >= 416.0, expanded


def test_table_final_text_bounds_recovers_header_but_not_leading_body_line() -> None:
    final_clip = fitz.Rect(57.7, 484.5, 526.4, 734.3)
    reference_clip = fitz.Rect(26.0, 472.9, 569.3, 735.4)
    caption = fitz.Rect(62.0, 741.4, 366.9, 752.9)
    text_lines = [
        (
            fitz.Rect(62.4, 476.9, 532.9, 487.8),
            10.9,
            "in 0/3 cases (quite far away). Gemini 2.5 Pro gets the color in 3/3 cases, and gets the timestamp in",
        ),
        (fitz.Rect(61.5, 484.5, 532.9, 495.5), 10.9, "1/3 cases (remaining 2/3 are within 3 seconds close)."),
        (fitz.Rect(79.8, 517.8, 111.3, 528.7), 10.9, "Model"),
        (fitz.Rect(197.6, 517.8, 221.2, 528.7), 10.9, "Trial"),
        (fitz.Rect(233.1, 517.8, 312.3, 528.7), 10.9, "Model response"),
        (fitz.Rect(79.8, 536.9, 151.6, 547.8), 10.9, "Gemini 1.5 Pro"),
        (fitz.Rect(206.3, 536.9, 212.4, 547.8), 10.9, "1"),
        (fitz.Rect(233.1, 536.9, 515.7, 547.8), 10.9, "The t-shirt the robot arms are trying to fold is a dark teal or"),
        (fitz.Rect(160.0, 565.0, 225.0, 576.0), 10.9, "Gemini 1.5 Pro"),
        (fitz.Rect(412.0, 565.0, 425.0, 576.0), 10.9, "1"),
        (fitz.Rect(466.0, 565.0, 515.0, 576.0), 10.9, "The t-shirt"),
        (fitz.Rect(412.0, 626.0, 425.0, 637.0), 10.9, "3"),
        (fitz.Rect(466.0, 626.0, 515.0, 637.0), 10.9, "The t-shirt"),
        (fitz.Rect(160.0, 654.0, 270.0, 665.0), 10.9, "2.5 Pro Preview 05-06"),
        (fitz.Rect(412.0, 654.0, 425.0, 665.0), 10.9, "1"),
        (fitz.Rect(466.0, 654.0, 515.0, 665.0), 10.9, "The t-shirt"),
        (fitz.Rect(412.0, 682.0, 425.0, 693.0), 10.9, "2"),
        (fitz.Rect(466.0, 682.0, 515.0, 693.0), 10.9, "The T-shirt"),
        (fitz.Rect(412.0, 710.0, 425.0, 721.0), 10.9, "3"),
        (fitz.Rect(466.0, 710.0, 515.0, 721.0), 10.9, "The t-shirt"),
    ]

    expanded = expand_table_clip_to_text_bounds(
        final_clip,
        reference_clip,
        caption,
        text_lines,
        "above",
    )

    assert 515.0 <= expanded.y0 <= 518.0, expanded
    assert expanded.y1 == final_clip.y1


def test_table_direction_tie_break_prefers_nearest_structured_table() -> None:
    caption = fitz.Rect(62.0, 162.0, 533.2, 200.6)
    page = fitz.Rect(0.0, 0.0, 595.3, 842.0)
    text_lines = [
        (fitz.Rect(123.0, 88.6, 162.5, 96.3), 7.8, "Gemini 1.5"),
        (fitz.Rect(166.7, 88.6, 206.2, 96.3), 7.8, "Gemini 1.5"),
        (fitz.Rect(62.4, 93.4, 102.9, 101.2), 7.8, "Benchmark"),
        (fitz.Rect(133.4, 98.2, 152.0, 106.0), 7.8, "Flash"),
        (fitz.Rect(212.9, 98.2, 247.4, 106.0), 7.8, "Flash-Lite"),
        (fitz.Rect(62.4, 111.8, 89.5, 119.5), 7.8, "FLEURS"),
        (fitz.Rect(133.0, 116.6, 152.4, 124.4), 7.8, "12.71"),
        (fitz.Rect(178.9, 116.6, 194.0, 124.4), 7.8, "7.14"),
        (fitz.Rect(222.6, 116.6, 237.7, 124.4), 7.8, "9.60"),
        (fitz.Rect(266.3, 116.6, 281.4, 124.4), 7.8, "9.04"),
        (fitz.Rect(310.0, 116.6, 325.1, 124.4), 7.8, "9.95"),
        (fitz.Rect(353.4, 116.6, 369.2, 124.3), 7.8, "6.66"),
        (fitz.Rect(401.3, 116.6, 420.7, 124.4), 7.8, "19.52"),
        (fitz.Rect(456.9, 116.6, 476.4, 124.4), 7.8, "12.16"),
        (fitz.Rect(507.2, 116.6, 522.3, 124.4), 7.8, "8.17"),
        (fitz.Rect(62.4, 132.0, 95.0, 139.8), 7.8, "CoVoST2"),
        (fitz.Rect(133.0, 136.8, 152.4, 144.6), 7.8, "34.81"),
        (fitz.Rect(178.9, 136.8, 194.0, 144.6), 7.8, "37.53"),
        (fitz.Rect(222.6, 136.8, 237.7, 144.6), 7.8, "34.74"),
        (fitz.Rect(266.3, 136.8, 281.4, 144.6), 7.8, "36.35"),
        (fitz.Rect(310.0, 136.8, 325.1, 144.6), 7.8, "36.15"),
        (fitz.Rect(353.4, 136.8, 369.2, 144.6), 7.8, "38.48"),
        (fitz.Rect(200.3, 217.8, 241.8, 226.0), 8.2, "Gemini 1.5"),
        (fitz.Rect(250.8, 217.8, 292.3, 226.0), 8.2, "Gemini 1.5"),
        (fitz.Rect(66.8, 222.9, 106.1, 231.1), 8.2, "Modalities"),
        (fitz.Rect(137.3, 222.9, 180.0, 231.1), 8.2, "Benchmark"),
        (fitz.Rect(211.3, 228.0, 230.9, 236.1), 8.2, "Flash"),
        (fitz.Rect(137.3, 242.9, 190.5, 251.1), 8.2, "ActivityNet-QA"),
        (fitz.Rect(213.1, 242.9, 229.0, 251.1), 8.2, "56.2"),
        (fitz.Rect(263.6, 242.9, 279.5, 251.1), 8.2, "57.3"),
        (fitz.Rect(62.0, 430.0, 533.2, 455.0), 10.0, "Table 6 | Evaluation of Gemini 2.5 vs. prior models"),
    ]

    direction, confidence = score_local_direction(
        caption,
        page,
        [],
        [],
        clip_height=520.0,
        margin_x=26.0,
        caption_gap=6.0,
        is_table=True,
        text_lines=text_lines,
    )

    assert direction == "above"
    assert confidence >= 0.6


def test_table_final_padding_keeps_text_bbox_before_caption() -> None:
    final_clip = fitz.Rect(159.4, 69.8, 452.7, 126.7)
    reference_clip = fitz.Rect(26.0, 0.0, 586.0, 126.4)
    caption = fitz.Rect(142.8, 132.4, 468.9, 142.4)
    text_lines = [
        (fitz.Rect(170.2, 75.8, 210.0, 86.0), 10.0, "Test set"),
        (fitz.Rect(252.0, 75.8, 341.0, 86.0), 10.0, "Offline"),
        (fitz.Rect(374.0, 75.8, 441.8, 86.0), 10.0, "Streaming"),
        (fitz.Rect(172.0, 90.0, 440.0, 100.0), 10.0, "w/o CS w/o RL w/ RL w/o CS w/o RL w/ RL"),
        (fitz.Rect(176.0, 106.0, 432.0, 116.0), 10.0, "A 4.53 1.70 1.59 6.19 5.85 2.28"),
        (fitz.Rect(176.0, 119.0, 441.8, 128.9), 10.0, "B 4.76 4.56 4.50 6.32 5.68 5.07"),
        (
            fitz.Rect(142.8, 132.4, 468.9, 142.4),
            10.0,
            "Table 5: Word Error Rate (WER, %) evaluation Result on code-switched test sets",
        ),
    ]

    expanded = expand_table_clip_to_text_bounds(
        final_clip,
        reference_clip,
        caption,
        text_lines,
        "above",
        pad=2.5,
    )

    assert expanded.y1 >= 131.0, expanded
    assert expanded.y1 <= caption.y0 - 1.0, expanded
    assert expanded.y0 == final_clip.y0


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


def test_colon_caption_is_not_reference_even_inside_long_text_block() -> None:
    long_block = {
        "lines": [
            {"spans": [{"text": "A long body paragraph line before the caption."}]}
            for _ in range(8)
        ],
    }
    assert not is_caption_reference(
        "Table 9: Vision to Text performance of Qwen3-Omni.",
        long_block,
        re.compile(r"^Table\s+\d+"),
    )


def test_pipe_caption_is_not_reference_even_inside_long_text_block() -> None:
    long_block = {
        "lines": [
            {"spans": [{"text": "A long body paragraph line before the caption."}]}
            for _ in range(8)
        ],
    }
    assert not is_caption_reference(
        "Figure 8 | Formal reasoning under practical and frontier regimes.",
        long_block,
        re.compile(r"^Figure\s+\d+"),
    )


def test_figure_baseline_recovers_connected_far_side_objects() -> None:
    clip = fitz.Rect(26, 155, 569, 384)
    caption = fitz.Rect(70, 390, 525, 429)
    page_rect = fitz.Rect(0, 0, 595, 842)
    vector_rects = [
        fitz.Rect(350, 92, 460, 120),
        fitz.Rect(360, 124, 450, 152),
    ]

    expanded = expand_clip_to_nearby_figure_objects(
        clip,
        caption,
        "above",
        [],
        vector_rects,
        page_rect,
        [],
        gap=6.0,
    )

    assert expanded.y0 < 90
    assert expanded.y1 == clip.y1


def test_figure_final_recovers_object_overlapping_far_edge() -> None:
    clip = fitz.Rect(155.4, 106.9, 428.2, 258.5)
    caption = fitz.Rect(71.0, 267.0, 524.0, 291.0)
    page_rect = fitz.Rect(0, 0, 595, 842)
    clipped_top_panel = fitz.Rect(241.5, 86.7, 382.4, 119.9)

    expanded = expand_clip_to_nearby_figure_objects(
        clip,
        caption,
        "above",
        [],
        [clipped_top_panel],
        page_rect,
        [],
        gap=6.0,
        max_expand=80.0,
    )

    assert expanded.y0 < 90
    assert expanded.y1 == clip.y1


def test_figure_object_recovery_respects_previous_caption_boundary() -> None:
    clip = fitz.Rect(26, 309, 569, 516)
    caption = fitz.Rect(70, 522, 371, 534)
    page_rect = fitz.Rect(0, 0, 595, 842)
    previous_caption = fitz.Rect(70, 210, 526, 303)
    previous_figure_object = fitz.Rect(100, 175, 500, 200)

    expanded = expand_clip_to_nearby_figure_objects(
        clip,
        caption,
        "above",
        [],
        [previous_figure_object],
        page_rect,
        [previous_caption],
        gap=6.0,
    )

    assert expanded == clip


def test_figure_final_padding_keeps_gap_before_caption() -> None:
    clip = fitz.Rect(64, 411, 532, 704.5)
    caption = fitz.Rect(70, 710.3, 524, 735.9)

    padded = pad_figure_clip_near_caption(
        clip,
        caption,
        "above",
        pad=4.0,
        min_caption_gap=2.0,
    )

    assert padded.y1 > clip.y1
    assert padded.y1 <= caption.y0 - 2.0


def test_long_pipe_figure_caption_flips_above_when_next_figure_steals_direction() -> None:
    caption = fitz.Rect(70.9, 195.9, 526.2, 275.7)
    page = fitz.Rect(0, 0, 595, 842)
    next_caption = fitz.Rect(70.9, 522.1, 371.0, 534.2)
    current_top_figure = fitz.Rect(79.7, 173.7, 512.0, 180.7)
    next_lower_figure = fitz.Rect(112.8, 311.9, 483.8, 519.6)

    direction = correct_bare_figure_caption_direction(
        "below",
        caption,
        "Figure 8 | Formal reasoning under practical and frontier regimes.",
        page,
        [],
        [current_top_figure, next_lower_figure],
        [next_caption],
        clip_height=650.0,
        caption_gap=6.0,
    )

    assert direction == "above"


def test_long_pipe_figure_caption_keeps_below_when_lower_object_is_nearer() -> None:
    caption = fitz.Rect(70.9, 195.9, 526.2, 235.0)
    page = fitz.Rect(0, 0, 595, 842)
    next_caption = fitz.Rect(70.9, 522.1, 371.0, 534.2)
    previous_far_object = fitz.Rect(80.0, 130.0, 510.0, 150.0)
    current_lower_figure = fitz.Rect(100.0, 241.0, 500.0, 430.0)

    direction = correct_bare_figure_caption_direction(
        "below",
        caption,
        "Figure 8 | Formal reasoning under practical and frontier regimes.",
        page,
        [],
        [previous_far_object, current_lower_figure],
        [next_caption],
        clip_height=650.0,
        caption_gap=6.0,
    )

    assert direction == "below"


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


def test_table_far_side_trims_trailing_section_heading() -> None:
    """表格下方紧跟的章节标题（编号被拆到正文）应从 final 远端剔除。

    复刻 Qwen3-Omni Table 5：标题块 "Performance of Audio→Text" 残留在表格
    远端，其编号 "5.1.2" 被拆到后续正文段落里。
    """
    clip = fitz.Rect(66.1, 267.4, 529.5, 460.0)
    caption = fitz.Rect(70.6, 243.0, 524.4, 264.9)
    layout_blocks = [
        _make_text_block(fitz.Rect(100.8, 420.4, 230.9, 431.4), "Performance of Audio→Text", "title_h3"),
        _make_text_block(fitz.Rect(70.4, 421.4, 526.1, 472.7), "5.1.2 We compare Qwen3-Omni with other leading specialist and generalist models on ASR.", "paragraph_group"),
    ]
    text_lines = [
        (fitz.Rect(70.9, 398.0, 130.0, 408.0), 8.0, "Multilingual"),
        (fitz.Rect(200.0, 398.0, 218.0, 408.0), 8.0, "74.4"),
        (fitz.Rect(70.4, 421.4, 95.0, 431.4), 10.0, "5.1.2"),
        (fitz.Rect(100.8, 420.4, 230.9, 431.4), 10.0, "Performance of Audio→Text"),
        (fitz.Rect(70.4, 421.4, 526.1, 431.4), 10.0, "5.1.2 We compare Qwen3-Omni with other leading specialist and generalist models"),
        (fitz.Rect(70.4, 433.0, 520.0, 443.0), 10.0, "chatting, audio reasoning, and music understanding benchmarks."),
    ]

    result = trim_table_far_side_section_heading(
        clip, caption, "below", layout_blocks, text_lines,
    )
    assert 413.0 <= result.y1 <= 415.0, result
    assert result.x0 == clip.x0 and result.x1 == clip.x1


def test_table_far_side_keeps_misclassified_last_data_row() -> None:
    """被误判为标题、但右侧带数字数据列的表格末行应保留，不得误裁。

    复刻 Qwen3-Omni Table 2：末行 "Generation RTF(Real Time Factor) 0.47 0.56 0.66"
    被布局模型误判为 title_h3，但右侧有数据列，属于真实表格行。
    """
    clip = fitz.Rect(99.0, 529.8, 496.4, 677.9)
    caption = fitz.Rect(70.6, 510.0, 524.0, 528.0)
    layout_blocks = [
        _make_text_block(fitz.Rect(103.8, 662.7, 244.1, 671.7), "Generation RTF(Real Time Factor)", "title_h3"),
        _make_text_block(fitz.Rect(325.7, 662.7, 469.8, 671.7), "0.47 0.56 0.66", "paragraph_group"),
        _make_text_block(fitz.Rect(70.6, 698.2, 526.1, 770.0), "sources across varying concurrency scenarios.", "paragraph_group"),
    ]
    text_lines = [
        (fitz.Rect(103.8, 637.9, 300.0, 647.9), 8.0, "Thinker Token Generation Rate (TPS)"),
        (fitz.Rect(103.8, 662.7, 244.1, 671.7), 8.0, "Generation RTF(Real Time Factor)"),
        (fitz.Rect(325.7, 662.7, 469.8, 671.7), 8.0, "0.47 0.56 0.66"),
        (fitz.Rect(70.6, 698.2, 526.1, 708.2), 10.0, "sources across varying concurrency scenarios."),
    ]

    result = trim_table_far_side_section_heading(
        clip, caption, "below", layout_blocks, text_lines,
    )
    assert result.y1 == clip.y1, result


def test_table_far_side_keeps_header_followed_by_table_rows() -> None:
    """Gemini 表头虽然可能被识别为 title_h3，但后续是表格行，不应被裁。"""
    clip = fitz.Rect(57.4, 86.2, 537.9, 420.0)
    caption = fitz.Rect(62.0, 425.6, 533.1, 464.2)
    layout_blocks = [
        _make_text_block(fitz.Rect(142.7, 88.7, 283.4, 98.7), "Key Results for Gemini 2.5 Pro", "title_h3"),
        _make_text_block(fitz.Rect(88.9, 101.1, 364.5, 111.1), "Area CCL", "paragraph_group"),
        _make_text_block(fitz.Rect(443.5, 101.1, 505.9, 111.1), "CCL reached?", "title_h3"),
        _make_text_block(fitz.Rect(142.7, 126.2, 526.9, 245.1), "Solve rate Autonomy Level 1 CCL not reached", "paragraph_group"),
    ]
    text_lines = [
        (fitz.Rect(142.7, 88.7, 283.4, 98.7), 8.0, "Key Results for Gemini 2.5 Pro"),
        (fitz.Rect(88.9, 101.1, 122.0, 111.1), 8.0, "Area"),
        (fitz.Rect(340.0, 101.1, 365.0, 111.1), 8.0, "CCL"),
        (fitz.Rect(443.5, 101.1, 505.9, 111.1), 8.0, "CCL reached?"),
        (fitz.Rect(142.7, 235.1, 335.8, 245.1), 8.0, "Solve rate on internal coding set"),
        (fitz.Rect(346.5, 235.2, 424.5, 245.1), 8.0, "Autonomy Level 1"),
        (fitz.Rect(443.5, 234.5, 526.9, 245.1), 8.0, "CCL not reached"),
    ]

    result = trim_table_far_side_section_heading(
        clip, caption, "above", layout_blocks, text_lines,
    )
    assert result.y0 == clip.y0, result


def test_table_far_side_trims_numbered_section_heading_above_table() -> None:
    """FunAudio 表格上方紧贴章节标题时，应只裁掉章节标题，保留下方表格。"""
    clip = fitz.Rect(135.4, 281.1, 421.0, 478.7)
    caption = fitz.Rect(181.0, 484.4, 430.7, 494.4)
    layout_blocks = [
        _make_text_block(fitz.Rect(137.9, 283.6, 273.5, 293.5), "Evaluation on Noise Robustness", "title_h3"),
        _make_text_block(fitz.Rect(199.4, 310.2, 398.1, 472.4), "FunAudio-ASR Environment canteen 20.67 20.34 19.88", "paragraph_group"),
    ]
    text_lines = [
        (fitz.Rect(105.0, 283.6, 132.0, 293.5), 10.0, "6.2.3"),
        (fitz.Rect(137.9, 283.6, 273.5, 293.5), 10.0, "Evaluation on Noise Robustness"),
        (fitz.Rect(199.4, 310.2, 271.0, 320.2), 8.0, "FunAudio-ASR"),
        (fitz.Rect(282.0, 310.2, 330.0, 320.2), 8.0, "Environment"),
        (fitz.Rect(342.0, 310.2, 398.1, 320.2), 8.0, "WER (%)"),
    ]

    result = trim_table_far_side_section_heading(
        clip, caption, "above", layout_blocks, text_lines,
    )
    assert 298.0 <= result.y0 <= 301.0, result


def test_table_far_side_keeps_same_row_data_cell_at_far_edge() -> None:
    """Attention 表格最右侧数据单元格误判为 title_h3 时，不应裁掉末行。"""
    clip = fitz.Rect(125.8, 93.3, 486.3, 246.9)
    caption = fitz.Rect(107.7, 71.2, 504.0, 92.1)
    layout_blocks = [
        _make_text_block(fitz.Rect(407.3, 217.7, 450.7, 228.9), "3.3 · 10^18", "title_h3"),
        _make_text_block(fitz.Rect(136.7, 230.5, 353.7, 240.5), "28.4 41.8", "paragraph_group"),
    ]
    text_lines = [
        (fitz.Rect(136.7, 217.7, 212.7, 228.9), 8.0, "Transformer"),
        (fitz.Rect(250.0, 217.7, 315.0, 228.9), 8.0, "28.4"),
        (fitz.Rect(407.3, 217.7, 450.7, 228.9), 8.0, "3.3 · 10^18"),
        (fitz.Rect(136.7, 230.5, 353.7, 240.5), 8.0, "28.4 41.8"),
    ]

    result = trim_table_far_side_section_heading(
        clip, caption, "below", layout_blocks, text_lines,
    )
    assert result.y1 == clip.y1, result


def test_table_far_side_keeps_layout_only_same_row_data_cell() -> None:
    """text_lines 缺失同排数据时，layout 同排数据块也应保护表格末行。"""
    clip = fitz.Rect(99.0, 529.8, 496.4, 674.2)
    caption = fitz.Rect(105.8, 513.7, 489.2, 523.8)
    layout_blocks = [
        _make_text_block(fitz.Rect(103.8, 662.7, 244.1, 671.7), "Generation RTF(Real Time Factor)", "title_h3"),
        _make_text_block(fitz.Rect(325.7, 662.7, 469.8, 671.7), "0.47 0.56 0.66", "paragraph_group"),
        _make_text_block(fitz.Rect(70.6, 698.2, 526.1, 708.2), "sources across varying concurrency scenarios.", "paragraph_group"),
    ]

    result = trim_table_far_side_section_heading(
        clip,
        caption,
        "below",
        layout_blocks,
        [],
    )

    assert result.y1 == clip.y1, result


def test_table_final_text_bounds_recovers_qwen_table2_tail_row() -> None:
    """Qwen Table 2 final 缺少末行时，应回补紧邻的结构化表格行。"""
    final_clip = fitz.Rect(99.0, 529.8, 496.4, 656.7)
    reference_clip = fitz.Rect(26.0, 529.8, 569.3, 681.1)
    caption = fitz.Rect(105.8, 513.7, 489.2, 523.8)
    text_lines = [
        (fitz.Rect(304.0, 538.3, 491.4, 562.0), 8.0, "Qwen3-Omni-30B-A3B 1 Concurrency 4 Concurrency 6 Concurrency"),
        (fitz.Rect(103.8, 568.1, 486.2, 616.9), 8.0, "Thinker-Talker Tail Packet Preprocessing Latency 72/160ms 94/180ms 100/200ms"),
        (fitz.Rect(103.8, 622.8, 487.2, 631.8), 8.0, "Overral Latency (Audio/Video) 234/547ms 728/1517ms 1172/2284ms"),
        (fitz.Rect(103.8, 637.9, 487.5, 656.8), 8.0, "Thinker Token Generation Rate (TPS) 75 tokens/s Talker Token Generation Rate (TPS) 140 tokens/s"),
        (fitz.Rect(103.8, 662.7, 244.1, 671.7), 8.0, "Generation RTF(Real Time Factor)"),
        (fitz.Rect(325.7, 662.7, 469.8, 671.7), 8.0, "0.47 0.56 0.66"),
        (fitz.Rect(70.6, 698.2, 526.1, 708.2), 10.0, "sources across varying concurrency scenarios. Experiments are conducted on the vLLM framework."),
    ]

    expanded = expand_table_clip_to_text_bounds(
        final_clip,
        reference_clip,
        caption,
        text_lines,
        "below",
    )

    assert 673.0 <= expanded.y1 <= 675.0, expanded
    assert expanded.y1 < 690.0, expanded


def test_table_final_text_bounds_recovers_tail_row_from_layout_blocks() -> None:
    """当 text_lines 漏掉末行时，layout 同行数据块可兜底回补表格行。"""
    final_clip = fitz.Rect(99.0, 529.8, 496.4, 656.7)
    reference_clip = fitz.Rect(26.0, 529.8, 569.3, 681.1)
    caption = fitz.Rect(105.8, 513.7, 489.2, 523.8)
    text_lines = [
        (fitz.Rect(304.0, 538.3, 491.4, 562.0), 8.0, "Qwen3-Omni-30B-A3B 1 Concurrency 4 Concurrency 6 Concurrency"),
        (fitz.Rect(103.8, 568.1, 486.2, 616.9), 8.0, "Thinker-Talker Tail Packet Preprocessing Latency 72/160ms 94/180ms 100/200ms"),
        (fitz.Rect(103.8, 622.8, 487.2, 631.8), 8.0, "Overral Latency (Audio/Video) 234/547ms 728/1517ms 1172/2284ms"),
        (fitz.Rect(103.8, 637.9, 487.5, 656.8), 8.0, "Thinker Token Generation Rate (TPS) 75 tokens/s Talker Token Generation Rate (TPS) 140 tokens/s"),
    ]
    layout_blocks = [
        _make_text_block(fitz.Rect(103.8, 662.7, 244.1, 671.7), "Generation RTF(Real Time Factor)", "title_h3"),
        _make_text_block(fitz.Rect(325.7, 662.7, 469.8, 671.7), "0.47 0.56 0.66", "paragraph_group"),
        _make_text_block(fitz.Rect(70.6, 698.2, 526.1, 708.2), "sources across varying concurrency scenarios.", "paragraph_group"),
    ]

    expanded = expand_table_clip_to_text_bounds(
        final_clip,
        reference_clip,
        caption,
        text_lines,
        "below",
        layout_text_blocks=layout_blocks,
    )

    assert 673.0 <= expanded.y1 <= 675.0, expanded
    assert expanded.y1 < 690.0, expanded


def test_table_final_text_bounds_trims_far_side_blank_before_table() -> None:
    """FunAudio Table 2 顶部远端空白较大时，应收紧到表格首行附近。"""
    final_clip = fitz.Rect(103.0, 550.3, 509.1, 689.9)
    reference_clip = fitz.Rect(26.0, 550.3, 586.0, 689.7)
    caption = fitz.Rect(155.7, 695.7, 456.0, 705.6)
    text_lines = [
        (fitz.Rect(113.4, 585.0, 160.0, 595.0), 8.0, "Test set"),
        (fitz.Rect(410.0, 585.0, 498.6, 595.0), 8.0, "FunAudio-ASR"),
        (fitz.Rect(113.4, 612.0, 160.0, 622.0), 8.0, "In-house"),
        (fitz.Rect(210.0, 612.0, 230.0, 622.0), 8.0, "7.20"),
        (fitz.Rect(470.0, 612.0, 498.6, 622.0), 8.0, "6.66"),
    ]

    trimmed = expand_table_clip_to_text_bounds(
        final_clip,
        reference_clip,
        caption,
        text_lines,
        "above",
    )

    assert 581.0 <= trimmed.y0 <= 583.0, trimmed
    assert trimmed.y1 == final_clip.y1


def test_table_final_text_bounds_trims_body_tail_before_header() -> None:
    """Kearns Table 1 顶部正文尾句进入 final 时，应裁到表头附近。"""
    final_clip = fitz.Rect(83.9, 384.5, 478.9, 494.5)
    reference_clip = fitz.Rect(26.0, 342.3, 586.0, 494.4)
    caption = fitz.Rect(134.4, 500.4, 477.9, 510.6)
    text_lines = [
        (fitz.Rect(86.4, 384.5, 126.0, 397.9), 10.0, "almost 13%."),
        (fitz.Rect(197.6, 408.9, 310.0, 419.8), 10.0, "Feature(s) Added"),
        (fitz.Rect(340.0, 408.9, 467.8, 419.8), 10.0, "Reduction in Trading Cost"),
        (fitz.Rect(144.2, 422.9, 250.0, 433.0), 10.0, "Bid-Ask Spread"),
        (fitz.Rect(390.0, 422.9, 422.7, 433.0), 10.0, "7.97%"),
    ]

    trimmed = expand_table_clip_to_text_bounds(
        final_clip,
        reference_clip,
        caption,
        text_lines,
        "above",
    )

    assert 406.0 <= trimmed.y0 <= 407.0, trimmed
    assert trimmed.y1 == final_clip.y1


def test_table_final_text_bounds_trims_numeric_body_tail_before_header() -> None:
    """Gemini Table 12 的数字正文尾句不应被当作表格起点保留。"""
    final_clip = fitz.Rect(57.7, 488.0, 526.4, 734.3)
    reference_clip = fitz.Rect(26.0, 472.9, 569.3, 735.4)
    caption = fitz.Rect(62.0, 741.4, 366.9, 752.9)
    text_lines = [
        (
            fitz.Rect(61.5, 488.2, 526.4, 498.9),
            10.0,
            "1/3 cases (remaining 2/3 are within 3 seconds close).",
        ),
        (fitz.Rect(79.8, 517.8, 121.0, 528.7), 10.0, "Model"),
        (fitz.Rect(204.0, 517.8, 226.0, 528.7), 10.0, "Trial"),
        (fitz.Rect(233.1, 517.8, 312.3, 528.7), 10.0, "Model response"),
        (fitz.Rect(79.8, 536.9, 157.0, 547.8), 10.0, "Gemini 1.5 Pro"),
        (fitz.Rect(204.0, 536.9, 212.0, 547.8), 10.0, "1"),
        (
            fitz.Rect(233.1, 536.9, 515.7, 559.0),
            10.0,
            "The t-shirt the robot arms are trying to fold is a dark teal or turquoise blue color.",
        ),
    ]

    trimmed = expand_table_clip_to_text_bounds(
        final_clip,
        reference_clip,
        caption,
        text_lines,
        "above",
    )

    assert 515.0 <= trimmed.y0 <= 516.0, trimmed
    assert trimmed.y1 == final_clip.y1


def test_table_final_text_bounds_keeps_wrapped_tail_cell_line() -> None:
    """GPT-5 Table 16 的短换行单元格尾行应保留到 final 底部。"""
    final_clip = fitz.Rect(76.4, 169.7, 519.0, 262.1)
    reference_clip = fitz.Rect(26.0, 168.8, 569.3, 364.1)
    caption = fitz.Rect(109.4, 151.9, 485.3, 162.8)
    text_lines = [
        (fitz.Rect(87.3, 179.1, 140.6, 189.1), 10.0, "Evaluation"),
        (fitz.Rect(198.4, 179.1, 250.3, 189.1), 10.0, "Capability"),
        (fitz.Rect(337.9, 179.1, 395.6, 189.1), 10.0, "Description"),
        (fitz.Rect(87.3, 237.7, 144.4, 247.7), 10.0, "Cyber Range"),
        (fitz.Rect(198.4, 237.7, 326.0, 247.7), 10.0, "Vulnerability Identification &"),
        (fitz.Rect(198.4, 249.6, 252.5, 259.6), 10.0, "Exploitation"),
        (fitz.Rect(337.9, 237.7, 508.0, 247.7), 10.0, "Can models conduct fully end-to-end"),
        (fitz.Rect(337.9, 249.6, 508.0, 259.6), 10.0, "cyber operations in a realistic, emulated"),
        (fitz.Rect(337.9, 261.6, 377.3, 271.6), 10.0, "network?"),
        (fitz.Rect(70.9, 305.9, 314.4, 316.8), 10.0, "5.1.2.1 Capture the Flag (CTF) Challenges"),
    ]

    expanded = expand_table_clip_to_text_bounds(
        final_clip,
        reference_clip,
        caption,
        text_lines,
        "below",
    )

    assert 273.5 <= expanded.y1 <= 275.0, expanded


def test_figure_noise_trim_ignores_sentence_tail_as_content_evidence() -> None:
    """GPT-5 Figure 29 顶部正文尾句不应阻止 far-side 图像边界收紧。"""
    original_clip = fitz.Rect(26.0, 195.5, 569.3, 400.4)
    candidate_clip = fitz.Rect(44.9, 328.7, 550.4, 400.4)
    image_rects = [fitz.Rect(70.9, 348.0, 524.4, 395.0)]
    text_lines = [
        (fitz.Rect(70.5, 328.7, 142.0, 336.8), 10.0, "of such behaviors."),
        (fitz.Rect(97.0, 354.0, 220.0, 364.0), 10.0, "Grader Sycophancy"),
    ]

    trimmed = trim_far_side_noise_before_content(
        original_clip,
        candidate_clip,
        "above",
        image_rects,
        [],
        text_lines,
        pad=8.0,
        min_gap=10.0,
    )

    assert 339.5 <= trimmed.y0 <= 341.0, trimmed
    assert trimmed.y1 == candidate_clip.y1


def test_figure_post_autocrop_trims_narrow_lowercase_sentence_tail() -> None:
    """窄正文尾句即使宽度不足 30%，也应从 Figure far side 裁掉。"""
    clip = fitz.Rect(44.9, 328.7, 550.4, 400.4)
    text_lines = [
        (fitz.Rect(70.5, 328.7, 142.0, 336.8), 10.0, "of such behaviors."),
        (fitz.Rect(97.0, 354.0, 220.0, 364.0), 10.0, "Grader Sycophancy"),
    ]

    trimmed, changed = trim_far_side_text_iterative(
        clip,
        text_lines,
        "above",
        typical_line_h=10.0,
        max_passes=1,
    )

    assert changed
    assert 342.0 <= trimmed.y0 <= 343.5, trimmed


def test_figure_title_recovery_ignores_lowercase_sentence_tail() -> None:
    """图内标题回收不应把正文尾句重新扩回 final。"""
    original_clip = fitz.Rect(26.0, 328.7, 569.3, 400.4)
    limited_clip = fitz.Rect(44.9, 342.8, 550.4, 400.4)
    text_lines = [
        (fitz.Rect(70.5, 328.7, 142.0, 336.8), 10.0, "of such behaviors."),
        (fitz.Rect(197.0, 354.0, 310.0, 364.0), 10.0, "Grader Sycophancy"),
    ]

    expanded = expand_clip_to_nearby_figure_title(
        original_clip,
        limited_clip,
        text_lines,
        "above",
    )

    assert expanded == limited_clip


def test_table_far_side_trims_single_number_section_heading() -> None:
    """Qwen Table 16 远端单级章节标题 `7 Conclusion` 应从表格截图剔除。"""
    clip = fitz.Rect(66.1, 374.4, 527.1, 739.3)
    caption = fitz.Rect(70.6, 336.6, 524.4, 368.4)
    layout_blocks = [
        _make_text_block(fitz.Rect(70.9, 724.9, 151.2, 736.8), "7 Conclusion", "title_h2"),
        _make_text_block(
            fitz.Rect(70.9, 750.3, 526.1, 771.3),
            "In this paper, we introduce Qwen3-Omni-30B-A3B, Qwen3-Omni-30B-A3B-Thinking, and Qwen3-Omni-Flash-Instruct.",
            "paragraph_group",
        ),
    ]

    result = trim_table_far_side_section_heading(
        clip,
        caption,
        "below",
        layout_blocks,
        [],
    )

    assert 718.0 <= result.y1 <= 720.0, result


def test_bare_figure_caption_prefers_above_when_next_caption_below() -> None:
    """裸 Figure caption 下方有下一张 caption、上方有对象时，应回到上方图。"""
    direction = correct_bare_figure_caption_direction(
        "below",
        fitz.Rect(275.1, 239.4, 320.1, 250.3),
        "Figure 22",
        fitz.Rect(0.0, 0.0, 595.3, 842.0),
        image_rects=[fitz.Rect(70.0, 130.0, 525.0, 230.0)],
        vector_rects=[],
        neighbor_caption_rects=[fitz.Rect(275.0, 520.0, 320.0, 531.0)],
        clip_height=400.0,
    )
    assert direction == "above"


def test_bare_figure_caption_keeps_below_without_above_object() -> None:
    direction = correct_bare_figure_caption_direction(
        "below",
        fitz.Rect(275.1, 239.4, 320.1, 250.3),
        "Figure 22",
        fitz.Rect(0.0, 0.0, 595.3, 842.0),
        image_rects=[],
        vector_rects=[],
        neighbor_caption_rects=[fitz.Rect(275.0, 520.0, 320.0, 531.0)],
        clip_height=400.0,
    )
    assert direction == "below"


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
        test_table_band_keeps_category_row_and_following_data_rows,
        test_table_band_keeps_strong_rows_across_group_spacing,
        test_table_band_stops_before_sentence_like_strong_row_after_gap,
        test_baseline_clip_stops_before_far_section_title_below_caption,
        test_baseline_clip_stops_after_far_body_above_caption,
        test_baseline_clip_preserves_near_table_cluster_before_far_body,
        test_baseline_clip_preserves_table_header_above_caption,
        test_baseline_clip_preserves_wide_numeric_table_blocks,
        test_baseline_clip_preserves_clustered_diagram_labels,
        test_baseline_clip_stops_at_wide_numeric_body_block,
        test_baseline_clip_stops_before_far_short_title_followed_by_body,
        test_baseline_clip_stops_after_isolated_far_title_above_caption,
        test_baseline_clip_ignores_other_column_title_above_caption,
        test_baseline_clip_keeps_original_when_limit_would_be_too_short,
        test_table_band_recognizes_compact_single_block_rows,
        test_looks_like_table_text_accepts_short_compact_table,
        test_restore_table_clip_width_recovers_over_narrow_structured_table,
        test_table_final_text_bounds_recovers_connected_header_band,
        test_table_final_text_bounds_stops_before_body_paragraph,
        test_table_final_text_bounds_recovers_header_but_not_leading_body_line,
        test_table_direction_tie_break_prefers_nearest_structured_table,
        test_table_direction_ignores_adjacent_table_reference_line,
        test_table_direction_keeps_short_numeric_cells_as_evidence,
        test_table_direction_prefers_nearest_structured_rows_over_chart_labels,
        test_table_appendix_reference_is_not_caption_context,
        test_colon_caption_is_not_reference_even_inside_long_text_block,
        test_limit_clip_by_neighbor_captions_bounds_same_page_items,
        test_table_direction_uses_text_structure_above_caption,
        test_table_direction_uses_text_structure_below_caption,
        test_layout_trims_section_title_from_short_figure,
        test_table_far_side_trims_trailing_section_heading,
        test_table_far_side_keeps_misclassified_last_data_row,
        test_table_far_side_keeps_header_followed_by_table_rows,
        test_table_far_side_trims_numbered_section_heading_above_table,
        test_table_far_side_keeps_same_row_data_cell_at_far_edge,
        test_table_far_side_keeps_layout_only_same_row_data_cell,
        test_table_final_text_bounds_recovers_qwen_table2_tail_row,
        test_table_final_text_bounds_recovers_tail_row_from_layout_blocks,
        test_table_final_text_bounds_trims_far_side_blank_before_table,
        test_table_final_text_bounds_trims_body_tail_before_header,
        test_table_final_text_bounds_trims_numeric_body_tail_before_header,
        test_table_final_text_bounds_keeps_wrapped_tail_cell_line,
        test_figure_noise_trim_ignores_sentence_tail_as_content_evidence,
        test_figure_post_autocrop_trims_narrow_lowercase_sentence_tail,
        test_figure_title_recovery_ignores_lowercase_sentence_tail,
        test_table_far_side_trims_single_number_section_heading,
        test_bare_figure_caption_prefers_above_when_next_caption_below,
        test_bare_figure_caption_keeps_below_without_above_object,
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
