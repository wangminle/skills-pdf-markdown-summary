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
    ownership_captions: Optional[List[RegionBBox]] = None,
) -> PairingResult:
    """单页配对：caption 与 content 的一对一匹配。

    使用贪心算法：
    1. 计算所有 (caption, content) 对的代价
    2. 按代价排序
    3. 贪心分配，确保一对一

    Args:
        page: 页码（1-based）
        captions: caption 区域列表（参与配对）
        contents: content 区域列表（figure/table）
        page_height: 页面高度（pt）
        max_dist: 最大配对距离
        kind: 资产类型（'figure' | 'table'），写入 AssetCandidate.kind
        ownership_captions: 多框归属判断用的题注全集。默认与 captions 相同；
            调用方传入比 captions 更大的题注池（如 Layout 自带题注区域）时，
            「相邻框是否另有更近题注」的判断不会因为池子缺项而失灵。

    Returns:
        PairingResult
    """
    result = PairingResult(page=page, method="greedy_nearest")

    if not captions or not contents:
        result.orphan_captions = [
            _region_to_candidate(c, "caption", kind=kind, page=page) for c in captions
        ]
        result.orphan_contents = [
            _region_to_candidate(c, "content", kind=kind, page=page) for c in contents
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

        # 多框分组：仅合并「没有更近 caption」的邻近同 kind 框，避免吞掉独立图表。
        # 归属判断用 ownership_captions（默认即 captions）：外部候选池只覆盖
        # 有 legacy record 的题注，缺了 Layout 题注池会让相邻独立图被误并。
        extra_frames = _find_multi_frames(
            content, contents, used_contents, page_height,
            captions=ownership_captions if ownership_captions else captions,
            primary_caption=cap,
            max_dist=max_dist,
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
        _region_to_candidate(captions[i], "caption", kind=kind, page=page)
        for i in range(len(captions))
        if i not in used_caps
    ]
    result.orphan_contents = [
        _region_to_candidate(contents[i], "content", kind=kind, page=page)
        for i in range(len(contents))
        if i not in used_contents
    ]

    # 整体置信度
    if result.pairs:
        result.confidence = sum(p[0].confidence for p in result.pairs) / len(result.pairs)

    return result


def _dedup_caption_regions(regions: List[RegionBBox]) -> List[RegionBBox]:
    """按几何去重题注区域（外部候选与 Layout 区域可能指同一条题注）。"""
    out: List[RegionBBox] = []
    seen: set = set()
    for region in regions:
        if region is None:
            continue
        key = tuple(round(v, 2) for v in (region.x0, region.y0, region.x1, region.y1))
        if key in seen:
            continue
        seen.add(key)
        out.append(region)
    return out


def _unique_best_content(
    caption: RegionBBox,
    contents: List[RegionBBox],
    page_height: float,
    max_dist: float,
) -> Optional[RegionBBox]:
    """该题注在配对距离内代价唯一最低的内容框。

    代价打平时返回 None：打平不能证明这块框「属于」这条题注，
    否则会把真正的多 panel 也拆开。
    """
    best: Optional[RegionBBox] = None
    best_cost = float("inf")
    tied = False
    for content in contents:
        if caption.edge_distance(content) > max_dist:
            continue
        cost = _cost_function(caption, content, page_height)
        if best is None or cost + 1e-6 < best_cost:
            best = content
            best_cost = cost
            tied = False
        elif abs(cost - best_cost) <= 1e-6:
            tied = True
    if tied:
        return None
    return best


def _find_multi_frames(
    primary: RegionBBox,
    all_contents: List[RegionBBox],
    used: set,
    page_height: float,
    captions: Optional[List[RegionBBox]] = None,
    primary_caption: Optional[RegionBBox] = None,
    max_dist: float = _DEFAULT_MAX_DIST,
) -> List[RegionBBox]:
    """查找主 content 框附近的额外同 kind 框（多 panel）。

    条件：
    1. 未被使用
    2. 与主框距离 <= _MULTI_FRAME_MAX_GAP
    3. 尺寸 >= _MULTI_FRAME_MIN_SIZE
    4. 水平或垂直对齐（共享边或投影重叠）
    5. 不属于其他题注。某框是另一条题注的唯一最佳内容时，即使当前题注
       在几何上更近（题注夹在上下两图之间时经常如此），也要留给那条题注。
       只比边距会在第二张题注参与配对前把独立图并走。
       captions 必须是本页题注「全集」（含 Layout 自带题注），只传外部候选
       会让归属判断看不到邻居自己的题注而误并（评审#3 P1）。

    Args:
        primary: 主 content 框
        all_contents: 全部 content 框
        used: 已使用的索引集合
        page_height: 页面高度
        captions: 本页全部 caption（用于归属检查，应为题注全集）
        primary_caption: 当前主配对 caption
        max_dist: 题注与内容的最大配对距离，与 pair_page 同口径

    Returns:
        额外框列表
    """
    # 另一条题注的唯一最佳内容属于那条题注。边距比较不够：上下两图相距
    # <=30pt 时，夹在中间的题注到下一张图往往更近，会在该图注配对前把框占走。
    claimed_by_other: set = set()
    if captions and primary_caption is not None:
        for cap in captions:
            if cap is primary_caption:
                continue
            owned = _unique_best_content(cap, all_contents, page_height, max_dist)
            if owned is not None:
                claimed_by_other.add(id(owned))

    extras: List[RegionBBox] = []
    for i, content in enumerate(all_contents):
        if i in used or content is primary:
            continue
        if content.width < _MULTI_FRAME_MIN_SIZE and content.height < _MULTI_FRAME_MIN_SIZE:
            continue

        dist = primary.edge_distance(content)
        if dist > _MULTI_FRAME_MAX_GAP:
            continue
        if id(content) in claimed_by_other:
            continue

        # 若相邻框有更近的其他 caption，应留给该 caption，不并入 multi-frame。
        # 距离相等不能算「没有更近的」：左右并列的两图两题注经常出现
        # edge_distance 完全相同（两侧都是 10pt），此时要看配对代价——
        # 另一题注与该框的水平对齐通常显著更好，实际存在独立配对关系。
        if captions and primary_caption is not None:
            primary_cost = _cost_function(
                primary_caption, content, page_height
            )
            better_other = False
            for cap in captions:
                if cap is primary_caption:
                    continue
                cap_dist = cap.edge_distance(content)
                prim_dist = primary_caption.edge_distance(content)
                if cap_dist + 1e-6 < prim_dist:
                    better_other = True
                    break
                if abs(cap_dist - prim_dist) <= 1e-6:
                    if _cost_function(cap, content, page_height) + 1e-6 < primary_cost:
                        better_other = True
                        break
            if better_other:
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


def _filter_layout_captions_by_kind(
    caption_regions: List[RegionBBox],
    kind: str,
    mixed_page: bool = False,
) -> List[RegionBBox]:
    """从 Layout 题注池筛出与当前分组类型一致的题注。

    caption_regions 是 figure/table 共用池。raw_class 带类型信息
    （figure-caption / table-caption）时按它筛；无法判别的通用
    caption 分两种情况：

    - 单类型页（本页只有 figure 或只有 table 一种内容）：不筛。否则
      单类型文档（后端只标通用 caption）的题注会被误丢。
    - 混合类型页（本页 figure 与 table 并存，mixed_page=True）：通用
      题注不再参与任何类型的配对（评审#4 第 2 条）。同一页同时有
      figure/table 内容时，一条题注被两类同时认领会产出「一条题注
      配两张图」的错配——通用题注无法判别归属时宁可留作孤儿，
      由外部候选或后续精修兜底。

    其余判别不出的部分保持原样，由配对代价兜底。
    """
    typed: List[RegionBBox] = []
    untyped: List[RegionBBox] = []
    for region in caption_regions:
        raw = (getattr(region, "raw_class", "") or "").lower()
        if "table" in raw:
            if kind == "table":
                typed.append(region)
        elif "figure" in raw or "caption" in raw and raw not in ("caption",):
            if kind == "figure":
                typed.append(region)
        else:
            untyped.append(region)
    if mixed_page and untyped:
        # 混合页：通用题注不进任何分组（原 review「无法判别时保留孤儿」）
        return typed
    return typed + untyped


def _region_to_candidate(
    region: RegionBBox,
    role: str,
    kind: str = "figure",
    page: int = 0,
) -> AssetCandidate:
    """将 RegionBBox 转为 AssetCandidate（用于孤儿列表）。"""
    asset_kind = getattr(region, "kind", None) or kind
    if asset_kind in ("caption", "other", "text"):
        asset_kind = kind
    cand = AssetCandidate(
        kind=asset_kind,
        page=page,
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

            # 混合类型页判定（评审#4 第 2 条）：本页 figure 与 table 内容并存
            # 时，无法判别类型的通用题注不得进入任何分组——一条题注被两类
            # 同时认领会产出「一条题注配两张图」的错配，宁可留作孤儿。
            mixed_page = bool(page_region.figure_regions) and bool(page_region.table_regions)

            # 获取 caption 区域：外部 caption 按页过滤；本页无外部时回退 Layout。
            # 回退必须筛类型：caption_regions 是 figure/table 共用池，Layout 把
            # 某页表格题注识别成 figure 类时，table 分组会把 figure 题注拿去
            # 配表格内容（外部候选只覆盖部分页/类型时该分支必走）。
            # 判别依据：每个 caption 区域的 raw_class（后端原始分类）——
            # 无从判别时保留为孤儿，不做类型混配。
            if caption_candidates:
                caps = [
                    RegionBBox(
                        bbox[0], bbox[1], bbox[2], bbox[3],
                        kind="caption", source="legacy_regex",
                    )
                    for p, text, bbox, k in caption_candidates
                    if p == page_no and k == kind
                ]
                if not caps:
                    caps = _filter_layout_captions_by_kind(
                        page_region.caption_regions, kind, mixed_page=mixed_page
                    )
            else:
                caps = _filter_layout_captions_by_kind(
                    page_region.caption_regions, kind, mixed_page=mixed_page
                )

            if not caps and not content_regions:
                continue

            # 多框归属证据 = 参与配对的题注 + 本页 Layout 题注全集。
            # 只用外部候选时，仅 Layout 检测到、legacy 无 record 的题注不可见，
            # 相邻独立图会被并入上一张图的多框（评审#3 P1）。
            # 混合页的通用题注从配对池排除后，归属证据同样不包含它们
            #（避免它们以归属证据的身份反过来阻止合法合并）。
            ownership_caps = _dedup_caption_regions(
                list(caps)
                + _filter_layout_captions_by_kind(
                    page_region.caption_regions, kind, mixed_page=mixed_page
                )
            )

            # 执行配对（显式传入 kind，避免 AssetCandidate 默认成 figure）
            page_result = pair_page(
                page=page_no,
                captions=caps,
                contents=content_regions,
                kind=kind,
                ownership_captions=ownership_caps,
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
