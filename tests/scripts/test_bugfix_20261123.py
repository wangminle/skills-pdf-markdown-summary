#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BUG-154~160 回归：源路径覆盖、共享清理、旋转坐标、空正文状态、强制方向、复用类型、评测键。"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import fitz
import pytest
from PIL import Image

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "skills", "pdf-markdown-summary", "scripts")
EVAL_DIR = os.path.join(PROJECT_ROOT, "tests", "eval")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
if EVAL_DIR not in sys.path:
    sys.path.insert(0, EVAL_DIR)

from core.extract_pdf_assets import main as extract_main
from core.pdf_to_markdown import main as pdf_to_markdown_main
from core.summarize_pdf import main as summarize_main
from run_eval import find_pred_files


def _make_two_figure_pdf(path: Path, label: str, *, rotate: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open() as doc:
        page = doc.new_page(width=612, height=792)
        page.draw_rect(fitz.Rect(76, 76, 270, 165), fill=(0.25, 0.4, 0.7))
        page.insert_text((76, 185), f"Figure 1: {label} layout")
        page.draw_rect(fitz.Rect(76, 206, 270, 268), fill=(0.7, 0.4, 0.25))
        page.insert_text((76, 287), f"Figure 2: {label} results")
        if rotate:
            page.set_rotation(rotate)
        doc.save(path)


def _index_items(folder: Path) -> list:
    return json.loads((folder / "index.json").read_text(encoding="utf-8"))["items"]


def _make_file_alias(source: Path, alias: Path, kind: str) -> None:
    if kind == "symlink":
        os.symlink(source, alias)
    else:
        os.link(source, alias)


def test_bug154_rejects_out_path_equal_to_source_pdf(tmp_path: Path) -> None:
    pdf = tmp_path / "source.pdf"
    _make_two_figure_pdf(pdf, "Alpha")
    before = hashlib.sha256(pdf.read_bytes()).hexdigest()

    rc = pdf_to_markdown_main([
        "--pdf", str(pdf),
        "--out", str(pdf),
        "--images", "off",
        "--tables", "off",
    ])

    assert rc != 0, "源 PDF 与 --out 相同时必须非零退出"
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == before, "源 PDF 字节不得被覆盖"
    assert pdf.read_bytes()[:5] == b"%PDF-", "源文件必须仍是 PDF"


@pytest.mark.parametrize("entry", ["markdown", "assets"])
@pytest.mark.parametrize("link_kind", ["symlink", "hardlink"])
def test_bug154_rejects_file_aliases_to_source_pdf(
    tmp_path: Path, entry: str, link_kind: str,
) -> None:
    pdf = tmp_path / "source.pdf"
    _make_two_figure_pdf(pdf, "Alias")
    before = hashlib.sha256(pdf.read_bytes()).hexdigest()
    alias = tmp_path / ("alias.md" if entry == "markdown" else "alias.txt")
    _make_file_alias(pdf, alias, link_kind)

    if entry == "markdown":
        rc = pdf_to_markdown_main([
            "--pdf", str(pdf),
            "--out", str(alias),
            "--images", "off",
            "--tables", "off",
        ])
    else:
        rc = extract_main([
            "--pdf", str(pdf),
            "--out-dir", str(tmp_path / "images"),
            "--out-text", str(alias),
        ])

    assert rc != 0, f"{link_kind} 别名不得绕过源 PDF 保护"
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == before
    assert pdf.read_bytes()[:5] == b"%PDF-"


@pytest.mark.parametrize("entry", ["layout-only", "markdown", "assets"])
@pytest.mark.parametrize("link_kind", ["same-path", "symlink", "hardlink"])
def test_bug154_rejects_derived_layout_alias_to_source(
    tmp_path: Path, entry: str, link_kind: str,
) -> None:
    layout = tmp_path / "images" / "layout_model.json"
    source = layout if link_kind == "same-path" else tmp_path / "source.pdf"
    _make_two_figure_pdf(source, "Layout path")
    if source != layout:
        layout.parent.mkdir()
        _make_file_alias(source, layout, link_kind)
    original = source.read_bytes()
    markdown = tmp_path / "markdown" / "paper.md"
    text = tmp_path / "text" / "paper.txt"

    if entry == "assets":
        rc = extract_main([
            "--pdf", str(source), "--out-dir", str(layout.parent), "--out-text", str(text),
            "--layout-driven", "on",
        ])
    else:
        options = ["--images", "off", "--tables", "off"] if entry == "layout-only" else []
        rc = pdf_to_markdown_main([
            "--pdf", str(source), "--out", str(markdown), "--asset-dir", str(layout.parent),
            "--layout-model-detail", "full", *options,
        ])

    assert rc == 2
    assert source.read_bytes() == original
    assert not markdown.exists() and not text.exists()
    assert not (layout.parent / "index.json").exists()


def test_bug154_rejects_layout_and_report_path_collision(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _make_two_figure_pdf(source, "Layout and report")
    layout = tmp_path / "images" / "layout_model.json"
    markdown = tmp_path / "markdown" / "paper.md"
    rc = pdf_to_markdown_main([
        "--pdf", str(source), "--out", str(markdown), "--asset-dir", str(layout.parent),
        "--images", "off", "--tables", "off", "--layout-model-detail", "full",
        "--report-json", str(layout),
    ])

    assert rc == 2
    assert not layout.exists() and not markdown.exists()


@pytest.mark.parametrize("log_option", ["--log-file", "--log-jsonl"])
def test_bug154_extract_rejects_log_path_equal_to_source_pdf(
    tmp_path: Path, log_option: str,
) -> None:
    pdf = tmp_path / "source.pdf"
    _make_two_figure_pdf(pdf, "Log")
    before = hashlib.sha256(pdf.read_bytes()).hexdigest()

    rc = extract_main([
        "--pdf", str(pdf),
        "--out-dir", str(tmp_path / "images"),
        "--out-text", str(tmp_path / "txt" / "document.txt"),
        log_option, str(pdf),
    ])

    assert rc != 0, f"{log_option} 不得追加日志到源 PDF"
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == before
    assert pdf.read_bytes()[:5] == b"%PDF-"


@pytest.mark.parametrize("link_kind", ["symlink", "hardlink"])
def test_bug154_rejects_outputs_aliased_to_same_file(
    tmp_path: Path, link_kind: str,
) -> None:
    from lib.output import validate_output_targets

    target = tmp_path / "target.md"
    target.write_text("keep", encoding="utf-8")
    alias = tmp_path / "alias.md"
    _make_file_alias(target, alias, link_kind)

    problems = validate_output_targets([
        (str(target), False, "输出 Markdown"),
        (str(alias), False, "blocks JSON"),
    ])

    assert problems, f"{link_kind} 输出别名必须被识别为同一路径身份"
    assert target.read_text(encoding="utf-8") == "keep"


def test_bug155_shared_asset_dir_does_not_prune_other_doc_images(tmp_path: Path) -> None:
    a = tmp_path / "alpha" / "source.pdf"
    b = tmp_path / "beta" / "source.pdf"
    _make_two_figure_pdf(a, "Alpha")
    _make_two_figure_pdf(b, "Beta")
    shared = tmp_path / "shared" / "images"

    assert pdf_to_markdown_main([
        "--pdf", str(a),
        "--out", str(tmp_path / "alpha" / "markdown" / "paper.md"),
        "--asset-dir", str(shared),
    ]) == 0
    alpha_paths = [shared / row["file"] for row in _index_items(shared)]
    assert all(p.is_file() for p in alpha_paths)

    assert pdf_to_markdown_main([
        "--pdf", str(b),
        "--out", str(tmp_path / "beta" / "markdown" / "paper.md"),
        "--asset-dir", str(shared),
    ]) == 0

    assert all(p.is_file() for p in alpha_paths), (
        "第二份 PDF 共用资源目录时，不得删除第一份 Markdown 仍在引用的图片"
    )
    alpha_md = (tmp_path / "alpha" / "markdown" / "paper.md").read_text(encoding="utf-8")
    for p in alpha_paths:
        assert p.name in alpha_md


def test_bug156_rotated_page_crops_have_visible_ink(tmp_path: Path) -> None:
    pdf = tmp_path / "rotated" / "source.pdf"
    _make_two_figure_pdf(pdf, "rotated", rotate=90)
    out_dir = tmp_path / "rotated" / "images"

    assert extract_main([
        "--pdf", str(pdf),
        "--out-dir", str(out_dir),
        "--out-text", str(tmp_path / "rotated" / "txt" / "document.txt"),
        "--preset", "robust",
    ]) == 0

    items = _index_items(out_dir)
    assert len(items) == 2
    for item in items:
        png = out_dir / item["file"]
        assert png.is_file()
        extrema = Image.open(png).convert("RGB").getextrema()
        assert any(lo < 250 for lo, _hi in extrema), (
            f"旋转页裁剪不得输出纯白 PNG: {png.name} extrema={extrema}"
        )
        assert item.get("status") in {"accepted", "accepted_with_margin"}, item


def test_bug157_scan_only_pdf_report_is_not_ready(tmp_path: Path) -> None:
    src = tmp_path / "with_text.pdf"
    _make_two_figure_pdf(src, "scan-src")
    scan = tmp_path / "scan" / "source.pdf"
    scan.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open(src) as source, fitz.open() as doc:
        pix = source[0].get_pixmap()
        page = doc.new_page(width=pix.width, height=pix.height)
        page.insert_image(page.rect, pixmap=pix)
        doc.save(scan)

    out_md = tmp_path / "scan" / "markdown" / "document.md"
    assert pdf_to_markdown_main([
        "--pdf", str(scan),
        "--out", str(out_md),
        "--images", "off",
        "--tables", "off",
    ]) == 0

    report = json.loads(
        (out_md.parent / "text" / "conversion_report.json").read_text(encoding="utf-8")
    )
    body = out_md.read_text(encoding="utf-8").strip()
    assert body.startswith("#"), "仍可写出标题"
    assert report["status"] != "ready", (
        f"无可提取正文时不得报告 ready，实际 status={report['status']!r}"
    )


def test_bug158_explicit_below_not_overridden_by_bare_correction(tmp_path: Path) -> None:
    pdf = tmp_path / "bare" / "source.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open() as doc:
        page = doc.new_page()
        page.draw_rect(fitz.Rect(76, 60, 270, 165), fill=(0.2, 0.4, 0.7))
        page.insert_text((76, 185), "Figure 1")
        page.draw_rect(fitz.Rect(76, 220, 270, 276), fill=(0.7, 0.4, 0.2))
        page.insert_text((76, 310), "Figure 2: Test layout")
        doc.save(pdf)

    out_dir = tmp_path / "bare" / "images"
    assert extract_main([
        "--pdf", str(pdf),
        "--out-dir", str(out_dir),
        "--out-text", str(tmp_path / "bare" / "txt" / "document.txt"),
        "--preset", "robust",
        "--below", "1",
    ]) == 0

    fig1 = next(item for item in _index_items(out_dir) if item["id"] == "1")
    caption_y0 = fig1["caption_bbox"][1]
    final_y0 = fig1["final_bbox"][1]
    assert final_y0 >= caption_y0 - 1.0, (
        f"显式 --below 1 必须从题注下方裁剪，caption_y0={caption_y0}, final_y0={final_y0}"
    )


def test_bug159_reuse_existing_rejects_directory_text_path(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    _make_two_figure_pdf(pdf, "reuse")
    out_dir = tmp_path / "images"
    text_file = tmp_path / "text" / "paper.txt"
    assert summarize_main([
        "--pdf", str(pdf),
        "--out-dir", str(out_dir),
        "--text-path", str(text_file),
    ]) == 0

    text_dir = tmp_path / "text_dir_as_path"
    text_dir.mkdir()
    rc = summarize_main([
        "--pdf", str(pdf),
        "--out-dir", str(out_dir),
        "--text-path", str(text_dir),
        "--reuse-existing",
    ])
    assert rc != 0, "目录不得被当成纯文本摘要素材"


def test_bug160_find_pred_files_single_index_uses_document_id() -> None:
    root = Path(PROJECT_ROOT) / "tests" / "results" / "_tmp_bug160_pred"
    # Use pytest tmp via a nested layout under a disposable path constructed in-memory
    # through TemporaryDirectory-like structure owned by the test via fixture-less Path.
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        formal = Path(td) / "DeepSeek_V3_2" / "images" / "index.json"
        formal.parent.mkdir(parents=True)
        formal.write_text(json.dumps({"items": [{"id": "1", "type": "figure", "page": 1}]}), encoding="utf-8")

        as_file = find_pred_files(formal)
        as_dir = find_pred_files(Path(td))
        assert "DeepSeek_V3_2" in as_dir
        assert "DeepSeek_V3_2" in as_file, (
            f"单文件正式 index.json 不得把父目录 images 当作论文 ID，实际键={sorted(as_file)}"
        )
        assert "images" not in as_file
