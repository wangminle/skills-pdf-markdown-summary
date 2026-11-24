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
from lib.markdown import render_markdown
from lib.models import CaptionCandidate
from lib.text_extract import (
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
        ("1 Introduction", 2),
        ("I. Introduction", 2),
        ("A. Appendix Detail", 3),
        ("Introduction", 2),
    ],
)
def test_infer_heading_level_from_numbering(text: str, expected: int) -> None:
    assert looks_like_structural_heading(text, is_bold=True, font_size=12.0)
    assert infer_heading_level(text, font_size=12.0, typical_font_size=10.0) == expected


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


# ---------------------------------------------------------------------------
# 双栏通栏阅读顺序
# ---------------------------------------------------------------------------

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
