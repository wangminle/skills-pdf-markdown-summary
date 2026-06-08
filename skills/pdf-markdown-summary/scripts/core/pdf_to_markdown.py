#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Core CLI for PDF-to-Markdown conversion.

This module keeps heavy PDF imports inside main execution paths so `--help`
stays fast and reliable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

_scripts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a PDF into Markdown with optional asset extraction.",
    )
    parser.add_argument("--pdf", required=True, help="Path to the source PDF")
    parser.add_argument("--out", default=None, help="Output Markdown path")
    parser.add_argument("--asset-dir", default="images", help="Image asset directory")
    parser.add_argument("--report-json", default=None, help="Output conversion report JSON")
    parser.add_argument("--blocks-json", default=None, help="Output Markdown blocks JSON")
    parser.add_argument("--tables", choices=["off", "auto", "screenshot", "structure"], default="off")
    parser.add_argument("--images", choices=["off", "figures"], default="off")
    parser.add_argument("--ocr", choices=["off", "auto", "force"], default="off")
    parser.add_argument("--preset", default="robust", choices=["robust"], help="Asset extraction preset")
    parser.add_argument("--allow-continued", action="store_true", default=False)
    return parser.parse_args(argv)


def _resolve_outputs(args: argparse.Namespace) -> Dict[str, str]:
    pdf_path = os.path.abspath(args.pdf)
    pdf_dir = os.path.dirname(pdf_path)
    stem = os.path.splitext(os.path.basename(pdf_path))[0]

    out_md = os.path.abspath(args.out or os.path.join(pdf_dir, f"{stem}.md"))
    out_dir = os.path.dirname(out_md)
    text_dir = os.path.join(out_dir, "text")
    asset_dir = args.asset_dir
    if not os.path.isabs(asset_dir):
        asset_dir = os.path.join(out_dir, asset_dir)
    asset_dir = os.path.abspath(asset_dir)

    return {
        "pdf_path": pdf_path,
        "pdf_dir": pdf_dir,
        "stem": stem,
        "text_dir": text_dir,
        "out_md": out_md,
        "asset_dir": asset_dir,
        "report_json": os.path.abspath(args.report_json or os.path.join(text_dir, "conversion_report.json")),
        "blocks_json": os.path.abspath(args.blocks_json or os.path.join(text_dir, "markdown_blocks.json")),
    }


def _paragraphs_to_document(pdf_path: str, title: str):
    from lib.markdown_models import MarkdownBlock, MarkdownDocument
    from lib.text_extract import gather_structured_text, pre_validate_pdf

    validation = pre_validate_pdf(pdf_path)
    gathered = gather_structured_text(pdf_path)

    blocks: List[MarkdownBlock] = []
    last_page: Optional[int] = None
    for paragraph in gathered.paragraphs:
        if paragraph.page != last_page:
            blocks.append(MarkdownBlock(type="page_break", page=paragraph.page))
            last_page = paragraph.page

        text = paragraph.text.strip()
        if not text:
            continue

        if getattr(paragraph, "is_heading", False):
            blocks.append(MarkdownBlock(type="heading", text=text, level=2, page=paragraph.page))
        else:
            blocks.append(MarkdownBlock(type="paragraph", text=text, page=paragraph.page))

    return MarkdownDocument(
        title=title,
        source_pdf=os.path.basename(pdf_path),
        blocks=blocks,
        meta={
            "generated_at": datetime.now().isoformat(),
            "text_layer_ratio": validation.text_layer_ratio,
            "has_text_layer": validation.has_text_layer,
            "warnings": validation.warnings,
        },
    )


def _run_asset_extraction(args: argparse.Namespace, paths: Dict[str, str]) -> Dict[str, Any]:
    if args.images == "off" and args.tables == "off":
        return {"enabled": False, "items": [], "index_json": ""}

    from core.extract_pdf_assets import main as extract_main
    from lib.output import load_index_json_items

    extraction_args = [
        "--pdf",
        paths["pdf_path"],
        "--out-dir",
        paths["asset_dir"],
        "--out-text",
        os.path.join(paths["text_dir"], f"{paths['stem']}.txt"),
        "--preset",
        args.preset,
    ]
    if args.allow_continued:
        extraction_args.append("--allow-continued")
    if args.tables == "off":
        extraction_args.append("--no-tables")

    exit_code = extract_main(extraction_args)
    index_json = os.path.join(paths["asset_dir"], "index.json")
    items = load_index_json_items(index_json) if exit_code == 0 and os.path.exists(index_json) else []
    return {
        "enabled": True,
        "exit_code": exit_code,
        "items": items,
        "index_json": index_json,
    }


def _append_asset_section(document, asset_result: Dict[str, Any], out_md: str) -> None:
    if not asset_result.get("items"):
        return

    from lib.markdown_models import MarkdownBlock

    document.blocks.append(MarkdownBlock(type="heading", text="提取资产", level=2))
    md_dir = os.path.dirname(os.path.abspath(out_md))
    for item in asset_result["items"]:
        file_value = item.get("current_file") or item.get("file") or ""
        if not file_value:
            continue
        asset_abs = os.path.join(os.path.dirname(asset_result["index_json"]), file_value)
        rel_path = os.path.relpath(asset_abs, md_dir).replace("\\", "/")
        label = f"{item.get('type', 'asset')} {item.get('id', '')}".strip()
        caption = item.get("caption") or label
        document.blocks.append(
            MarkdownBlock(
                type="image",
                text=label,
                path=rel_path,
                caption=caption,
                page=item.get("page"),
                meta=item,
            )
        )


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    paths = _resolve_outputs(args)

    if not os.path.exists(paths["pdf_path"]):
        print(f"PDF not found: {paths['pdf_path']}", file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(paths["out_md"]), exist_ok=True)
    os.makedirs(paths["asset_dir"], exist_ok=True)
    os.makedirs(paths["text_dir"], exist_ok=True)
    os.makedirs(os.path.dirname(paths["blocks_json"]), exist_ok=True)
    os.makedirs(os.path.dirname(paths["report_json"]), exist_ok=True)

    document = _paragraphs_to_document(paths["pdf_path"], paths["stem"])
    asset_result = _run_asset_extraction(args, paths)
    _append_asset_section(document, asset_result, paths["out_md"])

    from lib.markdown_render import render_markdown

    with open(paths["out_md"], "w", encoding="utf-8") as f:
        f.write(render_markdown(document))

    with open(paths["blocks_json"], "w", encoding="utf-8") as f:
        json.dump(document.to_dict(), f, ensure_ascii=False, indent=2)

    report = {
        "version": 1,
        "status": "ready",
        "source_pdf": paths["pdf_path"],
        "markdown": paths["out_md"],
        "blocks_json": paths["blocks_json"],
        "asset_dir": paths["asset_dir"],
        "assets": {
            "enabled": asset_result.get("enabled", False),
            "count": len(asset_result.get("items", [])),
            "index_json": asset_result.get("index_json", ""),
        },
        "ocr": {
            "mode": args.ocr,
            "status": "not_implemented" if args.ocr != "off" else "off",
        },
        "generated_at": datetime.now().isoformat(),
    }
    with open(paths["report_json"], "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Wrote Markdown: {paths['out_md']}")
    print(f"Wrote blocks: {paths['blocks_json']}")
    print(f"Wrote report: {paths['report_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
