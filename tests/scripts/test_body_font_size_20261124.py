# -*- coding: utf-8 -*-
"""WP-2.2 回归：正文字号 body_font_size 与行内粗体的 LaTeX 粗体字族。

对应 WBS 2.2 与 CHK-072 的探测结论：

- typical_font_size 是 8-14pt 全部 span 字号的算术平均，按 span 计数。表格、脚注
  里小字号 span 又多又短，会把均值拉低（Gemini 报告低 4.6%）。新增 body_font_size：
  按字符数加权的众数，取之前先把相差不超过 0.15pt 的字号并簇（LaTeX 的同一个名义
  字号在 PyMuPDF 里会拆成 9.96 与 10.06）。它只用于 Markdown 标题层级判定。
- DocumentLayoutModel.typical_font_size 是图表裁剪的依据，不跟着改：探测显示它若
  改用众数，Kimi-K3 有 84 个、Gemini 有 48 个版式单元会重新分类。
- 标题判定与版式模型的字重仍只认 PDF 粗体标志位（BUG-163 P1-2：字体名启发式会把
  图内 DejaVuSans-Bold 标签升为标题）。字体名只服务于行内 Markdown 样式，补上
  名字里没有 bold 字样的 LaTeX 粗体字族（CMBX、CMMIB、CMBSY、SFBX、txb）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import fitz
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "skills" / "pdf-markdown-summary" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from lib.models import GatheredText  # noqa: E402 - local script path is set above
from lib.text_extract import (  # noqa: E402 - local script path is set above
    _span_has_bold_flag,
    _span_is_bold,
    estimate_body_font_size,
    extract_text_with_format,
    format_spans_as_markdown,
    gather_structured_text,
    looks_like_structural_heading,
    strip_inline_markdown,
)

BODY_SENTENCE = (
    "The quick brown fox jumps over the lazy dog while the reader keeps "
    "track of long lines of ordinary body text in this paragraph."
)


# ---------------------------------------------------------------------------
# 正文字号估计：按字符加权的并簇众数
# ---------------------------------------------------------------------------

def test_body_font_size_weights_by_characters_not_span_count() -> None:
    # 表格：400 个短 span，每个 3 个字符；正文：60 个长 span，每个 100 个字符
    sizes = {8.5: 400 * 3, 10.96: 30 * 100, 11.07: 30 * 100}
    per_span_mean = (400 * 8.5 + 30 * 10.96 + 30 * 11.07) / 460

    body = estimate_body_font_size(sizes)

    assert body == pytest.approx(11.015, abs=1e-3)
    assert per_span_mean < body - 2  # 按 span 计数的均值会被表格拉低 2pt 以上


def test_body_font_size_merges_split_nominal_sizes() -> None:
    # LaTeX 10pt 正文拆成 9.96 与 10.06：单值众数只能在两者间随意挑一个
    sizes = {9.96: 500, 10.06: 500, 8.97: 360}

    assert estimate_body_font_size(sizes) == pytest.approx(10.01, abs=1e-3)


def test_body_font_size_keeps_sizes_apart_beyond_tolerance() -> None:
    # 间距超过 0.15pt 的字号不并簇；并列时取字符数最多的一簇
    assert estimate_body_font_size({10.0: 300, 10.4: 100, 10.8: 100}) == pytest.approx(10.0)
    # 相邻间距都不超过容差时链式并成一簇
    assert estimate_body_font_size({10.0: 100, 10.1: 100, 10.2: 100, 10.3: 100}) == pytest.approx(10.15)


def test_body_font_size_merges_exact_tolerance_boundary() -> None:
    assert estimate_body_font_size({10.0: 70, 10.15: 60, 11.0: 100}) == pytest.approx(10.0692)


def test_body_font_size_keeps_size_just_beyond_tolerance_apart() -> None:
    # BUG-186：0.15pt 恰好并簇，0.16pt 必须分开；10.16 字符更多，不能被 10.0 吞掉
    assert estimate_body_font_size({10.0: 100, 10.16: 1000}) == pytest.approx(10.16)
    assert estimate_body_font_size({10.0: 100, 10.15: 1000}) == pytest.approx(
        (10.0 * 100 + 10.15 * 1000) / 1100, abs=1e-4
    )


def test_body_font_size_ignores_out_of_range_and_handles_empty() -> None:
    assert estimate_body_font_size({}) == 0.0
    assert estimate_body_font_size({5.0: 1000, 25.0: 1000}) == 0.0
    # 超出 6-20pt 的上标、标题美术字不参与，哪怕字符更多
    assert estimate_body_font_size({10.96: 500, 5.98: 5000}) == pytest.approx(10.96)


# ---------------------------------------------------------------------------
# 表格密集文档：标题层级按正文字号判定，版式模型的典型字号不变
# ---------------------------------------------------------------------------

def _make_table_dense_pdf(path: Path) -> None:
    """一页正文加一个 13.4pt 的无编号粗体标题，另一页是大量 8.5pt 的表格短格。"""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 60), "Evaluation Summary", fontsize=13.4, fontname="Times-Bold")
    y = 100
    for index in range(60):
        size = 10.96 if index % 2 == 0 else 11.07
        page.insert_text((72, y), f"{index:02d} {BODY_SENTENCE}", fontsize=size, fontname="Times-Roman")
        y += 11

    table_page = doc.new_page(width=612, height=792)
    for row in range(50):
        for column in range(8):
            table_page.insert_text(
                (40 + column * 68, 60 + row * 13), f"{row * 8 + column:03d}", fontsize=8.5, fontname="Times-Roman",
            )
    doc.save(path)
    doc.close()


def _span_sizes_of_page(page) -> list:
    return [
        span["size"]
        for block in page.get_text("dict")["blocks"]
        for line in block.get("lines", [])
        for span in line.get("spans", [])
    ]


def _span_sizes(pdf_path: Path, page_limit: int = 0) -> list:
    sizes = []
    with fitz.open(str(pdf_path)) as doc:
        for page in list(doc)[:page_limit] if page_limit else doc:
            sizes.extend(_span_sizes_of_page(page))
    return sizes


def test_table_dense_pdf_keeps_many_small_table_spans(tmp_path) -> None:
    # 夹具前提：表格格子的 span 确实又多又短，否则下面的用例证明不了任何事
    pdf = tmp_path / "table-dense.pdf"
    _make_table_dense_pdf(pdf)
    sizes = _span_sizes(pdf)
    small = [s for s in sizes if abs(s - 8.5) < 1e-6]

    assert len(small) >= 300
    assert len(small) > 3 * len([s for s in sizes if 10.9 < s < 11.1])


def test_table_dense_heading_level_uses_body_font_size(tmp_path) -> None:
    pdf = tmp_path / "table-dense.pdf"
    _make_table_dense_pdf(pdf)

    gathered = gather_structured_text(str(pdf), out_json=str(tmp_path / "gathered_text.json"))
    heading = next(p for p in gathered.paragraphs if p.is_heading)

    assert heading.text == "Evaluation Summary"
    assert gathered.body_font_size == pytest.approx(11.015, abs=0.05)
    assert gathered.typical_font_size < 10.0  # 原均值口径被表格拉偏，保持原样输出
    # 13.4pt 对被拉偏的均值（约 8.8pt）是 1.5 倍以上，会误判成 H1；对正文 11pt 只是 1.2 倍
    assert heading.heading_level == 2

    data = json.loads((tmp_path / "gathered_text.json").read_text(encoding="utf-8"))
    assert data["body_font_size"] == pytest.approx(11.015, abs=0.05)
    assert data["typical_font_size"] == gathered.typical_font_size


def test_layout_model_typical_font_size_is_untouched(tmp_path) -> None:
    pdf = tmp_path / "table-dense.pdf"
    _make_table_dense_pdf(pdf)

    layout = extract_text_with_format(str(pdf))

    # 版式模型沿用原口径：前 5 页 6-20pt 全部 span 字号的算术平均
    in_range = [s for s in _span_sizes(pdf, page_limit=5) if 6 <= s <= 20]

    assert layout.typical_font_size == pytest.approx(sum(in_range) / len(in_range))
    assert layout.typical_font_size < 10.0
    assert layout.typical_font_size != pytest.approx(11.015, abs=0.05)


def test_body_font_size_falls_back_to_typical_when_not_estimable(tmp_path, monkeypatch) -> None:
    """估不出正文字号时回退 typical_font_size；两者不能都是默认常量 10.0。"""
    import lib.text_extract as te

    pdf = tmp_path / "table-dense.pdf"
    _make_table_dense_pdf(pdf)
    # 强制估计失败，验证回退分支确实读取了非默认的 typical_font_size
    monkeypatch.setattr(te, "estimate_body_font_size", lambda _chars: 0.0)

    gathered = te.gather_structured_text(str(pdf))

    assert gathered.typical_font_size < 10.0
    assert gathered.body_font_size == pytest.approx(gathered.typical_font_size)


# ---------------------------------------------------------------------------
# 行内粗体：LaTeX 粗体字族；结构判定仍只认标志位
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("font", [
    "CMBX10", "CMBX12", "CMBX7", "CMB10", "CMBSY10", "CMMIB10", "CMSSBX10",
    "SFBX1095", "txbsys", "ABCDEF+CMBX10",
])
def test_inline_bold_accepts_latex_bold_font_names(font: str) -> None:
    span = {"text": "x", "font": font, "flags": 4}

    assert _span_is_bold(span) is True
    assert _span_has_bold_flag(span) is False


@pytest.mark.parametrize("font", [
    "CMR10", "CMTI10", "CMSY10", "CMMI10", "CMSS10", "CMTT10", "CMEX10",
    "SFRM1000", "txsys", "txmi", "Times-Roman", "Times-Italic", "DejaVuSans",
])
def test_inline_bold_rejects_non_bold_fonts(font: str) -> None:
    assert _span_is_bold({"text": "x", "font": font, "flags": 4}) is False


def test_latex_bold_font_name_span_renders_bold_inline() -> None:
    spans = [
        {"text": "Important", "font": "CMBX10", "flags": 4},
        {"text": " result", "font": "CMR10", "flags": 4},
    ]
    rich = format_spans_as_markdown(spans)

    assert rich == "**Important** result"
    assert strip_inline_markdown(rich) == "Important result"


def test_heading_detection_still_requires_bold_flag_for_latex_bold_names(tmp_path, monkeypatch) -> None:
    """CMBX10 行内算粗体，但没有 flags 粗体位时整块仍是正文（真实 gather 路径）。"""
    import lib.text_extract as te

    span = {"text": "Model Architecture", "font": "CMBX10", "flags": 4, "size": 14.0}
    assert _span_is_bold(span) is True
    assert _span_has_bold_flag(span) is False

    pdf = tmp_path / "latex-bold.pdf"
    doc = fitz.open()
    doc.new_page(width=612, height=792)
    doc.save(str(pdf))
    doc.close()
    block = {
        "page": 1,
        "page_index": 0,
        "bbox": (72, 100, 300, 116),
        "text": "Model Architecture",
        "rich_text": "**Model Architecture**",
        "lines": [{"bbox": [72, 100, 300, 116], "spans": [span]}],
        "page_width": 612.0,
        "page_height": 792.0,
    }
    monkeypatch.setattr(te, "iter_native_text_blocks", lambda _doc: [block])

    gathered = te.gather_structured_text(str(pdf))
    paragraph = next(p for p in gathered.paragraphs if p.text == "Model Architecture")

    assert paragraph.is_heading is False
    assert paragraph.para_type == "paragraph"
    # 行内样式仍按字体名识别粗体，只是不升级为标题块
    assert paragraph.rich_text == "**Model Architecture**"


def test_slightly_larger_bold_heading_uses_paragraph_spacing(tmp_path: Path) -> None:
    pdf = tmp_path / "modest-heading.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=800)
        page.insert_text((65, 130), "Methods", fontname="Times-Bold", fontsize=12)
        for index in range(5):
            page.insert_text(
                (65, 170 + 20 * index),
                "The samples in this study were gathered independently from each of the original sources.",
                fontname="Times-Roman",
                fontsize=11,
            )
        doc.save(pdf)

    gathered = gather_structured_text(str(pdf))
    heading = next(p for p in gathered.paragraphs if p.text == "Methods")

    assert gathered.body_font_size == pytest.approx(11.0)
    assert heading.is_heading is True
    assert heading.heading_level == 2
    assert not looks_like_structural_heading(
        "Methods", is_bold=True, font_size=12, body_font_size=11,
    )
    assert looks_like_structural_heading(
        "Methods", is_bold=True, font_size=12, body_font_size=11,
        has_paragraph_spacing=True,
    )


# ---------------------------------------------------------------------------
# 数据契约
# ---------------------------------------------------------------------------

def test_gathered_text_default_keeps_old_construction_working() -> None:
    gathered = GatheredText(
        version="1.1", is_dual_column=False, headers_removed=[], footers_removed=[], paragraphs=[],
    )

    assert gathered.typical_font_size == 10.0
    assert gathered.body_font_size == 0.0
