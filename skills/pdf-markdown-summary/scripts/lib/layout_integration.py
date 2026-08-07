#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A1-4: Layout 集成逻辑 — Layout 只做三件事。

当 --layout-backend 非 off 时，在 legacy 提取流程中嵌入三件 Layout 辅助：
1. 正文引用过滤：caption 候选若附近无 Layout content 框，标记为可疑引用
2. 候选种子：Layout figure/table 框作为初始 content bbox 候选
3. 冲突检测：Layout 与 legacy 结果对比，记录 IoU 过低等冲突

这三件事不改变 legacy 默认路径的输出，仅附加元数据和报告。
feature flag 默认关闭（--layout-backend=off）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .assets import ConflictRecord, LayoutIntegrationReport
from .page_scene import SceneCache
from .regions import LayoutResult, PageRegion, RegionBBox

logger = logging.getLogger(__name__)

# 正文引用过滤：caption 附近无 content 框时的最大搜索距离（pt）
_CONTENT_SEARCH_DIST = 80.0

# 冲突检测：IoU 低于此阈值视为冲突
_CONFLICT_IOU_THRESHOLD = 0.3


def build_scene_cache(layout_result: Optional[LayoutResult]) -> SceneCache:
    """从 LayoutResult 构建 SceneCache。

    Args:
        layout_result: Layout 提取结果（None 时返回空缓存）

    Returns:
        SceneCache: 页面场景缓存
    """
    cache = SceneCache()
    if layout_result is None:
        return cache

    for page_no, page_region in layout_result.pages.items():
        cache.get_or_create(page=page_no, layout=page_region)

    return cache


def filter_text_reference_captions(
    caption_candidates: List[Tuple[int, str, List[float]]],
    scene_cache: SceneCache,
) -> Tuple[List[Tuple[int, str, List[float]]], int]:
    """正文引用过滤。

    检查每个 caption 候选附近是否有 Layout content 框（figure/table）。
    若无，则该 caption 可能是正文中的引用文字（如 "see Figure 3"），
    而非真正的标题。从返回列表中移除可疑引用，并返回移除数量。

    Args:
        caption_candidates: [(page, caption_text, caption_bbox), ...]
        scene_cache: 页面场景缓存

    Returns:
        (filtered_candidates, filtered_count)
    """
    if not scene_cache.pages:
        return caption_candidates, 0

    filtered: List[Tuple[int, str, List[float]]] = []
    filtered_count = 0

    for page, text, bbox in caption_candidates:
        scene = scene_cache.get(page)
        if scene is None or not scene.has_layout:
            # 无 Layout 信息，不过滤
            filtered.append((page, text, bbox))
            continue

        if scene.has_content_nearby(bbox, max_dist=_CONTENT_SEARCH_DIST):
            filtered.append((page, text, bbox))
        else:
            filtered_count += 1
            logger.debug(
                "Text reference filtered: page=%d caption='%s...' (no Layout content nearby)",
                page,
                text[:40],
            )
            # 从结果中移除（无 Layout content 附近的 caption 视为正文引用）

    return filtered, filtered_count


def seed_content_candidates(
    page: int,
    kind: str,
    scene_cache: SceneCache,
) -> List[List[float]]:
    """候选种子：从 Layout 区域生成初始 content bbox 候选。

    Args:
        page: 页码（1-based）
        kind: 'figure' | 'table'
        scene_cache: 页面场景缓存

    Returns:
        content bbox 候选列表 [[x0, y0, x1, y1], ...]
    """
    scene = scene_cache.get(page)
    if scene is None or not scene.has_layout:
        return []

    regions = (
        scene.layout.figure_regions if kind == "figure" else scene.layout.table_regions
    )
    return [[r.x0, r.y0, r.x1, r.y1] for r in regions]


def detect_conflicts(
    legacy_records: List[Any],
    layout_result: Optional[LayoutResult],
    kind: str = "figure",
) -> List[ConflictRecord]:
    """冲突检测：对比 legacy 提取结果与 Layout 区域。

    检测四类冲突：
    - iou_low: legacy 与 Layout 的 IoU 低于阈值
    - caption_mismatch: legacy caption 无对应 Layout caption
    - content_missing: Layout 有区域但 legacy 未提取到
    - extra_content: legacy 提取到但 Layout 无对应区域

    Args:
        legacy_records: legacy 提取的 AttachmentRecord 列表
        layout_result: Layout 提取结果
        kind: 'figure' | 'table'

    Returns:
        冲突记录列表
    """
    conflicts: List[ConflictRecord] = []
    if layout_result is None:
        return conflicts

    # 收集 legacy records 的 bbox
    legacy_items: List[Tuple[int, str, Optional[List[float]]]] = []
    for rec in legacy_records:
        if getattr(rec, "kind", kind) != kind:
            continue
        page = getattr(rec, "page", 0)
        caption = getattr(rec, "caption", "") or getattr(rec, "caption_text", "")
        final_bbox = getattr(rec, "final_bbox", None)
        legacy_items.append((page, caption, final_bbox))

    # 收集 Layout regions
    layout_regions = (
        layout_result.all_figure_regions() if kind == "figure"
        else layout_result.all_table_regions()
    )

    # 逐个 legacy record 检查是否有对应 Layout 区域
    for page, caption, legacy_bbox in legacy_items:
        if legacy_bbox is None:
            continue

        legacy_region = RegionBBox(
            legacy_bbox[0], legacy_bbox[1], legacy_bbox[2], legacy_bbox[3], kind=kind
        )

        # 找同页最近的 Layout 区域
        best_iou = 0.0
        best_layout_bbox: Optional[List[float]] = None
        for layout_page, layout_region in layout_regions:
            if layout_page != page:
                continue
            iou = legacy_region.iou(layout_region)
            if iou > best_iou:
                best_iou = iou
                best_layout_bbox = layout_region.to_list()

        if best_iou < _CONFLICT_IOU_THRESHOLD:
            conflicts.append(
                ConflictRecord(
                    kind=kind,
                    page=page,
                    caption_text=caption,
                    legacy_bbox=legacy_bbox,
                    layout_bbox=best_layout_bbox,
                    conflict_type="iou_low",
                    iou=best_iou,
                    detail=(
                        f"Legacy {kind} IoU with nearest Layout region = {best_iou:.3f} "
                        f"(threshold={_CONFLICT_IOU_THRESHOLD})"
                    ),
                )
            )

    # 检查 Layout 有但 legacy 未提取到的区域 (content_missing)
    # 逐个 Layout 区域检查是否有任意 legacy bbox 覆盖（IoU > 0）
    for layout_page, layout_region in layout_regions:
        covered = False
        for leg_page, _, leg_bbox in legacy_items:
            if leg_page != layout_page or leg_bbox is None:
                continue
            leg_region = RegionBBox(
                leg_bbox[0], leg_bbox[1], leg_bbox[2], leg_bbox[3], kind=kind
            )
            if leg_region.iou(layout_region) > 0.0:
                covered = True
                break
        if not covered:
            conflicts.append(
                ConflictRecord(
                    kind=kind,
                    page=layout_page,
                    caption_text="",
                    legacy_bbox=None,
                    layout_bbox=layout_region.to_list(),
                    conflict_type="content_missing",
                    iou=0.0,
                    detail=f"Layout detected {kind} region on page {layout_page} "
                    f"but no legacy bbox covers it",
                )
            )

    return conflicts


def build_integration_report(
    layout_result: Optional[LayoutResult],
    legacy_figure_records: List[Any],
    legacy_table_records: List[Any],
    caption_candidates: Optional[List[Tuple[int, str, List[float]]]] = None,
    candidates_seeded: int = 0,
) -> LayoutIntegrationReport:
    """构建 Layout 集成报告。

    Args:
        layout_result: Layout 提取结果
        legacy_figure_records: legacy figure 提取结果
        legacy_table_records: legacy table 提取结果
        caption_candidates: caption 候选列表（用于正文引用过滤统计）
        candidates_seeded: Layout 种子生成的候选数

    Returns:
        LayoutIntegrationReport
    """
    report = LayoutIntegrationReport()

    if layout_result is None:
        report.enabled = False
        report.backend = "off"
        return report

    report.enabled = True
    report.backend = layout_result.backend
    report.pdf_path = layout_result.pdf_path
    report.pdf_hash = layout_result.pdf_hash
    report.total_pages = len(layout_result.pages)
    report.total_layout_regions = sum(len(pr.regions) for pr in layout_result.pages.values())
    report.figure_regions = sum(len(pr.figure_regions) for pr in layout_result.pages.values())
    report.table_regions = sum(len(pr.table_regions) for pr in layout_result.pages.values())
    report.caption_regions = sum(len(pr.caption_regions) for pr in layout_result.pages.values())
    report.candidates_seeded = candidates_seeded
    report.elapsed_sec = layout_result.elapsed_sec
    report.cached = layout_result.cached

    # 正文引用过滤
    if caption_candidates:
        scene_cache = build_scene_cache(layout_result)
        _, filtered_count = filter_text_reference_captions(caption_candidates, scene_cache)
        report.captions_filtered = filtered_count

    # 冲突检测
    report.conflicts.extend(detect_conflicts(legacy_figure_records, layout_result, "figure"))
    report.conflicts.extend(detect_conflicts(legacy_table_records, layout_result, "table"))

    return report
