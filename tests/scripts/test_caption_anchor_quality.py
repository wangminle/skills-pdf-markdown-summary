#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Caption 锚点与截图质量回归测试。

覆盖两类已暴露问题：
1) build_caption_index 必须给候选项打分，否则 get_best_for_page 无法过滤正文引用。
2) 正文污染检测应能识别明显的整段正文区域，用于阻止误截结果落盘。
"""

import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "skills", "pdf-markdown-summary", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import fitz

from lib.caption_detection import build_caption_index
from lib.extract_figures import FIGURE_LINE_RE
from lib.refine import detect_text_pollution, limit_clip_by_neighbor_captions


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


def main() -> int:
    tests = [
        test_caption_index_scores_candidates,
        test_caption_index_respects_min_score_for_cross_page_lookup,
        test_detect_text_pollution_flags_dense_body_text,
        test_limit_clip_by_neighbor_captions_bounds_same_page_items,
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
