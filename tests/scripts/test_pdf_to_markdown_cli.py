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


def test_asset_extraction_failure_propagates_exit_code() -> None:
    """回归（2026-08-29 深度审查确认缺陷②）：资产提取失败必须传播退出码。

    修复前：extract 返回非 0 时，main() 仍输出 "Wrote Markdown..." 并 return 0，
    下游拿到无图 md 且无失败信号（静默失败）。
    修复后：main() 返回提取的退出码，report.assets 记录 exit_code。
    """
    import json

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pdf_path = root / "paper.pdf"
        _make_text_pdf(pdf_path)

        def fake_extract_main(argv):
            return 3  # 模拟提取失败

        original_main = extract_pdf_assets_module.main
        extract_pdf_assets_module.main = fake_extract_main
        try:
            exit_code = main(["--pdf", str(pdf_path), "--images", "figures"])
        finally:
            extract_pdf_assets_module.main = original_main

        assert exit_code == 3, f"提取失败应传播退出码，实际 {exit_code}"
        # Markdown 仍写出（部分成功），但 report 必须记录失败码
        report_path = pdf_path.parent / "text" / "conversion_report.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["assets"]["exit_code"] == 3
        assert report["status"] != "ready", (
            f"提取失败时报告顶层 status 不应为 ready，实际 {report.get('status')!r}"
        )


def test_extract_parser_accepts_no_figures() -> None:
    """提取层必须支持禁用 Figure，才能落实 --images off。"""
    from core.extract_pdf_assets import parse_args_modular

    args = parse_args_modular(["--pdf", "paper.pdf", "--no-figures"])
    assert getattr(args, "include_figures", True) is False


def test_images_off_tables_on_does_not_insert_figures() -> None:
    """回归：--images off --tables screenshot 不得导出或插入 Figure。

    修复前编排层只传 --no-tables，images=off 时仍跑完整提取并把 Figure
    写进 Markdown。现有测试只覆盖 images、tables 同时关闭。
    """
    import json

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pdf_path = root / "paper.pdf"
        out_md = root / "paper.md"
        _make_text_pdf(pdf_path)

        captured_args = []

        def fake_extract_main(argv):
            captured_args.extend(argv)
            out_dir = Path(argv[argv.index("--out-dir") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "index.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "type": "figure",
                                "id": "1",
                                "file": "Figure_1.png",
                                "caption": "A figure",
                            },
                            {
                                "type": "table",
                                "id": "1",
                                "file": "Table_1.png",
                                "caption": "A table",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            return 0

        original_main = extract_pdf_assets_module.main
        extract_pdf_assets_module.main = fake_extract_main
        try:
            exit_code = main(
                [
                    "--pdf", str(pdf_path),
                    "--out", str(out_md),
                    "--images", "off",
                    "--tables", "screenshot",
                ]
            )
        finally:
            extract_pdf_assets_module.main = original_main

        assert exit_code == 0
        assert "--no-figures" in captured_args, (
            f"images=off 应向提取器传递 --no-figures，实际 argv={captured_args}"
        )
        assert "--no-tables" not in captured_args

        markdown = out_md.read_text(encoding="utf-8").lower()
        assert "figure_1.png" not in markdown, "images=off 时 Markdown 不得插入 Figure"
        assert "a figure" not in markdown
        assert "table_1.png" in markdown
        assert "a table" in markdown

        report_path = out_md.parent / "text" / "conversion_report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["assets"]["count"] == 1


def test_assets_disabled_returns_zero() -> None:
    """资产提取未启用时（--images off --tables off），退出码保持 0。"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pdf_path = root / "paper.pdf"
        _make_text_pdf(pdf_path)

        def fake_extract_main(argv):  # pragma: no cover - 不应被调用
            raise AssertionError("extract 不应在资产关闭时被调用")

        original_main = extract_pdf_assets_module.main
        extract_pdf_assets_module.main = fake_extract_main
        try:
            exit_code = main(["--pdf", str(pdf_path)])
        finally:
            extract_pdf_assets_module.main = original_main

        assert exit_code == 0


def main_test() -> int:
    tests = [
        test_relative_asset_dir_resolves_next_to_markdown,
        test_custom_json_parent_dirs_are_created,
        test_asset_extraction_text_output_uses_markdown_text_dir,
        test_asset_extraction_failure_propagates_exit_code,
        test_extract_parser_accepts_no_figures,
        test_images_off_tables_on_does_not_insert_figures,
        test_assets_disabled_returns_zero,
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
