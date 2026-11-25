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
