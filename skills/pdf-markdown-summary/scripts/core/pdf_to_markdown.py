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
import re
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
    parser.add_argument("--images", choices=["off", "figures"], default="figures")
    parser.add_argument("--ocr", choices=["off", "auto", "force"], default="off")
    parser.add_argument("--preset", default="robust", choices=["robust"], help="Asset extraction preset")
    parser.add_argument("--allow-continued", action="store_true", default=False, help="Allow repeated-caption continuation items; structurally matched captionless table pages are recovered automatically")
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
    from lib.markdown import MarkdownBlock, MarkdownDocument
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


def _filter_assets_by_mode(
    items: List[Dict[str, Any]],
    args: argparse.Namespace,
) -> List[Dict[str, Any]]:
    """按 --images / --tables 过滤提取结果，关闭的类型不得进入 Markdown。"""
    inserted, _omitted = _split_assets_for_markdown(items, args)
    return inserted


def _split_assets_for_markdown(
    items: List[Dict[str, Any]],
    args: argparse.Namespace,
) -> tuple:
    """返回 (可插入条目, 被质量门拦住的条目)。

    review_required / rejected 不进正文，但必须出现在转换报告里。
    只数插入数会把「提了 13 张、正文只有 2 张」报成成功。
    """
    from lib.assess import markdown_insertable

    inserted: List[Dict[str, Any]] = []
    omitted: List[Dict[str, Any]] = []
    for item in items:
        kind = str(item.get("type") or "").lower()
        if kind == "figure" and args.images == "off":
            continue
        if kind == "table" and args.tables == "off":
            continue
        if not markdown_insertable(
            item.get("status"),
            review_required=item.get("review_required"),
            warnings=item.get("warnings"),
        ):
            omitted.append({
                "type": item.get("type"),
                "id": item.get("id"),
                "page": item.get("page"),
                "status": item.get("status"),
                "warnings": list(item.get("warnings") or []),
                "file": item.get("current_file") or item.get("file") or "",
            })
            continue
        inserted.append(item)
    return inserted, omitted


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
    if args.images == "off":
        extraction_args.append("--no-figures")
    if args.tables == "off":
        extraction_args.append("--no-tables")

    exit_code = extract_main(extraction_args)
    index_json = os.path.join(paths["asset_dir"], "index.json")
    items = load_index_json_items(index_json) if exit_code == 0 and os.path.exists(index_json) else []
    inserted, omitted = _split_assets_for_markdown(items, args)
    return {
        "enabled": True,
        "exit_code": exit_code,
        "items": inserted,
        "omitted": omitted,
        "extracted_count": len(inserted) + len(omitted),
        "index_json": index_json,
    }


def _caption_ident_for_kind(kind: str, text: str) -> str:
    """用正式提取器的编号口径解析题注编号（与资产 id 同源）。

    子图题注 Figure 3a / Figure 3(a) 的资产编号是 3（子图后缀不进入
    ident）；自建一套独立正则会得到 3a / 3(a)，比较必然失败、图片退回
    文末。这里直接复用 lib.idents 的 FIGURE_LINE_RE/TABLE_LINE_RE 与
    extract_figure_ident/extract_table_ident。
    """
    from lib.idents import (
        FIGURE_LINE_RE,
        TABLE_LINE_RE,
        extract_figure_ident,
        extract_table_ident,
    )

    if kind == "figure":
        match = FIGURE_LINE_RE.match(text.lstrip())
        return extract_figure_ident(match) if match else ""
    if kind == "table":
        match = TABLE_LINE_RE.match(text.lstrip())
        return extract_table_ident(match) if match else ""
    return ""


def _make_image_block(item: Dict[str, Any], out_md: str, index_json: str):
    from lib.markdown import MarkdownBlock

    file_value = item.get("current_file") or item.get("file") or ""
    if not file_value:
        return None
    md_dir = os.path.dirname(os.path.abspath(out_md))
    asset_abs = os.path.join(os.path.dirname(index_json), file_value)
    rel_path = os.path.relpath(asset_abs, md_dir).replace("\\", "/")
    label = f"{item.get('type', 'asset')} {item.get('id', '')}".strip()
    caption = item.get("caption") or label
    return MarkdownBlock(
        type="image",
        text=label,
        path=rel_path,
        caption=caption,
        page=item.get("page"),
        meta=item,
    )


def _asset_kind_matches_text(kind: str, text: str) -> bool:
    head = text.lstrip()
    # 英文前缀用词边界防止 "Figures"/"tables" 之外的误匹配；中文「图/表」
    # 与紧随的数字同属正则 word 字符，\b 会让「图1：」「表1：」匹配失败，
    # 故中文前缀单独匹配、不要求词边界。
    if kind == "figure":
        return bool(re.match(r"^(?:(?:figure|fig\.?)\b|图|图表|附图)", head, re.IGNORECASE))
    if kind == "table":
        return bool(re.match(r"^(?:(?:table|tab\.?)\b|表)", head, re.IGNORECASE))
    return False


def _block_is_caption_for_asset(block, item: Dict[str, Any]) -> bool:
    from lib.caption_detection import is_bare_caption_label, is_explicit_caption_format

    if getattr(block, "type", "") not in ("paragraph", "heading"):
        return False
    text = (getattr(block, "text", "") or "").strip()
    if not text:
        return False
    page = item.get("page")
    block_page = getattr(block, "page", None)
    if page is not None and block_page is not None and int(block_page) != int(page):
        return False
    kind = str(item.get("type") or "").lower()
    ident = str(item.get("id") or "").strip()
    if not ident:
        return False
    if not (is_explicit_caption_format(text) or is_bare_caption_label(text)):
        return False
    if not _asset_kind_matches_text(kind, text):
        return False
    found = _caption_ident_for_kind(kind, text)
    if not found:
        return False
    found_norm = re.sub(r"\s+", "", found).lower()
    expected = re.sub(r"\s+", "", ident).lower()
    return found_norm == expected


def _content_is_above_caption(item: Dict[str, Any]) -> bool:
    final_bbox = item.get("final_bbox") or []
    caption_bbox = item.get("caption_bbox") or []
    if len(final_bbox) < 4 or len(caption_bbox) < 4:
        return False
    return float(final_bbox[3]) <= float(caption_bbox[1]) + 2.0


def _append_asset_section(document, asset_result: Dict[str, Any], out_md: str) -> None:
    if not asset_result.get("items"):
        return

    from lib.markdown import MarkdownBlock

    document.blocks.append(MarkdownBlock(type="heading", text="提取资产", level=2))
    for item in asset_result["items"]:
        image = _make_image_block(item, out_md, asset_result.get("index_json") or "")
        if image is not None:
            document.blocks.append(image)


def _place_assets_in_document(document, asset_result: Dict[str, Any], out_md: str) -> None:
    """把可插入资产放到对应题注旁；找不到题注的仍追加到文末。"""
    items = list(asset_result.get("items") or [])
    if not items:
        return

    index_json = asset_result.get("index_json") or ""
    used_blocks: set = set()
    placements: List[tuple] = []
    unmatched: List[Dict[str, Any]] = []
    for item in items:
        image = _make_image_block(item, out_md, index_json)
        if image is None:
            continue
        match_idx = None
        for index, block in enumerate(document.blocks):
            if index in used_blocks:
                continue
            if _block_is_caption_for_asset(block, item):
                match_idx = index
                break
        if match_idx is None:
            unmatched.append(item)
            continue
        used_blocks.add(match_idx)
        placements.append((match_idx, _content_is_above_caption(item), image))

    for match_idx, before, image in sorted(placements, key=lambda row: row[0], reverse=True):
        insert_at = match_idx if before else match_idx + 1
        document.blocks.insert(insert_at, image)

    if unmatched:
        leftover = dict(asset_result)
        leftover["items"] = unmatched
        _append_asset_section(document, leftover, out_md)


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
    _place_assets_in_document(document, asset_result, paths["out_md"])

    from lib.markdown import render_markdown

    with open(paths["out_md"], "w", encoding="utf-8") as f:
        f.write(render_markdown(document))

    with open(paths["blocks_json"], "w", encoding="utf-8") as f:
        json.dump(document.to_dict(), f, ensure_ascii=False, indent=2)

    asset_exit = asset_result.get("exit_code")
    asset_failed = bool(asset_result.get("enabled") and asset_exit)
    omitted = asset_result.get("omitted") or []
    if asset_failed:
        report_status = "failed"
    elif omitted:
        report_status = "review"
    else:
        report_status = "ready"
    report = {
        "version": 1,
        "status": report_status,
        "source_pdf": paths["pdf_path"],
        "markdown": paths["out_md"],
        "blocks_json": paths["blocks_json"],
        "asset_dir": paths["asset_dir"],
        "assets": {
            "enabled": asset_result.get("enabled", False),
            "count": len(asset_result.get("items", [])),
            "extracted_count": asset_result.get(
                "extracted_count", len(asset_result.get("items", []))
            ),
            "omitted": omitted,
            "index_json": asset_result.get("index_json", ""),
            "exit_code": asset_exit,
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

    # 资产提取启用但失败时，必须向上游传播失败信号（避免静默产出无图 md）
    if asset_failed:
        print(
            f"ERROR: asset extraction failed (exit {asset_exit}); "
            f"Markdown written without figures/tables: {paths['out_md']}",
            file=sys.stderr,
        )
        return int(asset_exit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
