#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #4 / #5 / #6 / #7 回归测试（2026-10-06，2026-10-07 增补）。

- #4  [中] 多行标题必须归一为单行 ATX 标题（BUG-141）；独立公式碎片区域
       必须整块保留——图片开启时按原页截图、关闭时合并代码块（BUG-145）；
- #5  [高] 加密/0 页 PDF 预检须判无效（text_extract.py pre_validate_pdf），
       两个入口以 [ERROR] PDF validation failed 干净退出且 rc≠0；
- #6  [中] --dpi / --clip-height / --table-clip-height 必须有 >0 且有限的
       下界校验，非法值走 parser.error（SystemExit code=2）、不留 0 字节 PNG；
       渲染硬失败必须清理残骸并以非零退出码传播（BUG-142）；
- #7  [中] 输出路径（含父链与隐式 text 目录）撞已存在目录/文件时提前检测，
       中文提示且 rc=2，不再裸 PermissionError/FileExistsError（BUG-143）。
"""

import hashlib
import inspect
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "skills", "pdf-markdown-summary", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import fitz

from core import extract_pdf_assets as extract_pdf_assets_module
from core.pdf_to_markdown import main as pdf_to_markdown_main
from lib.text_extract import pre_validate_pdf


def _make_text_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=420, height=320)
    page.insert_text((48, 72), "Issue regression smoke test.", fontsize=12)
    doc.save(path)
    doc.close()


def _make_encrypted_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Secret", fontsize=12)
    doc.save(
        path,
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="owner",
        user_pw="user",
    )
    doc.close()


def _write_zero_page_pdf(path: Path) -> None:
    # PyMuPDF 拒绝保存 0 页文档，按 issue 手工构造
    path.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [] /Count 0 >> endobj\n"
        b"trailer << /Root 1 0 R /Size 3 >>\n%%EOF\n"
    )


# ==========================================================================
# #5 加密 / 0 页 PDF
# ==========================================================================


def test_pre_validate_marks_unreadable_encrypted_pdf_invalid(tmp_path: Path) -> None:
    pdf = tmp_path / "enc.pdf"
    _make_encrypted_pdf(pdf)
    result = pre_validate_pdf(str(pdf))
    assert result.is_valid is False
    assert any("encrypted" in e.lower() for e in result.errors), result.errors


def test_pre_validate_marks_zero_page_pdf_invalid(tmp_path: Path) -> None:
    pdf = tmp_path / "zeropage.pdf"
    _write_zero_page_pdf(pdf)
    result = pre_validate_pdf(str(pdf))
    assert result.is_valid is False
    assert any("no pages" in e.lower() for e in result.errors), result.errors


def test_pdf_to_markdown_encrypted_pdf_exits_cleanly(tmp_path: Path) -> None:
    pdf = tmp_path / "enc.pdf"
    _make_encrypted_pdf(pdf)
    out_md = tmp_path / "o.md"
    assert pdf_to_markdown_main(["--pdf", str(pdf), "--out", str(out_md)]) == 1
    assert not out_md.exists(), "预检失败时不得写出 Markdown"


def test_extract_pdf_assets_encrypted_pdf_exits_cleanly(tmp_path: Path) -> None:
    pdf = tmp_path / "enc.pdf"
    _make_encrypted_pdf(pdf)
    assert extract_pdf_assets_module.main(
        ["--pdf", str(pdf), "--out-dir", str(tmp_path / "img")]
    ) == 1


def test_pdf_to_markdown_zero_page_pdf_exits_cleanly(tmp_path: Path) -> None:
    pdf = tmp_path / "zeropage.pdf"
    _write_zero_page_pdf(pdf)
    assert pdf_to_markdown_main(["--pdf", str(pdf), "--out", str(tmp_path / "z.md")]) == 1


# ==========================================================================
# #6 --dpi / --clip-height 下界校验
# ==========================================================================


@pytest.mark.parametrize(
    "argv_fragment",
    [
        ["--dpi", "0"],
        ["--dpi", "-5"],
        ["--clip-height", "0"],
        ["--clip-height", "-500"],
        ["--table-clip-height", "0"],
        ["--table-clip-height", "-1.5"],
    ],
)
def test_parser_rejects_non_positive_geometry(argv_fragment) -> None:
    with pytest.raises(SystemExit) as excinfo:
        extract_pdf_assets_module.parse_args_modular(["--pdf", "x.pdf", *argv_fragment])
    assert excinfo.value.code == 2, "非法几何参数应以 argparse error（code=2）退出"


def test_parser_accepts_positive_geometry(tmp_path: Path) -> None:
    # tmp_path 未被使用，但保持与独立运行器 main_test 统一的 (tmp_path) 签名，
    # 否则 `python tests/scripts/test_issue_regressions_20261006.py` 固定失败。
    args = extract_pdf_assets_module.parse_args_modular(
        ["--pdf", "x.pdf", "--dpi", "72", "--clip-height", "100", "--table-clip-height", "50"]
    )
    assert args.dpi == 72
    assert args.clip_height == 100.0
    assert args.table_clip_height == 50.0


# ==========================================================================
# #7 输出路径撞已存在目录/文件
# ==========================================================================


def test_pdf_to_markdown_out_is_existing_dir_returns_2(tmp_path: Path) -> None:
    pdf = tmp_path / "ok.pdf"
    _make_text_pdf(pdf)
    adir = tmp_path / "adir"
    adir.mkdir()
    assert pdf_to_markdown_main(["--pdf", str(pdf), "--out", str(adir)]) == 2


def test_pdf_to_markdown_asset_dir_is_existing_file_returns_2(tmp_path: Path) -> None:
    pdf = tmp_path / "ok.pdf"
    _make_text_pdf(pdf)
    afile = tmp_path / "afile"
    afile.write_text("x", encoding="utf-8")
    assert pdf_to_markdown_main(
        ["--pdf", str(pdf), "--out", str(tmp_path / "o.md"), "--asset-dir", str(afile)]
    ) == 2


def test_extract_pdf_assets_index_json_is_existing_dir_returns_2(tmp_path: Path) -> None:
    pdf = tmp_path / "ok.pdf"
    _make_text_pdf(pdf)
    adir = tmp_path / "adir"
    adir.mkdir()
    assert extract_pdf_assets_module.main(
        ["--pdf", str(pdf), "--out-dir", str(tmp_path / "img"), "--index-json", str(adir)]
    ) == 2


def test_extract_pdf_assets_out_dir_is_existing_file_returns_2(tmp_path: Path) -> None:
    pdf = tmp_path / "ok.pdf"
    _make_text_pdf(pdf)
    afile = tmp_path / "afile"
    afile.write_text("x", encoding="utf-8")
    assert extract_pdf_assets_module.main(
        ["--pdf", str(pdf), "--out-dir", str(afile)]
    ) == 2


# ==========================================================================
# #4 续（BUG-141）：多行标题序列化必须归一为单行
# ==========================================================================


def test_render_block_normalizes_multiline_heading(tmp_path: Path) -> None:
    from lib.markdown import MarkdownBlock, render_block

    block = MarkdownBlock(
        type="heading",
        text="2.1 \nTasks as Attribute Value Matrices",
        level=2,
    )
    rendered = render_block(block)
    assert rendered == "## 2.1 Tasks as Attribute Value Matrices"
    assert "\n" not in rendered


def test_render_block_heading_parses_as_single_atx_heading(tmp_path: Path) -> None:
    # 真实 Markdown 解析回归：标题内部换行会把后半段漏成正文段落
    from markdown_it import MarkdownIt

    from lib.markdown import MarkdownBlock, render_markdown, MarkdownDocument

    document = MarkdownDocument(
        title="t",
        source_pdf="x.pdf",
        blocks=[MarkdownBlock(type="heading", text="2.4 \nEvaluation Metrics", level=2)],
    )
    tokens = MarkdownIt().parse(render_markdown(document))
    headings = [t for t in tokens if t.type == "heading_open"]
    assert len(headings) == 2  # 文档标题 + 该标题，不得拆出正文段落
    inline = tokens[tokens.index(headings[1]) + 1]
    assert inline.content == "2.4 Evaluation Metrics"


def test_render_block_paragraph_keeps_internal_newlines(tmp_path: Path) -> None:
    from lib.markdown import MarkdownBlock, render_block

    block = MarkdownBlock(type="paragraph", text="line one\nline two")
    assert render_block(block) == "line one\nline two"


# ==========================================================================
# #6 续（BUG-142）：nan/inf 拒绝 + 渲染硬失败清理与非零退出
# ==========================================================================


@pytest.mark.parametrize("option", ["--clip-height", "--table-clip-height"])
@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_parser_rejects_non_finite_geometry(option, value, tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as excinfo:
        extract_pdf_assets_module.parse_args_modular(["--pdf", "x.pdf", option, value])
    assert excinfo.value.code == 2, "nan/inf 必须以 argparse error（code=2）拒绝"


def _make_figure_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=420, height=400)
    page.draw_rect(fitz.Rect(70, 100, 350, 220), color=(0, 0, 0), fill=(0.2, 0.4, 0.6))
    page.insert_text((70, 240), "Figure 1: Checkerboard sample", fontsize=10)
    page.insert_text((50, 310), "Body text for issue regression testing.", fontsize=10)
    doc.save(path)
    doc.close()


def _failed_pixmap_save(self, path, *args, **kwargs):
    # 复现 PyMuPDF 原 issue 的失败次序：先创建 0 字节文件再抛异常
    Path(path).write_bytes(b"")
    raise RuntimeError("injected pixmap save failure")


def test_render_failure_leaves_no_zero_byte_png_and_returns_nonzero(tmp_path: Path) -> None:
    pdf = tmp_path / "fig.pdf"
    _make_figure_pdf(pdf)
    out_dir = tmp_path / "images"
    with patch.object(fitz.Pixmap, "save", _failed_pixmap_save):
        rc = extract_pdf_assets_module.main([
            "--pdf", str(pdf),
            "--out-dir", str(out_dir),
            "--out-text", str(tmp_path / "txt" / "source.txt"),
            "--no-tables",
        ])
    assert rc != 0, "渲染硬失败不得返回 0"
    zero_pngs = [p for p in out_dir.glob("*.png") if p.stat().st_size == 0]
    assert zero_pngs == [], f"渲染失败不得留下 0 字节残骸: {zero_pngs}"


def test_pdf_to_markdown_render_failure_propagates_failed_status(tmp_path: Path) -> None:
    pdf = tmp_path / "fig.pdf"
    _make_figure_pdf(pdf)
    report_json = tmp_path / "txt" / "report.json"
    images = tmp_path / "images"
    with patch.object(fitz.Pixmap, "save", _failed_pixmap_save):
        rc = pdf_to_markdown_main([
            "--pdf", str(pdf),
            "--out", str(tmp_path / "out.md"),
            "--asset-dir", str(images),
            "--images", "figures",
            "--tables", "off",
            "--report-json", str(report_json),
        ])
    assert rc != 0, "渲染硬失败必须向上游传播非零退出码"
    report = json.loads(report_json.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["assets"]["exit_code"] != 0
    zero_pngs = [p for p in images.glob("*.png") if p.stat().st_size == 0]
    assert zero_pngs == [], f"补裁/渲染失败不得留下 0 字节残骸: {zero_pngs}"


# ==========================================================================
# #7 续（BUG-143）：输出父路径与隐式 text 目录冲突必须提前 rc=2
# ==========================================================================


def test_pdf_to_markdown_out_parent_is_file_returns_2(tmp_path: Path) -> None:
    pdf = tmp_path / "ok.pdf"
    _make_text_pdf(pdf)
    blocker = tmp_path / "blocker"
    blocker.write_text("existing user file", encoding="utf-8")
    assert pdf_to_markdown_main([
        "--pdf", str(pdf), "--out", str(blocker / "out.md"),
        "--images", "off", "--tables", "off",
    ]) == 2
    assert blocker.read_text(encoding="utf-8") == "existing user file", "既有文件内容不得被破坏"


def test_extract_index_json_parent_is_file_returns_2(tmp_path: Path) -> None:
    pdf = tmp_path / "ok.pdf"
    _make_text_pdf(pdf)
    blocker = tmp_path / "blocker"
    blocker.write_text("existing user file", encoding="utf-8")
    assert extract_pdf_assets_module.main([
        "--pdf", str(pdf),
        "--out-dir", str(tmp_path / "images"),
        "--out-text", str(tmp_path / "txt" / "source.txt"),
        "--index-json", str(blocker / "index.json"),
    ]) == 2
    assert blocker.read_text(encoding="utf-8") == "existing user file", "既有文件内容不得被破坏"


def test_pdf_to_markdown_text_dir_is_existing_file_returns_2(tmp_path: Path) -> None:
    pdf = tmp_path / "ok.pdf"
    _make_text_pdf(pdf)
    (tmp_path / "text").write_text("existing user file", encoding="utf-8")
    assert pdf_to_markdown_main([
        "--pdf", str(pdf), "--out", str(tmp_path / "out.md"),
        "--images", "off", "--tables", "off",
    ]) == 2
    assert (tmp_path / "text").read_text(encoding="utf-8") == "existing user file"


# ==========================================================================
# #4 续（BUG-145）：独立公式碎片区域整块保留
# ==========================================================================


def _make_equation_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=420, height=500)
    page.insert_text((40, 80), "We compute the kappa agreement metric for this evaluation.", fontsize=10)
    page.insert_text((40, 95), "The score combines observed and expected agreement rates.", fontsize=10)
    # OCR 把分式公式拆成三段：分子、分数线 K--、分母
    page.insert_text((150, 140), "P(A) - P(E)", fontsize=10)
    page.insert_text((150, 158), "K--", fontsize=10)
    page.insert_text((160, 176), "1 - P(E)", fontsize=10)
    page.insert_text((40, 220), "Higher values indicate better overall annotation quality.", fontsize=10)
    doc.save(path)
    doc.close()


def test_detect_equation_groups_merges_ocr_fragments(tmp_path: Path) -> None:
    from lib.equation_regions import detect_equation_groups
    from lib.text_extract import gather_structured_text

    pdf = tmp_path / "eq.pdf"
    _make_equation_pdf(pdf)
    gathered = gather_structured_text(str(pdf))
    items = [(i, p.page, list(p.bbox), p.text) for i, p in enumerate(gathered.paragraphs)]
    groups = detect_equation_groups(items)
    assert len(groups) == 1, "三个公式碎片必须合并为一个公式区域"
    assert len(groups[0].member_keys) == 3
    texts = {gathered.paragraphs[k].text for k in groups[0].member_keys}
    assert texts == {"P(A) - P(E)", "K--", "1 - P(E)"}


def test_detect_equation_groups_skips_asset_overlaps_and_non_equations(tmp_path: Path) -> None:
    from lib.equation_regions import detect_equation_groups

    items = [
        (0, 1, [150.0, 129.2, 217.0, 143.0], "K = P(A) - P(E)"),
        (1, 1, [160.0, 147.2, 194.4, 161.0], "1 - P(E)"),
        (2, 1, [40.0, 200.0, 300.0, 212.0], "Figure 3: Scatter plot of the kappa = agreement"),
        (3, 1, [40.0, 220.0, 60.0, 232.0], "42"),
    ]
    # 资产区域完全覆盖第一个碎片 → 该碎片跳过，只剩分母单独成组
    exclusions = [(1, [140.0, 125.0, 230.0, 150.0])]
    groups = detect_equation_groups(items, exclusions=exclusions)
    assert [k for g in groups for k in g.member_keys] == [1]
    # 无排除时题注与页码仍不得入选
    groups = detect_equation_groups(items)
    member_keys = {k for g in groups for k in g.member_keys}
    assert 2 not in member_keys and 3 not in member_keys


def test_affiliation_en_dash_is_not_equation_fragment(tmp_path: Path) -> None:
    # PARADISE 实测误检：作者单位行的 LaTeX en-dash（Labs--Research）
    # 命中分式线模式；长文本的分式线不得作为强信号
    from lib.equation_regions import _is_equation_fragment

    assert _is_equation_fragment("AT&T Labs--Research") is False
    assert _is_equation_fragment("K--") is True


def test_detect_equation_groups_columns_do_not_break_grouping(tmp_path: Path) -> None:
    # 双栏页左右栏公式碎片纵向交错（左分子 y100、右求和限 y115、左分母 y128）：
    # 单趟顺序分组会在栏切换时把左栏公式拆成两段，必须按栏独立分组
    from lib.equation_regions import detect_equation_groups

    items = [
        (0, 2, [40.0, 40.0, 200.0, 52.0], "Left column body text line one here."),
        (1, 2, [220.0, 40.0, 380.0, 52.0], "Right column body text line one here."),
        (2, 2, [40.0, 420.0, 200.0, 432.0], "Left column body text line two here."),
        (3, 2, [220.0, 420.0, 380.0, 432.0], "Right column body text line two here."),
        (4, 2, [70.0, 100.0, 150.0, 112.0], "P(A) - P(E)"),
        (5, 2, [250.0, 115.0, 310.0, 127.0], "N'(x) ="),
        (6, 2, [80.0, 128.0, 140.0, 140.0], "1 - P(E)"),
    ]
    groups = detect_equation_groups(items)
    member_sets = sorted(sorted(g.member_keys) for g in groups)
    assert member_sets == [[4, 6], [5]], "左栏分子分母必须同组，右栏碎片独立成组"


def test_detect_equation_groups_absorbs_line_neighbors(tmp_path: Path) -> None:
    # Alexa 实测截断：原生公式行被拆成两个文本块，左侧被定义量
    # （`ϵ-accuracy`，无强数学信号）是独立块；只按命中碎片截取会截断公式，
    # 同视觉行紧邻的窄块必须并入区域
    from lib.equation_regions import detect_equation_groups

    items = [
        (0, 1, [54.0, 40.0, 340.0, 52.0], "The relative error rate is defined as follows."),
        (1, 1, [117.9, 254.2, 160.5, 264.4], "ϵ -accuracy"),
        (2, 1, [163.2, 251.0, 298.2, 265.6], "def =   P ( d  − d 1   < ϵ ) (4)"),
        (3, 1, [54.0, 276.3, 298.2, 358.0], "In other words, this is the probability of choosing a device."),
    ]
    groups = detect_equation_groups(items)
    assert len(groups) == 1
    assert sorted(groups[0].member_keys) == [1, 2], "左侧被定义量必须并入公式区域"
    assert groups[0].bbox[0] <= 117.9, "区域左界必须覆盖被定义量，避免截图截断"
    assert 3 not in groups[0].member_keys, "下方正文段落不得被吸收"


def test_equation_preserved_as_text_code_block_when_images_off(tmp_path: Path) -> None:
    pdf = tmp_path / "eq.pdf"
    _make_equation_pdf(pdf)
    report_json = tmp_path / "text" / "report.json"
    assert pdf_to_markdown_main([
        "--pdf", str(pdf), "--out", str(tmp_path / "out.md"),
        "--images", "off", "--tables", "off",
        "--report-json", str(report_json),
    ]) == 0
    md = (tmp_path / "out.md").read_text(encoding="utf-8")
    # 三个碎片必须收进同一个代码块，不得散落正文
    assert md.count("```") == 2, "图片关闭时公式区域必须合并为恰好一个代码块"
    fence = md.split("```")[1]
    for fragment in ("P(A) - P(E)", "K--", "1 - P(E)"):
        assert fragment in fence, f"碎片 {fragment} 必须保留在代码块内"
    assert "kappa agreement metric" in md, "正文段落保持原样"
    report = json.loads(report_json.read_text(encoding="utf-8"))
    assert report["equations"]["detected"] == 1
    assert report["equations"]["text_merged"] == 1


def test_equation_preserved_as_screenshot_when_images_on(tmp_path: Path) -> None:
    pdf = tmp_path / "eq.pdf"
    _make_equation_pdf(pdf)
    report_json = tmp_path / "text" / "report.json"
    assert pdf_to_markdown_main([
        "--pdf", str(pdf), "--out", str(tmp_path / "out.md"),
        "--images", "figures", "--tables", "off",
        "--report-json", str(report_json),
    ]) == 0
    md = (tmp_path / "out.md").read_text(encoding="utf-8")
    eq_pngs = list((tmp_path / "images").glob("Equation_p1_*.png"))
    assert len(eq_pngs) == 1, "公式区域必须按原页截图保留"
    assert eq_pngs[0].stat().st_size > 0
    assert f"](images/{eq_pngs[0].name}" in md, "Markdown 必须以相对路径引用公式截图"
    # 碎片不得再以独立段落形式出现（alt 文本除外）
    body_lines = [ln for ln in md.splitlines() if not ln.startswith("![")]
    assert not any(ln.strip() == "K--" for ln in body_lines)
    report = json.loads(report_json.read_text(encoding="utf-8"))
    assert report["equations"]["detected"] == 1
    assert report["equations"]["screenshot"] == 1


def test_short_assignment_sentence_is_not_an_equation(tmp_path: Path) -> None:
    # BUG-147：宽栏里的短正文「We set a=1.」含等号，但不能当成独立公式。
    # 仍保留「E = mc^2.」这类以句点结尾的真正公式。
    from lib.equation_regions import _is_equation_fragment, detect_equation_groups
    from lib.markdown import MarkdownBlock, MarkdownDocument
    from core.pdf_to_markdown import _preserve_equation_regions

    assert _is_equation_fragment("We set a=1.") is False
    assert _is_equation_fragment("E = mc^2.") is True
    items = [
        (0, 1, [40.0, 40.0, 360.0, 52.0], "Ordinary body paragraph spanning the column width."),
        (1, 1, [40.0, 250.0, 360.0, 262.0], "Ordinary body paragraph spanning the column width."),
        (2, 1, [70.0, 100.0, 180.0, 112.0], "We set a=1."),
    ]
    assert detect_equation_groups(items) == []
    document = MarkdownDocument(
        title="probe",
        source_pdf="probe.pdf",
        blocks=[
            MarkdownBlock(type="paragraph", text=text, page=page, meta={"bbox": list(bbox)})
            for _key, page, bbox, text in items
        ],
    )
    stats = _preserve_equation_regions(
        document,
        {"items": []},
        {"out_md": str(tmp_path / "out.md"), "asset_dir": str(tmp_path), "pdf_path": "unused.pdf"},
        images_enabled=False,
    )
    assert stats["detected"] == 0
    assert any(block.text == "We set a=1." for block in document.blocks)


def test_neighbor_absorption_stays_in_column_and_respects_barriers(tmp_path: Path) -> None:
    # BUG-146：邻块吸收不得跨栏、不得吞中间正文、不得把排除区重新并入。
    from lib.equation_regions import detect_equation_groups
    from lib.markdown import MarkdownBlock, MarkdownDocument
    from core.pdf_to_markdown import _preserve_equation_regions

    cross = [
        (0, 1, [40.0, 40.0, 200.0, 52.0], "Left column body text line one here."),
        (1, 1, [209.0, 40.0, 369.0, 52.0], "Right column body text line one here."),
        (2, 1, [40.0, 420.0, 200.0, 432.0], "Left column body text line two here."),
        (3, 1, [209.0, 420.0, 369.0, 432.0], "Right column body text line two here."),
        (4, 1, [130.0, 100.0, 200.0, 112.0], "y = x + z"),
        (5, 1, [209.0, 100.0, 250.0, 112.0], "Right prose."),
    ]
    groups = detect_equation_groups(cross)
    assert [g.member_keys for g in groups] == [[4]]
    assert groups[0].bbox[2] <= 200.0

    between = [
        (0, 1, [40.0, 40.0, 360.0, 52.0], "Ordinary body paragraph spanning the column width."),
        (1, 1, [40.0, 250.0, 360.0, 262.0], "Ordinary body paragraph spanning the column width."),
        (2, 1, [150.0, 100.0, 250.0, 112.0], "a = b + c"),
        (3, 1, [140.0, 116.0, 260.0, 128.0], "This is ordinary prose."),
        (4, 1, [150.0, 130.0, 250.0, 142.0], "d = e + f"),
    ]
    groups = detect_equation_groups(between)
    assert sorted(sorted(g.member_keys) for g in groups) == [[2], [4]]

    excluded = [
        (0, 1, [40.0, 40.0, 360.0, 52.0], "Ordinary body paragraph spanning the column width."),
        (1, 1, [40.0, 250.0, 360.0, 262.0], "Ordinary body paragraph spanning the column width."),
        (2, 1, [150.0, 100.0, 250.0, 112.0], "a = b + c"),
        (3, 1, [190.0, 114.0, 200.0, 126.0], "T"),
    ]
    groups = detect_equation_groups(excluded, exclusions=[(1, [185.0, 110.0, 205.0, 130.0])])
    assert [g.member_keys for g in groups] == [[2]]
    # 同一几何在没有排除框时，分母 T 必须被补进公式，证明排除检查确实生效
    groups = detect_equation_groups(excluded)
    assert sorted(groups[0].member_keys) == [2, 3]

    document = MarkdownDocument(
        title="probe",
        source_pdf="probe.pdf",
        blocks=[
            MarkdownBlock(type="paragraph", text=text, page=page, meta={"bbox": list(bbox)})
            for _key, page, bbox, text in cross
        ],
    )
    _preserve_equation_regions(
        document,
        {"items": []},
        {"out_md": str(tmp_path / "out.md"), "asset_dir": str(tmp_path), "pdf_path": "unused.pdf"},
        images_enabled=False,
    )
    assert any(block.text == "Right prose." for block in document.blocks)
    fenced = [block.text for block in document.blocks if block.text.startswith("```")]
    assert fenced and "Right prose." not in fenced[0]


def _covers(group_bbox, piece) -> bool:
    return (
        group_bbox[0] <= piece[0] + 1.0
        and group_bbox[1] <= piece[1] + 1.0
        and group_bbox[2] >= piece[2] - 1.0
        and group_bbox[3] >= piece[3] - 1.0
    )


def _equation_group_for(items, snippet: str):
    from lib.equation_regions import detect_equation_groups

    groups = detect_equation_groups(items)
    for group in groups:
        texts = [items[key][3] for key in group.member_keys]
        if any(snippet in text for text in texts):
            return group
    return None


def test_display_equation_bbox_covers_vertical_pieces(tmp_path: Path) -> None:
    # BUG-145：真实页碎片几何。区域必须盖住竖向分母、求和限、高括号和右侧公式，
    # 不能只包住命中的下标；正文段不得被并入。
    alexa_p2 = [
        (0, 2, [54.0, 80.0, 298.0, 92.0], "Left column body text establishing the column."),
        (1, 2, [54.42, 546.21, 298.21, 711.59], "Our dataset simulation pipeline is shown in Figure 2."),
        (2, 2, [315.0, 80.0, 559.0, 92.0], "Right column body text establishing the column."),
        (3, 2, [315.21, 400.0, 559.0, 412.0], "Another right column paragraph away from the formula."),
        (4, 2, [368.44, 555.63, 403.61, 566.57], "hm(t) ∝"),
        (5, 2, [406.43, 545.55, 420.82, 563.42], "∞\nX"),
        (6, 2, [406.38, 570.08, 420.87, 577.05], "k=0"),
        (7, 2, [423.72, 547.74, 438.59, 558.98], "βnk"),
        (8, 2, [426.11, 561.50, 436.78, 572.56], "tm"),
        (9, 2, [429.71, 567.94, 433.94, 574.91], "k"),
        (10, 2, [440.86, 553.98, 470.03, 566.57], "φm(ˆrm"),
        (11, 2, [462.96, 553.98, 501.39, 568.19], "k , t −tm"),
        (12, 2, [494.32, 555.76, 558.99, 568.19], "k )\n(1)"),
        (13, 2, [315.21, 584.79, 558.99, 618.89], "where β is the room absorption coefficient estimated from the desired reverberation time."),
    ]
    group = _equation_group_for(alexa_p2, "k=0")
    assert group is not None and group.complete
    for key in (4, 5, 6, 7, 10, 12):
        assert _covers(group.bbox, alexa_p2[key][2]), key
    assert 1 not in group.member_keys and 13 not in group.member_keys

    alexa_p3 = [
        (0, 3, [54.0, 80.0, 298.0, 92.0], "Left column body text establishing the column."),
        (1, 3, [54.42, 237.47, 298.21, 402.85], "we will refer to as the Alexa dataset for the GSCv2 recordings."),
        (2, 3, [315.0, 80.0, 559.0, 92.0], "Right column body text establishing the column."),
        (3, 3, [315.21, 202.11, 558.99, 273.34], "of 132k parameters. This produces a 128 dimensional embedding, which is passed to the N-ary classifier."),
        (4, 3, [395.93, 283.13, 422.31, 294.58], "ℓj = g"),
        (5, 3, [424.33, 273.25, 432.22, 283.22], " "),
        (6, 3, [432.21, 283.13, 444.27, 293.93], "zj,"),
        (7, 3, [445.93, 280.83, 460.33, 290.79], "X"),
        (8, 3, [451.72, 297.22, 454.54, 304.19], "i"),
        (9, 3, [461.98, 283.13, 469.89, 293.93], "zi"),
        (10, 3, [470.39, 273.25, 478.28, 283.22], "!"),
        (11, 3, [547.38, 283.36, 558.99, 293.32], "(2)"),
        (12, 3, [315.21, 309.84, 559.00, 367.85], "where g is a two-layer fully connected neural network. The final network output is given by applying a softmax function."),
    ]
    group = _equation_group_for(alexa_p3, "ℓj = g")
    assert group is not None and group.complete
    for key in (4, 5, 8, 10, 11):
        assert _covers(group.bbox, alexa_p3[key][2]), key
    assert 3 not in group.member_keys and 12 not in group.member_keys

    paradise_p5 = [
        (0, 5, [70.08, 70.08, 291.10, 93.04], "P(A), the actual agreement between the data and the key, is always computed from the confusion matrix M:"),
        (1, 5, [135.12, 102.41, 225.34, 112.67], "P(A) \n- \n~'~i~=l M(i, i)"),
        (2, 5, [194.40, 113.45, 200.22, 123.71], "T"),
        (3, 5, [70.32, 126.00, 291.02, 180.64], "Given the confusion matrices in Tables 3 and 4, P(E) = 0.079 for both agents."),
    ]
    group = _equation_group_for(paradise_p5, "P(A)")
    assert group is not None and group.complete
    assert _covers(group.bbox, paradise_p5[1][2])
    assert _covers(group.bbox, paradise_p5[2][2])
    assert 0 not in group.member_keys and 3 not in group.member_keys

    paradise_perf = [
        (0, 6, [70.0, 40.0, 302.0, 52.0], "Left column body text establishing the column width here."),
        (1, 6, [318.0, 40.0, 540.0, 52.0], "Right column body text establishing the column width."),
        (2, 6, [80.88, 113.04, 302.62, 145.84], "Given the definition of success and costs above and the model in Figure 1, performance for any dialogue is defined as follows:"),
        (3, 6, [100.80, 148.47, 282.09, 169.60], "n \nPerformance = (o~ • .N'(t~)) - ~ \nwi * .N'(ci)"),
        (4, 6, [222.24, 171.74, 234.08, 180.38], "i=1"),
        (5, 6, [80.40, 183.36, 302.34, 206.08], "Here ~ is a weight on success, and the cost functions are weighted by their coefficients."),
        (6, 6, [318.24, 49.44, 539.85, 157.60], "from a hypothetical experiment in which eight users were randomly assigned to communicate with Agent A."),
    ]
    group = _equation_group_for(paradise_perf, "i=1")
    assert group is not None and group.complete
    assert _covers(group.bbox, paradise_perf[3][2])
    assert _covers(group.bbox, paradise_perf[4][2])
    assert 2 not in group.member_keys and 5 not in group.member_keys and 6 not in group.member_keys

    paradise_norm = [
        (0, 6, [70.0, 40.0, 302.0, 52.0], "Left column body text establishing the column width here."),
        (1, 6, [318.0, 40.0, 540.0, 52.0], "Right column body text establishing the column width."),
        (2, 6, [80.40, 203.99, 302.65, 301.84], "The normalization function is used to overcome the problem that the values of ci are not on the same scale. This problem is easily solved by normalizing each factor x to its Z score:"),
        (3, 6, [160.32, 301.25, 192.68, 313.46], "N'(x) ="),
        (4, 6, [80.88, 312.38, 239.90, 334.72], "O'.:t: \nwhere ~r= is the standard deviation for x."),
        (5, 6, [318.24, 156.24, 540.44, 285.28], "To estimate the performance function, the weights must be solved for by considering user satisfaction."),
    ]
    group = _equation_group_for(paradise_norm, "N'(x)")
    assert group is not None and group.complete
    assert _covers(group.bbox, paradise_norm[3][2])
    assert _covers(group.bbox, paradise_norm[4][2])
    assert 2 not in group.member_keys and 5 not in group.member_keys


def test_dangling_equation_fragment_is_reported_not_packaged(tmp_path: Path) -> None:
    # 无法补全的求和下标保持原文，并在报告里标待复核，不能包装成碎片图片。
    from lib.markdown import MarkdownBlock, MarkdownDocument
    from core.pdf_to_markdown import _preserve_equation_regions

    pdf = tmp_path / "dangling.pdf"
    doc = fitz.open()
    page = doc.new_page(width=420, height=300)
    page.insert_text((40, 40), "Ordinary body paragraph spanning the column width.", fontsize=10)
    page.insert_text((40, 240), "Ordinary body paragraph spanning the column width.", fontsize=10)
    doc.save(pdf)
    doc.close()
    items = [
        (0, 1, [40.0, 40.0, 360.0, 52.0], "Ordinary body paragraph spanning the column width."),
        (1, 1, [200.0, 120.0, 220.0, 132.0], "k=0"),
        (2, 1, [40.0, 240.0, 360.0, 252.0], "Ordinary body paragraph spanning the column width."),
    ]
    document = MarkdownDocument(
        title="probe",
        source_pdf=str(pdf),
        blocks=[
            MarkdownBlock(type="paragraph", text=text, page=page, meta={"bbox": list(bbox)})
            for _key, page, bbox, text in items
        ],
    )
    asset_dir = tmp_path / "images"
    asset_dir.mkdir()
    stats = _preserve_equation_regions(
        document,
        {"items": []},
        {"out_md": str(tmp_path / "out.md"), "asset_dir": str(asset_dir), "pdf_path": str(pdf)},
        images_enabled=True,
    )
    assert stats["needs_review"] == 1
    assert stats["screenshot"] == 0
    assert list(asset_dir.glob("Equation_*.png")) == []
    assert any(block.text == "k=0" for block in document.blocks)


def test_a3_rerender_failure_keeps_existing_png_and_reports_hard_failure(tmp_path: Path) -> None:
    # BUG-148：重渲染先写临时文件，失败时旧 PNG 与哈希都还在，并进入 render_failures。
    from lib.models import AttachmentRecord
    from lib.pipeline import run_refinement_pipeline
    from lib.quality import QualityAssessment
    from lib.refiners.base import RefinementResult

    pdf = tmp_path / "fig.pdf"
    _make_figure_pdf(pdf)
    png = tmp_path / "images" / "Figure_1.png"
    png.parent.mkdir()
    with fitz.open(pdf) as doc:
        pix = doc[0].get_pixmap(dpi=72, clip=fitz.Rect(70, 100, 300, 220))
        pix.save(png)
    before = hashlib.sha256(png.read_bytes()).hexdigest()
    record = AttachmentRecord(
        kind="figure",
        ident="1",
        page=1,
        caption="Figure 1: Checkerboard sample",
        out_path=str(png),
        final_bbox=[70.0, 100.0, 300.0, 220.0],
        caption_bbox=[70.0, 230.0, 300.0, 248.0],
        content_bboxes=[[70.0, 100.0, 300.0, 220.0]],
        status="accepted",
    )
    pairing = {
        1: SimpleNamespace(
            page=1,
            pairs=[(
                SimpleNamespace(kind="figure", caption_bbox=[70.0, 230.0, 300.0, 248.0], content_bboxes=[]),
                [SimpleNamespace(kind="figure", content_bboxes=[[65.0, 95.0, 305.0, 225.0]])],
            )],
        )
    }

    def fake_refine(self, ctx):
        return RefinementResult(
            bbox=[65.0, 95.0, 305.0, 225.0],
            quality=QualityAssessment(confidence=0.95, status="accepted"),
        )

    failures = []
    with patch("lib.refiners.FigureRefiner.refine", fake_refine), patch.object(
        fitz.Pixmap, "save", _failed_pixmap_save
    ):
        report = run_refinement_pipeline(
            records=[record],
            pairing_results=pairing,
            pdf_path=str(pdf),
            out_dir=str(png.parent),
            dpi=72,
            render_failures=failures,
        )
    assert png.is_file() and png.stat().st_size > 0
    assert hashlib.sha256(png.read_bytes()).hexdigest() == before
    assert record.final_bbox == [70.0, 100.0, 300.0, 220.0]
    assert report.applied == 0
    assert failures, "A3 重渲染 I/O 失败必须进入 render_failures"
    assert report.records[0].applied is False
    assert "rerender failed" in report.records[0].reason


# ==========================================================================
# #4 续（BUG-145 重开 / BUG-147 重开 / BUG-149）：公式判定的三类补充反例
# ==========================================================================


def test_numeric_denominator_is_not_mistaken_for_page_number() -> None:
    # BUG-145 重开：纯数字块被无条件当成页码排除。分式的数字分母与页码
    # 文本形态相同，必须按「与公式成员上下紧贴且横向基本重合」区分。
    from lib.equation_regions import detect_equation_groups

    items = [
        (0, 1, [40.0, 40.0, 360.0, 52.0], "Ordinary body paragraph spanning the column width."),
        (1, 1, [150.0, 100.0, 250.0, 112.0], "a = b"),      # 分子
        (2, 1, [150.0, 113.0, 250.0, 119.0], "K--"),        # 分数线
        (3, 1, [194.0, 120.0, 206.0, 132.0], "2"),          # 数字分母
        (4, 1, [40.0, 250.0, 360.0, 262.0], "Ordinary body paragraph spanning the column width."),
    ]
    groups = detect_equation_groups(items)
    assert len(groups) == 1
    assert sorted(groups[0].member_keys) == [1, 2, 3], "纯数字分母必须并入公式区域"
    assert groups[0].bbox[3] >= 132.0, "区域下边界必须覆盖数字分母"
    assert groups[0].complete is True

    # 页面边距上的页码（横向不与公式主体对齐）仍不得入选
    margin_number = items + [(5, 1, [40.0, 134.0, 60.0, 146.0], "42")]
    groups = detect_equation_groups(margin_number)
    assert [sorted(g.member_keys) for g in groups] == [[1, 2, 3]], "页码不得被并进公式区域"


def test_numeric_denominator_reaches_cli_output(tmp_path: Path) -> None:
    # BUG-145 重开：合成分式 PDF 经正式 CLI 转换后，纯数字分母必须收进
    # 公式区域，不能作为独立段落散落正文。
    pdf = tmp_path / "frac.pdf"
    doc = fitz.open()
    page = doc.new_page(width=420, height=500)
    page.insert_text((40, 80), "We compute the kappa agreement metric for this evaluation.", fontsize=10)
    page.insert_text((150, 140), "P(A) - P(E)", fontsize=10)
    page.insert_text((150, 158), "K--", fontsize=10)
    page.insert_text((154, 176), "2", fontsize=10)
    page.insert_text((40, 220), "Higher values indicate better overall annotation quality.", fontsize=10)
    doc.save(pdf)
    doc.close()

    out_md = tmp_path / "out.md"
    report_json = tmp_path / "text" / "report.json"
    assert pdf_to_markdown_main([
        "--pdf", str(pdf), "--out", str(out_md),
        "--images", "off", "--tables", "off",
        "--report-json", str(report_json),
    ]) == 0

    md = out_md.read_text(encoding="utf-8")
    assert md.count("```") == 2, "三个公式碎片必须收进同一个代码块"
    fence = md.split("```")[1]
    for fragment in ("P(A) - P(E)", "K--", "2"):
        assert fragment in fence, f"碎片 {fragment!r} 必须保留在公式区域内"

    report = json.loads(report_json.read_text(encoding="utf-8"))
    assert report["equations"]["detected"] == 1
    assert report["equations"]["text_merged"] == 1
    assert report["equations"]["needs_review"] == 0


def test_single_word_and_chinese_sentences_are_not_equations() -> None:
    # BUG-147 重开：只数英文词会漏掉只有一个英文词的祈使句（`Assume x=1.`）
    # 与零英文词的中文句（`温度≥20℃时停止。`）。
    from lib.equation_regions import _is_equation_fragment, detect_equation_groups

    assert _is_equation_fragment("Assume x=1.") is False
    assert _is_equation_fragment("温度≥20℃时停止。") is False
    assert _is_equation_fragment("The threshold is 20 degrees when it stops.") is False
    # 英文词开头但紧跟等号是公式左侧，仍须判为公式
    assert _is_equation_fragment("def = P(d - d1 < e)") is True
    # 单字母变量的等式仍是公式
    assert _is_equation_fragment("E = mc^2.") is True

    items = [
        (0, 1, [40.0, 40.0, 360.0, 52.0], "Ordinary body paragraph spanning the column width."),
        (1, 1, [70.0, 100.0, 180.0, 112.0], "Assume x=1."),
        (2, 1, [70.0, 130.0, 180.0, 142.0], "温度≥20℃时停止。"),
        (3, 1, [40.0, 250.0, 360.0, 262.0], "Ordinary body paragraph spanning the column width."),
    ]
    assert detect_equation_groups(items) == [], "自然语言短句不得成为公式区域"


def test_group_without_equation_body_is_not_complete() -> None:
    # BUG-149：成员数量不是完整性证据。两个各自悬挂的碎片合组、或悬挂下标
    # 又吸收公式编号，成员数都会变成两个，但公式主体仍然缺失，必须继续
    # 标记待复核，不能被调用方截图替换。
    from lib.equation_regions import detect_equation_groups

    dangling_pair = [
        (0, 1, [40.0, 40.0, 360.0, 52.0], "Ordinary body paragraph spanning the column width."),
        (1, 1, [150.0, 100.0, 170.0, 112.0], "k=0"),
        (2, 1, [150.0, 116.0, 170.0, 128.0], "n=1"),
        (3, 1, [40.0, 250.0, 360.0, 262.0], "Ordinary body paragraph spanning the column width."),
    ]
    groups = detect_equation_groups(dangling_pair)
    assert len(groups) == 1 and len(groups[0].member_keys) == 2
    assert groups[0].complete is False, "两个悬挂碎片合组后公式主体仍缺失"

    dangling_plus_number = [
        (0, 1, [40.0, 40.0, 360.0, 52.0], "Ordinary body paragraph spanning the column width."),
        (1, 1, [150.0, 100.0, 170.0, 112.0], "k=0"),
        (2, 1, [280.0, 100.0, 300.0, 112.0], "(2)"),
        (3, 1, [40.0, 250.0, 360.0, 262.0], "Ordinary body paragraph spanning the column width."),
    ]
    groups = detect_equation_groups(dangling_plus_number)
    assert len(groups) == 1
    assert sorted(groups[0].member_keys) == [1, 2]
    assert groups[0].complete is False, "悬挂下标 + 公式编号不得放行"

    # 真正含公式主体的多碎片公式仍应放行
    with_body = [
        (0, 1, [40.0, 40.0, 360.0, 52.0], "Ordinary body paragraph spanning the column width."),
        (1, 1, [150.0, 100.0, 250.0, 112.0], "P(A) - P(E)"),
        (2, 1, [150.0, 116.0, 250.0, 122.0], "K--"),
        (3, 1, [40.0, 250.0, 360.0, 262.0], "Ordinary body paragraph spanning the column width."),
    ]
    groups = detect_equation_groups(with_body)
    assert len(groups) == 1 and groups[0].complete is True


def test_accessory_fragments_alone_are_not_complete(tmp_path: Path) -> None:
    # BUG-149 重开：`n`、`)`、`+`、孤立的 `∝`/`=`、`k=0` 都是附属碎片，
    # 单块或多块都撑不起公式主体，不得截图放行，必须保留原文待复核。
    from lib.equation_regions import _is_equation_accessory, _is_equation_body, detect_equation_groups

    for fragment in ("n", ")", "+", "K--", "k=0", "∝", "=", "(2)"):
        assert _is_equation_accessory(fragment) is True, f"{fragment!r} 是附属碎片"
        assert _is_equation_body(fragment) is False, f"{fragment!r} 不是公式主体"
    for body in ("hm(t) ∝", "ℓj = g", "P(A) - P(E)"):
        assert _is_equation_accessory(body) is False, f"{body!r} 是公式主体"

    lone_seed = [
        (0, 1, [40.0, 40.0, 360.0, 52.0], "Ordinary body paragraph spanning the column width."),
        (1, 1, [150.0, 120.0, 170.0, 132.0], "∝"),
        (2, 1, [40.0, 250.0, 360.0, 262.0], "Ordinary body paragraph spanning the column width."),
    ]
    groups = detect_equation_groups(lone_seed)
    assert len(groups) == 1, "孤立强符号仍可种子分组"
    assert groups[0].complete is False, "单块附属碎片不得标记完整"

    accessory_pair = [
        (0, 1, [40.0, 40.0, 360.0, 52.0], "Ordinary body paragraph spanning the column width."),
        (1, 1, [200.0, 120.0, 220.0, 132.0], "k=0"),
        (2, 1, [200.0, 136.0, 220.0, 148.0], "n"),
        (3, 1, [40.0, 250.0, 360.0, 262.0], "Ordinary body paragraph spanning the column width."),
    ]
    groups = detect_equation_groups(accessory_pair)
    assert len(groups) == 1 and len(groups[0].member_keys) == 2
    assert groups[0].complete is False, "附属碎片合组后公式主体仍缺失"

    # 正式 CLI 复现：只有 `n` 与 `k=0` 的合成 PDF 不得生成公式截图，
    # 报告必须计待复核，原文保留在 Markdown 里。
    pdf = tmp_path / "accessory.pdf"
    doc = fitz.open()
    page = doc.new_page(width=420, height=300)
    page.insert_text((40, 40), "Ordinary body paragraph spanning the column width.", fontsize=10)
    page.insert_text((200, 120), "k=0", fontsize=10)
    page.insert_text((200, 136), "n", fontsize=10)
    page.insert_text((40, 240), "Ordinary body paragraph spanning the column width.", fontsize=10)
    doc.save(pdf)
    doc.close()

    out_md = tmp_path / "out.md"
    report_json = tmp_path / "text" / "report.json"
    assert pdf_to_markdown_main([
        "--pdf", str(pdf), "--out", str(out_md),
        "--images", "figures", "--tables", "off",
        "--report-json", str(report_json),
    ]) == 0

    report = json.loads(report_json.read_text(encoding="utf-8"))
    eq = report["equations"]
    assert eq["detected"] == 1
    assert eq["needs_review"] == 1, "附属碎片必须计待复核，不得报告 ready"
    assert eq["screenshot"] == 0, "缺少公式主体不得截图"
    assert list((tmp_path / "images").glob("Equation_*.png")) == []
    md = out_md.read_text(encoding="utf-8")
    assert "n" in md and "k=0" in md, "待复核碎片的原文必须保留"


def test_merged_accessory_fragment_is_not_equation_body(tmp_path: Path) -> None:
    # BUG-149 再次重开：OCR/PyMuPDF 会把边角料合进同一个文本块（`k=0 )`），
    # 块长度兜底失效，必须按内容剥离附属成分后再判主体；复核报告同一份
    # 失败 PDF 的布局（正文 + 单块 `k=0 )` + 正文）走正式 CLI 复验。
    from lib.equation_regions import _is_equation_accessory, _is_equation_body, detect_equation_groups

    for merged in ("k=0 )", "k=0)", "n k=0", "n=1 )", "k = 0 )", "(2) )"):
        assert _is_equation_accessory(merged) is True, f"{merged!r} 同块合并后仍是附属碎片"
        assert _is_equation_body(merged) is False, f"{merged!r} 不得当公式主体"
    for body in ("hm(t) ∝", "ℓj = g", "def  = P(d - d1 < e)", "P(A) - P(E)"):
        assert _is_equation_body(body) is True, f"{body!r} 是公式主体"

    merged_items = [
        (0, 1, [40.0, 59.25, 275.1, 72.99], "Ordinary body paragraph spanning the column width."),
        (1, 1, [150.0, 119.25, 173.33, 132.99], "k=0 )"),
        (2, 1, [40.0, 229.25, 275.1, 242.99], "Ordinary body paragraph spanning the column width."),
    ]
    groups = detect_equation_groups(merged_items)
    assert len(groups) == 1, "同块附属碎片仍可种子分组"
    assert groups[0].complete is False, "同块附属碎片不得标记完整"

    pdf = tmp_path / "merged-accessory.pdf"
    doc = fitz.open()
    page = doc.new_page(width=420, height=300)
    page.insert_text((40, 70), "Ordinary body paragraph spanning the column width.", fontsize=10)
    page.insert_text((150, 130), "k=0 )", fontsize=10)
    page.insert_text((40, 240), "Ordinary body paragraph spanning the column width.", fontsize=10)
    doc.save(pdf)
    doc.close()

    out_md = tmp_path / "out.md"
    report_json = tmp_path / "text" / "report.json"
    assert pdf_to_markdown_main([
        "--pdf", str(pdf), "--out", str(out_md),
        "--images", "figures", "--tables", "off",
        "--report-json", str(report_json),
    ]) == 0

    eq = json.loads(report_json.read_text(encoding="utf-8"))["equations"]
    assert eq["detected"] == 1
    assert eq["needs_review"] == 1, "同块附属碎片必须计待复核，不得报告 ready"
    assert eq["screenshot"] == 0, "缺少公式主体不得截图"
    assert list((tmp_path / "images").glob("Equation_*.png")) == []
    md = out_md.read_text(encoding="utf-8")
    assert "k=0" in md, "待复核碎片的原文必须保留"


def test_double_space_leading_word_is_not_prose(tmp_path: Path) -> None:
    # BUG-150：前导词判定必须越过整个单词并跳过全部空白再判断等号。
    # `def  = ...`（双空格）是公式左侧，不得因回溯停在前一个空格而误判正文。
    from lib.equation_regions import _LEADING_PROSE_RE, _is_equation_fragment, detect_equation_groups

    assert _is_equation_fragment("def  = P(d - d1 < e)") is True, "双空格等号左侧仍是公式"
    assert _is_equation_fragment("def = P(d - d1 < e)") is True, "单空格等号左侧仍是公式"
    assert _is_equation_fragment("Assume  x=1.") is False, "双空格祈使句仍是正文"
    assert _is_equation_fragment("Assume x=1.") is False, "单空格祈使句仍是正文"
    assert _LEADING_PROSE_RE.match("Temperature=20") is None, "无空格紧贴等号不是正文"
    assert _LEADING_PROSE_RE.match("def") is None, "词在串尾不是正文"

    items = [
        (0, 1, [40.0, 40.0, 360.0, 52.0], "Ordinary body paragraph spanning the column width."),
        (1, 1, [70.0, 100.0, 250.0, 112.0], "def  = P(d - d1 < e)"),
        (2, 1, [40.0, 250.0, 360.0, 262.0], "Ordinary body paragraph spanning the column width."),
    ]
    groups = detect_equation_groups(items)
    assert len(groups) == 1 and groups[0].complete is True, "双空格公式的主体必须完整"

    # 正式 CLI 复现：双空格公式必须检出并整块保留。
    pdf = tmp_path / "twospace.pdf"
    doc = fitz.open()
    page = doc.new_page(width=420, height=300)
    page.insert_text((40, 40), "Ordinary body paragraph spanning the column width.", fontsize=10)
    page.insert_text((70, 120), "def  = P(d - d1 < e)", fontsize=10)
    page.insert_text((40, 240), "Ordinary body paragraph spanning the column width.", fontsize=10)
    doc.save(pdf)
    doc.close()

    out_md = tmp_path / "out.md"
    report_json = tmp_path / "text" / "report.json"
    assert pdf_to_markdown_main([
        "--pdf", str(pdf), "--out", str(out_md),
        "--images", "off", "--tables", "off",
        "--report-json", str(report_json),
    ]) == 0

    report = json.loads(report_json.read_text(encoding="utf-8"))
    eq = report["equations"]
    assert eq["detected"] == 1, "双空格公式必须检出"
    assert eq["text_merged"] == 1, "检出后必须整块合并为代码块"
    assert eq["needs_review"] == 0, "双空格公式主体完整，不得计待复核"
    md = out_md.read_text(encoding="utf-8")
    assert "P(d - d1 < e)" in md, "公式内容必须保留"


def test_equation_screenshot_keeps_existing_png_on_shared_asset_dir(tmp_path: Path) -> None:
    # BUG-151：多份 PDF 共用资源目录（默认同目录转换即可触发）时，公式截图
    # 文件名撞车；后一次转换不得覆盖既有截图（用户可能已编辑，AGENTS.md
    # 第 10 条），必须复用 get_unique_path 分配不冲突的文件名。
    formulas = {"a.pdf": "E = mc^2", "b.pdf": "F = ma"}
    for name, formula in formulas.items():
        pdf = tmp_path / name
        doc = fitz.open()
        page = doc.new_page(width=420, height=300)
        page.insert_text((40, 40), "Ordinary body paragraph spanning the column width.", fontsize=10)
        page.insert_text((150, 120), formula, fontsize=10)
        page.insert_text((40, 220), "Ordinary body paragraph spanning the column width.", fontsize=10)
        doc.save(pdf)
        doc.close()

    asset_dir = tmp_path / "images"
    out_mds = {}
    for name in formulas:
        out_md = tmp_path / name.replace(".pdf", ".md")
        out_mds[name] = out_md
        assert pdf_to_markdown_main([
            "--pdf", str(tmp_path / name), "--out", str(out_md),
            "--images", "figures", "--tables", "off",
            "--asset-dir", str(asset_dir),
        ]) == 0

    first_png = asset_dir / "Equation_p1_1.png"
    second_png = asset_dir / "Equation_p1_1_1.png"
    assert first_png.is_file(), "第一份文档的公式截图必须存在"
    assert second_png.is_file(), "第二份文档必须换用不冲突的文件名，不得覆盖既有截图"
    assert f"](images/{first_png.name})" in out_mds["a.pdf"].read_text(encoding="utf-8"), \
        "第一份 Markdown 必须引用自己的公式截图"
    assert f"](images/{second_png.name})" in out_mds["b.pdf"].read_text(encoding="utf-8"), \
        "第二份 Markdown 必须引用换名后的公式截图"


def test_multiletter_variable_continuation_merges_into_equation() -> None:
    # BUG-152：Attention 第 7 页公式 (3) 被排版拆成同行两块，右侧续块以
    # 多字母变量开头（`model · min(...)`），按前导词规则被误判成正文后，
    # 左半边 `lrate = d−0.5` 被单独截图，公式截断却仍报告 ready。
    from lib.equation_regions import _is_attachable_component, detect_equation_groups

    # 续块的前导词后紧跟中缀乘除运算符，是公式续块；英文句的第一个词
    # 后面跟的是另一个英文词，仍是正文。
    assert _is_attachable_component(
        "model · min(step_num−0.5, step_num · warmup_steps−1.5)\n(3)",
        [202.8, 617.4, 504.7, 632.0],
    ) is True, "多字母变量开头的数学续块必须可并入公式"
    assert _is_attachable_component("We set a=1.", [202.8, 617.4, 280.0, 629.2]) is False, \
        "英文短句仍不得并入公式"

    # Attention p7 公式 (3) 的真实几何：左半边 + 右侧续块 + 上下正文
    attention_p7 = [
        (0, 7, [107.5, 576.6, 504.0, 599.0],
         "We used the Adam optimizer [20] with β1 = 0.9, β2 = 0.98 and ϵ = 10−9. We varied the learning\n"
         "rate over the course of training, according to the formula:"),
        (1, 7, [162.9, 617.2, 219.3, 629.2], "lrate = d−0.5"),
        (2, 7, [202.8, 617.4, 504.7, 632.0],
         "model · min(step_num−0.5, step_num · warmup_steps−1.5)\n(3)"),
        (3, 7, [107.7, 642.7, 505.2, 674.7],
         "This corresponds to increasing the learning rate linearly for the first warmup_steps training steps,\n"
         "and decreasing it thereafter proportionally to the inverse square root of the step number. We used\n"
         "warmup_steps = 4000."),
    ]
    groups = detect_equation_groups(attention_p7)
    assert len(groups) == 1, "左半边与右侧续块必须合成一个公式区域"
    assert sorted(groups[0].member_keys) == [1, 2], "右侧续块必须并入左侧公式"
    assert groups[0].bbox[2] >= 504.0, "截图右界必须覆盖公式全长，不得截断"
    assert groups[0].complete is True

    # 续块横向间隙超过邻接阈值、无法并入时，左半边不得标记完整：
    # 必须保留原文并计待复核，不能输出半截公式还报告 ready。
    detached = [
        (0, 1, [40.0, 40.0, 360.0, 52.0], "Ordinary body paragraph spanning the column width."),
        (1, 1, [150.0, 100.0, 220.0, 112.0], "lrate = d−0.5"),
        (2, 1, [240.0, 101.0, 330.0, 113.0],
         "model · min(step_num−0.5, step_num · warmup_steps−1.5)"),
        (3, 1, [40.0, 250.0, 360.0, 262.0], "Ordinary body paragraph spanning the column width."),
    ]
    groups = detect_equation_groups(detached)
    assert len(groups) == 1, "左半边仍可种子分组"
    assert 2 not in groups[0].member_keys, "间隙过大时续块无法并入"
    assert groups[0].complete is False, "右边界有未并入的数学续块时不得报告完整"


def test_prose_with_math_operator_is_not_an_equation_continuation() -> None:
    from lib.equation_regions import _is_attachable_component, _is_math_continuation

    # BUG-153：正文中出现乘除子串，不能绕过正文守卫；不限于一个动词。
    for text in (
        "We set x × y = 1.",
        "Assume x ÷ y = 1.",
        "Note x · y = 1.",
        "where x × y = z.",
        "If x × y = z.",
        "The product x × y = z.",
        "We\nset x × y = 1.",
    ):
        assert not _is_math_continuation(text), f"正文不得误判为数学续块：{text}"
        assert not _is_attachable_component(text, [120.0, 117.0, 240.0, 129.0]), text

    # 单变量、下标和幂开头的真正续块，以及既有符号式短块，继续可以吸收。
    for text in (
        "model · min(step_num−0.5, step_num · warmup_steps−1.5)\n(3)",
        "rate_num × min(step_num)",
        "model^2 ÷ min(step_num)",
        "w^T x × b",
    ):
        assert _is_attachable_component(text, [202.8, 617.4, 504.7, 632.0]), text


def test_math_prose_neighbor_stays_outside_equation_group() -> None:
    from lib.equation_regions import detect_equation_groups

    for bbox in (
        [120.0, 117.0, 240.0, 129.0],  # 下方正文在8pt内且水平交叠，不能吸收。
        [240.0, 101.0, 330.0, 113.0],  # 右侧正文落在哨兵窗口，不能误报不完整。
    ):
        items = [
            (0, 1, [40.0, 40.0, 360.0, 52.0], "Ordinary body paragraph spanning the column width."),
            (1, 1, [150.0, 100.0, 220.0, 112.0], "E = mc^2"),
            (2, 1, bbox, "We set x × y = 1."),
            (3, 1, [40.0, 250.0, 360.0, 262.0], "Ordinary body paragraph spanning the column width."),
        ]
        groups = detect_equation_groups(items)
        assert len(groups) == 1
        assert groups[0].member_keys == [1], "正文必须留在公式分组之外"
        assert groups[0].bbox == items[1][2], "正文不得扩大公式截图边界"
        assert groups[0].complete is True, "正文不是未吸收的数学续块"


def test_math_prose_paragraph_is_preserved_by_cli(tmp_path: Path) -> None:
    pdf = tmp_path / "math-prose.pdf"
    doc = fitz.open()
    page = doc.new_page(width=420, height=300)
    for position, text in (
        ((40, 40), "Ordinary body paragraph spanning the column width."),
        ((150, 120), "E = mc^2"),
        ((120, 140), "We set x × y = 1."),
        ((40, 250), "Ordinary body paragraph spanning the column width."),
    ):
        page.insert_text(position, text, fontsize=10)
    doc.save(pdf)
    doc.close()

    out_md = tmp_path / "math-prose.md"
    report_json = tmp_path / "report.json"
    assert pdf_to_markdown_main([
        "--pdf", str(pdf), "--out", str(out_md),
        "--asset-dir", str(tmp_path / "images"),
        "--images", "figures", "--tables", "off", "--report-json", str(report_json),
    ]) == 0
    md = out_md.read_text(encoding="utf-8")
    assert "\n\nWe set x × y = 1.\n\n" in md, "正文必须保留为独立段落"
    assert "![E = mc^2]" in md, "公式图片不得吞入正文"
    report = json.loads(report_json.read_text(encoding="utf-8"))
    assert report["equations"]["groups"][0]["members"] == 1
    assert report["equations"]["screenshot"] == 1
    assert report["equations"]["needs_review"] == 0
    assert report["status"] == "ready"


def main_test() -> int:
    tests = [
        test_pre_validate_marks_unreadable_encrypted_pdf_invalid,
        test_pre_validate_marks_zero_page_pdf_invalid,
        test_pdf_to_markdown_encrypted_pdf_exits_cleanly,
        test_extract_pdf_assets_encrypted_pdf_exits_cleanly,
        test_pdf_to_markdown_zero_page_pdf_exits_cleanly,
        test_parser_accepts_positive_geometry,
        test_pdf_to_markdown_out_is_existing_dir_returns_2,
        test_pdf_to_markdown_asset_dir_is_existing_file_returns_2,
        test_extract_pdf_assets_index_json_is_existing_dir_returns_2,
        test_extract_pdf_assets_out_dir_is_existing_file_returns_2,
        test_render_block_normalizes_multiline_heading,
        test_render_block_heading_parses_as_single_atx_heading,
        test_render_block_paragraph_keeps_internal_newlines,
        test_render_failure_leaves_no_zero_byte_png_and_returns_nonzero,
        test_pdf_to_markdown_render_failure_propagates_failed_status,
        test_pdf_to_markdown_out_parent_is_file_returns_2,
        test_extract_index_json_parent_is_file_returns_2,
        test_pdf_to_markdown_text_dir_is_existing_file_returns_2,
        test_detect_equation_groups_merges_ocr_fragments,
        test_detect_equation_groups_skips_asset_overlaps_and_non_equations,
        test_affiliation_en_dash_is_not_equation_fragment,
        test_detect_equation_groups_columns_do_not_break_grouping,
        test_detect_equation_groups_absorbs_line_neighbors,
        test_equation_preserved_as_text_code_block_when_images_off,
        test_equation_preserved_as_screenshot_when_images_on,
        test_short_assignment_sentence_is_not_an_equation,
        test_neighbor_absorption_stays_in_column_and_respects_barriers,
        test_display_equation_bbox_covers_vertical_pieces,
        test_dangling_equation_fragment_is_reported_not_packaged,
        test_a3_rerender_failure_keeps_existing_png_and_reports_hard_failure,
        test_numeric_denominator_is_not_mistaken_for_page_number,
        test_numeric_denominator_reaches_cli_output,
        test_single_word_and_chinese_sentences_are_not_equations,
        test_group_without_equation_body_is_not_complete,
        test_accessory_fragments_alone_are_not_complete,
        test_merged_accessory_fragment_is_not_equation_body,
        test_double_space_leading_word_is_not_prose,
        test_equation_screenshot_keeps_existing_png_on_shared_asset_dir,
        test_multiletter_variable_continuation_merges_into_equation,
        test_prose_with_math_operator_is_not_an_equation_continuation,
        test_math_prose_neighbor_stays_outside_equation_group,
        test_math_prose_paragraph_is_preserved_by_cli,
    ]
    failed = 0
    for test in tests:
        with tempfile.TemporaryDirectory() as td:
            try:
                # 按签名分发：pytest 风格测试收 tmp_path，无参测试直接调用，
                # 独立入口与 pytest 两种运行方式必须都能全量执行。
                kwargs = {}
                if "tmp_path" in inspect.signature(test).parameters:
                    kwargs["tmp_path"] = Path(td)
                test(**kwargs)
                print(f"PASS {test.__name__}")
            except Exception as e:
                print(f"FAIL {test.__name__}: {e}")
                failed += 1
    print(f"\n测试结果: {len(tests) - failed} 通过, {failed} 失败")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main_test())
