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
    parser.add_argument("--asset-dir", default="images",
                        help="Image asset directory; relative paths resolve next to the Markdown output file (--out out/paper.md --asset-dir assets -> out/assets/), absolute paths are used as-is")
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


def _paragraphs_to_document(pdf_path: str, title: str, validation=None):
    from lib.markdown import MarkdownBlock, MarkdownDocument
    from lib.text_extract import gather_structured_text, pre_validate_pdf

    if validation is None:
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
            blocks.append(MarkdownBlock(type="heading", text=text, level=2, page=paragraph.page,
                                        meta={"bbox": list(paragraph.bbox)}))
        else:
            blocks.append(MarkdownBlock(type="paragraph", text=text, page=paragraph.page,
                                        meta={"bbox": list(paragraph.bbox)}))

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
    if not os.path.isfile(asset_abs):
        # BUG-133：index 引用的 PNG 缺失时不得生成死链图片块
        return None
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


def _blocks_covered_by_assets(document, items, protected_idx: set):
    """找出被已插入资产 final_bbox 完整覆盖的正文块（BUG-131）。

    只抑制同页、bbox 完整落入 final_bbox（2pt 容差）的 paragraph/heading
    块；明确是题注格式的行始终保留（避免吃掉下一张表/图的题注），
    部分重叠的段落保守保留。调用方需保证 items 只含实际插入文档的资产，
    review/rejected 或 tables off 的资产不进入，其原文自然保留。

    Returns:
        (covered, per_item_counts)：covered 为块索引集合，
        per_item_counts 以 id(item) 为键记录每项资产抑制的块数。
    """
    from lib.caption_detection import is_explicit_caption_format

    covered: set = set()
    per_item_counts: Dict[int, int] = {}
    for item in items:
        final_bbox = item.get("final_bbox") or []
        if len(final_bbox) < 4:
            continue
        fx0, fy0, fx1, fy1 = (float(v) for v in final_bbox[:4])
        page = item.get("page")
        for idx, block in enumerate(document.blocks):
            if idx in protected_idx or idx in covered:
                continue
            if getattr(block, "type", "") not in ("paragraph", "heading"):
                continue
            block_page = getattr(block, "page", None)
            if page is not None and block_page is not None and int(block_page) != int(page):
                continue
            bbox = (getattr(block, "meta", None) or {}).get("bbox")
            if not bbox or len(bbox) < 4:
                continue
            text = (getattr(block, "text", "") or "").strip()
            if text and is_explicit_caption_format(text):
                continue
            x0, y0, x1, y1 = (float(v) for v in bbox[:4])
            if x0 >= fx0 - 2 and y0 >= fy0 - 2 and x1 <= fx1 + 2 and y1 <= fy1 + 2:
                covered.add(idx)
                per_item_counts[id(item)] = per_item_counts.get(id(item), 0) + 1
    return covered, per_item_counts


def _preserve_equation_regions(
    document,
    asset_result: Dict[str, Any],
    paths: Dict[str, str],
    images_enabled: bool,
) -> Dict[str, Any]:
    """独立公式碎片区域整块保留（BUG-145 / issue #4 问题5）。

    扫描件 OCR 会把一个独立公式拆成多个碎片段落（分子/分数线/分母各一段），
    直接序列化不可可靠消费。检测与分组由 lib.equation_regions 完成，
    这里只按原页证据保留，不猜公式内容：

    - --images figures 时按组 bbox 从原页截图，碎片段落替换为图片块；
    - 图片关闭（或截图失败退回）时整块合并为 ```text 代码块，保留 OCR 原文；
    - 检测结果标记为不完整（只有悬挂下标、边界无法补全）时不替换，
      原文保留，并在 equations.needs_review 中显式计为待复核。

    与已嵌入资产 final_bbox 重叠的碎片跳过（截图已覆盖该区域）。
    截图失败按降级处理而非硬失败：文本仍完整保留，不丢数据。
    """
    from lib.equation_regions import detect_equation_groups

    paragraph_items = []
    for idx, block in enumerate(document.blocks):
        if getattr(block, "type", "") != "paragraph":
            continue
        page = getattr(block, "page", None)
        bbox = (getattr(block, "meta", None) or {}).get("bbox")
        if page is None or not bbox or len(bbox) < 4:
            continue
        paragraph_items.append((idx, int(page), [float(v) for v in bbox[:4]], block.text))

    exclusions = []
    for item in asset_result.get("items") or []:
        final_bbox = item.get("final_bbox")
        page = item.get("page")
        if final_bbox and len(final_bbox) >= 4 and page is not None:
            exclusions.append((int(page), [float(v) for v in final_bbox[:4]]))

    groups = detect_equation_groups(paragraph_items, exclusions=exclusions)
    stats: Dict[str, Any] = {
        "detected": len(groups),
        "screenshot": 0,
        "text_merged": 0,
        "render_fallback": 0,
        "needs_review": 0,
        "groups": [],
    }
    if not groups:
        return stats

    import fitz

    from lib.markdown import MarkdownBlock
    from lib.output import get_unique_path, save_pixmap_clean

    md_dir = os.path.dirname(os.path.abspath(paths["out_md"]))
    member_indices: set = set()
    replacements: Dict[int, MarkdownBlock] = {}
    for seq, group in enumerate(groups, 1):
        indices = sorted(int(k) for k in group.member_keys)
        anchor = indices[0]
        if not group.complete:
            stats["needs_review"] += 1
            stats["groups"].append({
                "page": group.page,
                "bbox": [round(v, 1) for v in group.bbox],
                "members": len(indices),
                "mode": "needs_review",
            })
            print(
                f"WARNING: 公式区域边界不完整，保留原文待复核（page {group.page}）",
                file=sys.stderr,
            )
            continue
        member_indices.update(indices)
        merged = "\n".join(
            (document.blocks[i].text or "").strip()
            for i in indices
            if (document.blocks[i].text or "").strip()
        )
        if not merged:
            continue
        meta = {"equation_group": group.to_dict()}
        replacement: Optional[MarkdownBlock] = None
        if images_enabled:
            # BUG-151：多份 PDF 共用资源目录时文件名会撞车，save_pixmap_clean
            # 直接替换已有文件会覆盖用户已有的截图（AGENTS.md 第 10 条）；
            # 复用 get_unique_path 换用不冲突的文件名，保留既有文件。
            out_path, _ = get_unique_path(
                os.path.join(paths["asset_dir"], f"Equation_p{group.page}_{seq}.png")
            )
            try:
                with fitz.open(paths["pdf_path"]) as doc:
                    page = doc[group.page - 1]
                    clip = fitz.Rect(group.bbox) + (-3.0, -3.0, 3.0, 3.0)
                    clip = clip & page.rect
                    pix = page.get_pixmap(dpi=300, clip=clip)
                    save_pixmap_clean(pix, out_path)
                rel_path = os.path.relpath(out_path, md_dir).replace("\\", "/")
                replacement = MarkdownBlock(
                    type="image",
                    text=f"Equation p{group.page}",
                    path=rel_path,
                    caption=" ".join(merged.split()),
                    page=group.page,
                    meta=meta,
                )
                stats["screenshot"] += 1
            except Exception as exc:
                stats["render_fallback"] += 1
                print(
                    f"WARNING: 公式区域截图失败，退回文本合并（page {group.page}）: {exc}",
                    file=sys.stderr,
                )
        if replacement is None:
            replacement = MarkdownBlock(
                type="paragraph",
                text=f"```text\n{merged}\n```",
                page=group.page,
                meta=meta,
            )
            stats["text_merged"] += 1
        replacements[anchor] = replacement
        stats["groups"].append({
            "page": group.page,
            "bbox": [round(v, 1) for v in group.bbox],
            "members": len(indices),
            "mode": "screenshot" if replacement.type == "image" else "text",
        })

    new_blocks = []
    for idx, block in enumerate(document.blocks):
        if idx in member_indices:
            if idx in replacements:
                new_blocks.append(replacements[idx])
            continue
        new_blocks.append(block)
    document.blocks[:] = new_blocks
    return stats


def _place_assets_in_document(document, asset_result: Dict[str, Any], out_md: str) -> None:
    """把可插入资产放到对应题注旁；找不到题注的仍追加到文末。

    插入成功后，按 final_bbox 抑制被截图完整覆盖的正文散行（BUG-131），
    避免表体文字与截图双重呈现；题注锚点块与框外正文保留。

    index 引用的 PNG 缺失时（BUG-133），对应资产按 missing_file 移入
    omitted：不插入死链、不参与正文抑制、不计入已嵌入，报告状态
    因此进入 review。无 file 字段的条目保持既有静默跳过。
    """
    items = list(asset_result.get("items") or [])
    if not items:
        return

    index_json = asset_result.get("index_json") or ""
    present_items: List[Dict[str, Any]] = []
    missing_items: List[Dict[str, Any]] = []
    for item in items:
        file_value = item.get("current_file") or item.get("file") or ""
        if file_value and not os.path.isfile(
            os.path.join(os.path.dirname(index_json), file_value)
        ):
            missing_items.append(item)
        else:
            present_items.append(item)
    if missing_items:
        omitted = asset_result.setdefault("omitted", [])
        for item in missing_items:
            if "status" in item:
                item["extraction_status"] = item["status"]
            item["status"] = "missing_file"
            omitted.append(item)
        asset_result["items"] = present_items
        items = present_items
    if not items:
        return {"inline": [], "appendix": [], "suppressed": {}}

    used_blocks: set = set()
    placements: List[tuple] = []
    unmatched: List[Dict[str, Any]] = []
    placed_items: List[Dict[str, Any]] = []
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
        placed_items.append(item)
        placements.append((match_idx, _content_is_above_caption(item), image))

    suppress, per_item_counts = _blocks_covered_by_assets(
        document, placed_items + unmatched, used_blocks,
    )

    placements_by_idx = {idx: (before, image) for idx, before, image in placements}
    new_blocks: List = []
    for index, block in enumerate(document.blocks):
        if index in suppress:
            continue
        entry = placements_by_idx.get(index)
        if entry is None:
            new_blocks.append(block)
        else:
            before, image = entry
            if before:
                new_blocks.extend([image, block])
            else:
                new_blocks.extend([block, image])
    document.blocks[:] = new_blocks

    if unmatched:
        leftover = dict(asset_result)
        leftover["items"] = unmatched
        _append_asset_section(document, leftover, out_md)

    return {
        "inline": placed_items,
        "appendix": unmatched,
        "suppressed": per_item_counts,
    }


def _annotate_and_persist_embed_status(asset_result: Dict[str, Any],
                                       placement: Optional[Dict[str, Any]]) -> None:
    """把 Markdown 放置结果回写为逐资产嵌入字段（ADJ-015）。

    inline=题注旁内联、appendix=文末资产区；未插入（被质量门拦住或没有
    图片文件）的资产 referenced_in_markdown=False。只有 pdf_to_markdown
    在完成放置后调用；extract_pdf_assets 独立入口不写这些字段，
    避免虚构嵌入状态。
    """
    inline_ids = {id(i) for i in (placement or {}).get("inline", [])}
    appendix_ids = {id(i) for i in (placement or {}).get("appendix", [])}
    suppressed = (placement or {}).get("suppressed", {})
    for item in asset_result.get("items") or []:
        if id(item) in inline_ids:
            item["referenced_in_markdown"] = True
            item["embed_mode"] = "inline"
        elif id(item) in appendix_ids:
            item["referenced_in_markdown"] = True
            item["embed_mode"] = "appendix"
        else:
            item["referenced_in_markdown"] = False
            item["embed_mode"] = None
        item["suppressed_text_blocks"] = int(suppressed.get(id(item), 0))
    for item in asset_result.get("omitted") or []:
        item["referenced_in_markdown"] = False
        item["embed_mode"] = None
    _persist_embed_status_to_index(asset_result)


def _persist_embed_status_to_index(asset_result: Dict[str, Any]) -> None:
    """把逐资产嵌入字段回写进 index.json（ADJ-015，best-effort）。

    新格式 index.json 的 items/figures/tables 三处视图同步更新；
    旧格式（纯 list）就地更新。文件缺失或结构不符时静默跳过，
    不影响 Markdown 主产物。
    """
    index_json = asset_result.get("index_json") or ""
    if not index_json or not os.path.exists(index_json):
        return

    def key_of(entry: Dict[str, Any]):
        return (
            str(entry.get("type") or ""),
            str(entry.get("id") or ""),
            entry.get("page"),
            str(entry.get("file") or entry.get("current_file") or ""),
        )

    status_by_key = {}
    for entry in asset_result.get("items") or []:
        if "referenced_in_markdown" in entry:
            status_by_key[key_of(entry)] = {
                "referenced_in_markdown": bool(entry.get("referenced_in_markdown")),
                "embed_mode": entry.get("embed_mode"),
                "suppressed_text_blocks": int(entry.get("suppressed_text_blocks") or 0),
            }
    for entry in asset_result.get("omitted") or []:
        # 被质量门拦住的资产必然未嵌入；即使未经过 annotate 也按 False 回写
        status_by_key.setdefault(key_of(entry), {
            "referenced_in_markdown": bool(entry.get("referenced_in_markdown", False)),
            "embed_mode": entry.get("embed_mode"),
            "suppressed_text_blocks": int(entry.get("suppressed_text_blocks") or 0),
        })
    if not status_by_key:
        return
    try:
        with open(index_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        targets = []
        if isinstance(data, list):
            targets = [data]
        elif isinstance(data, dict):
            targets = [data[k] for k in ("items", "figures", "tables")
                       if isinstance(data.get(k), list)]
        for lst in targets:
            for entry in lst:
                status = status_by_key.get(key_of(entry))
                if status:
                    entry.update(status)
        with open(index_json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except (OSError, ValueError, TypeError) as exc:
        print(f"WARNING: 回写嵌入状态到 index.json 失败（不影响主产物）: {exc}",
              file=sys.stderr)


def _summarize_embed_status(asset_result: Dict[str, Any]) -> Dict[str, Any]:
    """控制台/报告用的嵌入汇总（ADJ-015）。"""
    items = asset_result.get("items") or []
    omitted = asset_result.get("omitted") or []
    inline = sum(1 for i in items
                 if i.get("referenced_in_markdown") and i.get("embed_mode") == "inline")
    appendix = sum(1 for i in items
                   if i.get("referenced_in_markdown") and i.get("embed_mode") == "appendix")
    reasons: Dict[str, int] = {}
    for entry in omitted:
        reason = str(entry.get("status") or "unknown")
        reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "extracted": asset_result.get("extracted_count", len(items) + len(omitted)),
        "embedded": inline + appendix,
        "inline": inline,
        "appendix": appendix,
        "omitted": len(omitted),
        "omitted_reasons": reasons,
    }


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    paths = _resolve_outputs(args)

    if not os.path.exists(paths["pdf_path"]):
        print(f"PDF not found: {paths['pdf_path']}", file=sys.stderr)
        return 1

    from lib.output import validate_output_targets

    problems = validate_output_targets([
        (paths["out_md"], False, "输出 Markdown"),
        (paths["asset_dir"], True, "资源目录"),
        (paths["text_dir"], True, "文本目录"),
        (paths["blocks_json"], False, "blocks JSON"),
        (paths["report_json"], False, "report JSON"),
    ])
    if problems:
        for problem in problems:
            print(f"[ERROR] {problem}", file=sys.stderr)
        return 2

    from lib.text_extract import pre_validate_pdf

    validation = pre_validate_pdf(paths["pdf_path"])
    if not validation.is_valid:
        print(f"[ERROR] PDF validation failed: {validation.errors}", file=sys.stderr)
        return 1

    try:
        os.makedirs(os.path.dirname(paths["out_md"]), exist_ok=True)
        os.makedirs(paths["asset_dir"], exist_ok=True)
        os.makedirs(paths["text_dir"], exist_ok=True)
        os.makedirs(os.path.dirname(paths["blocks_json"]), exist_ok=True)
        os.makedirs(os.path.dirname(paths["report_json"]), exist_ok=True)
    except OSError as exc:
        print(f"[ERROR] 创建输出目录失败: {exc}", file=sys.stderr)
        return 2

    document = _paragraphs_to_document(paths["pdf_path"], paths["stem"], validation)
    if not (args.images == "off" and args.tables == "off"):
        print(f"Asset dir: {paths['asset_dir']} "
              f"(relative --asset-dir resolves next to the Markdown file)")
    asset_result = _run_asset_extraction(args, paths)
    equation_stats = _preserve_equation_regions(
        document, asset_result, paths, images_enabled=args.images != "off"
    )
    placement = _place_assets_in_document(document, asset_result, paths["out_md"])
    if asset_result.get("enabled"):
        _annotate_and_persist_embed_status(asset_result, placement)
    embed_summary = _summarize_embed_status(asset_result) if asset_result.get("enabled") else None

    from lib.markdown import render_markdown

    try:
        with open(paths["out_md"], "w", encoding="utf-8") as f:
            f.write(render_markdown(document))

        with open(paths["blocks_json"], "w", encoding="utf-8") as f:
            json.dump(document.to_dict(), f, ensure_ascii=False, indent=2)
    except OSError as exc:
        print(f"[ERROR] 写入输出文件失败: {exc}", file=sys.stderr)
        return 2

    asset_exit = asset_result.get("exit_code")
    asset_failed = bool(asset_result.get("enabled") and asset_exit)
    omitted = asset_result.get("omitted") or []
    if asset_failed:
        report_status = "failed"
    elif omitted or equation_stats.get("needs_review"):
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
            "embedded_count": (embed_summary or {}).get("embedded", 0),
            "embed": {
                "inline": (embed_summary or {}).get("inline", 0),
                "appendix": (embed_summary or {}).get("appendix", 0),
            },
            "omitted": omitted,
            "omitted_reasons": (embed_summary or {}).get("omitted_reasons", {}),
            "index_json": asset_result.get("index_json", ""),
            "exit_code": asset_exit,
        },
        "ocr": {
            "mode": args.ocr,
            "status": "not_implemented" if args.ocr != "off" else "off",
        },
        "equations": equation_stats,
        "generated_at": datetime.now().isoformat(),
    }
    try:
        with open(paths["report_json"], "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        print(f"[ERROR] 写入 report JSON 失败: {exc}", file=sys.stderr)
        return 2

    print(f"Wrote Markdown: {paths['out_md']}")
    print(f"Wrote blocks: {paths['blocks_json']}")
    print(f"Wrote report: {paths['report_json']}")
    if embed_summary:
        reasons = ", ".join(
            f"{k} {v}" for k, v in sorted(embed_summary["omitted_reasons"].items())
        ) or "none"
        print(
            f"Assets: extracted {embed_summary['extracted']}, "
            f"embedded {embed_summary['embedded']} "
            f"(inline {embed_summary['inline']}, appendix {embed_summary['appendix']}), "
            f"omitted {embed_summary['omitted']} ({reasons})"
        )
    if equation_stats.get("detected"):
        print(
            f"Equations: detected {equation_stats['detected']}, "
            f"screenshot {equation_stats['screenshot']}, "
            f"text merged {equation_stats['text_merged']}"
            + (f", render fallback {equation_stats['render_fallback']}"
               if equation_stats.get("render_fallback") else "")
            + (f", needs review {equation_stats['needs_review']}"
               if equation_stats.get("needs_review") else "")
        )

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
