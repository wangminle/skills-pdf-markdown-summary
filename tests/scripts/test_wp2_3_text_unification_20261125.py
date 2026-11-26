# -*- coding: utf-8 -*-
"""WP-2.3 回归：统一双栏几何判定、C0 控制字符清洗、渲染字段补齐与单次运行共享扫描。

对应 WBS 2.3、BUG-167 与 BUG-170：
- gather_structured_text 废除粗糙的 0.45/0.55 块中心占比双栏判定，改用与
  layout_model.detect_columns 同源的段落行宽与 x0 双峰几何判据，避免单栏多图
  文档（如 Kimi-K3）被误判为双栏导致页内错序与公式拆分。
- plain_text_from_lines 与 format_spans_as_markdown 剔除 NUL/SOH/DLE 等 C0
  控制字符，保留换行与制表符，保证 gathered_text.json 与 Markdown 解析一致。
- GatheredParagraph / GatheredText 补齐 para_type、font_name、line_count、
  num_columns 并落盘至 gathered_text.json，同时保持旧字段向后兼容。
- pdf_to_markdown 与 extract_pdf_assets 在单次运行内共享 validation、
  GatheredText 与 native_blocks，减少重复全页扫描。
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import fitz
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "skills" / "pdf-markdown-summary" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from lib.models import GatheredParagraph, GatheredText  # noqa: E402 - local script path is set above

CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@pytest.fixture(autouse=True)
def _restore_root_logger():
    """BUG-191：进程内调用 configure_logging 的用例要把根 logger 与 JSONL 全局还原。"""
    import lib.extraction_logger as extraction_logger

    root = logging.getLogger()
    handlers = root.handlers[:]
    level = root.level
    jsonl_file = extraction_logger._JSONL_FILE
    yield
    for handler in root.handlers[:]:
        if handler not in handlers:
            root.removeHandler(handler)
    for handler in handlers:
        if handler not in root.handlers:
            root.addHandler(handler)
    root.setLevel(level)
    extraction_logger._JSONL_FILE = jsonl_file


def _make_single_col_with_side_labels_pdf(path: Path) -> None:
    """构造类似 Kimi-K3 的单栏论文：满宽正文 + 大量左右分布的图内/表内窄标签。"""
    doc = fitz.open()
    body = (
        "This single-column technical report paragraph spans across the full text "
        "measure of the page to verify that dense chart labels never flip column mode."
    )
    for page_idx in range(2):
        page = doc.new_page(width=612, height=792)
        y = 72
        for line_idx in range(10):
            page.insert_text(
                (72, y),
                f"P{page_idx + 1}L{line_idx:02d} {body}",
                fontsize=10.5,
                fontname="Times-Roman",
            )
            y += 16

        # 下半页散布大量图内/表内小标签，使左右半页块中心各自占比 > 0.35
        for row in range(18):
            py = 290 + row * 22
            page.insert_text((80 + (row % 3) * 18, py), f"L{row:02d}", fontsize=8.0)
            page.insert_text((390 + (row % 3) * 20, py), f"R{row:02d}", fontsize=8.0)

        # 中部一条跨页面中线的公式碎片（宽度窄但跨越 x=306）
        if page_idx == 0:
            page.insert_text((260, 260), "Diag(a)S + bkv", fontsize=10.0)
    doc.save(path)
    doc.close()


def _make_real_two_column_paper_pdf(path: Path) -> None:
    """构造标准双栏论文（含顶部通栏标题 + 左右双栏正文）。"""
    base = fitz.open()
    page = base.new_page(width=612, height=792)
    page.insert_text(
        (72, 68),
        "A Unified Architecture for Two-Column Academic Paper Layout Analysis",
        fontsize=14,
        fontname="Times-Bold",
    )

    left_doc = fitz.open()
    left_page = left_doc.new_page(width=612, height=792)
    right_doc = fitz.open()
    right_page = right_doc.new_page(width=612, height=792)

    for i in range(16):
        y = 130 + i * 32
        left_page.insert_text(
            (54, y),
            f"Left column sentence {i:02d} discussing method details.",
            fontsize=10,
            fontname="Times-Roman",
        )
        right_page.insert_text(
            (321, y),
            f"Right column sentence {i:02d} reporting benchmark results.",
            fontsize=10,
            fontname="Times-Roman",
        )

    page.show_pdf_page(page.rect, left_doc, 0)
    page.show_pdf_page(page.rect, right_doc, 0)
    base.save(path)
    base.close()
    left_doc.close()
    right_doc.close()


def _make_short_numeric_two_col_table_pdf(path: Path) -> None:
    """只有极短数字单元格的两列表格，不应被判为双栏正文文档。"""
    base = fitz.open()
    page = base.new_page(width=612, height=792)
    left_doc = fitz.open()
    left_page = left_doc.new_page(width=612, height=792)
    right_doc = fitz.open()
    right_page = right_doc.new_page(width=612, height=792)
    for i in range(12):
        y = 120 + i * 24
        left_page.insert_text((110, y), f"{i}.1", fontsize=9.5)
        right_page.insert_text((360, y), f"{i}.9", fontsize=9.5)
    page.show_pdf_page(page.rect, left_doc, 0)
    page.show_pdf_page(page.rect, right_doc, 0)
    base.save(path)
    base.close()
    left_doc.close()
    right_doc.close()


def _make_simple_paper_pdf(path: Path) -> None:
    """含章节标题、正文、列表与图注的简单单栏 PDF。"""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "1 Introduction", fontsize=14, fontname="Times-Bold")
    page.insert_text(
        (72, 110),
        "First line of body paragraph explaining the problem clearly.",
        fontsize=10.5,
        fontname="Times-Roman",
    )
    page.insert_text(
        (72, 124),
        "Second line continuing the same paragraph cleanly.",
        fontsize=10.5,
        fontname="Times-Roman",
    )
    page.insert_text((72, 175), "- First bullet item in list", fontsize=10.5, fontname="Times-Roman")
    page.insert_text((72, 191), "- Second bullet item in list", fontsize=10.5, fontname="Times-Roman")
    page.insert_text((72, 230), "Figure 1: System overview diagram.", fontsize=10.0, fontname="Times-Roman")
    doc.save(path)
    doc.close()


# ---------------------------------------------------------------------------
# 1. 双栏判定统一（BUG-170）
# ---------------------------------------------------------------------------

def test_single_column_with_dense_side_labels_not_misclassified_as_dual_column(tmp_path: Path) -> None:
    from lib.text_extract import gather_structured_text

    pdf = tmp_path / "kimi-like-single-col.pdf"
    _make_single_col_with_side_labels_pdf(pdf)

    gathered = gather_structured_text(str(pdf))

    assert gathered.is_dual_column is False
    assert gathered.num_columns == 1
    assert all(p.column == -1 for p in gathered.paragraphs)
    assert all(not p.is_full_width for p in gathered.paragraphs)

    # 第一页段落应严格按 y 序排列，不因图内标签拆乱阅读顺序
    p1_ys = [p.bbox[1] for p in gathered.paragraphs if p.page == 1]
    assert p1_ys == sorted(p1_ys)


def test_real_two_column_pdf_detected_as_dual_column(tmp_path: Path) -> None:
    from lib.text_extract import gather_structured_text

    pdf = tmp_path / "two-col.pdf"
    _make_real_two_column_paper_pdf(pdf)

    gathered = gather_structured_text(str(pdf))

    assert gathered.is_dual_column is True
    assert gathered.num_columns == 2
    texts = [p.text.replace("\n", " ").strip() for p in gathered.paragraphs]
    title_idx = next(i for i, t in enumerate(texts) if "Unified Architecture" in t)
    first_left = next(i for i, t in enumerate(texts) if "Left column sentence 00" in t)
    last_left = next(i for i, t in enumerate(texts) if "Left column sentence 15" in t)
    first_right = next(i for i, t in enumerate(texts) if "Right column sentence 00" in t)
    assert title_idx < first_left < last_left < first_right


def test_dual_column_detection_continues_after_five_single_column_pages(tmp_path: Path) -> None:
    from lib.text_extract import gather_structured_text

    dual_pdf = tmp_path / "dual.pdf"
    pdf = tmp_path / "five-intro-pages-plus-dual.pdf"
    _make_real_two_column_paper_pdf(dual_pdf)
    with fitz.open() as merged, fitz.open(str(dual_pdf)) as dual:
        for page_index in range(5):
            intro = merged.new_page(width=612, height=792)
            for line_index in range(5):
                intro.insert_text(
                    (54, 120 + line_index * 30),
                    f"Introductory single-column page {page_index + 1}, line {line_index + 1}; "
                    "this introduction spans the full width of the page before the paper begins.",
                    fontsize=10,
                    fontname="Times-Roman",
                )
        merged.insert_pdf(dual)
        merged.save(pdf)

    gathered = gather_structured_text(str(pdf))

    assert gathered.is_dual_column is True
    texts = [p.text.replace("\n", " ") for p in gathered.paragraphs if p.page == 6]
    left = [index for index, text in enumerate(texts) if "Left column sentence" in text]
    right = [index for index, text in enumerate(texts) if "Right column sentence" in text]
    assert len(left) == len(right) == 16
    assert max(left) < min(right)


def test_single_column_intro_does_not_override_following_dual_column_page(tmp_path: Path) -> None:
    from lib.text_extract import gather_structured_text

    dual_pdf = tmp_path / "dual.pdf"
    pdf = tmp_path / "intro-plus-dual.pdf"
    _make_real_two_column_paper_pdf(dual_pdf)
    with fitz.open() as merged, fitz.open(str(dual_pdf)) as dual:
        intro = merged.new_page(width=612, height=792)
        for index in range(16):
            intro.insert_text(
                (54, 100 + index * 28),
                f"{index:02d} Broad introduction with a lot of detailed running prose across the page, before the paper proper begins.",
                fontsize=10,
                fontname="Times-Roman",
            )
        merged.insert_pdf(dual)
        merged.save(pdf)

    gathered = gather_structured_text(str(pdf))

    assert gathered.num_columns == 2
    texts = [p.text.replace("\n", " ") for p in gathered.paragraphs if p.page == 2]
    left = [index for index, text in enumerate(texts) if "Left column sentence" in text]
    right = [index for index, text in enumerate(texts) if "Right column sentence" in text]
    assert len(left) == len(right) == 16
    assert max(left) < min(right)


def test_two_column_short_numeric_cells_not_misclassified_as_dual_column(tmp_path: Path) -> None:
    from lib.text_extract import gather_structured_text

    pdf = tmp_path / "short-nums.pdf"
    _make_short_numeric_two_col_table_pdf(pdf)

    gathered = gather_structured_text(str(pdf))

    assert gathered.is_dual_column is False
    assert gathered.num_columns == 1


# ---------------------------------------------------------------------------
# 2. C0 控制字符清洗（BUG-167）
# ---------------------------------------------------------------------------

def test_sanitize_extracted_text_strips_c0_control_chars_keeps_whitespace() -> None:
    from lib.text_extract import sanitize_extracted_text

    raw = "A\x00B\x01C\x08D\x0bE\x0cF\x0eG\x10H\x11I\x1bJ\x7fK\tL\nM\rN 中文α"
    cleaned = sanitize_extracted_text(raw)

    assert CTRL_RE.search(cleaned) is None
    assert cleaned == "ABCDEFGHIJK\tL\nM\rN 中文α"


def test_plain_and_rich_text_strip_control_chars_consistently() -> None:
    from lib.text_extract import (
        plain_text_from_lines,
        rich_text_from_lines,
        strip_inline_markdown,
    )

    lines = [
        {
            "bbox": [72, 100, 300, 112],
            "spans": [
                {"text": "Alpha\x00 ", "font": "Times-Roman", "flags": 0, "size": 10.0},
                {"text": "Bold\x01\x10Term", "font": "Times-Bold", "flags": 16, "size": 10.0},
                {"text": " end\x11.", "font": "Times-Roman", "flags": 0, "size": 10.0},
            ],
        }
    ]
    plain = plain_text_from_lines(lines)
    rich = rich_text_from_lines(lines)

    assert CTRL_RE.search(plain) is None
    assert CTRL_RE.search(rich) is None
    assert plain == "Alpha BoldTerm end."
    assert "**BoldTerm**" in rich
    assert strip_inline_markdown(rich) == plain


def test_gather_structured_text_and_json_strip_control_chars(tmp_path: Path, monkeypatch) -> None:
    import lib.text_extract as te

    pdf = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page(width=612, height=792)
    doc.save(pdf)
    doc.close()

    dirty_lines = [
        {
            "bbox": [72, 100, 350, 114],
            "spans": [
                {"text": "Formula\x00\x01 value \x10\x11ok", "font": "Times-Roman", "flags": 0, "size": 10.5}
            ],
        }
    ]
    block = {
        "page": 1,
        "page_index": 0,
        "bbox": (72, 100, 350, 114),
        "text": te.plain_text_from_lines(dirty_lines),
        "rich_text": te.rich_text_from_lines(dirty_lines),
        "lines": dirty_lines,
        "page_width": 612.0,
        "page_height": 792.0,
    }
    monkeypatch.setattr(te, "iter_native_text_blocks", lambda _doc: [block])

    out_json = tmp_path / "gathered_text.json"
    gathered = te.gather_structured_text(str(pdf), out_json=str(out_json))

    assert len(gathered.paragraphs) == 1
    assert CTRL_RE.search(gathered.paragraphs[0].text) is None
    assert gathered.paragraphs[0].text == "Formula value ok"
    raw_json = out_json.read_text(encoding="utf-8")
    assert "\\u0000" not in raw_json
    assert "\\u0001" not in raw_json
    assert "\\u0010" not in raw_json

    layout = te.extract_text_with_format(str(pdf))
    layout_text = "".join(unit.text for page in layout.text_units.values() for unit in page)
    assert layout_text == "Formula value ok"
    assert CTRL_RE.search(layout_text) is None


def test_try_extract_text_strips_control_chars(tmp_path: Path, monkeypatch) -> None:
    import lib.text_extract as te

    doc = MagicMock()
    doc.__enter__.return_value = [
        SimpleNamespace(get_text=lambda _mode: "Alpha\x00\x01 Beta\x10\x11\nNext\tLine")
    ]
    monkeypatch.setattr(te, "open_pdf", lambda _path: doc)
    out_text = tmp_path / "paper.txt"

    assert te.try_extract_text("fake.pdf", str(out_text)) == str(out_text)
    text = out_text.read_text(encoding="utf-8")
    assert text == "Alpha Beta\nNext\tLine"
    assert CTRL_RE.search(text) is None


# ---------------------------------------------------------------------------
# 3. 渲染元数据字段补齐与向后兼容（WP-2.3 + WP-1.2）
# ---------------------------------------------------------------------------

def test_gathered_paragraph_and_json_include_full_rendering_metadata(tmp_path: Path) -> None:
    from lib.text_extract import gather_structured_text

    # 旧四参数构造 100% 向后兼容
    legacy = GatheredParagraph(page=1, text="legacy", bbox=(0, 0, 10, 10), is_heading=False)
    assert legacy.para_type == "paragraph"
    assert legacy.font_name == ""
    assert legacy.line_count == 0

    pdf = tmp_path / "paper.pdf"
    _make_simple_paper_pdf(pdf)
    out_json = tmp_path / "gathered_text.json"

    gathered = gather_structured_text(str(pdf), out_json=str(out_json))
    assert gathered.num_columns == 1

    by_prefix = {p.text.splitlines()[0]: p for p in gathered.paragraphs}
    heading = by_prefix["1 Introduction"]
    assert heading.para_type == "heading"
    assert heading.is_heading is True
    assert heading.font_name == "Times-Bold"
    assert heading.line_count == 1

    body = next(p for p in gathered.paragraphs if "First line of body paragraph" in p.text)
    assert body.para_type == "paragraph"
    assert body.font_name == "Times-Roman"
    assert body.line_count == 2

    bullet = next(p for p in gathered.paragraphs if "First bullet item" in p.text)
    assert bullet.para_type == "list"

    caption = next(p for p in gathered.paragraphs if p.text.startswith("Figure 1:"))
    assert caption.para_type == "caption"

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["num_columns"] == 1
    for item in payload["paragraphs"]:
        assert {"para_type", "font_name", "line_count", "font_size", "is_bold", "column"} <= set(item)
        assert item["para_type"] in {"heading", "caption", "list", "paragraph"}
        assert item["font_name"] in {"Times-Bold", "Times-Roman"}
        assert item["line_count"] >= 1
    json_by_prefix = {item["text"].splitlines()[0]: item for item in payload["paragraphs"]}
    assert json_by_prefix["1 Introduction"]["line_count"] == 1
    assert json_by_prefix["1 Introduction"]["font_name"] == "Times-Bold"


# ---------------------------------------------------------------------------
# 4. 单次运行共享底层扫描与上下文复用（WP-2.3）
# ---------------------------------------------------------------------------

def test_pdf_to_markdown_reuses_validation_gathered_and_native_blocks(
    tmp_path: Path, monkeypatch
) -> None:
    import core.extract_pdf_assets as epa
    import core.pdf_to_markdown as p2m
    import lib.text_extract as te

    pdf = tmp_path / "paper.pdf"
    _make_simple_paper_pdf(pdf)

    counts = {"pre_validate": 0, "gather": 0, "iter_blocks": 0}
    orig_validate = te.pre_validate_pdf
    orig_gather = te.gather_structured_text
    orig_iter = te.iter_native_text_blocks

    def spy_validate(*args, **kwargs):
        counts["pre_validate"] += 1
        return orig_validate(*args, **kwargs)

    def spy_gather(*args, **kwargs):
        counts["gather"] += 1
        return orig_gather(*args, **kwargs)

    def spy_iter(*args, **kwargs):
        counts["iter_blocks"] += 1
        return orig_iter(*args, **kwargs)

    monkeypatch.setattr(te, "pre_validate_pdf", spy_validate)
    monkeypatch.setattr(te, "gather_structured_text", spy_gather)
    monkeypatch.setattr(te, "iter_native_text_blocks", spy_iter)
    monkeypatch.setattr(epa, "pre_validate_pdf", spy_validate)
    monkeypatch.setattr(epa, "gather_structured_text", spy_gather)

    out_md = tmp_path / "out" / "paper.md"
    rc = p2m.main([
        "--pdf", str(pdf),
        "--out", str(out_md),
        "--images", "figures",
        "--tables", "off",
    ])

    assert rc == 0
    assert out_md.is_file()
    assert (out_md.parent / "text" / "gathered_text.json").is_file()
    assert (out_md.parent / "text" / "markdown_blocks.json").is_file()
    assert counts["pre_validate"] == 1
    assert counts["gather"] == 1
    assert counts["iter_blocks"] == 1


def test_extract_pdf_assets_standalone_shares_native_blocks(tmp_path: Path, monkeypatch) -> None:
    import core.extract_pdf_assets as epa
    import lib.text_extract as te

    pdf = tmp_path / "paper.pdf"
    _make_simple_paper_pdf(pdf)

    iter_calls = 0
    orig_iter = te.iter_native_text_blocks

    def spy_iter(*args, **kwargs):
        nonlocal iter_calls
        iter_calls += 1
        return orig_iter(*args, **kwargs)

    monkeypatch.setattr(te, "iter_native_text_blocks", spy_iter)

    out_dir = tmp_path / "images"
    out_text = tmp_path / "txt" / "paper.txt"
    rc = epa.main_modular([
        "--pdf", str(pdf),
        "--out-dir", str(out_dir),
        "--out-text", str(out_text),
        "--no-figures",
        "--no-tables",
        "--layout-driven", "on",
    ])

    assert rc == 0
    assert (tmp_path / "txt" / "gathered_text.json").is_file()
    assert (out_dir / "layout_model.json").is_file()
    assert iter_calls == 1


@pytest.mark.parametrize("log_level", ["INFO", "DEBUG"])
def test_reused_gather_logs_with_debug_level(tmp_path: Path, monkeypatch, log_level: str) -> None:
    import core.extract_pdf_assets as epa
    import lib.text_extract as te

    pdf = tmp_path / "paper.pdf"
    _make_simple_paper_pdf(pdf)
    gathered = te.gather_structured_text(str(pdf))
    messages = []
    monkeypatch.setattr(te.logger, "info", messages.append)

    with te.reuse_scan_context(str(pdf), gathered=gathered):
        assert epa.main_modular([
            "--pdf", str(pdf),
            "--out-dir", str(tmp_path / "images"),
            "--out-text", str(tmp_path / "txt" / "paper.txt"),
            "--no-figures", "--no-tables", "--layout-driven", "off",
            "--log-level", log_level,
        ]) == 0

    writes = [message for message in messages if "Wrote gathered text:" in message]
    assert len(writes) == (1 if log_level == "DEBUG" else 0)


def test_reuse_scan_context_isolates_by_pdf_path_and_restores_on_exit(tmp_path: Path) -> None:
    from lib.text_extract import get_reusable_scan_context, reuse_scan_context

    pdf_a = tmp_path / "a.pdf"
    pdf_b = tmp_path / "b.pdf"
    sentinel = GatheredText(
        version="1.1",
        is_dual_column=False,
        headers_removed=[],
        footers_removed=[],
        paragraphs=[],
    )

    assert get_reusable_scan_context(str(pdf_a)) is None

    with pytest.raises(RuntimeError):
        with reuse_scan_context(str(pdf_a), gathered=sentinel):
            hit = get_reusable_scan_context(str(pdf_a))
            assert hit is not None and hit["gathered"] is sentinel
            assert get_reusable_scan_context(str(pdf_b)) is None
            raise RuntimeError("boom")

    assert get_reusable_scan_context(str(pdf_a)) is None


# ---------------------------------------------------------------------------
# 5. BUG-188/189/190：峰位置、相邻列表阈值与长编号标题
# ---------------------------------------------------------------------------

def _synthetic_lines(entries, *, page_width: float = 612.0, page_height: float = 792.0):
    """把 (x0, width, text) 序列变成 detect_dual_column_from_blocks 的原生块。"""
    blocks = []
    for index, (x0, width, text) in enumerate(entries):
        y = 80.0 + (index % 40) * 17.0
        blocks.append({
            "page": 1,
            "page_index": 0,
            "bbox": (x0, y, x0 + width, y + 10.0),
            "text": text,
            "rich_text": text,
            "lines": [{
                "bbox": [x0, y, x0 + width, y + 10.0],
                "spans": [{"text": text, "font": "Times-Roman", "size": 10.0, "flags": 0}],
            }],
            "page_width": page_width,
            "page_height": page_height,
        })
    return blocks


def test_dual_column_guard_needs_sampled_narrow_lines() -> None:
    """BUG-170/191：窄行必须真正进入采样，满宽守卫删掉后用例会变红。"""
    from lib.text_extract import detect_dual_column_from_blocks

    narrow = []
    for index in range(10):
        narrow.append((80.0, 140.0, f"Left label number {index:02d}"))
        narrow.append((360.0, 140.0, f"Right label number {index:02d}"))
    wide = [(60.0, 480.0, "Full width body line " + "x" * 100) for _ in range(6)]

    # 只保留窄标签：宽 140pt、字符数 >= 8，满足采样条件，几何判据成立 -> 双栏。
    assert detect_dual_column_from_blocks(_synthetic_lines(narrow), 612.0) is True
    # 加上满宽正文主导页后被守卫否决：删掉守卫这里会变成 True。
    assert detect_dual_column_from_blocks(_synthetic_lines(wide + narrow), 612.0) is False


def test_short_numeric_cells_are_filtered_by_sample_text_length() -> None:
    """BUG-191：短单元格规则由「字符数 < 8」触发，不是样本不足或栏距上限。"""
    from lib.text_extract import detect_dual_column_from_blocks

    short = [(110.0, 100.0, "12.5±0")] * 10 + [(360.0, 100.0, "13.5±0")] * 10
    long = [(110.0, 100.0, "12.5±0.5")] * 10 + [(360.0, 100.0, "13.5±0.5")] * 10

    # 同样几何下 8 字符单元格可达采样 -> 双栏；7 字符以下被采样规则排除。
    assert detect_dual_column_from_blocks(_synthetic_lines(long), 612.0) is True
    assert detect_dual_column_from_blocks(_synthetic_lines(short), 612.0) is False


@pytest.mark.parametrize("right_x0", [(304.0, 305.0), (312.0, 313.0)])
def test_justified_small_column_gap_is_detected(right_x0) -> None:
    """BUG-188：x0 有抖动、行宽=栏宽时，10pt/18pt 栏距仍判双栏。"""
    from lib.text_extract import detect_dual_column_from_blocks

    left = [
        (54.0 if index % 2 == 0 else 55.0, 240.0, f"Left justified line {index:02d}")
        for index in range(10)
    ]
    right = [
        (right_x0[index % 2], 240.0, f"Right justified line {index:02d}")
        for index in range(10)
    ]

    assert detect_dual_column_from_blocks(_synthetic_lines(left + right), 595.3) is True


def test_lead_in_with_bullet_block_is_list_not_escaped() -> None:
    """BUG-189：引导语与列表项同块时整块判 list，行首标记不再被转义。"""
    from lib.markdown import MarkdownBlock, render_block
    from lib.text_extract import _looks_like_list_item

    text = "System prompt extraction\n- realistic attacks of user\nattacking system message"
    assert _looks_like_list_item(text) is True
    assert render_block(MarkdownBlock(type="list", text=text)) == text
    # 句末标点的引导语、超长引导语都不升级
    assert _looks_like_list_item("Body sentence ends here.\n- not a list item") is False
    assert _looks_like_list_item(
        "A lead-in sentence that is clearly longer than forty characters\n- item"
    ) is False


def test_numbered_items_between_font_and_adjacency_threshold_stay_list() -> None:
    """BUG-189：相邻项间距 11.6pt（字号 10.91）不再被确认函数降回 paragraph。"""
    from lib.text_extract import _confirm_ordered_lists

    def para(text, y0, y1):
        return GatheredParagraph(
            page=1, text=text, bbox=(84.0, y0, 300.0, y1),
            is_heading=False, font_size=10.91, para_type="list",
        )

    confirmed = [
        para("1. Reads a proxy configuration file.", 569.2, 580.1),
        para("2. Connects to the specified HTTP proxy.", 591.7, 602.6),
    ]
    _confirm_ordered_lists(confirmed)
    assert [p.para_type for p in confirmed] == ["list", "list"]

    too_far = [
        para("1. Reads a proxy configuration file.", 569.2, 580.1),
        para("2. Connects to the specified HTTP proxy.", 600.1, 611.0),
    ]
    _confirm_ordered_lists(too_far)
    assert [p.para_type for p in too_far] == ["paragraph", "paragraph"]


def test_embedded_next_number_confirms_adjacent_ordered_list_blocks() -> None:
    from lib.text_extract import _confirm_ordered_lists, _looks_like_list_item

    continuation = (
        "The first item continues with enough prose to occupy several source lines.\n"
        "2. The next contribution starts inside the same native PDF text block."
    )
    assert _looks_like_list_item(continuation, allow_single_non_unicode=True) is True
    paragraphs = [
        GatheredParagraph(
            page=1, text="1. The first contribution starts here.",
            bbox=(75.0, 100.0, 300.0, 125.0), is_heading=False,
            font_size=10.9, para_type="list",
        ),
        GatheredParagraph(
            page=1, text=continuation, bbox=(75.0, 128.0, 300.0, 190.0),
            is_heading=False, font_size=10.9, para_type="list",
        ),
    ]

    _confirm_ordered_lists(paragraphs)

    assert [p.para_type for p in paragraphs] == ["list", "list"]


def test_gemini_embedded_second_contribution_keeps_ordered_list_semantics() -> None:
    from lib.text_extract import gather_structured_text

    benchmark = PROJECT_ROOT / "tests" / "basic-benchmark"
    gathered = gather_structured_text(str(next(benchmark.glob("gemini_v2_5*.pdf"))))

    first = next(p for p in gathered.paragraphs if "Slice-Granularity Elasticity" in p.text)
    second = next(p for p in gathered.paragraphs if "Split-Phase SDC Detection" in p.text)
    assert first.page == second.page == 4
    assert not second.text.lstrip().startswith("2.")
    assert first.para_type == second.para_type == "list"

    from markdown_it import MarkdownIt

    from core.pdf_to_markdown import _paragraphs_to_document
    from lib.markdown import render_block

    document = _paragraphs_to_document(
        "gemini.pdf", "Gemini",
        SimpleNamespace(text_layer_ratio=1.0, has_text_layer=True, warnings=[]),
        gathered=gathered,
    )
    block = next(b for b in document.blocks if "Split-Phase SDC Detection" in b.text)
    tokens = MarkdownIt("commonmark").parse(render_block(block))
    assert any(
        token.type == "ordered_list_open" and token.attrGet("start") == 2
        for token in tokens
    )


def test_structured_font_metadata_comes_from_the_same_main_span(tmp_path: Path) -> None:
    from lib.text_extract import gather_structured_text

    pdf = tmp_path / "mixed-font.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=800)
        page.insert_text((65, 130), "1", fontname="Times-Bold", fontsize=7)
        page.insert_text(
            (68.5, 130), " Most of this line is an ordinary Helvetica sentence.",
            fontname="Helvetica", fontsize=11,
        )
        doc.save(pdf)

    paragraph = gather_structured_text(str(pdf)).paragraphs[0]

    assert paragraph.font_name == "Helvetica"
    assert paragraph.font_size == pytest.approx(11.0)
    assert paragraph.is_bold is False


def test_long_numbered_heading_requires_body_sized_font() -> None:
    """BUG-190：长编号行放行后，小于正文的表格数据与伪代码不再成为标题。"""
    from lib.text_extract import looks_like_structural_heading

    assert looks_like_structural_heading(
        "6 return x with xi,j = 1 if j ∈argtopk(si −β), and 0 otherwise",
        is_bold=True, font_size=6.97, body_font_size=9.97,
    ) is False
    assert looks_like_structural_heading(
        "33.2 (MuQ-MuLan)\n(Zhu et al., 2025)\n25.0\n26.1\n21.6\n29.1\n29.3",
        is_bold=True, font_size=8.15, body_font_size=9.98,
    ) is False
    # 与正文同号的长编号章节标题仍然放行
    assert looks_like_structural_heading(
        "9.1 More Evaluation on Speech and Music Understanding",
        is_bold=True, font_size=9.96, body_font_size=9.98,
    ) is True


def test_single_column_paper_with_single_dual_column_appendix_stays_single_column(tmp_path: Path) -> None:
    """BUG-193 边界：长单栏正文（10 页）+ 末页双栏附录/致谢不应把整篇单栏文档判成双栏。"""
    from lib.text_extract import detect_dual_column_from_blocks, iter_native_text_blocks

    pdf = tmp_path / "single-with-dual-appendix.pdf"
    with fitz.open() as doc:
        for _ in range(10):
            page = doc.new_page(width=612, height=792)
            for row in range(12):
                page.insert_text(
                    (60, 80 + row * 22),
                    "This is a full width single column body paragraph sentence spanning across the page cleanly.",
                    fontsize=10.5,
                )
        appendix = doc.new_page(width=612, height=792)
        for row in range(10):
            appendix.insert_text((55, 80 + row * 22), "Left column reference entry text here.", fontsize=10.0)
            appendix.insert_text((320, 80 + row * 22), "Right column reference entry text here.", fontsize=10.0)
        doc.save(pdf)

    with fitz.open(pdf) as doc:
        blocks = iter_native_text_blocks(doc)
    assert detect_dual_column_from_blocks(blocks, 612.0) is False


def test_confirm_ordered_lists_chains_multi_item_block_and_demotes_isolated_midline_number() -> None:
    """BUG-195 边界：多项块(1./2.)续接 3. 保留 list；仅含孤立非连续中段编号的普通段落降回 paragraph。"""
    from lib.models import GatheredParagraph
    from lib.text_extract import _confirm_ordered_lists

    chain = [
        GatheredParagraph(
            page=1, text="1. First item\n2. Second item", bbox=(72, 100, 400, 128),
            is_heading=False, column=-1, font_size=10.5, para_type="list",
        ),
        GatheredParagraph(
            page=1, text="3. Third item", bbox=(72, 134, 400, 148),
            is_heading=False, column=-1, font_size=10.5, para_type="list",
        ),
    ]
    _confirm_ordered_lists(chain)
    assert [p.para_type for p in chain] == ["list", "list"]

    isolated = [
        GatheredParagraph(
            page=1, text="Narrative prose continuing here.\n99. Random mid-block note.",
            bbox=(72, 100, 400, 128), is_heading=False, column=-1, font_size=10.5, para_type="list",
        ),
        GatheredParagraph(
            page=1, text="1. Unrelated line", bbox=(72, 134, 400, 148),
            is_heading=False, column=-1, font_size=10.5, para_type="list",
        ),
    ]
    _confirm_ordered_lists(isolated)
    assert [p.para_type for p in isolated] == ["paragraph", "paragraph"]


def test_cross_page_ordered_list_skips_only_page_furniture() -> None:
    """WP-3.3：跨页 1./2. 可越过页码与小号页眉，普通正文不得作为跳过的桥梁。"""
    from lib.text_extract import _confirm_ordered_lists, gather_structured_text

    def para(text, page, y0, y1, size=10.9, para_type="paragraph"):
        return GatheredParagraph(
            page=page, text=text, bbox=(75.0, y0, 400.0, y1),
            is_heading=False, font_size=size, para_type=para_type, line_count=1,
        )

    # 真页脚在 gather 阶段剔除（见镜像页码端到端测试）；剩余数字即使恰好
    # 等于所在页号，也属于正文并阻断续接。
    paragraphs = [
        para("1. First policy item", 18, 748.0, 759.0),
        para("18", 18, 780.0, 789.0, size=8.0),
        para("2. Second policy item", 19, 87.0, 112.0),
    ]
    _confirm_ordered_lists(paragraphs)
    assert [p.para_type for p in paragraphs] == ["paragraph", "paragraph", "paragraph"]

    prose_between = [
        para("1. First policy item", 18, 748.0, 759.0),
        para("Ordinary prose continues on the next page before any new item.", 19, 55.0, 80.0),
        para("2. Second policy item", 19, 87.0, 98.0, para_type="list"),
    ]
    _confirm_ordered_lists(prose_between)
    assert prose_between[0].para_type == "paragraph"
    assert prose_between[-1].para_type == "paragraph"

    false_positive = [
        para(
            "This report states an isolated numbered reference.\n1. The first isolated reference",
            1, 110.0, 140.0, para_type="list",
        ),
        para("This is a genuine short footnote giving further evidence.", 1, 175.0, 185.0, size=8.0),
        para("1", 1, 750.0, 758.0, size=8.0),
        para("This is a genuine small-font source note, not a running heading.", 2, 55.0, 65.0, size=8.0),
        para("2. The second isolated reference", 2, 240.0, 251.0, para_type="list"),
    ]
    _confirm_ordered_lists(false_positive)
    assert false_positive[0].para_type == "paragraph"
    assert false_positive[-1].para_type == "paragraph"
    assert false_positive[1].para_type == false_positive[3].para_type == "paragraph"

    benchmark = PROJECT_ROOT / "tests" / "basic-benchmark"
    gathered = gather_structured_text(str(next(benchmark.glob("gemini_v2_5*.pdf"))))
    first = next(p for p in gathered.paragraphs if p.text == "1. Child sexual abuse and exploitation")
    following = next(p for p in gathered.paragraphs if p.text.startswith("2. Hate speech"))
    assert (first.page, following.page) == (18, 19)
    assert first.para_type == following.para_type == "list"

    from markdown_it import MarkdownIt

    from core.pdf_to_markdown import _paragraphs_to_document
    from lib.markdown import render_markdown

    document = _paragraphs_to_document(
        "gemini.pdf", "Gemini",
        SimpleNamespace(text_layer_ratio=1.0, has_text_layer=True, warnings=[]),
        gathered=gathered,
    )
    markdown = render_markdown(document)
    lines = markdown.splitlines()
    markers = [
        index for index, line in enumerate(lines)
        if line.startswith(("1. Child sexual abuse", "2. Hate speech", "6. Medical advice"))
    ]
    list_ranges = [
        token.map for token in MarkdownIt("commonmark").parse(markdown)
        if token.type == "ordered_list_open" and token.map is not None
    ]
    assert len(markers) == 3
    assert any(all(start <= marker < end for marker in markers) for start, end in list_ranges)


def test_mixed_dual_column_document_keeps_single_column_page_in_y_order(tmp_path: Path) -> None:
    """BUG-202：文档级双栏不得把单栏页的右对齐签名移到页末。"""
    from lib.text_extract import gather_structured_text

    pdf = tmp_path / "mixed-single-dual-pages.pdf"
    with fitz.open() as doc, fitz.open() as left, fitz.open() as right:
        page = doc.new_page(width=600, height=800)
        left_page = left.new_page(width=600, height=800)
        right_page = right.new_page(width=600, height=800)
        for index in range(6):
            y = 110 + index * 27
            left_page.insert_text((45, y), f"Left-column paragraph number {index} explains the study.", fontsize=11)
            right_page.insert_text((325, y), f"Right-column paragraph number {index} presents a result.", fontsize=11)
        page.show_pdf_page(page.rect, left, 0)
        page.show_pdf_page(page.rect, right, 0)
        single = doc.new_page(width=600, height=800)
        single.insert_text((45, 100), "First block of the single-column page starts on the left.", fontsize=11)
        single.insert_text((327, 135), "Second block is a right-aligned signature.", fontsize=11)
        single.insert_text((45, 174), "Third block resumes on the left below the signature.", fontsize=11)
        single.insert_text((45, 220), "This is the last paragraph of the single column.", fontsize=11)
        doc.save(pdf)

    gathered = gather_structured_text(str(pdf))
    page2 = [p.text for p in gathered.paragraphs if p.page == 2]

    assert gathered.is_dual_column is True
    assert page2 == [
        "First block of the single-column page starts on the left.",
        "Second block is a right-aligned signature.",
        "Third block resumes on the left below the signature.",
        "This is the last paragraph of the single column.",
    ]


def test_sparse_body_with_long_table_cells_stays_single_column(tmp_path: Path) -> None:
    """CHK-091 表格残余：6 行宽正文 + 22 行小字号长单元格不是双栏正文。"""
    from lib.text_extract import gather_structured_text

    pdf = tmp_path / "sparse-body-two-column-table.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=612, height=792)
        for index in range(6):
            page.insert_text(
                (54, 70 + index * 12),
                f"Body {index} ordinary full width prose spans the page with enough words to establish the main font.",
                fontsize=10,
            )
        for row in range(22):
            for x, side in ((58, "A"), (313, "B")):
                text = f"{side}{row} table cell contains enough text to enter narrow-line geometry sampling"
                while len(text) > 8 and fitz.get_text_length(text, fontsize=8) > 150.0:
                    text = text[:-1]
                page.insert_text((x, 460 + row * 11), text, fontsize=8)
        doc.save(pdf)

    from lib.text_extract import extract_text_with_format

    assert gather_structured_text(str(pdf)).is_dual_column is False
    assert extract_text_with_format(str(pdf)).num_columns == 1


def test_single_page_long_abstract_does_not_hide_dual_column_body(tmp_path: Path) -> None:
    """CHK-091 S16：单页通栏摘要略多于正文时仍识别下方的双栏正文。"""
    from lib.text_extract import gather_structured_text

    pdf = tmp_path / "single-page-long-abstract.pdf"
    with fitz.open() as doc, fitz.open() as left, fitz.open() as right:
        page = doc.new_page(width=612, height=792)
        page.insert_text((54, 70), "A Unified Architecture for Two-Column Academic Paper Layout Analysis", fontsize=14)
        for index in range(12):
            page.insert_text(
                (54, 126 + index * 12),
                f"Abstract {index} provides enough full width prose to exercise the wide-character guard.",
                fontsize=10,
            )
        left_page = left.new_page(width=612, height=792)
        right_page = right.new_page(width=612, height=792)
        for index in range(12):
            page_text = f"Left {index} column body has ordinary prose with enough words for layout detection."
            while fitz.get_text_length(page_text, fontsize=10) > 240.0:
                page_text = page_text[:-1]
            left_page.insert_text((54, 290 + index * 12), page_text, fontsize=10)
            right_page.insert_text((318, 290 + index * 12), page_text.replace("Left", "Right"), fontsize=10)
        page.show_pdf_page(page.rect, left, 0)
        page.show_pdf_page(page.rect, right, 0)
        doc.save(pdf)

    gathered = gather_structured_text(str(pdf))

    assert gathered.is_dual_column is True
    left = [p for p in gathered.paragraphs if "Left" in p.text]
    right = [p for p in gathered.paragraphs if "Right" in p.text]
    assert left and right
    assert max(p.bbox[1] for p in left) < min(p.bbox[1] for p in right) or all(
        p.column == 0 for p in left
    ) and all(p.column == 1 for p in right)


def test_bottom_numeric_blocks_require_page_sequence_evidence(tmp_path: Path) -> None:
    """CHK-092：真实数字单元格保留，跨页同位置的页码序列仍剔除。"""
    from lib.text_extract import gather_structured_text

    genuine = tmp_path / "genuine-bottom-numbers.pdf"
    with fitz.open() as doc:
        for page_index, value in enumerate((42, 99)):
            page = doc.new_page(width=612, height=792)
            page.insert_text((72, 100), f"Ordinary body on page {page_index + 1}.", fontsize=11)
            page.insert_text((300, 770), str(value), fontsize=9)
        doc.save(genuine)
    genuine_texts = [p.text for p in gather_structured_text(str(genuine)).paragraphs]
    assert "42" in genuine_texts and "99" in genuine_texts

    numbered = tmp_path / "actual-page-number-sequence.pdf"
    with fitz.open() as doc:
        for page_index in range(3):
            page = doc.new_page(width=612, height=792)
            page.insert_text((72, 100), f"Ordinary body on page {page_index + 1}.", fontsize=11)
            page.insert_text((300, 770), str(page_index + 1), fontsize=9)
        doc.save(numbered)
    numbered_texts = [p.text for p in gather_structured_text(str(numbered)).paragraphs]
    assert len(numbered_texts) == 3
    assert all(text.startswith("Ordinary body") for text in numbered_texts)


def test_repeated_margin_text_is_removed_only_in_margin_zone(tmp_path: Path) -> None:
    """CHK-094：页眉/页脚同名文本只能删除实际位于页边的块，正文同名标题保留。"""
    from lib.text_extract import gather_structured_text

    pdf = tmp_path / "repeated-margin-text.pdf"
    with fitz.open() as doc:
        for page_index in range(3):
            page = doc.new_page(width=600, height=800)
            if page_index < 2:
                page.insert_text((55, 63), "Safety checklist", fontsize=10)
                page.insert_text(
                    (55, 230),
                    "Detailed instructions follow." if page_index == 0
                    else "Verify the safety constraints.",
                    fontsize=10,
                )
            else:
                page.insert_text((55, 280), "Safety checklist", fontsize=10)
        doc.save(pdf)

    gathered = gather_structured_text(str(pdf))
    body_titles = [p for p in gathered.paragraphs if p.text == "Safety checklist"]

    assert gathered.headers_removed == ["Safety checklist"]
    assert [p.page for p in body_titles] == [3]
    assert any("Detailed instructions follow." in p.text for p in gathered.paragraphs)
    assert any("Verify the safety constraints." in p.text for p in gathered.paragraphs)


def test_bottom_numeric_table_cells_survive_page_number_filter(tmp_path: Path) -> None:
    """CHK-094：页底表格里的 42/43 虽然跨页连续，也不能按页码删除。"""
    from lib.text_extract import gather_structured_text

    pdf = tmp_path / "bottom-table-numbers.pdf"
    with fitz.open() as doc:
        for page_index, (value, label) in enumerate(((42, "Tensile yield"), (43, "Young modulus"))):
            page = doc.new_page(width=600, height=800)
            page.insert_text((60, 130), f"Test measurements, batch {chr(65 + page_index)}.", fontsize=10)
            page.insert_text((60, 740), str(value), fontsize=10)
            page.insert_text((200, 724), label, fontsize=10)
        doc.save(pdf)

    texts = [p.text for p in gather_structured_text(str(pdf)).paragraphs]

    assert "42" in texts and "43" in texts
    assert "Tensile yield" in texts and "Young modulus" in texts


def test_sparse_dual_column_page_inherits_confirmed_columns(tmp_path: Path) -> None:
    """CHK-094：尾页窄行不足 6 条时沿用已确认的左右栏位，不左右交替。"""
    from lib.text_extract import gather_structured_text

    pdf = tmp_path / "sparse-tail-columns.pdf"
    with fitz.open() as doc:
        dense = doc.new_page(width=600, height=800)
        for index in range(4):
            dense.insert_text((50, 100 + 50 * index), f"Left column text at row {index}.", fontsize=10)
            dense.insert_text((330, 100 + 50 * index), f"Right column text at row {index}.", fontsize=10)
        sparse = doc.new_page(width=600, height=800)
        for index in range(2):
            sparse.insert_text((50, 115 + 55 * index), f"Left sparse column paragraph {index}.", fontsize=10)
            sparse.insert_text((330, 123 + 55 * index), f"Right sparse column paragraph {index}.", fontsize=10)
        doc.save(pdf)

    gathered = gather_structured_text(str(pdf))
    sparse_paragraphs = [p for p in gathered.paragraphs if p.page == 2]

    assert gathered.is_dual_column is True
    assert [p.text for p in sparse_paragraphs] == [
        "Left sparse column paragraph 0.",
        "Left sparse column paragraph 1.",
        "Right sparse column paragraph 0.",
        "Right sparse column paragraph 1.",
    ]
    assert [p.column for p in sparse_paragraphs] == [0, 0, 1, 1]


def test_single_column_page_with_two_column_table_keeps_row_order(tmp_path: Path) -> None:
    """CHK-094：通栏正文 + 同字号双列表格仍按行输出标签和读数，不误判双栏。"""
    from lib.text_extract import gather_structured_text

    pdf = tmp_path / "single-column-data-table.pdf"
    wide = "The preceding discussion describes a method for checking readings in each recorded experiment."
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=800)
        for index in range(5):
            page.insert_text((50, 150 + index * 19), f"{wide} {index}.", fontsize=10)
        for index in range(5):
            page.insert_text((50, 360 + index * 40), f"Descriptive label for the experiment group. {index}", fontsize=10)
            page.insert_text((330, 373 + index * 40), f"Corresponding readings in this column. {index}", fontsize=10)
        doc.save(pdf)

    gathered = gather_structured_text(str(pdf))
    table_rows = [
        p.text for p in gathered.paragraphs
        if p.text.startswith(("Descriptive label", "Corresponding readings"))
    ]

    assert gathered.num_columns == 1
    assert table_rows == [
        item
        for index in range(5)
        for item in (
            f"Descriptive label for the experiment group. {index}",
            f"Corresponding readings in this column. {index}",
        )
    ]


def test_cross_page_list_confirmation_rejects_mid_page_numbers(tmp_path: Path) -> None:
    """CHK-094：页面中部的 42 不是页码，不能充当跨页列表的桥梁。"""
    from lib.text_extract import gather_structured_text

    pdf = tmp_path / "mid-page-number-list.pdf"
    with fitz.open() as doc:
        first = doc.new_page(width=600, height=800)
        first.insert_text((60, 140), "1. Reported values use this reference label.", fontsize=10)
        first.insert_text((100, 270), "42", fontsize=10)
        second = doc.new_page(width=600, height=800)
        second.insert_text((60, 430), "2. Records here use another reference label.", fontsize=10)
        second.insert_text((80, 550), "Final unnumbered paragraph.", fontsize=10)
        doc.save(pdf)

    gathered = gather_structured_text(str(pdf))
    numbered = [p for p in gathered.paragraphs if p.text.startswith(("1.", "2."))]

    assert [p.para_type for p in numbered] == ["paragraph", "paragraph"]
    assert any(p.text == "42" for p in gathered.paragraphs)


@pytest.mark.parametrize(
    "labels", [("Tensile yield", "Young modulus"), ("Total observations", "Total observations")],
)
def test_bottom_table_numbers_sharing_a_row_with_labels_survive_page_number_filter(
    tmp_path: Path, labels: tuple[str, str],
) -> None:
    """CHK-095：极页边的表格数字与标签同行（各自独立成块）时不是页码。"""
    from lib.text_extract import gather_structured_text

    pdf = tmp_path / "bottom-grid-independent-numbers.pdf"
    with fitz.open() as doc:
        for page_index, label in enumerate(labels):
            page = doc.new_page(width=600, height=800)
            page.insert_text((330, 782), label, fontsize=10)
            page.insert_text((60, 130), f"Test measurements, batch {page_index + 1}.", fontsize=10)
            page.insert_text((60, 782), str(42 + page_index), fontsize=10)
            for y in (754, 792):
                page.draw_line((45, y), (555, y))
            for x in (45, 300, 555):
                page.draw_line((x, 754), (x, 792))
        doc.save(pdf)

    texts = [p.text for p in gather_structured_text(str(pdf)).paragraphs]

    assert "42" in texts and "43" in texts
    assert [text for text in texts if text in labels] == list(labels)


def test_page_number_beside_repeated_footer_text_is_still_removed(tmp_path: Path) -> None:
    """两端式页脚：页码与跨页重复的页脚文字同一行，页码仍按序列剔除。"""
    from lib.text_extract import gather_structured_text

    pdf = tmp_path / "footer-text-beside-page-number.pdf"
    with fitz.open() as doc:
        for page_index in range(3):
            page = doc.new_page(width=600, height=800)
            # 页码最后写入才与页脚文字分成两个原生块；写入顺序相反时两者并成一块，
            # 页码不是独立数字块，本就不进入页码候选。
            page.insert_text((330, 782), "Running footer text shared by every page.", fontsize=10)
            page.insert_text((60, 130), f"Chapter body paragraph number {page_index + 1}.", fontsize=10)
            page.insert_text((60, 782), str(page_index + 1), fontsize=10)
        doc.save(pdf)

    texts = [p.text for p in gather_structured_text(str(pdf)).paragraphs]

    assert not any(text in {"1", "2", "3"} for text in texts)
    assert not any(text.startswith("Running footer text") for text in texts)
    assert len([text for text in texts if text.startswith("Chapter body")]) == 3


@pytest.mark.parametrize("midpage_number", [None, "43"])
def test_cross_page_list_confirmation_rejects_unconfirmed_edge_numbers(
    tmp_path: Path, midpage_number: str | None,
) -> None:
    """CHK-095：页脚带里孤立的正文数值不是页码，不能连接两段独立的编号正文。"""
    from lib.text_extract import gather_structured_text

    pdf = tmp_path / "edge-body-number.pdf"
    with fitz.open() as doc:
        first = doc.new_page(width=600, height=800)
        first.insert_text((60, 690), "1. Reported values use this reference label.", fontsize=10)
        first.insert_text((100, 750), "42", fontsize=10)
        second = doc.new_page(width=600, height=800)
        second.insert_text((60, 230), "2. Records here use another reference label.", fontsize=10)
        if midpage_number:
            second.insert_text((100, 410), midpage_number, fontsize=10)
        second.insert_text((80, 550), "Final unnumbered paragraph.", fontsize=10)
        doc.save(pdf)

    gathered = gather_structured_text(str(pdf))
    numbered = [p for p in gathered.paragraphs if p.text.startswith(("1.", "2."))]

    assert [p.para_type for p in numbered] == ["paragraph", "paragraph"]
    assert any(p.text == "42" for p in gathered.paragraphs)
    if midpage_number:
        assert any(p.text == midpage_number for p in gathered.paragraphs)


def test_mirrored_footers_do_not_split_confirmed_list_in_markdown(tmp_path: Path) -> None:
    from markdown_it import MarkdownIt

    from core.pdf_to_markdown import main

    pdf = tmp_path / "mirrored-footer-list.pdf"
    with fitz.open() as doc:
        for page_index in range(2):
            page = doc.new_page(width=600, height=800)
            first_y = 580 if page_index == 0 else 130
            for item in range(2):
                number = page_index * 2 + item + 1
                page.insert_text((60, first_y + item * 26), f"{number}. Running list item number {number}.")
            page.insert_text(((60, 780), (535, 780))[page_index], str(page_index + 1), fontsize=10)
        doc.save(pdf)

    out = tmp_path / "markdown" / "paper.md"
    assert main(["--pdf", str(pdf), "--out", str(out), "--images", "off", "--tables", "off"]) == 0
    markdown = out.read_text(encoding="utf-8")
    tokens = MarkdownIt("commonmark").parse(markdown)
    assert sum(t.type == "ordered_list_open" for t in tokens) == 1
    assert sum(t.type == "list_item_open" for t in tokens) == 4
    assert "<!-- page 2 -->" not in markdown
    assert not {"1", "2"}.intersection(markdown.splitlines())


@pytest.mark.parametrize(
    "offset",
    [
        pytest.param(0, id="printed-number-equals-pdf-page"),
        pytest.param(-1, id="printed-number-offset-by-cover-page"),
    ],
)
def test_alternating_page_numbers_still_bridge_cross_page_lists(tmp_path: Path, offset: int) -> None:
    """页码左右交替（或带固定偏移）时跨页同位置序列不成立，页码留在段落里，仍须能连接列表。

    offset=-1 时多一页不带页码的封面：印刷页码比 PDF 页号小 1，只能靠
    相邻页数字的连续性认出它是页码。
    """
    from lib.text_extract import gather_structured_text

    pdf = tmp_path / f"alternating-page-numbers-{offset}.pdf"
    with fitz.open() as doc:
        page_count = 2 - offset
        for page_index in range(page_count):
            page = doc.new_page(width=600, height=800)
            item_number = page_index + 1 + offset
            number = item_number
            if number >= 1:
                # 页码按页奇偶左右交替：跨页同位置的序列不成立，页码不会被提前删除
                page.insert_text(((60, 780), (540, 40))[page_index % 2], str(number), fontsize=10)
            if item_number >= 1:
                page.insert_text((60, 300), f"{item_number}. Item number {item_number} of the list.", fontsize=10)
            else:
                page.insert_text((60, 300), "Cover page without a printed number.", fontsize=10)
        doc.save(pdf)

    gathered = gather_structured_text(str(pdf))
    numbered = [p for p in gathered.paragraphs if p.text.startswith(("1. Item", "2. Item"))]

    assert [p.para_type for p in numbered] == ["list", "list"]


WIDE_BODY_SENTENCE = (
    "The preceding discussion describes a method for checking readings in each recorded experiment."
)


def _draw_two_column_grid(page: "fitz.Page", ys: tuple, label: str) -> None:
    """五行双列网格，每个单元格两行；带框线。

    与 CHK-095 的复现探针同一写法：单元格两行用一次带换行的写入，提取器才会
    把每个单元格作为一个两行的原生块；逐行分写会并成左右连片的整行块。
    """
    second_line = "A second long line within this cell."
    for index in range(5):
        page.insert_text((50, ys[0] + 17 + index * 55), f"Descriptive {label} group {index}\n{second_line}", fontsize=10)
        page.insert_text((330, ys[0] + 22 + index * 55), f"Corresponding measurement group {index}\n{second_line}", fontsize=10)
    for y in ys:
        page.draw_line((45, y), (555, y))
    for x in (45, 300, 555):
        page.draw_line((x, ys[0]), (x, ys[-1]))


@pytest.mark.parametrize("body_lines", [pytest.param(5, id="five-body-lines"), pytest.param(8, id="eight-body-lines")])
def test_two_column_table_with_wrapped_cells_keeps_row_order(tmp_path: Path, body_lines: int) -> None:
    """CHK-095：单元格换成两行后，双列表格仍不能被当成双栏正文。"""
    from lib.text_extract import gather_structured_text

    pdf = tmp_path / f"wide-body-wrapped-grid-{body_lines}.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=800)
        for index in range(body_lines):
            page.insert_text((50, 150 + index * 19), WIDE_BODY_SENTENCE, fontsize=10)
        _draw_two_column_grid(page, (326, 379, 434, 489, 544, 600), "experiment")
        doc.save(pdf)

    gathered = gather_structured_text(str(pdf))
    table_cells = [
        p.text.splitlines()[0] for p in gathered.paragraphs
        if p.text.startswith(("Descriptive experiment", "Corresponding measurement"))
    ]

    assert gathered.num_columns == 1
    assert table_cells == [
        text
        for index in range(5)
        for text in (f"Descriptive experiment group {index}", f"Corresponding measurement group {index}")
    ]


def test_sparse_page_with_wide_body_does_not_inherit_columns(tmp_path: Path) -> None:
    """CHK-095：双栏正文之后的稀疏页若有通栏正文，其两列表格按行输出，不继承栏位。"""
    from lib.text_extract import gather_structured_text

    pdf = tmp_path / "sparse-two-row-grid.pdf"
    with fitz.open() as doc:
        dense = doc.new_page(width=600, height=800)
        for index in range(4):
            dense.insert_text((50, 100 + 50 * index), f"Left column text at row {index}.", fontsize=10)
            dense.insert_text((330, 108 + 50 * index), f"Right column text at row {index}.", fontsize=10)
        sparse = doc.new_page(width=600, height=800)
        sparse.insert_text((50, 150), WIDE_BODY_SENTENCE, fontsize=10)
        sparse.insert_text((50, 169), WIDE_BODY_SENTENCE, fontsize=10)
        sparse.insert_text((50, 360), "Descriptive label for experiment group A.", fontsize=10)
        sparse.insert_text((330, 373), "Corresponding readings for group A.", fontsize=10)
        sparse.insert_text((50, 400), "Descriptive label for experiment group B.", fontsize=10)
        sparse.insert_text((330, 413), "Corresponding readings for group B.", fontsize=10)
        for y in (342, 388, 430):
            sparse.draw_line((45, y), (555, y))
        for x in (45, 300, 555):
            sparse.draw_line((x, 342), (x, 430))
        doc.save(pdf)

    gathered = gather_structured_text(str(pdf))
    sparse_paragraphs = [p for p in gathered.paragraphs if p.page == 2]

    assert gathered.is_dual_column is True
    assert all(p.column == 0 for p in gathered.paragraphs if p.page == 1 and p.text.startswith("Left"))
    assert [(p.column, p.text) for p in sparse_paragraphs] == [
        (-1, WIDE_BODY_SENTENCE),
        (-1, WIDE_BODY_SENTENCE),
        (-1, "Descriptive label for experiment group A."),
        (-1, "Corresponding readings for group A."),
        (-1, "Descriptive label for experiment group B."),
        (-1, "Corresponding readings for group B."),
    ]


@pytest.mark.parametrize("right_first", [False, True])
def test_narrow_gutter_ruled_table_keeps_rows_and_cells_in_order(
    tmp_path: Path, right_first: bool,
) -> None:
    from lib.text_extract import gather_structured_text

    pdf = tmp_path / "ruled-table.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=800)
        for index in range(11):
            page.insert_text((50, 100 + index * 19), WIDE_BODY_SENTENCE, fontsize=10)
        for row in range(5):
            y = 345 + row * 55
            for x, dy, name in ((50, 0, "Label"), (320, -5 if right_first else 5, "Reading")):
                page.insert_text(
                    (x, y + dy),
                    f"{name} cell {row} contains grouped results and extended\n"
                    "The second line describes grouped results and extended",
                    fontsize=10,
                )
        for y in (329, 391, 446, 501, 556, 610):
            page.draw_line((45, y), (582, y))
        for x in (45, 310, 582):
            page.draw_line((x, 329), (x, 610))
        doc.save(pdf)

    result = gather_structured_text(str(pdf))
    cells = [p.text.split()[:3] for p in result.paragraphs if p.text.startswith(("Label cell", "Reading cell"))]
    assert result.num_columns == 1
    assert cells == [[kind, "cell", str(row)] for row in range(5) for kind in ("Label", "Reading")]
