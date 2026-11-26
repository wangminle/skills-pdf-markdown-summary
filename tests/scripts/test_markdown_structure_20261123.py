# -*- coding: utf-8 -*-
"""Markdown 结构修复回归（2026-11-23）：标题层级、通栏顺序、行内样式、CLI、题注对账。

对应 CHK-066 / F-1 / F-2 / F-3 / F-6 与题注对账起点过窄问题。
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Tuple

import fitz
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "skills" / "pdf-markdown-summary" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from core.pdf_to_markdown import (
    _block_is_caption_for_asset,
    _paragraphs_to_document,
    _place_assets_in_document,
    main,
    parse_args,
)
from lib.assess import (
    ExpectedCaption,
    expected_captions_from_page_text,
    merge_expected_captions,
    render_inventory_gap,
)
from lib.markdown import MarkdownBlock, render_block, render_markdown
from lib.models import CaptionCandidate
from lib.text_extract import (
    classify_block_column,
    gather_structured_text,
    infer_heading_level,
    looks_like_structural_heading,
)


def _make_cross_column_pdf(path: Path) -> None:
    """构造双栏+通栏样例。

    同页两次 insert_text 会把同行左右栏并进同一 block；用 show_pdf_page
    分栏盖印，保持与 CHK-066 复现样例一致的分块结构。
    """
    base = fitz.open()
    page = base.new_page(width=600, height=800)
    page.insert_text(
        (60, 72),
        "Wide heading above both columns - designed to straddle the page center",
        fontsize=14,
    )

    left = fitz.open()
    left_page = left.new_page(width=600, height=800)
    right = fitz.open()
    right_page = right.new_page(width=600, height=800)
    for i, y in enumerate((150, 215, 285, 350), start=1):
        left_page.insert_text((45, y), f"Left column paragraph number {i}.", fontsize=11)
        right_page.insert_text((340, y), f"Right column paragraph number {i}.", fontsize=11)
    page.show_pdf_page(page.rect, left, 0)
    page.show_pdf_page(page.rect, right, 0)
    base.save(path)
    base.close()
    left.close()
    right.close()


def _make_numbered_heading_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # 用粗体 flags：insert_textbox + fontname 带 Bold
    y = 72
    for text, size in (
        ("3 Model Architecture", 12),
        ("Body under section three.", 10),
        ("3.2 Attention", 10),
        ("Body under subsection.", 10),
        ("3.2.1 Scaled Dot-Product Attention", 10),
        ("Body under subsubsection.", 10),
    ):
        page.insert_text((72, y), text, fontsize=size, fontname="Times-Bold" if text[0].isdigit() and "Body" not in text else "Times-Roman")
        y += 28 if text[0].isdigit() and "Body" not in text else 22
    doc.save(path)
    doc.close()


def _make_inline_style_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=420, height=320)
    # 同一段混排：常规 + 粗体 + 斜体
    page.insert_text((48, 72), "Normal ", fontsize=12, fontname="Times-Roman")
    page.insert_text((95, 72), "bold", fontsize=12, fontname="Times-Bold")
    page.insert_text((125, 72), " and ", fontsize=12, fontname="Times-Roman")
    page.insert_text((155, 72), "italic", fontsize=12, fontname="Times-Italic")
    page.insert_text((190, 72), " text.", fontsize=12, fontname="Times-Roman")
    doc.save(path)
    doc.close()


# ---------------------------------------------------------------------------
# 标题层级
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text,expected",
    [
        ("3 Model Architecture", 2),
        ("3.2 Attention", 3),
        ("3.2.1 Scaled Dot-Product Attention", 4),
        ("1. Introduction", 2),
        ("2.3. Experimental Setup", 3),
        ("2.3.4. 实验模型", 4),
        ("1 Introduction", 2),
        ("1. Introduction", 2),
        ("2.3. Foo", 3),
        ("2.3.1. Foo", 4),
        ("I. Introduction", 2),
        ("A. Appendix Detail", 3),
        ("Introduction", 2),
    ],
)
def test_infer_heading_level_from_numbering(text: str, expected: int) -> None:
    assert looks_like_structural_heading(text, is_bold=True, font_size=12.0)
    assert infer_heading_level(text, font_size=12.0, typical_font_size=10.0) == expected


def test_long_numbered_heading_is_not_rejected() -> None:
    text = "3 Reinforcement Learning for Optimized Trade Execution in Global Electronic Markets"
    assert len(text) >= 50
    assert looks_like_structural_heading(text, is_bold=True, font_size=14.35)
    assert infer_heading_level(text, font_size=14.35, typical_font_size=10.9) == 2


def test_numbered_heading_levels_in_markdown_document(tmp_path: Path) -> None:
    pdf_path = tmp_path / "headings.pdf"
    _make_numbered_heading_pdf(pdf_path)
    doc = _paragraphs_to_document(str(pdf_path), title="Headings")
    headings = [b for b in doc.blocks if b.type == "heading"]
    by_text = {b.text.replace("\n", " ").strip(): b.level for b in headings}
    assert by_text.get("3 Model Architecture") == 2
    assert by_text.get("3.2 Attention") == 3
    assert by_text.get("3.2.1 Scaled Dot-Product Attention") == 4
    md = render_markdown(doc)
    assert "## 3 Model Architecture" in md
    assert "### 3.2 Attention" in md
    assert "#### 3.2.1 Scaled Dot-Product Attention" in md


def test_long_chapter_headings_and_figure_labels_in_benchmark() -> None:
    benchmark = PROJECT_ROOT / "tests" / "basic-benchmark"
    kearns = gather_structured_text(str(next(benchmark.glob("Kearns*.pdf"))))
    levels = {" ".join(p.text.split()): p.heading_level for p in kearns.paragraphs if p.is_heading}

    assert levels["3 Reinforcement Learning for Optimized Trade Execution"] == 2
    assert levels["5 Machine Learning for Smart Order Routing in Dark Pools"] == 2
    assert looks_like_structural_heading(
        "3 Long Section on the Reliability of Experimental Results Across Several Trading Venues",
        is_bold=True, font_size=14.35,
    )
    assert not looks_like_structural_heading(
        "3 Participants were included after screening. The remaining data were processed separately.",
        is_bold=True, font_size=14.35,
    )

    attention = gather_structured_text(str(next(benchmark.glob("1706.03762*.pdf"))))
    headings = {" ".join(p.text.split()) for p in attention.paragraphs if p.is_heading}
    assert "Scaled Dot-Product Attention" not in headings
    assert "Multi-Head Attention" not in headings
    assert "3.2.1 Scaled Dot-Product Attention" in headings
    assert "3.2.2 Multi-Head Attention" in headings


def test_deepseek_contents_rows_remain_text_and_body_headings_survive() -> None:
    benchmark = PROJECT_ROOT / "tests" / "basic-benchmark"
    gathered = gather_structured_text(str(next(benchmark.glob("DeepSeek*.pdf"))))
    paragraphs = {" ".join(p.text.split()): p for p in gathered.paragraphs}

    for text in ("1 Introduction 4", "2 Architecture 7", "3 General Infrastructures 16",
                 "4 Pre-Training 20", "5 Post-Training 25",
                 "6 Conclusion, Limitations, and Future Directions 37"):
        assert not paragraphs[text].is_heading
    assert paragraphs["1. Introduction"].heading_level == 2
    assert paragraphs["2. Architecture"].heading_level == 2


def test_toc_promoted_heading_uses_explicit_numbering_depth(tmp_path: Path) -> None:
    path = tmp_path / "toc-numbered-heading.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=800)
        page.insert_text((65, 130), "3.2 Verification", fontname="Helvetica", fontsize=14)
        for index in range(5):
            page.insert_text(
                (65, 170 + 20 * index),
                "The samples in this study were gathered independently from each of the original sources.",
                fontname="Times-Roman", fontsize=11,
            )
        doc.set_toc([[1, "3.2 Verification", 1]])
        doc.save(path)

    gathered = gather_structured_text(str(path))
    heading = next(p for p in gathered.paragraphs if p.text == "3.2 Verification")

    assert heading.is_heading is True
    assert heading.heading_level == 3


def test_body_heading_ending_in_year_is_not_a_contents_entry(tmp_path: Path) -> None:
    path = tmp_path / "year-heading.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        for index in range(1, 4):
            page.insert_text(
                (65, 85 + index * 40), f"{index} Results from {2020 + index}",
                fontsize=14, fontname="Times-Bold",
            )
        pdf.save(path)

    paragraphs = gather_structured_text(str(path)).paragraphs

    assert [p.heading_level for p in paragraphs] == [2, 2, 2]


def test_markdown_renders_literal_paragraph_prefixes_and_preserves_emphasis() -> None:
    from markdown_it import MarkdownIt

    from lib.markdown import MarkdownBlock, render_block

    plain = "1.\n2) Numbered words\n> α(t)\n+ plus\n- minus\n* literal\n-"
    block = MarkdownBlock(
        type="paragraph", text=plain, rich_text=plain.replace("Numbered", "**Numbered**"),
        meta={"para_type": "list"},  # gather 的旧元数据可能把普通的 1. 标作列表
    )

    rendered = render_block(block)

    assert [token.type for token in MarkdownIt("commonmark").parse(rendered)] == [
        "paragraph_open", "inline", "paragraph_close",
    ]
    assert "".join(text for _style, text in _inline_runs(rendered)) == plain
    assert ("b", "Numbered") in _inline_runs(rendered)
    assert block.to_dict()["text"] == plain
    assert render_block(MarkdownBlock(type="list", text="1. Item")) == "1. Item"


def test_pdf_conversion_keeps_ambiguous_number_and_quote_as_text(tmp_path: Path) -> None:
    from markdown_it import MarkdownIt

    path = tmp_path / "literal-prefixes.pdf"
    output = tmp_path / "markdown" / "paper.md"
    lines = ["1. Reported in the source note.", "2. Another printed number.", "> x in the upper range."]
    with fitz.open() as pdf:
        page = pdf.new_page()
        for index, line in enumerate(lines):
            page.insert_text((65, 85 + index * 40), line, fontsize=11)
        pdf.save(path)

    assert main(["--pdf", str(path), "--out", str(output), "--images", "off", "--tables", "off"]) == 0
    tokens = MarkdownIt("commonmark").parse(output.read_text(encoding="utf-8"))

    assert not any(token.type in {"ordered_list_open", "blockquote_open"} for token in tokens)
    assert len([token for token in tokens if token.type == "paragraph_open"]) == len(lines)
    rendered = output.read_text(encoding="utf-8")
    assert all(line in [text for _style, text in _inline_runs(rendered)] for line in lines)


@pytest.mark.parametrize("separate_blocks", [False, True])
def test_pdf_conversion_preserves_tightly_aligned_numbered_list(tmp_path: Path, separate_blocks: bool) -> None:
    from markdown_it import MarkdownIt

    path = tmp_path / "ordered-list.pdf"
    output = tmp_path / "markdown" / "paper.md"
    with fitz.open() as pdf, fitz.open() as overlay:
        page = pdf.new_page()
        page.insert_text((85, 85), "1. Prepare the samples.", fontsize=11)
        if separate_blocks:
            overlay.new_page().insert_text((85, 101), "2. Record the response.", fontsize=11)
            page.show_pdf_page(page.rect, overlay, 0)
        else:
            page.insert_text((85, 101), "2. Record the response.", fontsize=11)
        pdf.save(path)

    assert main(["--pdf", str(path), "--out", str(output), "--images", "off", "--tables", "off"]) == 0
    tokens = MarkdownIt("commonmark").parse(output.read_text(encoding="utf-8"))
    assert [token.type for token in tokens].count("list_item_open") == 2


def test_toc_entries_with_trailing_page_numbers_are_not_headings(tmp_path: Path) -> None:
    pdf_path = tmp_path / "toc.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 48), "Contents", fontsize=14, fontname="Times-Bold")
        for index, title in enumerate(("Introduction", "Architecture", "Training", "Evaluation", "Conclusion")):
            page.insert_text(
                (72, 72 + index * 24), f"{index + 1} {title} . . . . {index + 4}",
                fontsize=10.9, fontname="Times-Bold",
            )
        page.insert_text((72, 300), "1 Introduction", fontsize=14, fontname="Times-Bold")
        doc.save(pdf_path)

    gathered = gather_structured_text(str(pdf_path))
    toc = [p for p in gathered.paragraphs if p.text.rsplit(" ", 1)[-1].isdigit()]
    assert toc
    assert all(not p.is_heading for p in toc)
    assert any(p.is_heading and p.text == "1 Introduction" for p in gathered.paragraphs)


def test_plain_paragraph_escapes_block_syntax_but_preserves_lists() -> None:
    rendered = render_block(MarkdownBlock(
        type="paragraph",
        text="1. Introduction\n> alpha\n+ plain\n- plain\n* plain\n-0.5 negative",
    ))
    assert rendered == "1\\. Introduction\n\\> alpha\n\\+ plain\n\\- plain\n\\* plain\n-0.5 negative"
    assert render_block(MarkdownBlock(
        type="list", text="- actual list item", meta={"para_type": "list"},
    )) == "- actual list item"


# ---------------------------------------------------------------------------
# 双栏通栏阅读顺序
# ---------------------------------------------------------------------------

def test_narrow_cross_midline_block_is_not_full_width() -> None:
    column, full_width = classify_block_column((290, 10, 322, 20), 600, is_dual_column=True)
    assert (column, full_width) == (1, False)


def test_full_width_heading_before_left_column(tmp_path: Path) -> None:
    pdf_path = tmp_path / "cross-column.pdf"
    _make_cross_column_pdf(pdf_path)
    gathered = gather_structured_text(str(pdf_path))
    texts = [p.text.replace("\n", " ").strip() for p in gathered.paragraphs]
    wide = "Wide heading above both columns - designed to straddle the page center"
    assert wide in texts
    assert texts.index(wide) < texts.index("Left column paragraph number 1.")
    assert texts.index("Left column paragraph number 1.") < texts.index("Right column paragraph number 1.")
    assert texts.index("Left column paragraph number 4.") < texts.index("Right column paragraph number 1.")


def test_centered_short_heading_above_columns_is_full_width(tmp_path: Path) -> None:
    path = tmp_path / "centered-short-heading.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page(width=600, height=800)
        title = "Study of Energy Use"
        title_width = fitz.get_text_length(title, fontname="Times-Bold", fontsize=18)
        page.insert_text(
            (300 - title_width / 2, 85), title,
            fontname="Times-Bold", fontsize=18,
        )
        for index in range(5):
            page.insert_text(
                (50, 160 + 34 * index),
                f"Left paragraph {index + 1}, describing the procedure.", fontsize=10,
            )
            page.insert_text(
                (326, 170 + 34 * index),
                f"Right paragraph {index + 1}, describing the results.", fontsize=10,
            )
        pdf.save(path)

    gathered = gather_structured_text(str(path))
    paragraphs = {p.text: p for p in gathered.paragraphs}
    order = list(paragraphs)

    assert gathered.num_columns == 2
    assert paragraphs[title].is_heading is True
    assert paragraphs[title].is_full_width is True
    assert paragraphs[title].column == -1
    assert order.index(title) < order.index("Left paragraph 1, describing the procedure.")
    assert order.index("Left paragraph 5, describing the procedure.") < order.index(
        "Right paragraph 1, describing the results."
    )


def test_two_column_page_splits_at_wide_and_centered_display_blocks(tmp_path: Path) -> None:
    path = tmp_path / "multi-band.pdf"
    with fitz.open() as pdf, fitz.open() as left, fitz.open() as right:
        page = pdf.new_page(width=600, height=800)
        wide = "A full width separator drawn across the middle of both text columns"
        page.insert_text((55, 80), wide + " (top)", fontsize=14)
        page.insert_text((55, 390), wide + " (middle)", fontsize=14)
        page.insert_text((280, 210), "x + y = z", fontsize=12)
        for source, name, x in ((left, "Left", 45), (right, "Right", 340)):
            column = source.new_page(width=600, height=800)
            for i, y in enumerate((130, 175, 240, 285, 450, 495, 550, 595)):
                column.insert_text((x, y), f"{name} column paragraph number {i}.", fontsize=11)
            page.show_pdf_page(page.rect, source, 0)
        pdf.save(path)

    gathered = gather_structured_text(str(path))
    paragraphs = {p.text: p for p in gathered.paragraphs}
    order = list(paragraphs)

    assert gathered.num_columns == 2
    assert paragraphs[wide + " (top)"].is_full_width
    assert paragraphs[wide + " (middle)"].is_full_width
    assert paragraphs["x + y = z"].is_full_width
    assert order.index(wide + " (top)") < order.index("Left column paragraph number 0.")
    assert order.index("Left column paragraph number 1.") < order.index("Right column paragraph number 0.")
    assert order.index("Right column paragraph number 1.") < order.index("x + y = z")
    assert order.index("x + y = z") < order.index("Left column paragraph number 2.")
    assert order.index("Right column paragraph number 3.") < order.index(wide + " (middle)")
    assert order.index(wide + " (middle)") < order.index("Left column paragraph number 4.")
    assert order.index("Left column paragraph number 7.") < order.index("Right column paragraph number 4.")


def test_cross_column_conversion_report_not_blind_ready(tmp_path: Path) -> None:
    """通栏顺序曾错时仍标 ready；修复后结构告警应消失且顺序正确，报告可为 ready。

    若仍检测出阅读顺序告警，则不得标 ready。
    """
    pdf_path = tmp_path / "cross-column.pdf"
    out_md = tmp_path / "markdown" / "paper.md"
    report = tmp_path / "txt" / "conversion_report.json"
    _make_cross_column_pdf(pdf_path)
    exit_code = main([
        "--pdf", str(pdf_path),
        "--out", str(out_md),
        "--report-json", str(report),
        "--images", "off",
        "--tables", "off",
    ])
    assert exit_code == 0
    md = out_md.read_text(encoding="utf-8")
    wide_pos = md.find("Wide heading above both columns")
    left_pos = md.find("Left column paragraph number 1.")
    assert 0 <= wide_pos < left_pos
    import json
    payload = json.loads(report.read_text(encoding="utf-8"))
    warnings = payload.get("structure_warnings") or []
    if any("reading_order" in w for w in warnings):
        assert payload["status"] == "review"
    else:
        assert payload["status"] in ("ready", "review")


# ---------------------------------------------------------------------------
# 行内粗斜体
# ---------------------------------------------------------------------------

def _inline_runs(markdown: str) -> List[Tuple[str, str]]:
    """用 CommonMark 实际解析，返回 [(样式, 原文片段)]；样式为 ''/'b'/'i'/'bi'。

    相同样式的相邻片段合并；片段内空白原样保留，便于核对渲染后的用字。
    """
    from markdown_it import MarkdownIt

    bold = italic = False
    runs: List[Tuple[str, str]] = []
    for token in MarkdownIt("commonmark").parse(markdown):
        first_in_block = True  # 标题与正文等不同块不合并
        for child in token.children or []:
            if child.type == "strong_open":
                bold = True
                continue
            if child.type == "em_open":
                italic = True
                continue
            if child.type == "strong_close":
                bold = False
                continue
            if child.type == "em_close":
                italic = False
                continue
            if child.type in ("text", "text_special", "code_inline"):
                text = child.content
            elif child.type == "softbreak":
                text = "\n"
            else:
                continue
            style = ("b" if bold else "") + ("i" if italic else "")
            if not first_in_block and runs and runs[-1][0] == style:
                runs[-1] = (style, runs[-1][1] + text)
            else:
                runs.append((style, text))
            first_in_block = False
    return [(s, t) for s, t in runs if t]


def _squash(runs: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """折叠片段内空白并丢弃纯空白片段，得到便于与预期比较的结构。"""
    return [(s, " ".join(t.split())) for s, t in runs if t.split()]


def test_inline_bold_italic_preserved_in_gathered_text(tmp_path: Path) -> None:
    """行内样式只进 rich_text 与 Markdown 渲染；text 保持纯文本供题注匹配等使用。"""
    pdf_path = tmp_path / "inline.pdf"
    _make_inline_style_pdf(pdf_path)
    gathered = gather_structured_text(str(pdf_path))
    plain = " ".join(p.text for p in gathered.paragraphs)
    rich = "\n".join(p.rich_text for p in gathered.paragraphs)
    assert "*" not in plain
    assert "Normal bold and italic text." in " ".join(plain.split())
    assert _squash(_inline_runs(rich)) == [
        ("", "Normal"), ("b", "bold"), ("", "and"), ("i", "italic"), ("", "text."),
    ]

    md = render_markdown(_paragraphs_to_document(str(pdf_path), title="Inline"))
    assert "**bold**" in md and "*italic*" in md
    assert _squash(_inline_runs(md)) == [
        ("", "Inline"), ("", "Normal"), ("b", "bold"), ("", "and"), ("i", "italic"), ("", "text."),
    ]


# ---------------------------------------------------------------------------
# CLI --tables structure 占位说明
# ---------------------------------------------------------------------------

def test_tables_structure_help_mentions_placeholder() -> None:
    buf = io.StringIO()
    with pytest.raises(SystemExit) as exc:
        with redirect_stdout(buf):
            parse_args(["--help"])
    assert exc.value.code == 0
    help_text = buf.getvalue()
    assert "--tables" in help_text
    assert "structure" in help_text
    assert "placeholder" in help_text.lower() or "占位" in help_text or "screenshot" in help_text.lower()


# ---------------------------------------------------------------------------
# 题注对账：不依赖识别器候选索引
# ---------------------------------------------------------------------------

def test_expected_captions_from_page_text_finds_missed_caption(tmp_path: Path) -> None:
    pdf_path = tmp_path / "fig.pdf"
    doc = fitz.open()
    page = doc.new_page(width=420, height=320)
    page.insert_text((48, 72), "Figure 7: Independent text-layer caption.", fontsize=10)
    page.insert_text((48, 200), "Some body citing Figure 7 in prose.", fontsize=10)
    doc.save(pdf_path)
    doc.close()

    from lib.pdf_backend import open_pdf

    with open_pdf(str(pdf_path)) as pdf:
        text_expected = expected_captions_from_page_text(pdf)
    keys = {(item.kind, item.ident, item.page) for item in text_expected}
    assert ("figure", "7", 1) in keys

    # 空索引 + 文本层合并后仍应保留
    merged = merge_expected_captions([], text_expected)
    assert any(item.kind == "figure" and item.ident == "7" for item in merged)


def test_merge_expected_captions_keeps_index_and_text_union() -> None:
    index_item = ExpectedCaption(
        kind="figure",
        ident="1",
        page=1,
        text="Figure 1: From index",
        score=80.0,
        candidate=CaptionCandidate(
            rect=(0, 0, 1, 1),
            text="Figure 1: From index",
            number="1",
            kind="figure",
            page=0,
            block_idx=0,
            line_idx=0,
            spans=[],
            block={},
            score=80.0,
        ),
    )
    text_item = ExpectedCaption(
        kind="figure",
        ident="2",
        page=2,
        text="Figure 2: Only in text layer",
        score=50.0,
        candidate=CaptionCandidate(
            rect=(0, 0, 1, 1),
            text="Figure 2: Only in text layer",
            number="2",
            kind="figure",
            page=1,
            block_idx=0,
            line_idx=0,
            spans=[],
            block={},
            score=50.0,
        ),
    )
    merged = merge_expected_captions([index_item], [text_item])
    keys = {(i.kind, i.ident, i.page) for i in merged}
    assert ("figure", "1", 1) in keys
    assert ("figure", "2", 2) in keys


# ---------------------------------------------------------------------------
# CHK-068 P1-1：文本层题注期望必须能走完缺口补裁（BUG-164）
# ---------------------------------------------------------------------------

def test_text_layer_caption_survives_inventory_gap_render(tmp_path: Path) -> None:
    """rect 必须是 Rect 对象，而不是 get_text("dict") 的四元组。"""
    from lib.pdf_backend import open_pdf

    pdf_path = tmp_path / "gap.pdf"
    doc = fitz.open()
    page = doc.new_page(width=420, height=320)
    page.insert_text((48, 72), "Figure 7: Caption the recognizer index never saw.", fontsize=10)
    doc.save(pdf_path)
    doc.close()

    with open_pdf(str(pdf_path)) as pdf:
        expected = [c for c in expected_captions_from_page_text(pdf) if c.kind == "figure"]
    assert [c.ident for c in expected] == ["7"]
    assert isinstance(expected[0].candidate.rect, fitz.Rect)

    with fitz.open(pdf_path) as render_doc:
        record = render_inventory_gap(render_doc[0], expected[0], str(tmp_path / "images"), dpi=72)
    assert record is not None
    assert record.ident == "7" and record.review_required
    x0, y0, x1, y1 = record.final_bbox
    assert x0 < x1 and y0 < y1 and y0 >= 72
    assert os.path.isfile(record.out_path)


def test_text_layer_caption_scan_skips_superscript_footnotes() -> None:
    """表体行的上角标脚注编号不得与标签词融合成假题注（与识别器同口径）。"""
    from types import SimpleNamespace

    line = {
        "bbox": [48, 100, 300, 112],
        "spans": [
            {"text": "Table", "flags": 0},
            {"text": "2", "flags": 1},  # PyMuPDF flags bit0 = 上角标
            {"text": ": summary of ablation runs", "flags": 0},
        ],
    }
    page = SimpleNamespace(
        get_text=lambda *_args, **_kwargs: {
            "blocks": [{"type": 0, "bbox": [48, 100, 300, 112], "lines": [line]}]
        }
    )
    assert expected_captions_from_page_text([page]) == []


# ---------------------------------------------------------------------------
# CHK-068 P1-2：结构判定只认 PDF 粗体标志位（BUG-163）
# ---------------------------------------------------------------------------

def _single_line_block(text: str, font: str, flags: int) -> Dict[str, Any]:
    span = {"text": text, "font": font, "size": 9.0, "flags": flags, "color": 0}
    return {
        "page": 1, "page_index": 0, "bbox": (72, 100, 300, 112),
        "text": text, "rich_text": text,
        "lines": [{"bbox": [72, 100, 300, 112], "spans": [span]}],
        "page_width": 612.0, "page_height": 792.0,
    }


@pytest.fixture
def blank_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page(width=612, height=792)
    doc.save(path)
    doc.close()
    return path


@pytest.mark.parametrize(
    "font,flags,expect_bold",
    [
        # 图内标签常见：字体名带 Bold，但 PDF 没有置粗体标志位
        ("DejaVuSans-Bold", 0, False),
        ("NimbusSanL-Bold", 0, False),
        ("DejaVuSans", 16, True),
        ("DejaVuSans-Bold", 16, True),
    ],
)
def test_layout_model_bold_follows_flag_not_font_name(
    blank_pdf: Path, monkeypatch, font: str, flags: int, expect_bold: bool
) -> None:
    """版式模型字重只看标志位：图内粗体标签不得被判成 title_h3 并改变裁剪依据。"""
    import lib.text_extract as te

    block = _single_line_block("Training loss curve", font, flags)
    monkeypatch.setattr(te, "iter_native_text_blocks", lambda _doc: [block])
    layout = te.extract_text_with_format(str(blank_pdf))
    unit = layout.text_units[0][0]
    assert (unit.font_weight == "bold") is expect_bold
    assert unit.text_type.startswith("title") is expect_bold


@pytest.mark.parametrize(
    "flags,expect_heading",
    [(0, False), (16, True)],
)
def test_heading_detection_ignores_font_name_heuristics(
    blank_pdf: Path, monkeypatch, flags: int, expect_heading: bool
) -> None:
    """Markdown 标题分类同样只看标志位，图内的 DejaVuSans-Bold 文字不升为标题。"""
    import lib.text_extract as te

    block = _single_line_block("3.2 Attention Mechanism", "DejaVuSans-Bold", flags)
    monkeypatch.setattr(te, "iter_native_text_blocks", lambda _doc: [block])
    paragraphs = te.gather_structured_text(str(blank_pdf)).paragraphs
    assert len(paragraphs) == 1
    assert paragraphs[0].is_heading is expect_heading
    assert paragraphs[0].rich_text == ""


# ---------------------------------------------------------------------------
# CHK-068 P1-3：行内样式的序列化不得产生畸形标记，也不得改变正文用字（BUG-163）
# ---------------------------------------------------------------------------

_BOLD, _ITALIC, _BOLD_ITALIC = {"flags": 16}, {"flags": 2}, {"flags": 18}
_REGULAR: Dict[str, Any] = {}


@pytest.mark.parametrize(
    "pieces,expected_runs",
    [
        # 相邻同样式 span 先合并；span 自带的首尾空白留在标记外
        (
            [("stack of", _REGULAR), (" ", _ITALIC), ("N", _ITALIC), (" = 6 identical layers", _REGULAR)],
            [("", "stack of"), ("i", "N"), ("", "= 6 identical layers")],
        ),
        (
            [("components of", _REGULAR), (" q", _ITALIC), (" and", _REGULAR), (" k", _ITALIC),
             (" are independent", _REGULAR)],
            [("", "components of"), ("i", "q"), ("", "and"), ("i", "k"), ("", "are independent")],
        ),
        (
            [("a ", _REGULAR), (" bold ", _BOLD), ("tail", _REGULAR)],
            [("", "a"), ("b", "bold"), ("", "tail")],
        ),
        (
            [("  ", _BOLD), ("x", _REGULAR)],
            [("", "x")],
        ),
        # 不同样式的 run 紧邻：交界两侧都是文字字符时星号可以唯一解析
        (
            [("q", _ITALIC), ("W", _BOLD)],
            [("i", "q"), ("b", "W")],
        ),
        (
            [("x", _BOLD_ITALIC), ("y", _ITALIC)],
            [("bi", "x"), ("i", "y")],
        ),
        (
            [("输入", _BOLD), ("α", _ITALIC), ("输出", _REGULAR)],
            [("b", "输入"), ("i", "α"), ("", "输出")],
        ),
        # 交界处是符号（作者名后的等贡献星号）：星号会连成 "***"，后一个 run 退回纯文本
        (
            [("Ashish Vaswani", _BOLD), ("∗", _ITALIC)],
            [("b", "Ashish Vaswani"), ("", "∗")],
        ),
        # run 以符号结尾且后面紧跟文字：闭标记无法闭合，退回纯文本；
        # 其后的 run 不再与标记紧邻，样式照常保留
        (
            [("Encoder:", _BOLD), ("N", _ITALIC), (" = 6", _REGULAR)],
            [("", "Encoder:"), ("i", "N"), ("", "= 6")],
        ),
        (
            [("x", _REGULAR), ("(y)", _ITALIC), ("z", _REGULAR)],
            [("", "x(y)z")],
        ),
        # 紧贴标记的字面下划线：不转义就会从词内下划线变成强调分隔符（benchmark 实测）
        (
            [("step", _ITALIC), ("_num", _REGULAR)],
            [("i", "step"), ("", "_num")],
        ),
        (
            [("x_1", _REGULAR), ("a", _BOLD)],
            [("", "x_1"), ("b", "a")],
        ),
        # 控制字符、组合符号不是空白也不是标点：符号开头的标记在其后无法闭合
        ([("\x01", _REGULAR), (".", _ITALIC)], [("", "\x01.")]),
        # emoji 是符号类别，其后以文字开头的标记不受影响
        (
            [("🤗 ", _REGULAR), ("Query:", _BOLD)],
            [("", "🤗"), ("b", "Query:")],
        ),
        # 数学符号开头且前邻文字：各渲染器结论不一，退回纯文本
        (
            [("x", _REGULAR), ("→y", _ITALIC), ("z", _REGULAR)],
            [("", "x→yz")],
        ),
        # 样式 run 内的字面星号；常规文本里的星号/下划线与标记相邻
        ([("p < 0.05*", _BOLD)], [("b", "p < 0.05*")]),
        ([("sig*", _REGULAR), ("A", _BOLD)], [("", "sig*"), ("b", "A")]),
        ([("A", _BOLD), ("*1", _REGULAR)], [("b", "A"), ("", "*1")]),
        ([("cost_", _REGULAR), ("A", _BOLD)], [("", "cost_"), ("b", "A")]),
        # 无法无歧义表达时退回纯文本：只丢样式，不丢字
        (
            [("A", _BOLD), ("(x", _ITALIC), ("y", _REGULAR)],
            [("b", "A"), ("", "(xy")],
        ),
    ],
)
def test_inline_style_renders_exactly_the_source_text(pieces, expected_runs) -> None:
    from lib.text_extract import format_spans_as_markdown

    spans = [{"text": text, **flags} for text, flags in pieces]
    rendered = format_spans_as_markdown(spans)
    runs = _inline_runs(rendered)
    assert _squash(runs) == expected_runs
    # 渲染后的用字与原文一字不差（段首缩进会被块级解析吃掉，故两侧都先 strip）
    plain = "".join(s["text"] for s in spans)
    assert "".join(t for _s, t in runs).strip() == plain.strip()


def test_strip_inline_markdown_restores_plain_text() -> None:
    """保真自检用的逆变换：去掉标记后与原文逐字一致。"""
    from lib.text_extract import format_spans_as_markdown, strip_inline_markdown

    for pieces in (
        [("Ashish Vaswani", _BOLD), ("∗", _ITALIC)],
        [("p < 0.05*", _BOLD)],
        [("sig*", _REGULAR), ("A", _BOLD)],
        [("final_bbox", _REGULAR), (" and ", _ITALIC), ("x_1", _REGULAR)],
    ):
        plain = "".join(t for t, _f in pieces)
        rich = format_spans_as_markdown([{"text": t, **f} for t, f in pieces])
        assert strip_inline_markdown(rich) == plain


def _make_bold_caption_pdf(path: Path) -> None:
    """题注以粗体「Figure 1:」开头，是论文里最常见的加粗题注形态。"""
    doc = fitz.open()
    page = doc.new_page(width=420, height=320)
    page.insert_text((48, 72), "Figure 1:", fontsize=10, fontname="Times-Bold")
    page.insert_text((95, 72), " Bold lead-in caption text.", fontsize=10, fontname="Times-Roman")
    page.insert_text((48, 200), "Body paragraph that mentions Figure 1 in prose.", fontsize=10)
    doc.save(path)
    doc.close()


def test_bold_caption_keeps_plain_text_and_stays_matchable(tmp_path: Path) -> None:
    """题注匹配一律用纯文本；加粗的「Figure 1:」不得因此匹配失败。"""
    pdf_path = tmp_path / "bold-caption.pdf"
    _make_bold_caption_pdf(pdf_path)
    paragraphs = gather_structured_text(str(pdf_path)).paragraphs
    caption = next(p for p in paragraphs if p.text.startswith("Figure 1:"))
    assert "*" not in caption.text
    assert caption.rich_text.startswith("**Figure 1:**")

    doc = _paragraphs_to_document(str(pdf_path), title="T")
    block = next(b for b in doc.blocks if b.text.startswith("Figure 1:"))
    assert "*" not in block.text
    assert _block_is_caption_for_asset(block, {"type": "figure", "id": "1", "page": 1})
    assert "**Figure 1:** Bold lead-in caption text." in render_markdown(doc)


def test_bold_caption_figure_is_inserted_inline_not_appendix(tmp_path: Path) -> None:
    pdf_path = tmp_path / "bold-caption.pdf"
    _make_bold_caption_pdf(pdf_path)
    doc = _paragraphs_to_document(str(pdf_path), title="T")
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "Figure_1.png").write_bytes(b"png")
    item = {
        "type": "figure", "id": "1", "page": 1, "file": "Figure_1.png",
        "caption": "Figure 1: Bold lead-in caption text.",
        "final_bbox": [60, 80, 360, 190],
    }
    placement = _place_assets_in_document(
        doc,
        {"items": [item], "index_json": str(tmp_path / "images" / "index.json")},
        str(tmp_path / "markdown" / "paper.md"),
    )
    assert [i["id"] for i in placement["inline"]] == ["1"]
    assert placement["appendix"] == []
    md = render_markdown(doc)
    blocks = [b for b in md.split("\n\n") if b.strip()]
    caption_idx = next(i for i, b in enumerate(blocks) if b.startswith("**Figure 1:**"))
    assert blocks[caption_idx + 1].startswith("![Figure 1:")
    assert "提取资产" not in md


def test_rich_text_is_ignored_when_it_diverges_from_plain_text(
    tmp_path: Path, monkeypatch
) -> None:
    """富文本与纯文本对不上时宁可不加样式，正文一字不差。"""
    from types import SimpleNamespace

    import lib.text_extract as te
    from lib.models import GatheredParagraph

    pdf_path = tmp_path / "guard.pdf"
    _make_inline_style_pdf(pdf_path)
    fake = SimpleNamespace(
        is_dual_column=False, typical_font_size=10.0, structure_warnings=[],
        paragraphs=[
            GatheredParagraph(page=1, text="alpha beta gamma", bbox=(0, 0, 100, 10),
                              is_heading=False, rich_text="**alpha** beta GAMMA"),
            GatheredParagraph(page=1, text="delta epsilon", bbox=(0, 20, 100, 30),
                              is_heading=False, rich_text="**delta** epsilon"),
        ],
    )
    monkeypatch.setattr(te, "gather_structured_text", lambda _path, *_a, **_k: fake)
    validation = SimpleNamespace(text_layer_ratio=1.0, has_text_layer=True, warnings=[])
    md = render_markdown(_paragraphs_to_document(str(pdf_path), title="T", validation=validation))
    assert "alpha beta gamma" in md
    assert "GAMMA" not in md and "**alpha**" not in md
    assert "**delta** epsilon" in md


def test_toc_extraction_and_conservative_heading_fallback(tmp_path: Path) -> None:
    """WP-1.2 / BUG-171：提取书签目录并保守提升同页唯一粗体/大字号标题，忽略小字号图内标签。"""
    import json

    pdf_path = tmp_path / "toc-fallback.pdf"
    out_json = tmp_path / "gathered.json"
    with fitz.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 90), "Acknowledgements", fontsize=12.5, fontname="Times-Bold")
        page.insert_text((72, 130), "Normal prose about model evaluation metrics.", fontsize=10.0)
        page.insert_text((180, 300), "Figure label inside chart", fontsize=8.0)
        doc.set_toc([
            [1, "Acknowledgements", 1],
            [2, "Figure label inside chart", 1],
        ])
        doc.save(pdf_path)

    gathered = gather_structured_text(str(pdf_path), out_json=str(out_json))
    assert len(gathered.toc) == 2
    assert gathered.toc[0] == {"level": 1, "title": "Acknowledgements", "page": 1}

    by_text = {" ".join(p.text.split()): p for p in gathered.paragraphs}
    assert by_text["Acknowledgements"].is_heading is True
    assert by_text["Acknowledgements"].heading_level == 2
    assert by_text["Figure label inside chart"].is_heading is False

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["toc"] == gathered.toc


def test_caption_and_list_tight_classification(tmp_path: Path) -> None:
    """WP-3.3 / WP-4.3：正文陈述句与数值常量不被误标成 caption/list，真实项目符号渲染为规范列表。"""
    pdf_path = tmp_path / "caption-list.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 80), "Figures show steady improvements across benchmarks.", fontsize=10.5)
        page.insert_text((72, 120), "Figure 1: Overview of the architecture.", fontsize=10.5)
        page.insert_text((72, 160), "-0.69", fontsize=10.5)
        page.insert_text((72, 200), "1.000", fontsize=10.5)
        page.insert_text((72, 240), "2.0 Flash", fontsize=10.5)
        page.insert_text((72, 280), "- First real bullet item", fontsize=10.5)
        page.insert_text((72, 296), "- Second real bullet item", fontsize=10.5)
        doc.save(pdf_path)

    gathered = gather_structured_text(str(pdf_path))
    by_text = {" ".join(p.text.split()): p for p in gathered.paragraphs}
    assert by_text["Figures show steady improvements across benchmarks."].para_type == "paragraph"
    assert by_text["Figure 1: Overview of the architecture."].para_type == "caption"
    assert by_text["-0.69"].para_type == "paragraph"
    assert by_text["1.000"].para_type == "paragraph"
    assert by_text["2.0 Flash"].para_type == "paragraph"
    bullet_paras = [p for p in gathered.paragraphs if "real bullet item" in p.text]
    assert bullet_paras and all(p.para_type == "list" for p in bullet_paras)

    md = render_markdown(_paragraphs_to_document(str(pdf_path), title="Caption List"))
    assert "- First real bullet item" in md
    assert "- Second real bullet item" in md
    assert "\\- First real bullet item" not in md

    # 同时验证 Unicode 圆点经由 native_blocks 直入时也能识别为 list 并规范化为 "- "
    from lib.text_extract import _looks_like_list_item
    assert _looks_like_list_item("• Unicode bullet item") is True


def test_markdown_list_and_fenced_equation_rendering() -> None:
    """WP-4.3 / BUG-165：Unicode 列表规范化渲染，语义勾号/实心圆不误改，代码块围栏内的行首符号不被误转义。"""
    from lib.text_extract import _looks_like_list_item

    assert render_block(MarkdownBlock(type="list", text="• Alpha\n▪ Beta")) == "- Alpha\n- Beta"
    assert render_block(MarkdownBlock(type="list", text="✓ Passed\n● Active")) == "✓ Passed\n● Active"
    assert _looks_like_list_item("✓ Passed") is False
    assert _looks_like_list_item("● Active") is False
    fenced = "```text\n1. Keep equation line\n- x\n```"
    assert render_block(MarkdownBlock(type="paragraph", text=fenced)) == fenced


def test_styled_unicode_bullets_render_as_real_lists_in_benchmark() -> None:
    """WP-3.3/4.3：圆点自身的行内样式不得阻止列表规范化，后续强调仍保留。"""
    from markdown_it import MarkdownIt

    styled = MarkdownBlock(
        type="list", text="• Alpha item", rich_text="*•* **Alpha item**",
    )
    assert render_block(styled) == "- **Alpha item**"
    assert render_block(MarkdownBlock(
        type="list", text="• Bold whole item", rich_text="**• Bold whole item**",
    )) == "- **Bold whole item**"
    assert render_block(MarkdownBlock(
        type="list", text="•Bold word", rich_text="•**Bold word**",
    )) == "- **Bold word**"

    benchmark = PROJECT_ROOT / "tests" / "basic-benchmark"
    pdf = next(benchmark.glob("Kearns*.pdf"))
    markdown = render_markdown(_paragraphs_to_document(str(pdf), title="Kearns"))
    tokens = MarkdownIt("commonmark").parse(markdown)

    assert "*•*" not in markdown
    assert "- **Optimized Trade Execution via Reinforcement Learning [14].**" in markdown
    assert sum(token.type == "list_item_open" for token in tokens) >= 3


def test_literal_hash_and_html_like_text_survive_commonmark() -> None:
    """BUG-203：正文的 # 与 <EOS>/<pad> 不得变成标题或 HTML。"""
    from markdown_it import MarkdownIt

    from lib.markdown import _escape_inline_literals

    assert _escape_inline_literals(
        "**Bold**", has_markup=True, plain_text=" Bold ",
    ) == "**Bold**"

    source = "# Langs\n<EOS>\n<pad>\n7,168\n=\nRL*F\n\\\"false\\\""
    rendered = render_block(MarkdownBlock(type="paragraph", text=source))
    tokens = MarkdownIt("commonmark").parse(rendered)
    assert not any(token.type == "heading_open" for token in tokens)
    assert not any(token.type == "html_block" for token in tokens)
    assert not any(token.type == "em_open" for token in tokens for child in token.children or [])
    roundtrip = "".join(
        child.content for token in tokens for child in token.children or []
        if child.type in ("text", "text_special")
    )
    assert "RL*F" in roundtrip
    assert "\\\"false\\\"" in roundtrip
    assert "=" in roundtrip
    assert any(
        child.type == "text" and "<EOS>" in child.content
        for token in tokens for child in token.children or []
    )

    benchmark = PROJECT_ROOT / "tests" / "basic-benchmark"
    qwen = render_markdown(_paragraphs_to_document(
        str(next(benchmark.glob("2509*.pdf"))), title="Qwen",
    ))
    attention = render_markdown(_paragraphs_to_document(
        str(next(benchmark.glob("1706*.pdf"))), title="Attention",
    ))
    qwen_tokens = MarkdownIt("commonmark").parse(qwen)
    attention_tokens = MarkdownIt("commonmark").parse(attention)
    assert not any(
        token.type == "inline" and token.content in ("", "Langs")
        and index > 0 and qwen_tokens[index - 1].type == "heading_open"
        for index, token in enumerate(qwen_tokens)
    )
    assert not any(
        token.type == "html_block" and token.content.strip() in ("<EOS>", "<pad>")
        for token in attention_tokens
    )

    rich_tokens = MarkdownIt("commonmark").parse(render_block(MarkdownBlock(
        type="paragraph", text="Bold and RL*F", rich_text="**Bold** and RL*F",
    )))
    assert any(
        child.type == "strong_open" for token in rich_tokens for child in token.children or []
    )
    assert "RL*F" in "".join(
        child.content for token in rich_tokens for child in token.children or []
        if child.type in ("text", "text_special")
    )

    kimi = render_markdown(_paragraphs_to_document(
        str(next(benchmark.glob("2607*.pdf"))), title="Kimi",
    ))
    gemini = render_markdown(_paragraphs_to_document(
        str(next(benchmark.glob("gemini*.pdf"))), title="Gemini",
    ))
    gpt = render_markdown(_paragraphs_to_document(
        str(next(benchmark.glob("gpt*.pdf"))), title="GPT",
    ))
    kimi_tokens = MarkdownIt("commonmark").parse(kimi)
    assert not any(
        token.type == "inline" and token.content == "7,168"
        and index > 0 and kimi_tokens[index - 1].type == "heading_open"
        for index, token in enumerate(kimi_tokens)
    )
    gemini_text = "".join(
        child.content for token in MarkdownIt("commonmark").parse(gemini)
        for child in token.children or [] if child.type in ("text", "text_special")
    )
    gpt_text = "".join(
        child.content for token in MarkdownIt("commonmark").parse(gpt)
        for child in token.children or [] if child.type in ("text", "text_special")
    )
    assert "RL*F" in gemini_text
    assert "\\\"false\\\"" in gpt_text


def test_nested_and_alphabetic_lists_keep_structure(tmp_path: Path) -> None:
    """BUG-205：数字父项跨字母子项连续，字母标记作为嵌套列表保留。"""
    from markdown_it import MarkdownIt

    pdf = tmp_path / "nested-list.pdf"
    rows = [
        (60, 75, "The workflow has two stages:"),
        (72, 102, "1. First stage has a long explanation"),
        (91, 116, "which continues on a second printed line."),
        (91, 140, "(a) First prerequisite"),
        (91, 155, "(b) Second prerequisite"),
        (72, 180, "2. Second stage"),
        (60, 220, "The following two alternative steps are equivalent:"),
        (72, 250, "a) Run a local conversion"),
        (72, 265, "b) Run conversion in another environment"),
        (60, 300, "Unrelated body paragraph ends the list."),
    ]
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=800)
        for x, y, text in rows:
            page.insert_text((x, y), text, fontsize=10)
        doc.save(pdf)

    markdown = render_markdown(_paragraphs_to_document(str(pdf), title="Nested"))
    tokens = MarkdownIt("commonmark").parse(markdown)

    assert "\\1." not in markdown and "\\2." not in markdown
    assert "    - (a) First prerequisite" in markdown
    assert "- a) Run a local conversion" in markdown
    assert sum(token.type == "list_item_open" for token in tokens) == 6
    assert sum(token.type == "ordered_list_open" for token in tokens) == 1
    assert sum(token.type == "bullet_list_open" for token in tokens) == 2


def test_nested_sibling_list_blocks_keep_shared_indent() -> None:
    """同级子项拆成多个 list 块时都应保留缩进，不得只缩进第一块。"""
    from markdown_it import MarkdownIt

    from lib.markdown import MarkdownDocument

    document = MarkdownDocument(title="Nested siblings", source_pdf="synthetic.pdf")
    document.blocks = [
        MarkdownBlock(type="list", text="1. Parent item one", page=1, meta={"bbox": [72, 100, 320, 112]}),
        MarkdownBlock(type="list", text="- Child item A", page=1, meta={"bbox": [92, 118, 320, 130]}),
        MarkdownBlock(type="list", text="- Child item B", page=1, meta={"bbox": [92, 136, 320, 148]}),
        MarkdownBlock(type="list", text="2. Parent item two", page=1, meta={"bbox": [72, 154, 320, 166]}),
    ]
    markdown = render_markdown(document)

    assert "    - Child item A" in markdown
    assert "    - Child item B" in markdown
    assert "\n- Child item B" not in markdown
    tokens = MarkdownIt("commonmark").parse(markdown)
    # 两个父项 level 1；两个同级子项都在第一个父项内部的 level 3
    assert [token.level for token in tokens if token.type == "list_item_open"] == [1, 3, 3, 1]
    assert sum(token.type == "ordered_list_open" for token in tokens) == 1
    assert sum(token.type == "bullet_list_open" for token in tokens) == 1


def test_side_by_side_list_blocks_are_not_indented_as_sublists() -> None:
    """同页并排的右栏列表 x0 更大但不在上一块下方，不得当作嵌套子项。"""
    from lib.markdown import MarkdownDocument

    document = MarkdownDocument(title="Columns", source_pdf="synthetic.pdf")
    document.blocks = [
        MarkdownBlock(type="list", text="- Left column item", page=12, meta={"bbox": [108, 685, 400, 697]}),
        MarkdownBlock(type="list", text="- Right column item", page=12, meta={"bbox": [270, 685, 520, 697]}),
    ]
    markdown = render_markdown(document)

    assert "\n- Right column item" in markdown
    assert "    - Right column item" not in markdown


def test_list_items_escape_literal_stars_backslashes_and_html_like_text() -> None:
    """列表项的字面星号、反斜杠与类 HTML 文本不得被 CommonMark 解释（BUG-203/211 同类）。"""
    from markdown_it import MarkdownIt

    plain = "Use a*b*c notation and C:\\path\\to\\file, <EOS> and <pad>"
    rendered = render_block(MarkdownBlock(type="list", text=f"- {plain}"))
    tokens = MarkdownIt("commonmark").parse(rendered)

    assert rendered.startswith("- ")
    assert "\\*" in rendered and "\\\\" in rendered and "&lt;EOS>" in rendered
    assert not any(token.type in ("html_block", "html_inline") for token in tokens)
    assert not any(token.type == "em_open" for token in tokens for child in token.children or [])
    roundtrip = "".join(
        child.content for token in tokens for child in token.children or []
        if child.type in ("text", "text_special")
    )
    assert roundtrip == plain
    # "* " 是列表标记而非字面星号：转义后仍是项目符号
    assert render_block(MarkdownBlock(type="list", text="* first\n* second")) == "- first\n- second"

    original = "• Reinforcement Learning (RL*F)"
    styled = "• **Reinforcement Learning (RL\\*F)**"
    styled_tokens = MarkdownIt("commonmark").parse(render_block(MarkdownBlock(
        type="list", text=original, rich_text=styled,
    )))
    styled_text = "".join(
        child.content for token in styled_tokens for child in token.children or []
        if child.type in ("text", "text_special")
    )
    assert "RL*F" in styled_text
    assert any(
        child.type == "strong_open" for token in styled_tokens for child in token.children or []
    )


def test_bold_backslashes_are_escaped_exactly_once() -> None:
    """BUG-220：粗体样式 run 内已有的转义反斜杠不得再被转义一次。"""
    from markdown_it import MarkdownIt

    from lib.text_extract import format_spans_as_markdown

    spans = [
        {"text": "C:\\path and \\two", "font": "Times-Bold", "flags": 16},
        {"text": " and normal", "font": "Times-Roman", "flags": 4},
    ]
    plain = "".join(span["text"] for span in spans)
    rich = format_spans_as_markdown(spans)

    rendered = render_block(MarkdownBlock(type="paragraph", text=plain, rich_text=rich))
    tokens = MarkdownIt("commonmark").parse(rendered)
    roundtrip = "".join(
        child.content for token in tokens for child in token.children or []
        if child.type in ("text", "text_special")
    )

    assert roundtrip == plain
    # 两个字面反斜杠各转义一次（输出 4 个），不得出现第二次转义
    assert rendered.count("\\\\") == 2
    assert any(child.type == "strong_open" for token in tokens for child in token.children or [])

    list_rendered = render_block(MarkdownBlock(type="list", text=f"- {plain}", rich_text=f"- {rich}"))
    list_tokens = MarkdownIt("commonmark").parse(list_rendered)
    list_roundtrip = "".join(
        child.content for token in list_tokens for child in token.children or []
        if child.type in ("text", "text_special")
    )
    assert list_roundtrip == plain


def test_heading_and_table_blocks_escape_literal_markup() -> None:
    """BUG-221：标题块与 table 块的字面星号、反斜杠与尖括号不得被 CommonMark 解释。"""
    from markdown_it import MarkdownIt

    md = MarkdownIt("commonmark")

    def text_of(markdown: str) -> str:
        tokens = md.parse(markdown)
        return "".join(
            child.content for token in tokens for child in token.children or []
            if child.type in ("text", "text_special")
        )

    original = "3.2 A*B*C and C:\\path <EOS>"
    heading = render_block(MarkdownBlock(type="heading", text=original, level=2))
    heading_tokens = md.parse(heading)
    assert heading_tokens[0].type == "heading_open"
    assert not any(token.type == "em_open" for token in heading_tokens for child in token.children or [])
    assert not any(token.type in ("html_block", "html_inline") for token in heading_tokens)
    assert text_of(heading) == original

    table_original = "| a * b * c | <EOS> |"
    table = render_block(MarkdownBlock(type="table", text=table_original))
    table_tokens = md.parse(table)
    assert not any(token.type in ("html_block", "html_inline") for token in table_tokens)
    assert text_of(table) == table_original
    # 普通标题与井号开头标题的层级语义不变
    assert render_block(MarkdownBlock(type="heading", text="1 Introduction", level=1)) == "# 1 Introduction"
    assert render_block(MarkdownBlock(type="heading", text="# Langs", level=2)) == "## # Langs"


def test_extended_caption_formats_and_nonbold_large_headings(tmp_path: Path) -> None:
    """BUG-207/208：题注格式与资产标识符对齐，编号标题不依赖粗体。"""
    pdf = tmp_path / "caption-heading-boundaries.pdf"
    rows = [
        (60, 75, "Helvetica", 16, "1 Introduction"),
        (60, 113, "Helvetica", 10, "The first body paragraph provides ordinary prose about the method."),
        (60, 155, "Helvetica-Bold", 10, "1. Install the package"),
        (60, 170, "Helvetica-Bold", 10, "2. Run the setup command"),
        (60, 219, "Helvetica-Bold", 10, "Figure 1: Ordinary caption"),
        (60, 245, "Helvetica-Bold", 10, "Figure II: Roman numeral caption"),
        (60, 271, "Helvetica-Bold", 10, "Extended Data Figure 1: Supplementary plot"),
        (60, 297, "Helvetica-Bold", 10, "Supplementary Table 1: Results"),
        (60, 323, "Helvetica-Bold", 10, "Tab. 2: Measurements"),
        (60, 349, "Helvetica", 10, "Table 6. Also, we evaluate whether the effect generalizes."),
        (60, 393, "Helvetica", 16, "2 Method"),
        (60, 430, "Helvetica", 10, "Another body paragraph provides ordinary prose about the experiments."),
    ]
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=800)
        for x, y, font, size, text in rows:
            page.insert_text((x, y), text, fontname=font, fontsize=size)
        doc.save(pdf)

    paragraphs = gather_structured_text(str(pdf)).paragraphs
    by_text = {p.text: p for p in paragraphs}

    assert by_text["1 Introduction"].heading_level == 2
    assert by_text["2 Method"].heading_level == 2
    steps = by_text["1. Install the package\n2. Run the setup command"]
    assert steps.is_heading is False
    assert steps.para_type == "list"
    for text in (
        "Figure 1: Ordinary caption",
        "Figure II: Roman numeral caption",
        "Extended Data Figure 1: Supplementary plot",
        "Supplementary Table 1: Results",
        "Tab. 2: Measurements",
    ):
        assert by_text[text].para_type == "caption"
    assert by_text[
        "Table 6. Also, we evaluate whether the effect generalizes."
    ].para_type == "paragraph"


def test_full_layout_export_includes_unblocked_text_units(tmp_path: Path) -> None:
    """BUG-209：full 必须包含未进入聚合块的全部行单元，且默认输出保持原结构。"""
    from lib.text_extract import extract_text_with_format

    pdf = tmp_path / "full-units.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=800)
        page.insert_text((50, 100), "An isolated one-line paragraph in the original PDF.", fontsize=10)
        page.insert_text((50, 170), "A second isolated paragraph also belongs to the document.", fontsize=10)
        doc.save(pdf)

    model = extract_text_with_format(str(pdf))
    full = model.to_dict(full_text_export=True)
    default = model.to_dict()
    expected = sum(len(units) for units in model.text_units.values())

    assert expected == 2
    assert "text_units" not in default
    assert sum(len(units) for units in full["text_units"].values()) == expected
    assert {
        unit["text"] for units in full["text_units"].values() for unit in units
    } == {
        "An isolated one-line paragraph in the original PDF.",
        "A second isolated paragraph also belongs to the document.",
    }


def test_layout_model_default_cli_matches_explicit_blocks(tmp_path: Path) -> None:
    """WP-4.2：省略 --layout-model-detail 必须与显式 blocks 逐字节一致。"""
    from core.extract_pdf_assets import main as assets_main

    pdf = tmp_path / "default-blocks.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=420, height=320)
        page.insert_text((48, 72), "Default layout export compatibility check.", fontsize=11)
        doc.save(pdf)

    outputs = {}
    for mode in ("default", "blocks"):
        out_dir = tmp_path / mode / "images"
        args = [
            "--pdf", str(pdf), "--out-dir", str(out_dir),
            "--out-text", str(tmp_path / mode / "txt" / "paper.txt"),
            "--no-figures", "--no-tables", "--layout-driven", "on",
        ]
        if mode == "blocks":
            args.extend(["--layout-model-detail", "blocks"])
        assert assets_main(args) == 0
        outputs[mode] = (out_dir / "layout_model.json").read_bytes()

    assert outputs["default"] == outputs["blocks"]


def test_layout_detail_is_forwarded_by_markdown_and_process(tmp_path: Path, monkeypatch) -> None:
    """WP-4.2：full/summary 不再局限于底层资产入口，process 继续透传。"""
    import json

    import core.process_pdf as process_pdf

    pdf = tmp_path / "forward-layout-detail.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=420, height=320)
        page.insert_text((48, 72), "Forward the selected layout detail level.", fontsize=11)
        doc.save(pdf)

    out_md = tmp_path / "full" / "paper.md"
    assert main([
        "--pdf", str(pdf), "--out", str(out_md), "--images", "figures", "--tables", "off",
        "--layout-model-detail", "full",
    ]) == 0
    full = json.loads((out_md.parent / "images" / "layout_model.json").read_text(encoding="utf-8"))
    assert "text_units" in full

    calls = []

    def fake_load(filename: str, _module_name: str):
        if filename == "pdf_to_markdown.py":
            return lambda argv: calls.append(argv) or 0
        return lambda _argv: 0

    monkeypatch.setattr(process_pdf, "_load_sibling_main", fake_load)
    assert process_pdf.main([
        "--pdf", str(pdf), "--out", str(tmp_path / "combined" / "paper.md"),
        "--layout-model-detail", "summary",
    ]) == 0
    assert len(calls) == 1
    option_index = calls[0].index("--layout-model-detail")
    assert calls[0][option_index + 1] == "summary"


def test_legacy_gathered_text_construction_and_consumers_remain_compatible(tmp_path: Path) -> None:
    """WP-1.2：旧构造、Markdown 转换、JSON 落盘和图表上下文消费方保持兼容。"""
    import json
    from types import SimpleNamespace

    from lib.figure_contexts import build_figure_contexts
    from lib.models import AttachmentRecord, GatheredParagraph, GatheredText
    from lib.text_extract import write_gathered_text_json

    paragraphs = [
        GatheredParagraph(1, "1 Legacy heading", (50, 40, 200, 55), True),
        GatheredParagraph(
            1, "The legacy consumer discusses Figure 1 in ordinary prose.",
            (50, 80, 400, 95), False,
        ),
    ]
    gathered = GatheredText("1.0", False, [], [], paragraphs)
    validation = SimpleNamespace(text_layer_ratio=1.0, has_text_layer=True, warnings=[])

    document = _paragraphs_to_document("legacy.pdf", "Legacy", validation, gathered=gathered)
    assert [block.type for block in document.blocks] == ["page_break", "heading", "paragraph"]
    assert document.meta["num_columns"] == 1
    assert document.meta["body_font_size"] == 0.0
    json.dumps(document.to_dict(), ensure_ascii=False)

    out_json = tmp_path / "legacy-gathered.json"
    write_gathered_text_json(gathered, str(out_json))
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert {"version", "is_dual_column", "headers_removed", "footers_removed", "paragraphs"} <= set(payload)
    assert payload["version"] == "1.0"
    assert payload["paragraphs"][0]["text"] == "1 Legacy heading"
    assert payload["paragraphs"][0]["heading_level"] == 0
    assert payload["toc"] == []

    record = AttachmentRecord("figure", "1", 1, "Figure 1: Legacy", "")
    contexts = build_figure_contexts("unused.pdf", [record], gathered_text=gathered)
    assert len(contexts) == 1
    assert contexts[0].first_mention is not None
    assert "legacy consumer" in contexts[0].first_mention.text_window


def test_layout_model_detail_export_modes(tmp_path: Path) -> None:
    """WP-4.2：layout_model.to_dict 与 extract_pdf_assets --layout-model-detail 支持 summary/blocks/full。"""
    import json
    from core.extract_pdf_assets import main as assets_main
    from lib.text_extract import extract_text_with_format

    long_line = "token_" * 42  # 252 chars > 200 单元截断线
    pdf_path = tmp_path / "detail.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=2000, height=1200)
        for i in range(12):
            page.insert_text((40, 80 + i * 12), long_line, fontsize=10.0)
        doc.save(pdf_path)

    model = extract_text_with_format(str(pdf_path))
    summary_d = model.to_dict(include_details=False)
    legacy_summary_d = model.to_dict(False)
    default_d = model.to_dict()
    no_units_d = model.to_dict(include_units=False)
    full_d = model.to_dict(full_text_export=True)

    page_blocks = next(iter(default_d["text_blocks"].values()))
    full_page_blocks = next(iter(full_d["text_blocks"].values()))
    no_units_page_blocks = next(iter(no_units_d["text_blocks"].values()))

    assert "text_blocks" not in summary_d
    assert legacy_summary_d == summary_d
    assert page_blocks, "应生成非空 text_blocks"
    assert len(page_blocks[0]["text"]) <= 2000
    assert len(page_blocks[0]["units"][0]["text"]) <= 200
    assert "units" not in no_units_page_blocks[0]
    assert len(full_page_blocks[0]["text"]) > 2000
    assert len(full_page_blocks[0]["units"][0]["text"]) > 200

    out_dir = tmp_path / "images"
    out_text = tmp_path / "text" / "detail.txt"
    rc = assets_main([
        "--pdf", str(pdf_path),
        "--out-dir", str(out_dir),
        "--out-text", str(out_text),
        "--no-figures",
        "--no-tables",
        "--layout-model-detail", "summary",
    ])
    assert rc == 0
    saved_layout = json.loads((out_dir / "layout_model.json").read_text(encoding="utf-8"))
    assert "text_blocks" not in saved_layout


def test_pdf_to_markdown_meta_carries_body_font_size_and_toc(tmp_path: Path) -> None:
    """WP-4.1：markdown_blocks.json 元数据透传 body_font_size 与 toc。"""
    import json

    pdf_path = tmp_path / "meta.pdf"
    out_md = tmp_path / "md" / "paper.md"
    with fitz.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 80), "1. Introduction", fontsize=13.0, fontname="Times-Bold")
        page.insert_text((72, 110), "1.1. Details", fontsize=11.5, fontname="Times-Bold")
        page.insert_text((72, 150), "Body prose in 10.5pt font size across multiple words.", fontsize=10.5)
        doc.set_toc([[1, "Introduction", 1]])
        doc.save(pdf_path)

    assert main(["--pdf", str(pdf_path), "--out", str(out_md), "--images", "off", "--tables", "off"]) == 0
    blocks_payload = json.loads((tmp_path / "md" / "text" / "markdown_blocks.json").read_text(encoding="utf-8"))
    report_payload = json.loads((tmp_path / "md" / "text" / "conversion_report.json").read_text(encoding="utf-8"))
    assert blocks_payload["meta"]["body_font_size"] > 0
    assert blocks_payload["meta"]["toc"] == [{"level": 1, "title": "Introduction", "page": 1}]
    assert report_payload["status"] == "ready"


def test_layout_columns_use_same_page_body_font_size(tmp_path: Path) -> None:
    """CHK-094：前页 10pt 双栏不被后页 14pt 单栏正文的字号参照滤掉。"""
    from lib.layout_model import detect_columns
    from lib.text_extract import extract_text_with_format

    pdf = tmp_path / "page-local-layout-font.pdf"
    with fitz.open() as doc:
        dense = doc.new_page(width=600, height=800)
        for index in range(4):
            dense.insert_text((50, 100 + 50 * index), f"Left column text at row {index}.", fontsize=10)
            dense.insert_text((330, 100 + 50 * index), f"Right column text at row {index}.", fontsize=10)
        wide = doc.new_page(width=600, height=800)
        for index in range(4):
            wide.insert_text(
                (50, 180 + 25 * index),
                "Wide typography in editorial appendix: text has sufficient length to span most of the page.",
                fontsize=14,
            )
        doc.save(pdf)

    model = extract_text_with_format(str(pdf))
    num_columns, column_gap, _units = detect_columns(model.text_units, 600.0)

    assert num_columns == 2
    assert column_gap > 0


def test_bold_literal_stars_and_backslashes_roundtrip(tmp_path: Path) -> None:
    """CHK-094：粗体 x**2 与两个连续反斜杠必须逐字回读且保留粗体。"""
    from markdown_it import MarkdownIt

    pdf = tmp_path / "bold-literals.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=800)
        page.insert_text((50, 130), "x**2", fontsize=11, fontname="Helvetica-Bold")
        page.insert_text((50, 230), r"Path: \\server", fontsize=11, fontname="Helvetica-Bold")
        page.insert_text((50, 330), "A normal body sentence.", fontsize=11)
        doc.save(pdf)

    markdown = render_markdown(_paragraphs_to_document(str(pdf), title="Bold"))
    tokens = MarkdownIt("commonmark").parse(markdown)
    text = "".join(
        child.content for token in tokens for child in token.children or []
        if child.type in ("text", "text_special")
    )

    assert "x**2" in text
    assert r"Path: \\server" in text
    assert sum(
        child.type == "strong_open" for token in tokens for child in token.children or []
    ) >= 2


def test_right_column_list_resets_indent_stack() -> None:
    """CHK-094：右栏列表起点更低、x0 更大时也不能继承左栏缩进。"""
    from markdown_it import MarkdownIt

    from lib.markdown import MarkdownDocument

    document = MarkdownDocument(title="Columns", source_pdf="synthetic.pdf")
    document.blocks = [
        MarkdownBlock(type="list", text="- Left column item", page=1,
                      meta={"bbox": [50, 300, 260, 312], "column": 0}),
        MarkdownBlock(type="list", text="- Right column item", page=1,
                      meta={"bbox": [330, 400, 540, 412], "column": 1}),
    ]
    markdown = render_markdown(document)
    tokens = MarkdownIt("commonmark").parse(markdown)

    assert "\n- Right column item" in markdown
    assert "    - Right column item" not in markdown
    assert [token.level for token in tokens if token.type == "list_item_open"] == [1, 1]


def test_unconfirmed_cross_page_list_keeps_page_marker(tmp_path: Path) -> None:
    """CHK-094：编号虽连续但缩进不同，跨页列表不合并，分页标记保留。"""
    from markdown_it import MarkdownIt

    pdf = tmp_path / "distinct-cross-page-lists.pdf"
    with fitz.open() as doc:
        first = doc.new_page(width=600, height=800)
        first.insert_text((60, 110), "1. Common item A", fontsize=10)
        first.insert_text((60, 126), "2. Common item B", fontsize=10)
        second = doc.new_page(width=600, height=800)
        second.insert_text((180, 140), "3. Separate item C", fontsize=10)
        second.insert_text((180, 156), "4. Separate item D", fontsize=10)
        doc.save(pdf)

    markdown = render_markdown(_paragraphs_to_document(str(pdf), title="Lists"))
    tokens = MarkdownIt("commonmark").parse(markdown)

    assert "<!-- page 2 -->" in markdown
    assert sum(token.type == "ordered_list_open" for token in tokens) == 2


def test_explicit_layout_export_works_when_assets_disabled(tmp_path: Path) -> None:
    """CHK-094：--images off --tables off 配显式 full 仍生成 layout_model.json。"""
    import json

    pdf = tmp_path / "layout-export-off.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=420, height=320)
        page.insert_text((48, 72), "Layout export while assets are off.", fontsize=11)
        doc.save(pdf)

    out_md = tmp_path / "result" / "paper.md"
    assert main([
        "--pdf", str(pdf), "--out", str(out_md),
        "--images", "off", "--tables", "off",
        "--layout-model-detail", "full",
    ]) == 0
    layout_path = out_md.parent / "images" / "layout_model.json"

    assert layout_path.exists()
    payload = json.loads(layout_path.read_text(encoding="utf-8"))
    assert "text_units" in payload


@pytest.mark.parametrize("font", ["Helvetica", "Helvetica-Bold"])
def test_asterisk_list_items_survive_rich_text_escaping(tmp_path: Path, font: str) -> None:
    """CHK-095/BUG-233：星号项目符号在 rich_text 里被转义成字面星号后仍须渲染为列表。"""
    from markdown_it import MarkdownIt

    pdf = tmp_path / "asterisk-list.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=800)
        page.insert_text((50, 100), "* First item in an asterisk list.", fontsize=10, fontname=font)
        page.insert_text((50, 117), "* Second item in an asterisk list.", fontsize=10, fontname=font)
        doc.save(pdf)

    gathered = gather_structured_text(str(pdf))
    items = [p for p in gathered.paragraphs if p.text.startswith("* ")]

    assert [p.para_type for p in items] == ["list", "list"]
    # 生成期把星号当字面字符转义（BUG-217），列表渲染必须认得这种写法
    assert all("\\* " in p.rich_text for p in items)
    markdown = render_markdown(_paragraphs_to_document(str(pdf), title="Stars", gathered=gathered))
    tokens = MarkdownIt("commonmark").parse(markdown)

    assert sum(token.type == "bullet_list_open" for token in tokens) == 1
    assert sum(token.type == "list_item_open" for token in tokens) == 2
    assert "\\*" not in markdown
    plain = "".join(
        child.content for token in tokens for child in token.children or []
        if child.type in ("text", "text_special")
    )
    assert "First item in an asterisk list." in plain
    assert "Second item in an asterisk list." in plain
    assert sum(
        child.type == "strong_open" for token in tokens for child in token.children or []
    ) == (2 if font == "Helvetica-Bold" else 0)


def test_layout_only_export_preserves_existing_assets(tmp_path: Path) -> None:
    """CHK-095/BUG-231：关闭图表时显式导出布局模型，不得覆盖索引或删除已有图表 PNG。"""
    import json

    pdf = tmp_path / "one-figure.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=800)
        page.insert_text((60, 100), "A short paper with one figure and its caption below the framed box.", fontsize=10)
        page.draw_rect(fitz.Rect(150, 180, 450, 380), color=(0, 0, 0), width=1.5)
        page.insert_text((60, 420), "Figure 1: A framed box used as the only figure.", fontsize=10)
        doc.save(pdf)

    out_md = tmp_path / "result" / "paper.md"
    assert main(["--pdf", str(pdf), "--out", str(out_md), "--tables", "off"]) == 0
    asset_dir = out_md.parent / "images"
    index_path = asset_dir / "index.json"
    baseline_index = index_path.read_bytes()
    baseline_images = {path.name: path.read_bytes() for path in asset_dir.glob("Figure_*.png")}
    assert json.loads(baseline_index)["items"] and baseline_images

    assert main([
        "--pdf", str(pdf), "--out", str(out_md), "--images", "off", "--tables", "off",
        "--layout-model-detail", "full",
    ]) == 0

    assert index_path.read_bytes() == baseline_index
    assert {path.name: path.read_bytes() for path in asset_dir.glob("Figure_*.png")} == baseline_images
    layout_only = (asset_dir / "layout_model.json").read_bytes()
    assert "text_units" in json.loads(layout_only)
    # 与完整资产提取按同档位写出的布局模型逐字节一致
    assert main([
        "--pdf", str(pdf), "--out", str(out_md), "--tables", "off",
        "--layout-model-detail", "full",
    ]) == 0
    assert (asset_dir / "layout_model.json").read_bytes() == layout_only
