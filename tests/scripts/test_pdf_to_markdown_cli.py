#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF-to-Markdown CLI 回归测试。

覆盖导出路径解析与自定义 JSON 输出目录创建。
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "skills", "pdf-markdown-summary", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import fitz

from core import extract_pdf_assets as extract_pdf_assets_module
from core.pdf_to_markdown import _resolve_outputs, _run_asset_extraction, main


def _make_text_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=420, height=320)
    page.insert_text((48, 72), "Markdown export smoke test.", fontsize=12)
    doc.save(path)
    doc.close()


def test_relative_asset_dir_resolves_next_to_markdown() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pdf_path = root / "input" / "paper.pdf"
        out_md = root / "output" / "paper.md"
        pdf_path.parent.mkdir(parents=True)
        out_md.parent.mkdir(parents=True)

        args = argparse.Namespace(
            pdf=str(pdf_path),
            out=str(out_md),
            asset_dir="images",
            report_json=None,
            blocks_json=None,
        )
        paths = _resolve_outputs(args)

        assert Path(paths["asset_dir"]) == out_md.parent / "images"
        assert Path(paths["report_json"]) == out_md.parent / "text" / "conversion_report.json"
        assert Path(paths["blocks_json"]) == out_md.parent / "text" / "markdown_blocks.json"


def test_custom_json_parent_dirs_are_created() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pdf_path = root / "input" / "paper.pdf"
        out_md = root / "output" / "markdown" / "paper.md"
        report_json = root / "output" / "assets" / "report.json"
        blocks_json = root / "output" / "assets" / "blocks.json"
        pdf_path.parent.mkdir(parents=True)
        _make_text_pdf(pdf_path)

        exit_code = main([
            "--pdf", str(pdf_path),
            "--out", str(out_md),
            "--report-json", str(report_json),
            "--blocks-json", str(blocks_json),
        ])

        assert exit_code == 0
        assert out_md.exists()
        assert report_json.exists()
        assert blocks_json.exists()


def test_asset_extraction_text_output_uses_markdown_text_dir() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pdf_path = root / "input" / "paper.pdf"
        asset_dir = root / "output" / "markdown" / "images"
        text_dir = root / "output" / "text"
        pdf_path.parent.mkdir(parents=True)
        _make_text_pdf(pdf_path)

        captured_args = []
        original_main = extract_pdf_assets_module.main

        def fake_extract_main(argv):
            captured_args.extend(argv)
            out_dir = Path(argv[argv.index("--out-dir") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "index.json").write_text('{"items": []}', encoding="utf-8")
            return 0

        extract_pdf_assets_module.main = fake_extract_main
        try:
            args = argparse.Namespace(
                images="figures",
                tables="off",
                preset="robust",
                allow_continued=False,
            )
            _run_asset_extraction(
                args,
                {
                    "pdf_path": str(pdf_path),
                    "asset_dir": str(asset_dir),
                    "text_dir": str(text_dir),
                    "stem": "paper",
                },
            )
        finally:
            extract_pdf_assets_module.main = original_main

        assert "--out-text" in captured_args
        out_text = Path(captured_args[captured_args.index("--out-text") + 1])
        assert out_text == text_dir / "paper.txt"


def main_test() -> int:
    tests = [
        test_relative_asset_dir_resolves_next_to_markdown,
        test_custom_json_parent_dirs_are_created,
        test_asset_extraction_text_output_uses_markdown_text_dir,
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
    raise SystemExit(main_test())
