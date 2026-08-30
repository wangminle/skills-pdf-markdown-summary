#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Commit 13: 入口瘦身 - 核心入口模块

本模块提供 extract_pdf_assets 的核心入口点：
- parse_args(): 命令行参数解析
- main(): 主入口函数

架构说明：
- 本模块作为新的稳定 CLI 入口
- 调用 scripts/lib/ 下的模块化组件
- V0.3.1：主流程不再依赖 scripts-old/

使用方式：
    python -m scripts.core.extract_pdf_assets --pdf paper.pdf --preset robust

或通过兼容层：
    python scripts/extract_pdf_assets.py --pdf paper.pdf --preset robust
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import List, Optional

# 确保 scripts 目录在 path 中
_scripts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

# 从 lib 导入核心组件
from lib.env_priority import apply_preset_robust, get_env_str, parse_comma_list
from lib.extract_figures import extract_figures
from lib.extract_tables import extract_tables
from lib.figure_contexts import build_figure_contexts
from lib.layout_model import should_enable_layout_driven
from lib.models import AttachmentRecord, DocumentLayoutModel, GatheredText
from lib.output import prune_unindexed_images, write_index_json, write_manifest
from lib.text_extract import gather_structured_text, pre_validate_pdf, try_extract_text

# 日志系统
try:
    from lib.extraction_logger import configure_logging, get_logger, log_event

    _HAS_EXTRACTION_LOGGER = True
except ImportError:
    _HAS_EXTRACTION_LOGGER = False

    def configure_logging(level="INFO", **kwargs):
        logging.basicConfig(
            level=getattr(logging, level.upper(), logging.INFO),
            format="[%(levelname)s] %(message)s",
        )
        return "fallback"

    def get_logger(name):
        return logging.getLogger(name)

    def log_event(event_type, **kwargs):
        pass


logger = get_logger(__name__)


def build_parser_modular() -> argparse.ArgumentParser:
    """构建 extract_pdf_assets 的 argparse parser（供 parse 与 preset dest 映射共用）。"""
    p = argparse.ArgumentParser(
        description="Extract text and figure/table images from a PDF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/extract_pdf_assets.py --pdf paper.pdf
  python scripts/extract_pdf_assets.py --pdf paper.pdf --preset robust
  python scripts/extract_pdf_assets.py --pdf paper.pdf --preset robust --debug-captions
""",
    )

    # === 输入/输出 ===
    p.add_argument("--pdf", required=True, help="Path to PDF file")
    p.add_argument("--preset", default=None, choices=["robust"], help="Parameter preset")
    p.add_argument("--out-text", default=None, help="Output text path (.txt)")
    p.add_argument("--out-dir", default=None, help="Output directory for PNGs")
    p.add_argument("--manifest", default=None, help="Output CSV manifest path")
    p.add_argument("--index-json", default=None, help="Output index.json path")
    p.add_argument(
        "--prune-images",
        action="store_true",
        default=True,
        help="Remove unindexed Figure_*/Table_* PNGs (default: enabled)",
    )
    p.add_argument("--no-prune-images", action="store_false", dest="prune_images")

    # === 渲染与裁剪（Figure） ===
    p.add_argument("--dpi", type=int, default=300, help="Render DPI")
    p.add_argument("--clip-height", type=float, default=650.0, help="Clip window height (pt)")
    p.add_argument("--margin-x", type=float, default=20.0, help="Horizontal margin (pt)")
    p.add_argument("--caption-gap", type=float, default=5.0, help="Gap between caption and crop (pt)")
    p.add_argument("--max-caption-chars", type=int, default=160, help="Max caption chars for filename")
    p.add_argument("--max-caption-words", type=int, default=12, help="Max words for filename")
    p.add_argument("--min-figure", type=int, default=1, help="Minimum figure number")
    p.add_argument("--max-figure", type=int, default=999, help="Maximum figure number")
    p.add_argument(
        "--include-figures",
        dest="include_figures",
        action="store_true",
        default=True,
        help="Enable figure extraction (default: enabled)",
    )
    p.add_argument(
        "--no-figures",
        dest="include_figures",
        action="store_false",
        help="Disable figure extraction",
    )

    # === Autocrop ===
    p.add_argument("--autocrop", action="store_true", default=False, help="Enable autocrop for figures")
    p.add_argument("--autocrop-pad", type=int, default=30, help="Autocrop padding (px)")
    p.add_argument("--autocrop-white-th", type=int, default=250, help="Autocrop white threshold")
    p.add_argument(
        "--autocrop-white-threshold",
        type=int,
        dest="autocrop_white_th",
        help="Alias of --autocrop-white-th",
    )

    # === 方向覆盖（Figure） ===
    p.add_argument("--below", default="", help="Figure ids to crop BELOW captions (e.g. 2,3,S1)")
    p.add_argument("--above", default="", help="Figure ids to crop ABOVE captions (e.g. 1,4)")
    p.add_argument("--allow-continued", action="store_true", default=False, help="Allow exporting continued items")

    # === Phase A: text-trim ===
    p.add_argument("--text-trim", action="store_true", default=False, help="Enable text trim")
    p.add_argument("--text-trim-width-ratio", type=float, default=0.5, help="Text trim width ratio")
    p.add_argument("--text-trim-font-min", type=float, default=7.0, help="Min font size for masking")
    p.add_argument("--text-trim-font-max", type=float, default=16.0, help="Max font size for masking")
    p.add_argument("--text-trim-gap", type=float, default=6.0, help="Gap for text trim (pt)")
    p.add_argument("--adjacent-th", type=float, default=24.0, help="Adjacency threshold (pt)")

    # === Phase B: objects ===
    p.add_argument("--object-pad", type=float, default=8.0, help="Object padding (pt)")
    p.add_argument("--object-min-area-ratio", type=float, default=0.012, help="Min area ratio for object region")
    p.add_argument("--object-merge-gap", type=float, default=6.0, help="Object merge gap (pt)")

    # === Phase D: text-mask assisted autocrop ===
    p.add_argument("--autocrop-mask-text", action="store_true", default=False, help="Mask text for autocrop")
    p.add_argument("--mask-font-max", type=float, default=14.0, help="Max font size to mask")
    p.add_argument("--mask-width-ratio", type=float, default=0.5, help="Mask width ratio")
    p.add_argument("--mask-top-frac", type=float, default=0.6, help="Near-side fraction for mask")

    # === Safety ===
    p.add_argument("--no-refine", default="", help="Comma-separated figure ids to disable refinements")
    p.add_argument(
        "--refine-near-edge-only",
        action="store_true",
        default=True,
        help="Only adjust near-caption edge (default: enabled)",
    )
    p.add_argument(
        "--no-refine-near-edge-only",
        action="store_false",
        dest="refine_near_edge_only",
        help="Allow adjusting both edges during refinement",
    )

    # === 表格选项 ===
    p.add_argument(
        "--include-tables",
        dest="include_tables",
        action="store_true",
        default=True,
        help="Enable table extraction (default: enabled)",
    )
    p.add_argument("--no-tables", dest="include_tables", action="store_false", help="Disable table extraction")
    p.add_argument("--table-clip-height", type=float, default=520.0, help="Table clip height (pt)")
    p.add_argument("--table-margin-x", type=float, default=26.0, help="Table margin-x (pt)")
    p.add_argument("--table-caption-gap", type=float, default=6.0, help="Table caption gap (pt)")
    p.add_argument("--t-below", default="", help="Table ids to crop BELOW captions")
    p.add_argument("--t-above", default="", help="Table ids to crop ABOVE captions")
    p.add_argument("--table-autocrop", action="store_true", default=True, help="Enable table autocrop")
    p.add_argument("--no-table-autocrop", dest="table_autocrop", action="store_false", help="Disable table autocrop")
    p.add_argument("--table-autocrop-pad", type=int, default=20, help="Table autocrop padding (px)")
    p.add_argument("--table-adjacent-th", type=float, default=28.0, help="Table adjacency threshold (pt)")
    p.add_argument("--table-object-min-area-ratio", type=float, default=0.005, help="Table object min area ratio")
    p.add_argument("--table-object-merge-gap", type=float, default=4.0, help="Table object merge gap")

    # === 智能识别与版式驱动 ===
    p.add_argument(
        "--smart-caption-detection",
        action="store_true",
        default=True,
        help="Enable smart caption detection (default: enabled)",
    )
    p.add_argument("--no-smart-caption-detection", action="store_false", dest="smart_caption_detection")
    p.add_argument("--debug-captions", action="store_true", default=False, help="Print caption scoring details")
    p.add_argument("--debug-visual", action="store_true", default=False, help="Enable debug visualization output")
    p.add_argument(
        "--adaptive-line-height",
        action="store_true",
        default=True,
        help="Enable adaptive line height (default: enabled)",
    )
    p.add_argument("--no-adaptive-line-height", action="store_false", dest="adaptive_line_height")
    p.add_argument("--layout-driven", default="on", choices=["auto", "on", "off"], help="Layout driven mode")

    # === A1: Layout 语义区域后端（feature flag，默认关闭） ===
    p.add_argument(
        "--layout-backend",
        default=None,
        choices=["off", "pymupdf4llm"],
        help="Layout backend for semantic region extraction (default: off, "
        "env: PDF_SUMMARY_LAYOUT_BACKEND)",
    )

    # === 日志 ===
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    p.add_argument("--log-file", default=None)
    p.add_argument("--log-jsonl", default=None)

    return p


def parse_args_modular(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """
    命令行参数解析。

    Args:
        argv: 命令行参数列表，默认使用 sys.argv[1:]

    Returns:
        argparse.Namespace
    """
    return build_parser_modular().parse_args(argv)


def main_modular(argv: Optional[List[str]] = None) -> int:
    """
    主入口函数。

    解析参数 → 文本提取 → 图像提取 → 写出索引
    """
    parser = build_parser_modular()
    args = parser.parse_args(argv)

    if getattr(args, "preset", None) == "robust":
        apply_preset_robust(args, argv=argv, parser=parser)

    pdf_path = os.path.abspath(args.pdf)
    if not os.path.exists(pdf_path):
        logger.error(f"PDF not found: {pdf_path}")
        return 1

    pdf_dir = os.path.dirname(pdf_path)
    pdf_stem = os.path.splitext(os.path.basename(pdf_path))[0]

    out_dir = os.path.abspath(args.out_dir or os.path.join(pdf_dir, "images"))
    out_text = os.path.abspath(args.out_text or os.path.join(pdf_dir, "text", f"{pdf_stem}.txt"))
    text_dir = os.path.dirname(out_text)
    gathered_json = os.path.join(text_dir, "gathered_text.json")

    index_json = os.path.abspath(args.index_json or os.path.join(out_dir, "index.json"))
    manifest_path = os.path.abspath(args.manifest) if args.manifest else None

    layout_model_json = os.path.join(out_dir, "layout_model.json")
    figure_contexts_json = os.path.join(out_dir, "figure_contexts.json")

    # 与 scripts-old 行为保持一致：默认开启结构化日志落盘到 out_dir/run.log.jsonl
    if getattr(args, "log_jsonl", None) is None:
        args.log_jsonl = os.path.join(out_dir, "run.log.jsonl")

    run_id = configure_logging(level=args.log_level, log_file=args.log_file, log_jsonl=args.log_jsonl)

    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(text_dir, exist_ok=True)

    validation = pre_validate_pdf(pdf_path)
    if not validation.is_valid:
        logger.error(f"PDF validation failed: {validation.errors}")
        return 1

    try_extract_text(pdf_path, out_text)
    gathered_text: GatheredText = gather_structured_text(pdf_path, out_json=gathered_json)

    layout_model: Optional[DocumentLayoutModel] = None
    enable_layout = False
    if args.layout_driven == "on":
        enable_layout = True
    elif args.layout_driven == "auto":
        enable_layout, _ = should_enable_layout_driven(pdf_path)
    elif args.layout_driven == "off":
        enable_layout = False

    if enable_layout:
        from lib.text_extract import extract_text_with_format

        layout_model = extract_text_with_format(pdf_path, out_json=layout_model_json)

    # === A1: Layout 语义区域后端（feature flag） ===
    layout_backend_name = args.layout_backend
    if layout_backend_name is None:
        layout_backend_name = get_env_str("PDF_SUMMARY_LAYOUT_BACKEND", "off")

    layout_result = None
    layout_report = None
    if layout_backend_name and layout_backend_name.lower() != "off":
        try:
            from lib.backends import get_backend
            from lib.layout_integration import build_integration_report

            backend = get_backend(layout_backend_name)
            if backend is not None:
                logger.info(
                    "Layout backend '%s' v%s enabled for %s",
                    backend.name, backend.version, pdf_path,
                )
                layout_result = backend.extract(pdf_path)
                logger.info(
                    "Layout extracted: %d pages, %d regions, %.3fs (cached=%s)",
                    len(layout_result.pages),
                    sum(len(pr.regions) for pr in layout_result.pages.values()),
                    layout_result.elapsed_sec,
                    layout_result.cached,
                )
            else:
                logger.warning(
                    "Layout backend '%s' not available, falling back to off",
                    layout_backend_name,
                )
        except Exception as e:
            logger.warning("Layout backend error: %s, falling back to off", e)

    below_figs = parse_comma_list(args.below)
    above_figs = parse_comma_list(args.above)
    no_refine_figs = parse_comma_list(args.no_refine)

    records: List[AttachmentRecord] = []
    if getattr(args, "include_figures", True):
        records.extend(
            extract_figures(
                pdf_path=pdf_path,
                out_dir=out_dir,
                dpi=args.dpi,
                clip_height=args.clip_height,
                margin_x=args.margin_x,
                caption_gap=args.caption_gap,
                max_caption_chars=args.max_caption_chars,
                max_caption_words=args.max_caption_words,
                min_figure=args.min_figure,
                max_figure=args.max_figure,
                autocrop=bool(args.autocrop),
                autocrop_pad_px=args.autocrop_pad,
                autocrop_white_threshold=args.autocrop_white_th,
                below_figs=below_figs,
                above_figs=above_figs,
                text_trim=bool(args.text_trim),
                text_trim_width_ratio=args.text_trim_width_ratio,
                text_trim_font_min=args.text_trim_font_min,
                text_trim_font_max=args.text_trim_font_max,
                text_trim_gap=args.text_trim_gap,
                adjacent_th=args.adjacent_th,
                object_pad=args.object_pad,
                object_min_area_ratio=args.object_min_area_ratio,
                object_merge_gap=args.object_merge_gap,
                autocrop_mask_text=bool(args.autocrop_mask_text),
                mask_font_max=args.mask_font_max,
                mask_width_ratio=args.mask_width_ratio,
                mask_top_frac=args.mask_top_frac,
                refine_near_edge_only=bool(args.refine_near_edge_only),
                no_refine_figs=no_refine_figs,
                allow_continued=bool(args.allow_continued),
                smart_caption_detection=bool(args.smart_caption_detection),
                debug_captions=bool(args.debug_captions),
                debug_visual=bool(args.debug_visual),
                adaptive_line_height=bool(args.adaptive_line_height),
                layout_model=layout_model,
            )
        )

    if getattr(args, "include_tables", True):
        t_below = parse_comma_list(args.t_below)
        t_above = parse_comma_list(args.t_above)
        # --no-refine 同时作用于 Figure 和 Table，保持与文档 2.1 节约定一致
        records.extend(
            extract_tables(
                pdf_path=pdf_path,
                out_dir=out_dir,
                dpi=args.dpi,
                table_clip_height=args.table_clip_height,
                table_margin_x=args.table_margin_x,
                table_caption_gap=args.table_caption_gap,
                max_caption_chars=args.max_caption_chars,
                max_caption_words=args.max_caption_words,
                autocrop=bool(args.table_autocrop),
                autocrop_pad_px=args.table_autocrop_pad,
                autocrop_white_threshold=args.autocrop_white_th,
                t_below=t_below,
                t_above=t_above,
                text_trim=bool(args.text_trim),
                text_trim_width_ratio=args.text_trim_width_ratio,
                text_trim_font_min=args.text_trim_font_min,
                text_trim_font_max=args.text_trim_font_max,
                text_trim_gap=args.text_trim_gap,
                adjacent_th=args.table_adjacent_th,
                object_pad=args.object_pad,
                object_min_area_ratio=args.table_object_min_area_ratio,
                object_merge_gap=args.table_object_merge_gap,
                autocrop_mask_text=bool(args.autocrop_mask_text),
                mask_font_max=args.mask_font_max,
                mask_width_ratio=args.mask_width_ratio,
                mask_top_frac=args.mask_top_frac,
                refine_near_edge_only=bool(args.refine_near_edge_only),
                allow_continued=bool(args.allow_continued),
                smart_caption_detection=bool(args.smart_caption_detection),
                debug_captions=bool(args.debug_captions),
                debug_visual=bool(args.debug_visual),
                adaptive_line_height=bool(args.adaptive_line_height),
                layout_model=layout_model,
                no_refine_tables=no_refine_figs,
            )
        )

    build_figure_contexts(
        pdf_path,
        records,
        gathered_text=gathered_text,
        out_json=figure_contexts_json,
    )

    # === A1/A2/A3: Layout 后端开启时的影子报告 + 可选精修 ===
    pairing_results = None
    if layout_result is not None:
        # 统一从 records 提取 caption 候选：优先真实 caption_bbox，禁止用 final_bbox 冒充
        def _caption_candidates_for_pairing(with_kind: bool):
            out = []
            for r in records:
                page = getattr(r, "page", 0)
                text = getattr(r, "caption", "") or getattr(r, "caption_text", "") or ""
                bbox = getattr(r, "caption_bbox", None)
                kind = getattr(r, "kind", "figure")
                if not (page and text and bbox):
                    continue
                if with_kind:
                    out.append((page, text, bbox, kind))
                else:
                    out.append((page, text, bbox))
            return out

        # A1: Layout 集成报告
        try:
            from lib.layout_integration import build_integration_report

            figure_records = [r for r in records if getattr(r, "kind", "figure") == "figure"]
            table_records = [r for r in records if getattr(r, "kind", "") == "table"]
            caption_candidates = _caption_candidates_for_pairing(with_kind=False)

            layout_report = build_integration_report(
                layout_result=layout_result,
                legacy_figure_records=figure_records,
                legacy_table_records=table_records,
                caption_candidates=caption_candidates,
            )
            report_path = os.path.join(out_dir, "layout_integration.json")
            import json as _json

            with open(report_path, "w", encoding="utf-8") as f:
                _json.dump(layout_report.to_dict(), f, ensure_ascii=False, indent=2)
            logger.info(
                "Layout integration report: %d conflicts, %d captions filtered -> %s",
                len(layout_report.conflicts),
                layout_report.captions_filtered,
                report_path,
            )
        except Exception as e:
            logger.warning("Layout integration report failed: %s", e)

        # A2: 全页配对与多框（结果供 A3 复用，避免重复配对）
        try:
            from lib.pairing import pair_layout_regions, pairing_report

            caption_candidates = _caption_candidates_for_pairing(with_kind=True)
            # 若 records 尚无 caption_bbox，退回 Layout 自带 caption_regions（传 None）
            pairing_results = pair_layout_regions(
                layout_result,
                caption_candidates if caption_candidates else None,
            )
            pair_report = pairing_report(pairing_results)

            pair_report_path = os.path.join(out_dir, "layout_pairing.json")
            import json as _json2

            with open(pair_report_path, "w", encoding="utf-8") as f:
                _json2.dump(pair_report, f, ensure_ascii=False, indent=2)
            logger.info(
                "Layout pairing: %d pairs, %d multi-frame, %d duplicate groups -> %s",
                pair_report["total_pairs"],
                pair_report["multi_frame_count"],
                pair_report["duplicate_occupancy"]["n_groups"],
                pair_report_path,
            )
        except Exception as e:
            logger.warning("Layout pairing failed: %s", e)
            pairing_results = None

        # A3: 精修改造（复用 A2 pairing_results）
        if pairing_results is not None:
            try:
                from lib.pipeline import run_refinement_pipeline

                refinement_report = run_refinement_pipeline(
                    records=records,
                    pairing_results=pairing_results,
                    pdf_path=pdf_path,
                    out_dir=out_dir,
                    dpi=args.dpi,
                )

                refine_report_path = os.path.join(out_dir, "layout_refinement.json")
                import json as _json3

                with open(refine_report_path, "w", encoding="utf-8") as f:
                    _json3.dump(refinement_report.to_dict(), f, ensure_ascii=False, indent=2)
                logger.info(
                    "A3 refinement: %d/%d matched, %d refined, %d applied, %d kept legacy -> %s",
                    refinement_report.matched,
                    refinement_report.total_records,
                    refinement_report.refined,
                    refinement_report.applied,
                    refinement_report.kept_legacy,
                    refine_report_path,
                )
            except Exception as e:
                logger.warning("A3 refinement failed: %s", e)

    write_manifest(records, manifest_path)
    write_index_json(
        records,
        index_json,
        pdf_path=pdf_path,
        preset=args.preset,
        run_id=run_id,
        log_jsonl=args.log_jsonl,
        layout_model=layout_model,
        validation=validation,
    )

    if args.prune_images:
        pruned = prune_unindexed_images(out_dir=out_dir, index_json_path=index_json)
        if pruned:
            logger.info(f"Pruned {pruned} unindexed images")

    return 0


__all__ = [
    "parse_args",
    "main",
    "parse_args_modular",
    "main_modular",
    "AttachmentRecord",
    "DocumentLayoutModel",
    "GatheredText",
    "write_index_json",
    "write_manifest",
    "prune_unindexed_images",
    "pre_validate_pdf",
    "try_extract_text",
    "gather_structured_text",
    "build_figure_contexts",
]


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """
    命令行参数解析入口（模块化实现）。
    """
    return parse_args_modular(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """
    主入口（模块化实现）。
    """
    return main_modular(argv)


if __name__ == "__main__":
    sys.exit(main())
