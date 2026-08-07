#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A2: 全页配对与多框。

实现同页序列对齐 + 一对一匹配，消除候选重复占用。
支持多框 content_bboxes 并集（多 panel/组合图）。

当 layout-backend 开启时，用 Layout 语义区域做配对；
关闭时不执行，legacy 路径不变。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .assets import AssetCandidate, PairingResult
from .regions import LayoutResult, PageRegion, RegionBBox

logger = logging.getLogger(__name__)

# 配对参数
_DEFAULT_MAX_DIST = 200.0  # caption 到 content 的最大搜索距离（pt）
_DEFAULT_IOU_THRESHOLD = 0.05  # 低于此 IoU 不考虑配对
_MULTI_FRAME_MAX_GAP = 30.0  # 多框分组的最大间距（pt）
_MULTI_FRAME_MIN_SIZE = 50.0  # 多框分组的最小区域尺寸（pt）


def _bbox_to_region(bbox: List[float], kind: str = "other") -> RegionBBox:
    """将 [x0, y0, x1, y1] 转为 RegionBBox。"""
    return RegionBBox(bbox[0], bbox[1], bbox[2], bbox[3], kind=kind)


def _cost_function(
    caption: RegionBBox,
    content: RegionBBox,
    page_height: float = 800.0,
) -> float:
    """配对代价函数。

    综合 IoU、距离和方向一致性。

    Returns:
        代价值（越小越好）
    """
    iou = caption.iou(content)
    dist = caption.edge_distance(content)

    # 方向偏好：caption 通常在 content 上方或下方
    vgap = caption.vertical_gap(content)
    h_overlap = caption.horizontal_overlap(content)

    # 水平重叠加分（caption 和 content 通常水平对齐）
    overlap_ratio = h_overlap / max(caption.width, 1.0) if caption.width > 0 else 0.0

    # 代价 = 距离惩罚 - IoU 奖励 - 水平对齐奖励
    cost = dist / 100.0  # 距离每 100pt 增加 1 代价
    cost -= iou * 5.0  # IoU 每增加 0.2 减少 1 代价
    cost -= overlap_ratio * 2.0  # 水平对齐奖励

    # 方向惩罚：如果 content 在 caption 左侧或右侧（非上下），增加代价
    if vgap < 5.0 and h_overlap < min(caption.width, content.width) * 0.3:
        cost += 3.0  # 非上下关系，增加代价

    return cost


def pair_page(
    page: int,
    captions: List[RegionBBox],
    contents: List[RegionBBox],
    page_height: float = 800.0,
    max_dist: float = _DEFAULT_MAX_DIST,
    kind: str = "figure",
) -> PairingResult:
    """单页配对：caption 与 content 的一对一匹配。

    使用贪心算法：
    1. 计算所有 (caption, content) 对的代价
    2. 按代价排序
    3. 贪心分配，确保一对一

    Args:
        page: 页码（1-based）
        captions: caption 区域列表
        contents: content 区域列表（figure/table）
        page_height: 页面高度（pt）
        max_dist: 最大配对距离
        kind: 资产类型（'figure' | 'table'），写入 AssetCandidate.kind

    Returns:
        PairingResult
    """
    result = PairingResult(page=page, method="greedy_nearest")

    if not captions or not contents:
        result.orphan_captions = [
            _region_to_candidate(c, "caption", kind=kind) for c in captions
        ]
        result.orphan_contents = [
            _region_to_candidate(c, "content", kind=kind) for c in contents
        ]
        return result

    # 计算所有配对的代价
    pairs: List[Tuple[float, int, int]] = []
    for ci, cap in enumerate(captions):
        for oi, content in enumerate(contents):
            dist = cap.edge_distance(content)
            if dist > max_dist:
                continue
            cost = _cost_function(cap, content, page_height)
            pairs.append((cost, ci, oi))

    # 按代价排序
    pairs.sort(key=lambda x: x[0])

    # 贪心一对一分配
    used_caps: set = set()
    used_contents: set = set()

    for cost, ci, oi in pairs:
        if ci in used_caps or oi in used_contents:
            continue
        used_caps.add(ci)
        used_contents.add(oi)

        cap = captions[ci]
        content = contents[oi]

        # 构建配对（kind 必须写入，否则 A3 匹配会把 table 错归到 figure）
        asset_kind = getattr(content, "kind", None) or kind
        candidate = AssetCandidate(
            kind=asset_kind,
            page=page,
            caption_bbox=cap.to_list(),
            content_bboxes=[content.to_list()],
            sources={"layout"},
            confidence=max(0.0, 1.0 - abs(cost) / 10.0),
        )

        # 多框分组：查找附近同 kind 的未使用 content（按对象身份标记索引，避免相等 bbox 误标）
        extra_frames = _find_multi_frames(
            content, contents, used_contents, page_height
        )
        extra_ids = {id(ef) for ef in extra_frames}
        for ef_i, ef in enumerate(contents):
            if ef_i in used_contents or id(ef) not in extra_ids:
                continue
            candidate.content_bboxes.append(ef.to_list())
            used_contents.add(ef_i)

        result.pairs.append((candidate, [candidate]))

    # 未配对的孤儿
    result.orphan_captions = [
        _region_to_candidate(captions[i], "caption", kind=kind)
        for i in range(len(captions))
        if i not in used_caps
    ]
    result.orphan_contents = [
        _region_to_candidate(contents[i], "content", kind=kind)
        for i in range(len(contents))
        if i not in used_contents
    ]

    # 整体置信度
    if result.pairs:
        result.confidence = sum(p[0].confidence for p in result.pairs) / len(result.pairs)

    return result


def _find_multi_frames(
    primary: RegionBBox,
    all_contents: List[RegionBBox],
    used: set,
    page_height: float,
) -> List[RegionBBox]:
    """查找主 content 框附近的额外同 kind 框（多 panel）。

    条件：
    1. 未被使用
    2. 与主框距离 <= _MULTI_FRAME_MAX_GAP
    3. 尺寸 >= _MULTI_FRAME_MIN_SIZE
    4. 水平或垂直对齐（共享边或投影重叠）

    Args:
        primary: 主 content 框
        all_contents: 全部 content 框
        used: 已使用的索引集合
        page_height: 页面高度

    Returns:
        额外框列表
    """
    extras: List[RegionBBox] = []
    for i, content in enumerate(all_contents):
        if i in used or content is primary:
            continue
        if content.width < _MULTI_FRAME_MIN_SIZE and content.height < _MULTI_FRAME_MIN_SIZE:
            continue

        dist = primary.edge_distance(content)
        if dist > _MULTI_FRAME_MAX_GAP:
            continue

        # 水平或垂直对齐检查
        h_overlap = primary.horizontal_overlap(content)
        vgap = primary.vertical_gap(content)

        # 水平排列（左右相邻，y 范围重叠）
        if h_overlap < min(primary.width, content.width) * 0.3 and vgap < 10.0:
            extras.append(content)
        # 垂直排列（上下相邻，x 范围重叠）
        elif vgap < _MULTI_FRAME_MAX_GAP and h_overlap > min(primary.width, content.width) * 0.5:
            extras.append(content)

    return extras


def _region_to_candidate(
    region: RegionBBox,
    role: str,
    kind: str = "figure",
) -> AssetCandidate:
    """将 RegionBBox 转为 AssetCandidate（用于孤儿列表）。"""
    asset_kind = getattr(region, "kind", None) or kind
    if asset_kind in ("caption", "other", "text"):
        asset_kind = kind
    cand = AssetCandidate(
        kind=asset_kind,
        page=0,
        sources={"layout"},
        confidence=0.0,
    )
    if role == "caption":
        cand.caption_bbox = region.to_list()
    else:
        cand.content_bboxes = [region.to_list()]
    return cand


def pair_layout_regions(
    layout_result: LayoutResult,
    caption_candidates: Optional[List[Tuple[int, str, List[float], str]]] = None,
) -> Dict[int, PairingResult]:
    """对整个 PDF 的 Layout 区域进行全页配对。

    Args:
        layout_result: Layout 提取结果
        caption_candidates: 外部 caption 候选 [(page, text, bbox, kind), ...]
            如果提供，优先使用这些 caption；否则使用 Layout caption 区域

    Returns:
        按页码索引的 PairingResult
    """
    results: Dict[int, PairingResult] = {}

    # 按 kind 分组处理
    for kind in ("figure", "table"):
        content_class = "figure_regions" if kind == "figure" else "table_regions"

        for page_no, page_region in layout_result.pages.items():
            # 获取 content 区域
            content_regions = getattr(page_region, content_class, [])
            if not content_regions:
                continue

            # 获取 caption 区域
            if caption_candidates:
                # 使用外部 caption 候选
                caps = [
                    RegionBBox(
                        bbox[0], bbox[1], bbox[2], bbox[3],
                        kind="caption", source="legacy_regex",
                    )
                    for p, text, bbox, k in caption_candidates
                    if p == page_no and k == kind
                ]
            else:
                # 使用 Layout caption 区域
                caps = list(page_region.caption_regions)

            if not caps and not content_regions:
                continue

            # 执行配对（显式传入 kind，避免 AssetCandidate 默认成 figure）
            page_result = pair_page(
                page=page_no,
                captions=caps,
                contents=content_regions,
                kind=kind,
            )

            # 合并到结果（同页可能有 figure 和 table 两种）
            if page_no in results:
                existing = results[page_no]
                existing.pairs.extend(page_result.pairs)
                existing.orphan_captions.extend(page_result.orphan_captions)
                existing.orphan_contents.extend(page_result.orphan_contents)
            else:
                results[page_no] = page_result

    # 统计
    total_pairs = sum(len(r.pairs) for r in results.values())
    total_orphan_caps = sum(len(r.orphan_captions) for r in results.values())
    total_orphan_contents = sum(len(r.orphan_contents) for r in results.values())
    multi_frame_count = sum(
        1 for r in results.values() for p, _ in r.pairs if len(p.content_bboxes) > 1
    )

    logger.info(
        "Layout pairing: %d pages, %d pairs, %d orphan captions, "
        "%d orphan contents, %d multi-frame assets",
        len(results),
        total_pairs,
        total_orphan_caps,
        total_orphan_contents,
        multi_frame_count,
    )

    return results


def pairing_report(pairing_results: Dict[int, PairingResult]) -> Dict[str, Any]:
    """生成配对报告（用于 JSON 输出和退出条件验证）。"""
    total_pairs = sum(len(r.pairs) for r in pairing_results.values())
    total_orphan_caps = sum(len(r.orphan_captions) for r in pairing_results.values())
    total_orphan_contents = sum(len(r.orphan_contents) for r in pairing_results.values())
    multi_frame_assets = [
        {
            "page": p,
            "caption_bbox": pair.caption_bbox,
            "content_bboxes": pair.content_bboxes,
            "n_frames": len(pair.content_bboxes),
        }
        for p, r in pairing_results.items()
        for pair, _ in r.pairs
        if len(pair.content_bboxes) > 1
    ]

    # 检查一对一约束：每个 content 框只被使用一次
    all_content_bboxes: List[Tuple[int, List[float]]] = []
    for page, r in pairing_results.items():
        for pair, _ in r.pairs:
            for cb in pair.content_bboxes:
                all_content_bboxes.append((page, [round(v, 2) for v in cb]))

    # 统计重复占用
    from collections import Counter

    bbox_counts = Counter((p, tuple(cb)) for p, cb in all_content_bboxes)
    duplicate_groups = [
        {"page": p, "bbox": list(cb), "count": c}
        for (p, cb), c in bbox_counts.items()
        if c > 1
    ]

    return {
        "total_pages": len(pairing_results),
        "total_pairs": total_pairs,
        "orphan_captions": total_orphan_caps,
        "orphan_contents": total_orphan_contents,
        "multi_frame_assets": multi_frame_assets,
        "multi_frame_count": len(multi_frame_assets),
        "duplicate_occupancy": {
            "n_groups": len(duplicate_groups),
            "n_assets_involved": sum(d["count"] for d in duplicate_groups),
            "details": duplicate_groups,
        },
        "pages": [
            {
                "page": p,
                "pairs": len(r.pairs),
                "orphan_captions": len(r.orphan_captions),
                "orphan_contents": len(r.orphan_contents),
                "confidence": round(r.confidence, 4),
            }
            for p, r in sorted(pairing_results.items())
        ],
    }
