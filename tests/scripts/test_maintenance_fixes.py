#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中低优先级健壮性与一致性修复回归测试。"""

import os
import sys
import tempfile
import importlib.util
import json
import importlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "skills" / "pdf-markdown-summary" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import fitz

from core import extract_pdf_assets, process_pdf, summarize_pdf
from lib import idents
from lib.caption_detection import score_caption_candidate
from lib.extract_figures import FIGURE_LINE_RE as EXTRACT_FIGURE_LINE_RE, extract_figures
from lib.extract_helpers import collect_draw_items
from lib.extract_tables import TABLE_LINE_RE as EXTRACT_TABLE_LINE_RE
from lib.figure_contexts import build_figure_contexts
from lib.idents import stable_debug_number
from lib.models import AttachmentRecord, CaptionCandidate, GatheredParagraph, GatheredText
from lib.pdf_backend import managed_pdf_document, open_pdf
from lib.refine import (
    detect_far_side_text_evidence,
    expand_clip_to_rendered_horizontal_rule,
    refine_clip_by_objects,
    trim_far_side_text_post_autocrop,
)
from lib.extraction_logger import configure_logging


def _make_pdf(path: Path) -> None:
    with fitz.open() as doc:
        doc.new_page(width=300, height=300)
        doc.save(path)


def test_managed_pdf_document_closes_on_exception() -> None:
    captured = {}

    @managed_pdf_document
    def fail_after_open(pdf_path, *, _doc=None):
        captured["raw"] = _doc.raw
        raise RuntimeError("expected")

    with tempfile.TemporaryDirectory() as td:
        pdf_path = Path(td) / "paper.pdf"
        _make_pdf(pdf_path)
        try:
            fail_after_open(str(pdf_path))
        except RuntimeError:
            pass
        else:
            raise AssertionError("应传播被包装函数的异常")

    assert captured["raw"].is_closed


def test_caption_without_objects_gets_no_position_score() -> None:
    candidate = CaptionCandidate(
        rect=fitz.Rect(10, 10, 100, 20),
        text="Figure 1",
        number="1",
        kind="figure",
        page=0,
        block_idx=0,
        line_idx=0,
        spans=[],
        block={"lines": [{"spans": [{"text": "Figure 1"}]}]},
    )
    assert score_caption_candidate(candidate, [], []) == 18.0


def test_extract_figures_skips_reference_without_smart_index() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pdf_path = root / "reference.pdf"
        out_dir = root / "images"
        with fitz.open() as doc:
            page = doc.new_page(width=500, height=700)
            text = "\n".join([
                "Figure 1 is discussed in this long body paragraph.",
                "This paragraph continues with enough explanatory text to be treated as body content.",
                "It deliberately spans several lines inside one PDF text block for the regression test.",
                "There is no real figure caption or nearby figure object on this page.",
                "The extraction loop must apply is_caption_reference even when smart indexing is disabled.",
                "Otherwise this body reference can become a false screenshot anchor.",
                "The final line keeps the block comfortably above the long-block threshold.",
            ])
            page.insert_textbox(fitz.Rect(40, 60, 460, 300), text, fontsize=10)
            doc.save(pdf_path)

        records = extract_figures(
            str(pdf_path),
            str(out_dir),
            smart_caption_detection=False,
            adaptive_line_height=False,
            global_anchor="above",
            refine_safe=False,
        )
        assert records == []


def test_process_pdf_reuses_markdown_extraction() -> None:
    calls = {"markdown": 0, "summary": 0}
    summary_args = []

    def markdown_main(argv):
        calls["markdown"] += 1
        out_md = Path(argv[argv.index("--out") + 1])
        asset_dir = out_md.parent / argv[argv.index("--asset-dir") + 1]
        text_dir = out_md.parent / "text"
        asset_dir.mkdir(parents=True, exist_ok=True)
        text_dir.mkdir(parents=True, exist_ok=True)
        (asset_dir / "index.json").write_text('{"items": []}', encoding="utf-8")
        (text_dir / "paper.txt").write_text("text", encoding="utf-8")
        return 0

    def summary_main(argv):
        calls["summary"] += 1
        summary_args.extend(argv)
        return 0

    original_loader = process_pdf._load_sibling_main
    process_pdf._load_sibling_main = lambda filename, module_name: (
        markdown_main if filename == "pdf_to_markdown.py" else summary_main
    )
    try:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pdf_path = root / "paper.pdf"
            out_md = root / "out" / "paper.md"
            _make_pdf(pdf_path)
            assert process_pdf.main(["--pdf", str(pdf_path), "--out", str(out_md)]) == 0
    finally:
        process_pdf._load_sibling_main = original_loader

    assert calls == {"markdown": 1, "summary": 1}
    assert "--reuse-existing" in summary_args


def test_summarize_reuse_requires_existing_assets() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pdf_path = root / "paper.pdf"
        out_dir = root / "images"
        text_path = root / "text" / "paper.txt"
        _make_pdf(pdf_path)
        assert summarize_pdf.main([
            "--pdf", str(pdf_path),
            "--out-dir", str(out_dir),
            "--text-path", str(text_path),
            "--reuse-existing",
        ]) == 1


def test_summarize_reuse_does_not_extract_again() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pdf_path = root / "paper.pdf"
        out_dir = root / "images"
        text_path = root / "text" / "paper.txt"
        _make_pdf(pdf_path)
        out_dir.mkdir()
        text_path.parent.mkdir()
        (out_dir / "index.json").write_text('{"items": []}', encoding="utf-8")
        text_path.write_text("prepared text", encoding="utf-8")

        original_main = extract_pdf_assets.main
        extract_pdf_assets.main = lambda argv: (_ for _ in ()).throw(
            AssertionError("复用模式不应再次执行资产提取")
        )
        try:
            assert summarize_pdf.main([
                "--pdf", str(pdf_path),
                "--out-dir", str(out_dir),
                "--text-path", str(text_path),
                "--reuse-existing",
            ]) == 0
        finally:
            extract_pdf_assets.main = original_main


def test_shared_patterns_and_stable_debug_number() -> None:
    assert EXTRACT_FIGURE_LINE_RE is idents.FIGURE_LINE_RE
    assert EXTRACT_TABLE_LINE_RE is idents.TABLE_LINE_RE
    assert stable_debug_number("SIV") == stable_debug_number("SIV")
    assert stable_debug_number("12") == 12


def test_collect_draw_items_uses_item_geometry_fallback() -> None:
    class Page:
        number = 0

        @staticmethod
        def get_drawings():
            return [{"rect": None, "items": [("re", fitz.Rect(20, 30, 120, 80), 1)]}]

    items = collect_draw_items(Page())
    assert len(items) == 1
    assert items[0].rect == fitz.Rect(20, 30, 120, 80)


def test_figure_contexts_find_supplementary_mentions() -> None:
    gathered = GatheredText(
        version="1.0",
        is_dual_column=False,
        headers_removed=[],
        footers_removed=[],
        paragraphs=[
            GatheredParagraph(
                page=1,
                text="Supplementary Figure 1 and Supplementary Table 2 provide details.",
                bbox=(0, 0, 100, 20),
                is_heading=False,
            )
        ],
    )
    records = [
        AttachmentRecord("figure", "S1", 2, "caption", "figure.png"),
        AttachmentRecord("table", "S2", 3, "caption", "table.png"),
    ]
    contexts = build_figure_contexts("unused.pdf", records, gathered_text=gathered)
    assert [len(ctx.all_mentions) for ctx in contexts] == [1, 1]


def test_far_side_text_detection_ignores_short_figure_internal_title() -> None:
    clip = fitz.Rect(141, 57, 473, 245)
    figure_title = (fitz.Rect(148, 71, 450, 81), 10.0, "Scaled Dot-Product Attention Multi-Head Attention")

    has_evidence, _ = detect_far_side_text_evidence(
        clip,
        [figure_title],
        "above",
        edge_zone=40.0,
        min_width_ratio=0.30,
    )
    trimmed, was_trimmed = trim_far_side_text_post_autocrop(
        clip,
        [figure_title],
        "above",
        typical_line_h=12.0,
        scan_lines=3,
    )

    assert not has_evidence
    assert not was_trimmed
    assert trimmed == clip


def test_object_refinement_preserves_near_edge_when_many_small_objects_would_be_cut() -> None:
    clip = fitz.Rect(26.0, 90.7, 586.0, 306.3)
    caption = fitz.Rect(108.0, 312.3, 504.2, 355.1)
    large_component = fitz.Rect(282.9, 156.0, 434.9, 245.8)
    small_label_band = [
        fitz.Rect(120.0, 240.0, 132.0, 302.0),
        fitz.Rect(150.0, 239.0, 162.0, 301.0),
        fitz.Rect(180.0, 241.0, 192.0, 300.0),
        fitz.Rect(210.0, 242.0, 222.0, 302.1),
        fitz.Rect(270.0, 244.0, 282.0, 299.5),
        fitz.Rect(330.0, 243.0, 342.0, 301.5),
        fitz.Rect(390.0, 241.5, 402.0, 300.5),
        fitz.Rect(450.0, 240.5, 462.0, 302.0),
        fitz.Rect(492.0, 242.0, 504.0, 301.0),
    ]

    refined = refine_clip_by_objects(
        clip,
        caption,
        "above",
        image_rects=[],
        vector_rects=[large_component] + small_label_band,
        object_pad=8.0,
        min_area_ratio=0.012,
        merge_gap=6.0,
        near_edge_only=True,
        use_axis_union=True,
        use_horizontal_union=False,
    )

    assert abs(refined.y1 - clip.y1) < 0.01


def test_object_refinement_preserves_near_edge_when_vertical_text_labels_would_be_cut() -> None:
    clip = fitz.Rect(26.0, 76.3, 586.0, 596.3)
    caption = fitz.Rect(108.0, 602.3, 504.0, 634.2)
    upper_component = fitz.Rect(122.0, 226.0, 484.0, 331.0)
    lower_component = fitz.Rect(150.0, 444.0, 470.0, 549.4)
    label_words = [
        "The", "Law", "will", "never", "be", "perfect", ",", "but", "its",
        "application", "should", "be", "just", "-", "this", "is", "what",
        "we", "are", "missing", ",", "in", "my", "opinion", ".", "<EOS>", "<pad>",
    ]
    text_labels = [
        (fitz.Rect(120.0 + idx * 14.0, 545.0, 132.0 + idx * 14.0, 560.0 + (idx % 5) * 7.0), 9.3, word)
        for idx, word in enumerate(label_words)
    ]
    text_labels[9] = (fitz.Rect(246.0, 545.0, 258.0, 590.0), 9.3, "application")
    text_labels[19] = (fitz.Rect(386.0, 545.0, 398.0, 577.0), 9.3, "missing")

    refined = refine_clip_by_objects(
        clip,
        caption,
        "above",
        image_rects=[],
        vector_rects=[upper_component, lower_component],
        object_pad=8.0,
        min_area_ratio=0.012,
        merge_gap=6.0,
        near_edge_only=True,
        use_axis_union=True,
        use_horizontal_union=False,
        text_lines=text_labels,
    )

    assert abs(refined.y1 - clip.y1) < 0.01


def test_table_clip_expands_to_rendered_horizontal_rule_between_caption_and_header() -> None:
    with tempfile.TemporaryDirectory() as td:
        pdf_path = Path(td) / "table-rule.pdf"
        with fitz.open() as doc:
            page = doc.new_page(width=300, height=220)
            page.insert_textbox(
                fitz.Rect(40, 35, 260, 52),
                "Table 1: Caption",
                fontsize=10,
            )
            page.draw_line(fitz.Point(60, 56), fitz.Point(240, 56), color=(0, 0, 0), width=1.0)
            page.insert_textbox(fitz.Rect(75, 60, 230, 82), "Header A     Header B", fontsize=10)
            doc.save(pdf_path)

        with open_pdf(pdf_path) as doc:
            page = doc[0]
            caption = fitz.Rect(40, 35, 260, 52)
            clip = fitz.Rect(30, 60, 270, 130)
            expanded = expand_clip_to_rendered_horizontal_rule(
                clip,
                page,
                caption,
                "below",
                scale=4.0,
            )

    assert expanded.y0 < 56.0
    assert expanded.y1 == clip.y1


def test_estimate_far_side_text_coverage_detects_far_paragraphs() -> None:
    from lib.acceptance import estimate_far_side_text_coverage

    clip = fitz.Rect(0, 100, 400, 500)
    text_lines = [
        (fitz.Rect(20, 110, 380, 125), 10.0, "This is a long far-side paragraph line one"),
        (fitz.Rect(20, 130, 380, 145), 10.0, "This is a long far-side paragraph line two"),
    ]
    cov = estimate_far_side_text_coverage(clip, text_lines, "above")
    assert cov > 0.10


def test_evaluate_refinement_acceptance_checks_ink_and_coverage() -> None:
    from lib.acceptance import evaluate_refinement_acceptance
    from lib.models import AcceptanceThresholds

    thresholds = AcceptanceThresholds(
        height_ratio=0.6,
        area_ratio=0.55,
        object_coverage=0.85,
        ink_density=0.90,
    )
    base_clip = fitz.Rect(0, 0, 200, 400)
    final_clip = fitz.Rect(0, 0, 200, 200)
    accepted, hard_reject, reason = evaluate_refinement_acceptance(
        final_clip,
        base_clip,
        thresholds,
        final_metrics=(40000.0, 0.05, 0.01),
        base_metrics=(80000.0, 0.40, 0.20),
        page_width=600.0,
    )
    assert not accepted
    assert not hard_reject
    assert reason


def test_determine_direction_prefers_moderate_local_over_global() -> None:
    from lib.direction import determine_direction

    caption = fitz.Rect(100, 400, 300, 420)
    page = fitz.Rect(0, 0, 600, 800)
    direction = determine_direction(
        caption,
        page,
        "1",
        global_anchor="below",
        local_evidence=("above", 0.55),
    )
    assert direction == "above"


def test_table_no_refine_preserves_baseline_clip() -> None:
    with tempfile.TemporaryDirectory() as td:
        pdf_path = Path(td) / "table-no-refine.pdf"
        with fitz.open() as doc:
            page = doc.new_page(width=400, height=500)
            page.insert_textbox(
                fitz.Rect(40, 420, 360, 440),
                "Table 1: Example table caption",
                fontsize=10,
            )
            page.draw_rect(fitz.Rect(60, 300, 340, 410), color=(0, 0, 0), width=1.0)
            page.insert_textbox(fitz.Rect(80, 310, 150, 330), "A", fontsize=10)
            page.insert_textbox(fitz.Rect(200, 310, 270, 330), "B", fontsize=10)
            doc.save(pdf_path)

        from lib.extract_tables import extract_tables

        refined_dir = Path(td) / "refined"
        baseline_dir = Path(td) / "baseline"
        refined = extract_tables(
            str(pdf_path),
            str(refined_dir),
            table_clip_height=180.0,
            autocrop=True,
            text_trim=True,
            smart_caption_detection=False,
            no_refine_tables=[],
        )
        baseline = extract_tables(
            str(pdf_path),
            str(baseline_dir),
            table_clip_height=180.0,
            autocrop=True,
            text_trim=True,
            smart_caption_detection=False,
            no_refine_tables=["1"],
        )
        assert len(refined) == 1 and len(baseline) == 1
        refined_pix = fitz.Pixmap(str(refined[0].out_path))
        baseline_pix = fitz.Pixmap(str(baseline[0].out_path))
        assert baseline_pix.height >= refined_pix.height
        assert baseline_pix.width >= refined_pix.width * 0.95


def test_figure_fallback_skips_short_phase_a_and_writes_structured_event() -> None:
    figure_module = importlib.import_module("lib.extract_figures")

    with tempfile.TemporaryDirectory() as td:
        pdf_path = Path(td) / "fallback-figure.pdf"
        out_dir = Path(td) / "out"
        log_path = out_dir / "run.log.jsonl"

        with fitz.open() as doc:
            page = doc.new_page(width=420, height=520)
            page.insert_textbox(
                fitz.Rect(40, 40, 380, 180),
                "Abstract\n" + "This is long abstract text that should not be used as a fallback clip. " * 4,
                fontsize=10,
            )
            page.draw_rect(fitz.Rect(90, 270, 330, 360), color=(0, 0, 0), width=1.0)
            page.insert_textbox(fitz.Rect(40, 430, 380, 455), "Figure 1: Sparse radar style figure.", fontsize=10)
            doc.save(pdf_path)

        old_evaluate = figure_module.evaluate_refinement_acceptance
        old_trim = figure_module.trim_clip_head_by_text_v2
        try:
            configure_logging(level="INFO", log_jsonl=str(log_path))

            def force_reject(*args, **kwargs):
                return False, False, "forced fallback"

            def force_phase_a_trim(clip, *args, **kwargs):
                return fitz.Rect(clip.x0, max(clip.y0, 250.0), clip.x1, clip.y1)

            figure_module.evaluate_refinement_acceptance = force_reject
            figure_module.trim_clip_head_by_text_v2 = force_phase_a_trim

            records = extract_figures(
                str(pdf_path),
                str(out_dir),
                dpi=72,
                clip_height=430.0,
                autocrop=False,
                text_trim=True,
                smart_caption_detection=False,
                debug_visual=True,
            )
        finally:
            figure_module.evaluate_refinement_acceptance = old_evaluate
            figure_module.trim_clip_head_by_text_v2 = old_trim

        assert len(records) == 1
        events = [
            json.loads(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert any(evt["event"] == "refine_fallback" for evt in events)
        selected_events = [
            evt
            for evt in events
            if evt["event"] == "refine_fallback_selected"
        ]
        assert len(selected_events) == 1
        assert selected_events[0]["stage"] == "baseline"

        legend_path = out_dir / "debug" / "Figure_1_p1_stages_legend.txt"
        legend = legend_path.read_text(encoding="utf-8")
        assert "phase_d:" in legend


def test_analyze_debug_batch_reads_phase_d_and_structured_fallback_logs() -> None:
    analyzer_path = PROJECT_ROOT / "tests" / "scripts" / "analyze_debug_batch.py"
    spec = importlib.util.spec_from_file_location("analyze_debug_batch_for_test", analyzer_path)
    assert spec is not None and spec.loader is not None
    analyzer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = analyzer
    spec.loader.exec_module(analyzer)

    with tempfile.TemporaryDirectory() as td:
        pdf_dir = Path(td) / "paper"
        debug_dir = pdf_dir / "images" / "debug"
        assets_dir = pdf_dir / "assets"
        debug_dir.mkdir(parents=True)
        assets_dir.mkdir(parents=True)

        legend_path = debug_dir / "Figure_1_p1_stages_legend.txt"
        legend_path.write_text(
            """=== Figure 1 Debug Legend (Page 1) ===

Caption: 10.0,400.0 -> 300.0,420.0 (290.0×20.0pt)

baseline:
  Position: 10.0,0.0 -> 300.0,400.0
  Size: 290.0×400.0pt (22.38 sq.in)
  Color: RGB(0, 102, 255)
  Description: baseline

phase_d:
  Position: 10.0,250.0 -> 300.0,400.0
  Size: 290.0×150.0pt (8.39 sq.in)
  Color: RGB(255, 0, 0)
  Description: phase d

final:
  Position: 10.0,0.0 -> 300.0,400.0
  Size: 290.0×400.0pt (22.38 sq.in)
  Color: RGB(255, 0, 0)
  Description: final
""",
            encoding="utf-8",
        )
        (assets_dir / "run.log.jsonl").write_text(
            json.dumps(
                {
                    "event": "refine_fallback",
                    "kind": "figure",
                    "id": "1",
                    "page": 1,
                    "message": "",
                    "details": {"reason": "ink below mass/density threshold"},
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        parsed = analyzer.parse_legend(legend_path)
        assert parsed is not None
        assert "phase_d_shrink>25%" in parsed.notes
        assert "fallback_to_baseline" in parsed.notes

        logs = analyzer.scan_logs(pdf_dir)
        assert logs and "refine_fallback" in logs[0]
        assert "ink below mass/density threshold" in logs[0]


def main() -> int:
    tests = [
        test_managed_pdf_document_closes_on_exception,
        test_caption_without_objects_gets_no_position_score,
        test_extract_figures_skips_reference_without_smart_index,
        test_process_pdf_reuses_markdown_extraction,
        test_summarize_reuse_requires_existing_assets,
        test_summarize_reuse_does_not_extract_again,
        test_shared_patterns_and_stable_debug_number,
        test_collect_draw_items_uses_item_geometry_fallback,
        test_figure_contexts_find_supplementary_mentions,
        test_far_side_text_detection_ignores_short_figure_internal_title,
        test_object_refinement_preserves_near_edge_when_many_small_objects_would_be_cut,
        test_object_refinement_preserves_near_edge_when_vertical_text_labels_would_be_cut,
        test_table_clip_expands_to_rendered_horizontal_rule_between_caption_and_header,
        test_estimate_far_side_text_coverage_detects_far_paragraphs,
        test_evaluate_refinement_acceptance_checks_ink_and_coverage,
        test_determine_direction_prefers_moderate_local_over_global,
        test_table_no_refine_preserves_baseline_clip,
        test_figure_fallback_skips_short_phase_a_and_writes_structured_event,
        test_analyze_debug_batch_reads_phase_d_and_structured_fallback_logs,
    ]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as exc:
            print(f"FAIL {test.__name__}: {exc}")
            failed += 1
    print(f"\n测试结果: {passed} 通过, {failed} 失败")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
