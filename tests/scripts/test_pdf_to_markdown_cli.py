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
from core.pdf_to_markdown import _filter_assets_by_mode, _resolve_outputs, _run_asset_extraction, main


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
            # 显式关闭：--images 的裸默认已改为 figures，不再能靠「不传参」表示关闭。
            exit_code = main(["--pdf", str(pdf_path), "--images", "off", "--tables", "off"])
        finally:
            extract_pdf_assets_module.main = original_main

        assert exit_code == 0


def test_images_extracted_by_default() -> None:
    """默认不传 --images 时必须提取 Figure。

    修复前 `--images` 裸默认是 off，`pdf_to_markdown.py --pdf x.pdf` 会整段
    跳过资产提取，Markdown 里一张图都没有，使用方必须显式补
    `--images figures` 才有图——静默产出「无图 md」是主要坑点。
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
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            return 0

        original_main = extract_pdf_assets_module.main
        extract_pdf_assets_module.main = fake_extract_main
        try:
            exit_code = main(["--pdf", str(pdf_path), "--out", str(out_md)])
        finally:
            extract_pdf_assets_module.main = original_main

        assert exit_code == 0
        assert "--no-figures" not in captured_args, (
            f"默认必须启用 Figure 提取，实际 argv={captured_args}"
        )
        assert "--no-tables" in captured_args, (
            f"tables 默认仍为 off，应传 --no-tables，实际 argv={captured_args}"
        )

        markdown = out_md.read_text(encoding="utf-8").lower()
        assert "figure_1.png" in markdown, "默认应把 Figure 插入 Markdown"
        assert "a figure" in markdown

        report = json.loads(
            (out_md.parent / "text" / "conversion_report.json").read_text(encoding="utf-8")
        )
        assert report["assets"]["enabled"] is True
        assert report["assets"]["count"] == 1
        assert report["status"] == "ready"
        assert report["assets"]["omitted"] == []


def test_omitted_assets_are_reported_instead_of_silent_ready() -> None:
    """review/rejected 资产不进 Markdown 时，报告必须点名，不能假装 ready。"""
    import json

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pdf_path = root / "paper.pdf"
        out_md = root / "paper.md"
        _make_text_pdf(pdf_path)

        def fake_extract_main(argv):
            out_dir = Path(argv[argv.index("--out-dir") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "index.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "type": "figure",
                                "id": "1",
                                "status": "accepted",
                                "file": "Figure_1.png",
                                "caption": "Figure 1",
                            },
                            {
                                "type": "table",
                                "id": "2",
                                "status": "review_required",
                                "warnings": ["table_band_open", "object_truncation"],
                                "file": "Table_2.png",
                                "caption": "Table 2",
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
                ["--pdf", str(pdf_path), "--out", str(out_md), "--tables", "screenshot"]
            )
        finally:
            extract_pdf_assets_module.main = original_main

        assert exit_code == 0
        markdown = out_md.read_text(encoding="utf-8")
        assert "Figure_1.png" in markdown
        assert "Table_2.png" not in markdown
        report = json.loads(
            (out_md.parent / "text" / "conversion_report.json").read_text(encoding="utf-8")
        )
        assert report["status"] == "review"
        omitted = report["assets"]["omitted"]
        assert omitted[0]["type"] == "table" and omitted[0]["id"] == "2"
        assert "table_band_open" in omitted[0]["warnings"]
        assert report["assets"]["extracted_count"] == 2
        assert report["assets"]["count"] == 1


def test_filter_skips_review_and_rejected_assets() -> None:
    args = argparse.Namespace(images="figures", tables="screenshot")
    items = [
        {"type": "figure", "id": "1", "status": "accepted"},
        {"type": "figure", "id": "2", "status": "accepted_with_margin"},
        {"type": "figure", "id": "3", "status": "review_required"},
        {"type": "table", "id": "4", "status": "rejected"},
        {"type": "table", "id": "5"},
    ]
    filtered = _filter_assets_by_mode(items, args)
    assert [item["id"] for item in filtered] == ["1", "2", "5"]


def _make_captioned_pdf(path: Path, lines: list[tuple[float, str]]) -> None:
    doc = fitz.open()
    page = doc.new_page(width=420, height=480)
    for y, text in lines:
        page.insert_text((48, y), text, fontsize=12)
    doc.save(path)
    doc.close()


def _run_markdown_with_fake_assets(
    pdf_path: Path, out_md: Path, items: list, extra_argv: list | None = None,
) -> str:
    import json

    def fake_extract_main(argv):
        out_dir = Path(argv[argv.index("--out-dir") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.json").write_text(
            json.dumps({"items": items}), encoding="utf-8"
        )
        return 0

    original_main = extract_pdf_assets_module.main
    extract_pdf_assets_module.main = fake_extract_main
    try:
        argv = ["--pdf", str(pdf_path), "--out", str(out_md)]
        if extra_argv:
            argv.extend(extra_argv)
        exit_code = main(argv)
    finally:
        extract_pdf_assets_module.main = original_main
    assert exit_code == 0
    return out_md.read_text(encoding="utf-8")


def test_assets_insert_after_matching_caption_not_in_appendix() -> None:
    """题注在正文里时，截图必须跟在该题注后面，而不是堆到文末。"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pdf_path = root / "paper.pdf"
        out_md = root / "paper.md"
        _make_captioned_pdf(
            pdf_path,
            [
                (72, "Intro paragraph about the method."),
                (140, "Figure 1: System architecture overview."),
                (210, "The following section discusses results."),
            ],
        )
        markdown = _run_markdown_with_fake_assets(
            pdf_path,
            out_md,
            [
                {
                    "type": "figure",
                    "id": "1",
                    "page": 1,
                    "status": "accepted",
                    "file": "Figure_1.png",
                    "caption": "Figure 1: System architecture overview.",
                }
            ],
        )
        lines = [line for line in markdown.splitlines() if line.strip()]
        caption_i = next(
            i for i, line in enumerate(lines)
            if line.startswith("Figure 1:") and "Figure_1.png" not in line
        )
        image_i = next(i for i, line in enumerate(lines) if "Figure_1.png" in line)
        later_i = next(i for i, line in enumerate(lines) if line.startswith("The following section"))
        assert caption_i < image_i < later_i, markdown
        assert "## 提取资产" not in markdown


def test_body_citation_does_not_steal_in_body_slot() -> None:
    """「Figure 1 shows that ...」是正文引用，截图仍应落到文末附录。"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pdf_path = root / "paper.pdf"
        out_md = root / "paper.md"
        _make_captioned_pdf(
            pdf_path,
            [(72, "Figure 1 shows that the system works well in practice.")],
        )
        markdown = _run_markdown_with_fake_assets(
            pdf_path,
            out_md,
            [
                {
                    "type": "figure",
                    "id": "1",
                    "page": 1,
                    "status": "accepted",
                    "file": "Figure_1.png",
                    "caption": "Figure 1: Hidden caption.",
                }
            ],
        )
        assert "Figure_1.png" in markdown
        assert "## 提取资产" in markdown
        citation_at = markdown.find("Figure 1 shows that")
        appendix_at = markdown.find("## 提取资产")
        image_at = markdown.find("Figure_1.png")
        assert citation_at < appendix_at < image_at, markdown


def test_table_above_caption_inserts_image_before_caption() -> None:
    """表格在题注上方时，截图插在题注段落之前，保持表→题注阅读顺序。"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pdf_path = root / "paper.pdf"
        out_md = root / "paper.md"
        _make_captioned_pdf(
            pdf_path,
            [
                (72, "Intro paragraph about the method."),
                (140, "Table 7: Attribute value matrix, circuit domain."),
                (210, "The following section discusses results."),
            ],
        )
        markdown = _run_markdown_with_fake_assets(
            pdf_path,
            out_md,
            [
                {
                    "type": "table",
                    "id": "7",
                    "page": 1,
                    "status": "accepted",
                    "file": "Table_7.png",
                    "caption": "Table 7: Attribute value matrix, circuit domain.",
                    "final_bbox": [60.0, 108.0, 286.0, 169.0],
                    "caption_bbox": [84.0, 174.0, 268.0, 187.0],
                }
            ],
            extra_argv=["--tables", "screenshot"],
        )
        lines = [line for line in markdown.splitlines() if line.strip()]
        intro_i = next(i for i, line in enumerate(lines) if line.startswith("Intro paragraph"))
        image_i = next(i for i, line in enumerate(lines) if "Table_7.png" in line)
        caption_i = next(
            i for i, line in enumerate(lines)
            if line.startswith("Table 7:") and "Table_7.png" not in line
        )
        later_i = next(i for i, line in enumerate(lines) if line.startswith("The following section"))
        assert intro_i < image_i < caption_i < later_i, markdown
        assert "## 提取资产" not in markdown


def _place_single_asset_blocks(kind: str, caption_text: str, ident: str) -> list:
    """直调插图逻辑：题注段落 + 后续正文 + 一个资产，返回最终块类型序列。"""
    from core.pdf_to_markdown import _place_assets_in_document
    from lib.markdown import MarkdownBlock, MarkdownDocument

    document = MarkdownDocument(
        title="示例",
        source_pdf="example.pdf",
        blocks=[
            MarkdownBlock(type="paragraph", text=caption_text, page=1),
            MarkdownBlock(type="paragraph", text="后续正文", page=1),
        ],
    )
    item = {
        "type": kind,
        "id": ident,
        "page": 1,
        "file": "image.png",
        "caption": caption_text,
    }
    _place_assets_in_document(
        document,
        {"items": [item], "index_json": "/tmp/assets/index.json"},
        "/tmp/document.md",
    )
    return [block.type for block in document.blocks]


def test_chinese_no_space_caption_keeps_image_in_body() -> None:
    """中文无空格题注「图1：」「表1：」必须命中插图（词边界不能夹在汉字与数字之间）。"""
    blocks = _place_single_asset_blocks("figure", "图1：系统架构", "1")
    assert blocks == ["paragraph", "image", "paragraph"], blocks
    blocks = _place_single_asset_blocks("table", "表1：实验结果", "1")
    assert blocks == ["paragraph", "image", "paragraph"], blocks


def test_subfigure_caption_matches_parent_ident() -> None:
    """子图题注 Figure 3a / Figure 3(a) 的资产编号是 3（与提取链同口径），必须命中插图。"""
    for caption in ("Figure 3a: Detail", "Figure 3(a): Detail"):
        blocks = _place_single_asset_blocks("figure", caption, "3")
        assert blocks == ["paragraph", "image", "paragraph"], (caption, blocks)


def test_caption_ident_mismatch_still_goes_to_appendix() -> None:
    """编号不一致的题注不得抢位（守卫：编号比较仍然生效，附录带标题块）。"""
    blocks = _place_single_asset_blocks("figure", "图2：另一张图", "1")
    assert blocks == ["paragraph", "paragraph", "heading", "image"], blocks
    blocks = _place_single_asset_blocks("figure", "Figure 4: Other figure.", "3")
    assert blocks == ["paragraph", "paragraph", "heading", "image"], blocks


def main_test() -> int:
    tests = [
        test_relative_asset_dir_resolves_next_to_markdown,
        test_custom_json_parent_dirs_are_created,
        test_asset_extraction_text_output_uses_markdown_text_dir,
        test_asset_extraction_failure_propagates_exit_code,
        test_extract_parser_accepts_no_figures,
        test_images_off_tables_on_does_not_insert_figures,
        test_assets_disabled_returns_zero,
        test_images_extracted_by_default,
        test_filter_skips_review_and_rejected_assets,
        test_assets_insert_after_matching_caption_not_in_appendix,
        test_body_citation_does_not_steal_in_body_slot,
        test_table_above_caption_inserts_image_before_caption,
        test_chinese_no_space_caption_keeps_image_in_body,
        test_subfigure_caption_matches_parent_ident,
        test_caption_ident_mismatch_still_goes_to_appendix,
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
