#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中低优先级健壮性与一致性修复回归测试。"""

import os
import sys
import tempfile
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
from lib.pdf_backend import managed_pdf_document


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
