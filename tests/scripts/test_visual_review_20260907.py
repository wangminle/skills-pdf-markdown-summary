#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""20260907 visual 复核报告中已确认缺陷的回归测试。"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path
import importlib

import fitz
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "skills", "pdf-markdown-summary", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from lib.acceptance import evaluate_refinement_acceptance
from lib.caption_detection import (
    is_caption_reference,
    is_likely_caption_context,
    is_likely_reference_context,
    score_caption_candidate,
)
from lib.clip_limit import limit_clip_by_neighbor_captions
from lib.direction import score_local_direction
from lib.figure_post import expand_clip_to_nearby_figure_objects
from lib.models import AcceptanceThresholds, CaptionCandidate
from lib.refine import (
    expand_clip_to_nearby_table_header,
    refine_clip_to_table_band,
    trim_clip_head_by_text_v2,
)
from lib.table_refine import trim_table_clip_far_side_body


def _candidate(text: str, *, kind: str = "table", number: str = "6", y0: float = 700.0) -> CaptionCandidate:
    rect = fitz.Rect(70.0, y0, 525.0, y0 + 12.0)
    return CaptionCandidate(
        rect=rect,
        text=text,
        number=number,
        kind=kind,
        page=0,
        block_idx=0,
        line_idx=0,
        spans=[{"text": text, "flags": 0, "size": 10.0}],
        block={"lines": [{"spans": [{"text": text}]}]},
        score=0.0,
    )


def test_body_citation_table_n_also_is_reference() -> None:
    text = (
        "Table 6. Also, we evaluate different modes of DeepSeek-V4-Flash and "
        "DeepSeek-V4-Pro and"
    )
    assert is_likely_reference_context(text)
    assert not is_likely_caption_context(text)
    assert is_caption_reference(text, {"lines": []}, re.compile(r"^Table\s+\d+"))


def test_pipe_caption_with_based_on_is_real_caption() -> None:
    text = (
        "Figure 9 | Results on autonomous cyber offense suite. These benchmarks "
        "are based on “capture-the-flag” (CTF) challenges."
    )
    assert is_likely_caption_context(text)
    assert not is_likely_reference_context(text)
    assert not is_caption_reference(text, {"lines": []}, re.compile(r"^Figure\s+\d+"))

    candidate = _candidate(text, kind="figure", number="9", y0=280.0)
    chart = fitz.Rect(80.0, 70.0, 520.0, 270.0)
    score = score_caption_candidate(candidate, [chart], [])
    assert score >= 25.0, score


def test_stacked_table_caption_pairs_with_content_below() -> None:
    """DeepSeek Table 3/10/11：题注上方是前一张表，真实表格在题注下方。"""
    page_rect = fitz.Rect(0.0, 0.0, 595.0, 842.0)
    current_caption = fitz.Rect(70.5, 513.9, 452.2, 526.0)
    previous_caption = fitz.Rect(70.5, 233.5, 296.9, 245.5)
    text_lines = []
    for row in range(8):
        y0 = 262.0 + row * 28.0
        for col in range(4):
            x0 = 95.0 + col * 100.0
            text_lines.append((fitz.Rect(x0, y0, x0 + 70.0, y0 + 10.0), 8.0, f"{row}.{col}"))
    text_lines.append((fitz.Rect(86.5, 548.0, 180.2, 558.9), 9.0, "Injected Instruction"))
    text_lines.append((
        fitz.Rect(86.5, 571.7, 409.9, 582.6),
        9.0,
        "Reasoning Effort 0.9 1.2 1.5 1.8",
    ))
    # Previous table's last rows sit closer to the current caption than to Table 2,
    # but still belong to Table 2 because that caption attaches downward.
    text_lines.append((fitz.Rect(95.5, 413.8, 150.9, 424.7), 8.0, "Think Max"))
    text_lines.append((fitz.Rect(178.3, 413.9, 277.5, 424.8), 8.0, "Push reasoning 1.0 2.0"))
    for row in range(4):
        y0 = 585.0 + row * 14.0
        for col in range(3):
            x0 = 90.0 + col * 140.0
            text_lines.append((fitz.Rect(x0, y0, x0 + 80.0, y0 + 10.0), 8.0, f"cell{row}{col}"))

    direction, confidence = score_local_direction(
        current_caption,
        page_rect,
        [],
        [],
        clip_height=520.0,
        is_table=True,
        text_lines=text_lines,
        neighbor_caption_rects=[previous_caption],
    )
    assert direction == "below", (direction, confidence)


def test_stacked_table_caption_below_keeps_current_table() -> None:
    """Gemini 风格：题注在表下方时，两题注之间的表仍属于当前题注。"""
    page_rect = fitz.Rect(0.0, 0.0, 595.0, 842.0)
    previous_caption = fitz.Rect(70.0, 200.0, 480.0, 212.0)
    current_caption = fitz.Rect(70.0, 430.0, 480.0, 442.0)
    text_lines = []
    for row in range(6):
        y0 = 110.0 + row * 14.0
        for col in range(4):
            x0 = 90.0 + col * 100.0
            text_lines.append((fitz.Rect(x0, y0, x0 + 70.0, y0 + 10.0), 8.0, f"p{row}.{col}"))
    for row in range(8):
        y0 = 230.0 + row * 22.0
        for col in range(4):
            x0 = 90.0 + col * 100.0
            text_lines.append((fitz.Rect(x0, y0, x0 + 70.0, y0 + 10.0), 8.0, f"c{row}.{col}"))

    direction, confidence = score_local_direction(
        current_caption,
        page_rect,
        [],
        [],
        clip_height=520.0,
        is_table=True,
        text_lines=text_lines,
        neighbor_caption_rects=[previous_caption],
    )
    assert direction == "above", (direction, confidence)


def test_stacked_tables_ignore_section_heading_above_previous_caption() -> None:
    """DeepSeek Table 10/11：上一题注上方的章节标题不能阻止它向下附着。"""
    page_rect = fitz.Rect(0.0, 0.0, 595.0, 842.0)
    previous_caption = fitz.Rect(70.0, 261.3, 520.0, 273.4)
    current_caption = fitz.Rect(70.0, 395.5, 520.0, 407.6)
    text_lines = [
        (fitz.Rect(70.0, 230.9, 220.0, 243.8), 11.0, "B. Evaluation Details"),
    ]
    for col, label in enumerate(["#", "Agent Win", "RAG Win", "Tie"]):
        x0 = 90.0 + col * 90.0
        text_lines.append((fitz.Rect(x0, 289.4, x0 + 70.0, 299.4), 8.0, label))
    for row in range(4):
        y0 = 307.0 + row * 16.0
        for col in range(4):
            x0 = 90.0 + col * 90.0
            text_lines.append((fitz.Rect(x0, y0, x0 + 40.0, y0 + 10.0), 8.0, f"{row}{col}"))
    text_lines.append((
        fitz.Rect(70.0, 410.3, 412.0, 421.2),
        9.0,
        "DeepSeek-V4-Pro. Most of the tool calls are parallel for Agentic Search.",
    ))
    for col, label in enumerate(["Version", "Tool Calls", "Prefill", "Output"]):
        x0 = 90.0 + col * 90.0
        text_lines.append((fitz.Rect(x0, 437.2, x0 + 70.0, 447.1), 8.0, label))
    for col, value in enumerate(["V4", "16.2", "13649", "1526"]):
        x0 = 90.0 + col * 90.0
        text_lines.append((fitz.Rect(x0, 454.7, x0 + 70.0, 464.6), 8.0, value))

    direction, confidence = score_local_direction(
        current_caption,
        page_rect,
        [],
        [],
        clip_height=520.0,
        is_table=True,
        text_lines=text_lines,
        neighbor_caption_rects=[previous_caption],
    )
    assert direction == "below", (direction, confidence)


def test_side_by_side_captions_split_x_range() -> None:
    clip = fitz.Rect(26.0, 240.6, 569.3, 380.7)
    left_caption = fitz.Rect(70.9, 386.7, 290.4, 398.7)
    right_caption = fitz.Rect(306.7, 386.7, 526.2, 398.8)

    left = limit_clip_by_neighbor_captions(
        clip, left_caption, "above", [right_caption], gap=6.0,
    )
    right = limit_clip_by_neighbor_captions(
        clip, right_caption, "above", [left_caption], gap=6.0,
    )
    assert left.x1 <= 300.0, left
    assert right.x0 >= 296.0, right
    assert left.x1 <= right.x0


def test_text_trim_keeps_far_side_plot_objects() -> None:
    clip = fitz.Rect(26.0, 260.4, 586.0, 646.3)
    caption = fitz.Rect(72.0, 652.3, 540.0, 663.1)
    page_rect = fitz.Rect(0.0, 0.0, 612.0, 792.0)
    text_lines = [
        (
            fitz.Rect(72.0, 297.0, 399.0, 309.0),
            10.0,
            "Fable 5, at roughly half of the latter’s cost. Figure 13 summarizes the comparison.",
        ),
        (fitz.Rect(139.0, 469.4, 229.4, 480.2), 9.0, "(a) Kimi Code Bench 2.0"),
        (fitz.Rect(396.6, 469.2, 458.4, 480.0), 9.0, "(b) BrowseComp"),
        (fitz.Rect(150.2, 636.8, 218.2, 647.6), 9.0, "(c) GDPval-AA v2"),
        (fitz.Rect(396.3, 636.8, 458.8, 647.6), 9.0, "(d) AA-Briefcase"),
    ]
    object_rects = [
        fitz.Rect(80.0, 270.0, 290.0, 455.0),
        fitz.Rect(320.0, 270.0, 530.0, 455.0),
        fitz.Rect(80.0, 490.0, 290.0, 630.0),
        fitz.Rect(320.0, 490.0, 530.0, 630.0),
    ]

    trimmed = trim_clip_head_by_text_v2(
        clip,
        page_rect,
        caption,
        "above",
        text_lines,
        typical_line_h=11.0,
        object_rects=object_rects,
    )
    assert trimmed.y0 <= 275.0, trimmed


def test_text_trim_drops_section_heading_above_figure_image() -> None:
    """FunAudio Figure 3：4.1 小节标题应在流程图图片之前被裁掉。"""
    clip = fitz.Rect(26.0, 0.0, 586.0, 254.8)
    caption = fitz.Rect(191.8, 257.8, 420.2, 267.7)
    page_rect = fitz.Rect(0.0, 0.0, 612.0, 792.0)
    text_lines = [
        (fitz.Rect(108.0, 74.3, 252.6, 84.3), 10.0, "3.2 Supervised Fine-tuning Data"),
        (fitz.Rect(107.7, 96.0, 505.4, 106.0), 10.0, "The supervised fine-tuning (SFT) data consist of approximately millions of hours of data."),
        (fitz.Rect(108.0, 148.9, 170.2, 160.9), 12.0, "4 Training"),
        (fitz.Rect(108.0, 176.1, 120.5, 186.1), 10.0, "4.1"),
        (fitz.Rect(130.4, 176.1, 260.1, 186.1), 10.0, "Pre-training of Audio Encoder"),
        (fitz.Rect(191.8, 257.8, 420.2, 267.7), 9.0, "Figure 3: The pre-training pipeline for the audio encoder."),
    ]
    object_rects = [fitz.Rect(127.8, 206.8, 484.2, 250.7)]
    trimmed = trim_clip_head_by_text_v2(
        clip, page_rect, caption, "above", text_lines, object_rects=object_rects,
    )
    assert trimmed.y0 >= 186.0, trimmed
    assert trimmed.y0 <= 210.0, trimmed


def test_text_trim_drops_list_items_above_figure_image() -> None:
    """GPT-5 Figure 22/29：题注上方的项目列表不应进入最终图。"""
    clip = fitz.Rect(26.0, 0.0, 569.3, 403.4)
    caption = fitz.Rect(275.1, 406.4, 320.1, 417.3)
    page_rect = fitz.Rect(0.0, 0.0, 595.3, 842.0)
    text_lines = [
        (fitz.Rect(87.3, 221.9, 524.4, 233.0), 10.0, "• Right: Strong goals lead to higher deception rates. When gpt-5-thinking is given a"),
        (fitz.Rect(98.1, 235.5, 524.3, 246.4), 10.0, "strong goal, e.g., “Your only goal is X. This is your sole measure of success.” it takes"),
        (fitz.Rect(70.5, 298.8, 524.3, 309.7), 10.0, "Additionally, Apollo found that gpt-5-thinking often reasons about what a typical eval"),
        (fitz.Rect(70.9, 325.9, 155.6, 336.8), 10.0, "of such behaviors."),
        (fitz.Rect(275.1, 406.4, 320.1, 417.3), 10.0, "Figure 29"),
    ]
    object_rects = [fitz.Rect(70.0, 347.5, 523.5, 395.7)]
    trimmed = trim_clip_head_by_text_v2(
        clip, page_rect, caption, "above", text_lines, object_rects=object_rects,
    )
    assert trimmed.y0 >= 330.0, trimmed
    assert trimmed.y0 <= 350.0, trimmed


def test_unpolluted_low_ratio_figure_is_kept() -> None:
    thresholds = AcceptanceThresholds(
        height_ratio=0.45,
        area_ratio=0.40,
        object_coverage=0.70,
        ink_density=0.70,
    )
    base = fitz.Rect(26.0, 101.9, 586.0, 621.9)
    refined = fitz.Rect(26.0, 425.4, 586.0, 621.9)
    accepted, hard_reject, reason = evaluate_refinement_acceptance(
        refined,
        base,
        thresholds,
        final_metrics=(refined.width * refined.height, 0.9, 0.8),
        base_metrics=(base.width * base.height, 0.4, 0.3),
        page_width=612.0,
        allow_low_ratio_keep=True,
    )
    assert not hard_reject
    assert accepted, reason


def test_figure_extraction_does_not_fallback_to_abstract() -> None:
    figure_module = importlib.import_module("lib.extract_figures")

    with tempfile.TemporaryDirectory() as td:
        pdf_path = Path(td) / "radar.pdf"
        out_dir = Path(td) / "out"
        with fitz.open() as doc:
            page = doc.new_page(width=612, height=792)
            page.insert_textbox(
                fitz.Rect(70, 80, 540, 400),
                "Abstract. " + (
                    "This paper presents a long abstract paragraph that must not remain "
                    "in the exported figure crop after refinement. "
                ) * 8,
                fontsize=10,
            )
            page.draw_rect(fitz.Rect(160, 430, 450, 610), color=(0, 0, 0), width=1.5)
            page.insert_text((180, 630), "Figure 1: Performance comparison radar chart.", fontsize=10)
            doc.save(pdf_path)

        old_trim = figure_module.trim_clip_head_by_text_v2
        try:
            def keep_radar(clip, *args, **kwargs):
                return fitz.Rect(clip.x0, 425.4, clip.x1, min(clip.y1, 621.9))

            figure_module.trim_clip_head_by_text_v2 = keep_radar
            records = figure_module.extract_figures(
                str(pdf_path),
                str(out_dir),
                dpi=72,
                clip_height=650.0,
                autocrop=False,
                text_trim=True,
                smart_caption_detection=False,
            )
        finally:
            figure_module.trim_clip_head_by_text_v2 = old_trim

        assert len(records) == 1
        bbox = records[0].final_bbox
        assert bbox[1] >= 410.0, bbox
        assert bbox[3] <= 630.0, bbox


def test_long_table_band_covers_rows_beyond_short_baseline() -> None:
    caption = fitz.Rect(72.0, 83.0, 540.0, 94.0)
    search_clip = fitz.Rect(70.0, 135.0, 540.0, 700.0)
    text_lines = []
    for row in range(40):
        y0 = 140.0 + row * 13.5
        text_lines.append((fitz.Rect(77.5, y0, 150.0, y0 + 9.0), 8.0, f"Benchmark {row}"))
        for col in range(6):
            x0 = 200.0 + col * 50.0
            text_lines.append((fitz.Rect(x0, y0, x0 + 30.0, y0 + 9.0), 8.0, f"{row}.{col}"))
    text_lines.append((fitz.Rect(77.5, 338.0, 120.0, 347.0), 9.0, "Agentic"))
    text_lines.append((fitz.Rect(77.5, 574.0, 120.0, 583.0), 9.0, "Vision"))

    refined, changed = refine_clip_to_table_band(
        search_clip,
        caption,
        text_lines,
        "below",
        typical_line_h=10.0,
    )
    assert changed
    assert refined.y1 >= 670.0, refined


def test_table_header_recovers_when_footnote_overlaps_header() -> None:
    """K3 Table 3：合并题注与 Proprietary 表头重叠时，仍应把表头拉回。"""
    original = fitz.Rect(70.9, 126.0, 541.3, 416.6)
    limited = fitz.Rect(70.9, 126.0, 541.3, 416.6)
    caption = fitz.Rect(71.7, 63.3, 540.0, 120.0)
    text_lines = [
        (
            fitz.Rect(71.7, 63.3, 540.0, 74.1),
            9.0,
            'Table 3: Results on our in-house benchmarks. Bold denotes the best reported result per benchmark; "-" denotes scores not yet',
        ),
        (
            fitz.Rect(72.0, 73.2, 540.0, 84.0),
            9.0,
            "included in this report. Unless otherwise noted, models are evaluated at maximum reasoning effort (GPT-5.5 at xhigh); harness",
        ),
        (
            fitz.Rect(72.0, 83.0, 540.0, 94.0),
            9.0,
            "assignments are shown in the Harness column. a13 fallbacks and 1 refusal out of 80 tasks. b10 refusals out of 80 tasks. c3 refusals",
        ),
        (
            fitz.Rect(72.0, 93.0, 540.0, 104.0),
            9.0,
            "out of 80 tasks. dIncludes 2 tasks that Claude Fable 5 refused to answer. eIncludes 14 tasks that Claude Fable 5 refused to answer. f6",
        ),
        (
            fitz.Rect(72.0, 99.3, 369.1, 120.0),
            8.0,
            "refusals out of 95 tasks. g Reported metric is 1-hallucination rate; higher is better.",
        ),
        (fitz.Rect(355.9, 118.2, 401.0, 127.2), 8.0, "Proprietary"),
        (fitz.Rect(483.4, 118.2, 533.9, 127.2), 8.0, "Open Weight"),
        (fitz.Rect(75.6, 133.2, 120.4, 142.1), 8.0, "Benchmark"),
        (fitz.Rect(178.8, 133.2, 210.0, 142.1), 8.0, "Harness"),
        (fitz.Rect(234.2, 133.2, 267.3, 142.1), 8.0, "Kimi K3"),
        (fitz.Rect(278.9, 133.2, 329.8, 142.1), 8.0, "Claude Fable"),
        (fitz.Rect(77.5, 160.0, 140.0, 170.0), 8.0, "GPQA Diamond"),
        (fitz.Rect(200.1, 160.0, 215.8, 170.0), 8.0, "93.5"),
        (fitz.Rect(263.2, 160.0, 278.9, 170.0), 8.0, "92.6"),
        (fitz.Rect(325.9, 160.0, 341.6, 170.0), 8.0, "94.1"),
        (fitz.Rect(77.5, 180.0, 160.0, 190.0), 8.0, "Kimi Code Bench"),
        (fitz.Rect(200.1, 180.0, 215.8, 190.0), 8.0, "59.9"),
        (fitz.Rect(263.2, 180.0, 278.9, 190.0), 8.0, "76.9"),
        (fitz.Rect(325.9, 180.0, 341.6, 190.0), 8.0, "71.2"),
    ]
    recovered = expand_clip_to_nearby_table_header(
        original,
        limited,
        text_lines,
        caption,
        "below",
    )
    assert recovered.y0 <= 118.2, recovered
    assert recovered.y0 >= 110.0, recovered


def test_table_text_bounds_do_not_swallow_following_survey() -> None:
    """DeepSeek Table 8：表格后的调查正文不应被 final 文本扩边吃进。"""
    caption = fitz.Rect(70.5, 215.1, 526.2, 227.2)
    clip = fitz.Rect(65.8, 246.8, 529.5, 394.4)
    text_lines = [
        (fitz.Rect(110.3, 267.4, 136.0, 276.4), 8.0, "Model"),
        (fitz.Rect(161.7, 267.4, 200.1, 276.4), 8.0, "Haiku 4.5"),
        (fitz.Rect(96.5, 283.8, 149.7, 292.8), 8.0, "Pass Rate (%)"),
        (fitz.Rect(176.4, 283.8, 185.4, 292.8), 8.0, "13"),
        (
            fitz.Rect(87.8, 308.8, 524.4, 321.8),
            9.0,
            "In a survey asking DeepSeek developers and researchers (N= 85) — all with experience of",
        ),
        (
            fitz.Rect(70.9, 324.4, 524.4, 335.4),
            9.0,
            "using DeepSeek-V4-Pro for agentic coding in their daily work — whether DeepSeek-V4-Pro is",
        ),
    ]
    trimmed = trim_table_clip_far_side_body(clip, caption, text_lines, "below")
    assert trimmed.y1 <= 305.0, trimmed


def test_figure_object_expand_ignores_glyph_sized_vectors() -> None:
    """DeepSeek Figure 1：摘要文字的小矢量不应把精裁上边界重新扩回去。"""
    limited = fitz.Rect(65.8, 466.0, 529.9, 720.7)
    caption = fitz.Rect(70.9, 726.3, 525.8, 738.4)
    page = fitz.Rect(0.0, 0.0, 595.3, 841.9)
    glyph_vectors = [
        fitz.Rect(80.0, 433.8, 89.0, 444.7),
        fitz.Rect(92.0, 433.8, 101.0, 444.7),
        fitz.Rect(80.0, 447.1, 89.0, 459.2),
    ]
    chart = [fitz.Rect(70.0, 470.4, 523.5, 715.8)]
    expanded = expand_clip_to_nearby_figure_objects(
        limited, caption, "above", [], glyph_vectors + chart, page, max_expand=80.0,
    )
    assert expanded.y0 >= 460.0, expanded
