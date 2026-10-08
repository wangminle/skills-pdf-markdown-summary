#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A3: 后端编排和回退策略。

当 layout-backend 开启时，对有 Layout 候选框的资产使用新精修器；
无候选框或 layout-backend 关闭时，保留 legacy 路径（不改输出）。

流程：
1. 提取完成后，根据 A2 配对结果找到每个 record 的 Layout 候选框
2. 对有候选框的 record 运行 FigureRefiner / TableRefiner
3. 如果精修结果质量可接受（accepted / accepted_with_margin），更新 record 并重新渲染
4. 否则保留 legacy 结果
5. 产出 layout_refinement.json 报告
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .models import AttachmentRecord
from .quality import (
    QualityAssessment,
    STATUS_ACCEPTED,
    STATUS_ACCEPTED_WITH_MARGIN,
    STATUS_REJECTED,
    STATUS_REVIEW_REQUIRED,
)

logger = logging.getLogger(__name__)

# 质量阈值：只有 accepted / accepted_with_margin 才用精修框覆盖 legacy 几何
_ACCEPTABLE_STATUSES = {STATUS_ACCEPTED, STATUS_ACCEPTED_WITH_MARGIN}

# IoU 阈值：精修结果与 legacy 结果 IoU 过低时不覆盖（防止大幅改变）
_MAX_LEGACY_IOU_DIFF = 0.3

# 精修结果对 legacy 的最低覆盖率：低于此值说明候选框过紧，回退到 legacy
_MIN_LEGACY_COVERAGE = 0.55

# record↔Layout 候选匹配的最低 IoU：禁止「任意正重叠即绑定」，降低跨资产误绑
_MIN_MATCH_IOU = 0.25

# 图注框重合度：record 的 caption_bbox 与候选的 caption_bbox 重合到此值即视为
# 「同一条图注」。同图注是比内容框 IoU 更强的身份证据——两张相邻图的截图框
# 漂移后 IoU 可以互相倒挂，但图注框不会（评审#3 P1）。
_MIN_CAPTION_IOU = 0.5


@dataclass
class RefinementRecord:
    """单个资产的精修记录。"""
    ident: str = ""
    kind: str = ""
    page: int = 0
    legacy_bbox: Optional[List[float]] = None
    candidate_bbox: Optional[List[float]] = None
    refined_bbox: Optional[List[float]] = None
    applied: bool = False
    reason: str = ""
    quality: Optional[Dict[str, Any]] = None
    step_notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ident": self.ident,
            "kind": self.kind,
            "page": self.page,
            "legacy_bbox": self.legacy_bbox,
            "candidate_bbox": self.candidate_bbox,
            "refined_bbox": self.refined_bbox,
            "applied": self.applied,
            "reason": self.reason,
            "quality": self.quality,
            "step_notes": self.step_notes,
        }


@dataclass
class RefinementReport:
    """全部资产的精修报告。"""
    total_records: int = 0
    matched: int = 0
    refined: int = 0
    applied: int = 0
    kept_legacy: int = 0
    records: List[RefinementRecord] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_records": self.total_records,
            "matched": self.matched,
            "refined": self.refined,
            "applied": self.applied,
            "kept_legacy": self.kept_legacy,
            "records": [r.to_dict() for r in self.records],
        }


def _bbox_iou(a: List[float], b: List[float]) -> float:
    """计算两个 bbox 的 IoU。"""
    ix0 = max(a[0], b[0])
    iy0 = max(a[1], b[1])
    ix1 = min(a[2], b[2])
    iy1 = min(a[3], b[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _bbox_coverage(small: List[float], big: List[float]) -> float:
    """计算 small 对 big 的覆盖率：small 覆盖了多少 big 的面积。

    用于检测精修结果是否遗漏了 legacy 框中的内容。
    """
    ix0 = max(small[0], big[0])
    iy0 = max(small[1], big[1])
    ix1 = min(small[2], big[2])
    iy1 = min(small[3], big[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    area_big = max(0.0, big[2] - big[0]) * max(0.0, big[3] - big[1])
    return inter / area_big if area_big > 0 else 0.0


def _union_bboxes(bboxes: List[List[float]]) -> List[float]:
    return [
        min(b[0] for b in bboxes),
        min(b[1] for b in bboxes),
        max(b[2] for b in bboxes),
        max(b[3] for b in bboxes),
    ]


def _captions_identical(
    caption_a: Optional[List[float]],
    caption_b: Optional[List[float]],
) -> bool:
    """两个图注框是否指同一条图注（资产身份证据）。"""
    if not caption_a or not caption_b:
        return False
    return _bbox_iou(list(caption_a), list(caption_b)) >= _MIN_CAPTION_IOU


def _optimal_assignment(
    rec_ids: List[int],
    frames: List[tuple],
    edge_weight: Dict[int, Dict[tuple, Tuple[float, float]]],
) -> Dict[int, tuple]:
    """二分图的精确字典序最优分配。

    目标依次是：身份边数最大、匹配基数最大、IoU 总和最大。
    将三层目标编码为不会进位串扰的整数权重，再用最小费用流求解。
    每条记录还有一条零费用的「不匹配」边，因此身份优先级不会被
    强制最大基数破坏。复杂度为多项式，高密度页也不再退化成贪心。

    Args:
        rec_ids: 记录索引（按顺序处理）
        frames: 候选 frame 列表（右侧节点）
        edge_weight: 记录 -> {frame -> (conf, iou) 字典序得分}

    Returns:
        记录 -> frame 的匹配（部分记录可能无匹配）
    """
    if not rec_ids or not frames:
        return {}

    n = len(rec_ids)
    m = len(frames)
    max_matches = min(n, m)
    iou_scale = 10**9
    match_unit = max_matches * iou_scale + 1
    confirmed_unit = max_matches * (match_unit + iou_scale) + 1

    source = 0
    rec_offset = 1
    frame_offset = rec_offset + n
    sink = frame_offset + m
    node_count = sink + 1
    # 边结构：[to, reverse_index, residual_capacity, cost]
    graph: List[List[List[int]]] = [[] for _ in range(node_count)]

    def add_edge(u: int, v: int, capacity: int, cost: int) -> List[int]:
        forward = [v, len(graph[v]), capacity, cost]
        backward = [u, len(graph[u]), 0, -cost]
        graph[u].append(forward)
        graph[v].append(backward)
        return forward

    for i in range(n):
        add_edge(source, rec_offset + i, 1, 0)
        add_edge(rec_offset + i, sink, 1, 0)  # 允许该记录不匹配
    for j in range(m):
        add_edge(frame_offset + j, sink, 1, 0)

    frame_pos = {frame: j for j, frame in enumerate(frames)}
    match_edges: Dict[Tuple[int, tuple], List[int]] = {}
    for i, ri in enumerate(rec_ids):
        for frame, (confirmed, iou) in edge_weight.get(ri, {}).items():
            j = frame_pos.get(frame)
            if j is None:
                continue
            benefit = (
                (1 if confirmed > 0 else 0) * confirmed_unit
                + match_unit
                + max(0, int(round(iou * iou_scale)))
            )
            match_edges[(ri, frame)] = add_edge(
                rec_offset + i, frame_offset + j, 1, -benefit,
            )

    # 每条记录发送 1 单位流。残量网络里的反向边允许后续增广
    # 重排早期匹配，避免贪心占住其他记录的唯一 frame。
    inf = 10**100
    for _ in range(n):
        dist = [inf] * node_count
        prev_node = [-1] * node_count
        prev_edge = [-1] * node_count
        dist[source] = 0
        for _pass in range(node_count - 1):
            changed = False
            for u in range(node_count):
                if dist[u] == inf:
                    continue
                for ei, edge in enumerate(graph[u]):
                    v, _rev, capacity, cost = edge
                    if capacity <= 0:
                        continue
                    candidate = dist[u] + cost
                    if candidate < dist[v]:
                        dist[v] = candidate
                        prev_node[v] = u
                        prev_edge[v] = ei
                        changed = True
            if not changed:
                break
        if prev_node[sink] < 0:
            break
        v = sink
        while v != source:
            u = prev_node[v]
            edge = graph[u][prev_edge[v]]
            edge[2] -= 1
            graph[v][edge[1]][2] += 1
            v = u

    result: Dict[int, tuple] = {}
    for (ri, frame), edge in match_edges.items():
        if edge[2] == 0:
            result[ri] = frame
    return result


def _match_records_to_candidates(
    records: List[AttachmentRecord],
    pairing_results: Dict[int, Any],
) -> Dict[int, Dict[str, Any]]:
    """将 records 与 A2 配对结果一对一匹配。

    返回 record_index -> {
        "bbox": union bbox,
        "content_bboxes": 原始多框列表,
        "caption_bbox": 可选 caption 框,
    }

    约束：
    1. 每个候选 pair 最多绑定一个 record（标记已使用，禁止重复占用）；
    2. 优先「图注身份一致」的边：record.caption_bbox 与候选 caption_bbox
       重合即为同一条图注，该边即使内容框 IoU 低于 _MIN_MATCH_IOU 也成立。
       内容框 IoU 只看几何，上下相邻两图的截图框漂移后会互相倒挂，导致
       两张图互换绑定（用对方的框重渲染 = 截图串图）；图注框不受此影响。
    3. 在一对一约束下求字典序最优分配：先最大化身份边数（身份边不可被
       普通 IoU 边挤占），再最大化匹配基数，最后最大化 IoU 总和
       （评审#4 第 1 条）。Kuhn 增广只保证基数，增广找到的第一条可行路径
       不一定是总分最高的分配（实测反例：2 记录 2 候选 0.808 对最优
       1.084，两分配基数相同；3 周旋转的改进是任何 2-opt 交换都够不到的
       局部最优）。
    """
    mapping: Dict[int, Dict[str, Any]] = {}

    # 构建候选池：(page, kind) -> list of candidate dicts
    pair_index: Dict[Tuple[int, str], List[Dict[str, Any]]] = {}
    for page_no, pr in pairing_results.items():
        if pr is None:
            continue
        page = getattr(pr, "page", page_no)
        for pair in getattr(pr, "pairs", []):
            if not (isinstance(pair, (list, tuple)) and len(pair) >= 2):
                continue
            caption_cand, content_list = pair[0], pair[1]
            kind = getattr(caption_cand, "kind", None) or "figure"
            if content_list:
                kind = getattr(content_list[0], "kind", None) or kind
            if kind not in ("figure", "table"):
                kind = "figure"

            all_bboxes: List[List[float]] = []
            for cc in content_list:
                cc_kind = getattr(cc, "kind", kind)
                if cc_kind != kind:
                    continue
                bboxes = getattr(cc, "content_bboxes", []) or []
                all_bboxes.extend([list(b) for b in bboxes])

            # 兼容：有的测试把 content 直接放在 caption_cand 上
            if not all_bboxes:
                bboxes = getattr(caption_cand, "content_bboxes", []) or []
                all_bboxes.extend([list(b) for b in bboxes])

            if not all_bboxes:
                continue

            # 去重（保留顺序）
            dedup: List[List[float]] = []
            seen = set()
            for b in all_bboxes:
                key_b = tuple(round(v, 2) for v in b)
                if key_b in seen:
                    continue
                seen.add(key_b)
                dedup.append(list(b))

            cap_bb = getattr(caption_cand, "caption_bbox", None)
            entry = {
                "bbox": _union_bboxes(dedup),
                "content_bboxes": dedup,
                "caption_bbox": list(cap_bb) if cap_bb else None,
            }
            pair_index.setdefault((page, kind), []).append(entry)

    # 一对一匹配：字典序最优分配——先身份边数、再匹配基数、最后 IoU 总和。
    # 纯 IoU 贪心会让一个可匹配两个候选的记录先占用另一条记录的唯一
    # 候选，后者彻底失去精修机会（实测：候选 [0,0,100,100]/[65,0,165,100]
    # 与记录 [5,0,105,100]/[0,0,80,100] 只匹配 1 条，实际可匹配 2 条）。

    # 候选按 bbox_id 折叠：同框（page+kind+union bbox 相同）的多个候选
    # 是同一几何实体，只能被一条记录占用。折叠后的图节点即 bbox_id。
    cand_bbox_ids: Dict[Tuple[int, str], List[tuple]] = {}
    for key, candidates in pair_index.items():
        ids: List[tuple] = []
        for cand in candidates:
            bbox_id = (key[0], key[1], tuple(round(v, 2) for v in cand["bbox"]))
            ids.append(bbox_id)
        cand_bbox_ids[key] = ids

    adj: Dict[int, List[Tuple[int, float, int, Tuple[int, str]]]] = {}
    for i, rec in enumerate(records):
        rec_page = getattr(rec, "page", 0)
        rec_kind = getattr(rec, "kind", "figure")
        rec_bbox = getattr(rec, "final_bbox", None)
        if rec_bbox is None:
            continue
        rec_caption = getattr(rec, "caption_bbox", None)
        key = (rec_page, rec_kind)
        candidates = pair_index.get(key, [])
        for ci, cand in enumerate(candidates):
            iou = _bbox_iou(rec_bbox, cand["bbox"])
            confirmed = _captions_identical(rec_caption, cand.get("caption_bbox"))
            # 图注身份一致的边不受 IoU 阈值限制：身份是真值，几何只是估计。
            if confirmed or iou >= _MIN_MATCH_IOU:
                adj.setdefault(i, []).append((1 if confirmed else 0, iou, ci, key))

    # 用最小费用流精确求解「先最大化身份边数、再最大化匹配基数、
    # 最后最大化 IoU 总和」的分配（Kuhn 增广只保证基数，且增广找到的第一条
    # 可行路径不一定是总分最高的分配——实测反例：2 记录 2 候选可得 0.808
    # 而最优为 1.084，两分配基数相同；另有 3 周旋转的改进是任何 2-opt
    # 交换都够不到的局部最优；身份边不设优先级时又会被普通 IoU 边挤占，
    # A3 按错误区域重渲染 = 截图串图）。该求解器为多项式复杂度，高密度页
    # 也保持同一优化目标，不再超过阈值就退回贪心。
    def _same_frame(key: Tuple[int, str], ci: int) -> tuple:
        return cand_bbox_ids[key][ci]

    # 每条边只保留「该记录对该 frame 的最佳边」：同 frame 的多个候选
    # 是同一几何实体，记录对其分数取最高即可（其余边不可能进入解）。
    # 值 = (conf, iou, ci, key)：conf/iou 是字典序得分，ci/key 回定位候选。
    best_edge_per_frame: Dict[int, Dict[tuple, Tuple[float, float, int, Tuple[int, str]]]] = {}
    for ri, edges in adj.items():
        per_frame: Dict[tuple, Tuple[float, float, int, Tuple[int, str]]] = {}
        for conf, iou, ci, key in edges:
            frame = _same_frame(key, ci)
            cur = per_frame.get(frame)
            if cur is None or (conf, iou) > (cur[0], cur[1]):
                per_frame[frame] = (float(conf), float(iou), ci, key)
        best_edge_per_frame[ri] = per_frame

    # 按 (page, kind) 分组求解；frame 天然只属于一个组（bbox_id 含组键）。
    group_of: Dict[Tuple[int, str], List[int]] = {}
    for ri, edges in adj.items():
        for conf, iou, ci, key in edges:
            group_of.setdefault(key, []).append(ri)
    for key in group_of:
        group_of[key] = sorted(set(group_of[key]))

    match_of_record: Dict[int, Tuple[Tuple[int, str], int]] = {}
    for key, rec_ids in group_of.items():
        frames: List[tuple] = []
        seen_frames: set = set()
        for ri in rec_ids:
            for frame in best_edge_per_frame.get(ri, {}):
                if frame not in seen_frames:
                    seen_frames.add(frame)
                    frames.append(frame)
        edge_weight: Dict[int, Dict[tuple, Tuple[float, float]]] = {}
        for ri in rec_ids:
            wmap: Dict[tuple, Tuple[float, float]] = {}
            for frame, (conf, iou, ci, k) in best_edge_per_frame.get(ri, {}).items():
                if frame not in seen_frames:
                    continue
                wmap[frame] = (conf, iou)
            edge_weight[ri] = wmap
        chosen = _optimal_assignment(rec_ids, frames, edge_weight)
        for ri, frame in chosen.items():
            _conf, _iou, ci, k = best_edge_per_frame[ri][frame]
            match_of_record[ri] = (k, ci)

    for ri, (key, ci) in match_of_record.items():
        mapping[ri] = pair_index[key][ci]

    return mapping


def _rerender_asset(
    pdf_path: str,
    page_num: int,
    bbox: List[float],
    out_path: str,
    dpi: int = 300,
    render_failures: Optional[List[Dict[str, Any]]] = None,
    ident: str = "",
    kind: str = "",
) -> bool:
    """用新 bbox 重新渲染资产图片。

    落盘走 save_pixmap_clean：先写临时文件，成功后再替换。失败时旧 PNG
    保持原字节，并把硬失败记入 render_failures（若调用方提供）。

    Args:
        pdf_path: PDF 文件路径
        page_num: 页码（0-based）
        bbox: 新的裁剪框 [x0, y0, x1, y1]
        out_path: 输出文件路径
        dpi: 渲染 DPI
        render_failures: 可选的硬失败收集列表
        ident: 资产编号，写入失败记录
        kind: 资产类型，写入失败记录

    Returns:
        True 如果成功
    """
    try:
        import fitz
        from .output import save_pixmap_clean
        from .pdf_backend import create_rect

        doc = fitz.open(pdf_path)
        try:
            page = doc[page_num]
            clip = create_rect(*bbox)
            pix = page.get_pixmap(dpi=dpi, clip=clip)
            save_pixmap_clean(pix, out_path)
        finally:
            doc.close()
        return True
    except Exception as e:
        logger.warning(f"Re-render failed for page {page_num}: {e}")
        if render_failures is not None:
            render_failures.append({
                "kind": kind or "asset",
                "id": ident,
                "page": page_num + 1,
                "error": str(e),
            })
        return False


def run_refinement_pipeline(
    records: List[AttachmentRecord],
    pairing_results: Dict[int, Any],
    pdf_path: str,
    out_dir: str,
    dpi: int = 300,
    skip_idents: Optional[Set[str]] = None,
    render_failures: Optional[List[Dict[str, Any]]] = None,
) -> RefinementReport:
    """执行 A3 精修管道。

    对有 Layout 候选框的 record 运行新精修器；
    如果精修结果质量可接受且与 legacy 差异合理，则更新 record 并重新渲染。

    Args:
        records: 提取产出的 AttachmentRecord 列表
        pairing_results: A2 配对结果列表
        pdf_path: PDF 文件路径
        out_dir: 输出目录
        dpi: 渲染 DPI
        skip_idents: 不参与精修的 id 集合（对应 CLI 的 --no-refine）。
            这些 record 既不参与候选匹配（不占用候选），也不做精修，
            但在报告中留一条 skipped 记录，便于核对排除范围。
        render_failures: 重渲染 I/O 硬失败收集列表。失败时旧图保留，
            几何回滚，同时向该列表追加记录，供主入口返回非零退出码。

    Returns:
        RefinementReport
    """
    report = RefinementReport(total_records=len(records))

    # --no-refine 的排除必须延续到 A3：legacy 阶段已按同一列表跳过裁剪微调，
    # A3 再按 Layout 候选覆盖同一 id 就等于无视用户显式排除（评审#3 P2）。
    skip_set = {str(x).strip() for x in (skip_idents or []) if str(x).strip()}
    pool = records
    if skip_set:
        pool = [r for r in records if str(getattr(r, "ident", "")) not in skip_set]
        for rec in records:
            if str(getattr(rec, "ident", "")) not in skip_set:
                continue
            report.records.append(
                RefinementRecord(
                    ident=rec.ident,
                    kind=rec.kind,
                    page=rec.page,
                    legacy_bbox=list(rec.final_bbox) if rec.final_bbox else None,
                    applied=False,
                    reason="skipped: id listed in --no-refine",
                )
            )

    # 匹配 records 到 Layout 候选框
    candidate_map = _match_records_to_candidates(pool, pairing_results)
    report.matched = len(candidate_map)

    if not candidate_map:
        logger.info("A3: no Layout candidates matched, all records keep legacy")
        return report

    # 延迟导入 refiners（避免在 layout-backend off 时加载）
    try:
        from .refiners import FigureRefiner, TableRefiner
        from .refiners.base import RefinementContext
        from .pdf_backend import open_pdf
    except ImportError as e:
        logger.warning(f"A3: refiners not available: {e}")
        return report

    # 打开 PDF 文档用于精修
    try:
        from .extract_helpers import collect_draw_items, collect_text_lines
    except ImportError as e:
        logger.warning(f"A3: helpers not available: {e}")
        return report

    with open_pdf(pdf_path) as doc:
        for rec_idx, cand_info in candidate_map.items():
            # 兼容旧映射（纯 list bbox）与新映射（dict）
            if isinstance(cand_info, dict):
                cand_bbox = list(cand_info["bbox"])
                cand_frames = [list(b) for b in (cand_info.get("content_bboxes") or [cand_bbox])]
                cand_caption = cand_info.get("caption_bbox")
            else:
                cand_bbox = list(cand_info)
                cand_frames = [list(cand_bbox)]
                cand_caption = None

            rec = pool[rec_idx]
            rec_record = RefinementRecord(
                ident=rec.ident,
                kind=rec.kind,
                page=rec.page,
                legacy_bbox=list(rec.final_bbox) if rec.final_bbox else None,
                candidate_bbox=list(cand_bbox),
            )

            legacy_bbox = rec.final_bbox
            if legacy_bbox is None:
                rec_record.reason = "no legacy final_bbox"
                report.records.append(rec_record)
                continue

            page_num = rec.page - 1  # 0-based

            try:
                page = doc[page_num]
                page_rect = page.rect
                text_dict = page.get_text_dict()
                text_lines = collect_text_lines(text_dict)
                draw_items = collect_draw_items(page.raw)

                from .pdf_backend import create_rect
                image_rects: List = []
                vector_rects: List = []
                for item in draw_items:
                    if item.orient == 'O':
                        vector_rects.append(item.rect)
                for blk in text_dict.get("blocks", []):
                    if blk.get("type") == 1:
                        bbox = blk.get("bbox")
                        if bbox:
                            image_rects.append(create_rect(*bbox))

                real_caption = getattr(rec, "caption_bbox", None) or cand_caption
                if real_caption and len(real_caption) == 4:
                    cap_cy = (real_caption[1] + real_caption[3]) / 2.0
                    cand_cy = (cand_bbox[1] + cand_bbox[3]) / 2.0
                    direction = "above" if cand_cy <= cap_cy else "below"
                    caption_rect = create_rect(*real_caption)
                else:
                    if cand_bbox[1] < legacy_bbox[1]:
                        direction = "below"
                    else:
                        direction = "above"
                    if direction == "above":
                        caption_rect = create_rect(
                            cand_bbox[0], cand_bbox[3] + 1,
                            cand_bbox[2], cand_bbox[3] + 2,
                        )
                    else:
                        caption_rect = create_rect(
                            cand_bbox[0], cand_bbox[1] - 2,
                            cand_bbox[2], cand_bbox[1] - 1,
                        )

                ctx = RefinementContext(
                    page=page,
                    page_rect=page_rect,
                    candidate_bbox=list(cand_bbox),
                    candidate_bboxes=[list(b) for b in cand_frames],
                    caption_bbox=caption_rect,
                    direction=direction,
                    kind=rec.kind,
                    text_lines=text_lines,
                    image_rects=image_rects,
                    vector_rects=vector_rects,
                    dpi=dpi,
                    scale=dpi / 72.0,
                    page_num=page_num,
                    extra={'legacy_bbox': list(legacy_bbox) if legacy_bbox else None},
                )

                if rec.kind == "table":
                    refiner = TableRefiner()
                else:
                    refiner = FigureRefiner()

                result = refiner.refine(ctx)
                report.refined += 1

                rec_record.refined_bbox = result.bbox
                rec_record.step_notes = result.notes
                if result.quality:
                    rec_record.quality = result.quality.to_dict()

                q_status = result.quality.status if result.quality else STATUS_REVIEW_REQUIRED
                q_warnings = list(result.quality.warnings) if result.quality else []
                q_conf = result.quality.confidence if result.quality else None
                q_review = q_status in (STATUS_REVIEW_REQUIRED, STATUS_REJECTED)

                def _apply_quality_meta(target_status: str, extra_warnings: Optional[List[str]] = None) -> None:
                    """四态元数据始终写回 record（几何是否覆盖另议）。"""
                    warns = list(extra_warnings or [])
                    # 合并去重
                    merged = list(dict.fromkeys(list(rec.warnings) + q_warnings + warns))
                    rec.warnings = merged
                    rec.review_required = target_status in (STATUS_REVIEW_REQUIRED, STATUS_REJECTED) or q_review
                    rec.status = target_status
                    if q_conf is not None:
                        rec.boundary_confidence = q_conf

                if result.quality and result.quality.status in _ACCEPTABLE_STATUSES:
                    legacy_iou = _bbox_iou(legacy_bbox, result.bbox)
                    legacy_cov = _bbox_coverage(result.bbox, legacy_bbox)
                    if legacy_iou < _MAX_LEGACY_IOU_DIFF:
                        rec_record.applied = False
                        rec_record.reason = (
                            f"legacy_iou={legacy_iou:.2f} < {_MAX_LEGACY_IOU_DIFF}"
                            f", status={result.quality.status}"
                        )
                        # 几何保留 legacy，但质量告警仍落盘为 review_required
                        _apply_quality_meta(
                            STATUS_REVIEW_REQUIRED,
                            [f"legacy_iou_too_low={legacy_iou:.2f}"],
                        )
                        report.kept_legacy += 1
                    elif legacy_cov < _MIN_LEGACY_COVERAGE:
                        rec_record.applied = False
                        rec_record.reason = (
                            f"legacy_cov={legacy_cov:.2f} < {_MIN_LEGACY_COVERAGE}"
                            f" (refined too tight vs legacy), kept legacy"
                        )
                        _apply_quality_meta(
                            STATUS_REVIEW_REQUIRED,
                            [f"legacy_cov_too_low={legacy_cov:.2f}"],
                        )
                        report.kept_legacy += 1
                    else:
                        legacy_signals = list(rec.source_signals)
                        legacy_boundary = rec.boundary_confidence
                        legacy_warnings = list(rec.warnings)
                        legacy_review = rec.review_required
                        legacy_status = rec.status
                        legacy_content = list(rec.content_bboxes) if rec.content_bboxes else (
                            [list(legacy_bbox)] if legacy_bbox else []
                        )

                        rec.final_bbox = list(result.bbox)
                        # 多 panel：保留 A2 多框；单框时与 final 对齐
                        if len(cand_frames) > 1:
                            rec.content_bboxes = [list(b) for b in cand_frames]
                        else:
                            rec.content_bboxes = [list(result.bbox)]
                        rec.source_signals = legacy_signals + ["layout_refiner"]
                        # 状态只降不升：legacy rejected（正文引用、文本污染等
                        # 内容级否决）不能因几何质量可接受而晋升为可插入状态，
                        # 否则被拒绝的资产会经 _MARKDOWN_INSERTABLE 重新进入正文。
                        if legacy_status == STATUS_REJECTED:
                            _apply_quality_meta(
                                STATUS_REVIEW_REQUIRED,
                                ["legacy_rejected_preserved"],
                            )
                        else:
                            _apply_quality_meta(result.quality.status)

                        if rec.out_path:
                            out_path = rec.out_path
                            if not os.path.isabs(out_path):
                                out_path = os.path.join(out_dir, rec.out_path)

                            rerender_ok = _rerender_asset(
                                pdf_path, page_num, result.bbox, out_path, dpi=dpi,
                                render_failures=render_failures,
                                ident=str(rec.ident),
                                kind=str(rec.kind),
                            )
                            if rerender_ok:
                                rec_record.applied = True
                                rec_record.reason = (
                                    f"applied, status={rec.status}"
                                )
                                report.applied += 1
                            else:
                                rec.final_bbox = legacy_bbox
                                rec.content_bboxes = legacy_content
                                rec.source_signals = legacy_signals
                                rec.boundary_confidence = legacy_boundary
                                rec.warnings = legacy_warnings
                                rec.review_required = legacy_review
                                rec.status = legacy_status
                                rec_record.applied = False
                                rec_record.reason = "rerender failed, kept legacy"
                                report.kept_legacy += 1
                        else:
                            rec_record.applied = True
                            rec_record.reason = "applied (no rerender, no out_path)"
                            report.applied += 1
                else:
                    # 非 acceptable：几何保留 legacy，四态元数据必须写回
                    rec_record.applied = False
                    status = q_status
                    rec_record.reason = f"status={status}, kept legacy geometry"
                    _apply_quality_meta(status)
                    report.kept_legacy += 1

            except Exception as e:
                rec_record.applied = False
                rec_record.reason = f"error: {e}"
                report.kept_legacy += 1
                logger.warning(f"A3: refinement failed for {rec.ident} (page {rec.page}): {e}")

            report.records.append(rec_record)

    return report
