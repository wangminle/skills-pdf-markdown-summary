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
from typing import Any, Dict, List, Optional, Tuple

from .models import AttachmentRecord
from .quality import QualityAssessment, STATUS_ACCEPTED, STATUS_ACCEPTED_WITH_MARGIN

logger = logging.getLogger(__name__)

# 质量阈值：只有 accepted / accepted_WITH_MARGIN 才覆盖 legacy
_ACCEPTABLE_STATUSES = {STATUS_ACCEPTED, STATUS_ACCEPTED_WITH_MARGIN}

# IoU 阈值：精修结果与 legacy 结果 IoU 过低时不覆盖（防止大幅改变）
_MAX_LEGACY_IOU_DIFF = 0.3

# 精修结果对 legacy 的最低覆盖率：低于此值说明候选框过紧，回退到 legacy
_MIN_LEGACY_COVERAGE = 0.55

# record↔Layout 候选匹配的最低 IoU：禁止「任意正重叠即绑定」，降低跨资产误绑
_MIN_MATCH_IOU = 0.25


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


def _match_records_to_candidates(
    records: List[AttachmentRecord],
    pairing_results: Dict[int, Any],
) -> Dict[int, List[float]]:
    """将 records 与 A2 配对结果匹配，返回 record_index -> candidate_bbox 映射。

    匹配逻辑：按页码和 kind 匹配配对结果中的 content bbox。
    pairing_results 是 Dict[int, PairingResult]（page_no -> PairingResult）。
    PairingResult.pairs 是 List[Tuple[AssetCandidate, List[AssetCandidate]]]。
    """
    mapping: Dict[int, List[float]] = {}

    # 构建配对索引：(page, kind) -> list of content_bbox (union)
    pair_index: Dict[Tuple[int, str], List[List[float]]] = {}
    for page_no, pr in pairing_results.items():
        if pr is None:
            continue
        # PairingResult.page is 1-based
        page = getattr(pr, "page", page_no)
        for pair in getattr(pr, "pairs", []):
            # pair is (caption_candidate, content_candidates_list)
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                caption_cand, content_list = pair[0], pair[1]
                # 优先 caption/content 候选上的 kind；禁止默认落到 figure 造成跨类混池
                kind = getattr(caption_cand, "kind", None) or "figure"
                if content_list:
                    kind = getattr(content_list[0], "kind", None) or kind
                if kind not in ("figure", "table"):
                    kind = "figure"
                # Collect all content_bboxes from content candidates
                all_bboxes: List[List[float]] = []
                for cc in content_list:
                    cc_kind = getattr(cc, "kind", kind)
                    if cc_kind not in (kind, "figure", "table"):
                        continue
                    if cc_kind != kind:
                        continue  # 禁止跨 kind 并入同一候选
                    bboxes = getattr(cc, "content_bboxes", [])
                    all_bboxes.extend(bboxes)
                if all_bboxes:
                    all_x0 = min(b[0] for b in all_bboxes)
                    all_y0 = min(b[1] for b in all_bboxes)
                    all_x1 = max(b[2] for b in all_bboxes)
                    all_y1 = max(b[3] for b in all_bboxes)
                    key = (page, kind)
                    pair_index.setdefault(key, []).append([all_x0, all_y0, all_x1, all_y1])

    # 匹配 records 到配对结果（records page is 1-based, pairing page is 1-based）
    for i, rec in enumerate(records):
        rec_page = getattr(rec, "page", 0)
        rec_kind = getattr(rec, "kind", "figure")
        rec_bbox = getattr(rec, "final_bbox", None)

        key = (rec_page, rec_kind)
        candidates = pair_index.get(key, [])

        if not candidates or rec_bbox is None:
            continue

        # 找 IoU 最高的候选；低于阈值则不绑定
        best_iou = 0.0
        best_bbox = None
        for cand in candidates:
            iou = _bbox_iou(rec_bbox, cand)
            if iou > best_iou:
                best_iou = iou
                best_bbox = cand

        if best_bbox is not None and best_iou >= _MIN_MATCH_IOU:
            mapping[i] = best_bbox

    return mapping


def _rerender_asset(
    pdf_path: str,
    page_num: int,
    bbox: List[float],
    out_path: str,
    dpi: int = 300,
) -> bool:
    """用新 bbox 重新渲染资产图片。

    Args:
        pdf_path: PDF 文件路径
        page_num: 页码（0-based）
        bbox: 新的裁剪框 [x0, y0, x1, y1]
        out_path: 输出文件路径
        dpi: 渲染 DPI

    Returns:
        True 如果成功
    """
    try:
        import fitz
        from .pdf_backend import create_rect

        doc = fitz.open(pdf_path)
        try:
            page = doc[page_num]
            clip = create_rect(*bbox)
            pix = page.get_pixmap(dpi=dpi, clip=clip)
            pix.save(out_path)
        finally:
            doc.close()
        return True
    except Exception as e:
        logger.warning(f"Re-render failed for page {page_num}: {e}")
        return False


def run_refinement_pipeline(
    records: List[AttachmentRecord],
    pairing_results: Dict[int, Any],
    pdf_path: str,
    out_dir: str,
    dpi: int = 300,
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

    Returns:
        RefinementReport
    """
    report = RefinementReport(total_records=len(records))

    # 匹配 records 到 Layout 候选框
    candidate_map = _match_records_to_candidates(records, pairing_results)
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
        for rec_idx, cand_bbox in candidate_map.items():
            rec = records[rec_idx]
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

                # Separate into image_rects and vector_rects (same as extract_figures.py)
                from .pdf_backend import create_rect
                image_rects: List = []
                vector_rects: List = []
                for item in draw_items:
                    if item.orient == 'O':
                        vector_rects.append(item.rect)
                for blk in text_dict.get("blocks", []):
                    if blk.get("type") == 1:  # image block
                        bbox = blk.get("bbox")
                        if bbox:
                            image_rects.append(create_rect(*bbox))

                # 方向与 caption：优先使用 record 上真实 caption_bbox
                real_caption = getattr(rec, "caption_bbox", None)
                if real_caption and len(real_caption) == 4:
                    cap_cy = (real_caption[1] + real_caption[3]) / 2.0
                    cand_cy = (cand_bbox[1] + cand_bbox[3]) / 2.0
                    # content 在 caption 上方 → direction=above（与 legacy 语义一致）
                    direction = "above" if cand_cy <= cap_cy else "below"
                    caption_rect = create_rect(*real_caption)
                else:
                    direction = "above"
                    if cand_bbox[1] < legacy_bbox[1]:
                        direction = "below"
                    else:
                        direction = "above"
                    # 无真实 caption 时，从候选框边缘推导伪 caption（兼容旧路径）
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

                # 选择精修器
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

                # 决定是否应用
                if result.quality and result.quality.status in _ACCEPTABLE_STATUSES:
                    # 检查与 legacy 的差异是否合理
                    legacy_iou = _bbox_iou(legacy_bbox, result.bbox)
                    legacy_cov = _bbox_coverage(result.bbox, legacy_bbox)
                    if legacy_iou < _MAX_LEGACY_IOU_DIFF:
                        rec_record.applied = False
                        rec_record.reason = (
                            f"legacy_iou={legacy_iou:.2f} < {_MAX_LEGACY_IOU_DIFF}"
                            f", status={result.quality.status}"
                        )
                        report.kept_legacy += 1
                    elif legacy_cov < _MIN_LEGACY_COVERAGE:
                        rec_record.applied = False
                        rec_record.reason = (
                            f"legacy_cov={legacy_cov:.2f} < {_MIN_LEGACY_COVERAGE}"
                            f" (refined too tight vs legacy), kept legacy"
                        )
                        report.kept_legacy += 1
                    else:
                        # 应用精修结果：更新 record 并重新渲染
                        legacy_signals = list(rec.source_signals)
                        legacy_boundary = rec.boundary_confidence
                        legacy_warnings = list(rec.warnings)
                        legacy_review = rec.review_required
                        legacy_status = rec.status

                        rec.final_bbox = list(result.bbox)
                        rec.content_bboxes = [list(result.bbox)]
                        rec.source_signals = legacy_signals + ["layout_refiner"]
                        rec.boundary_confidence = result.quality.confidence
                        rec.warnings = list(result.quality.warnings)
                        rec.review_required = result.quality.status == "review_required"
                        rec.status = result.quality.status

                        # 重新渲染
                        if rec.out_path:
                            out_path = rec.out_path
                            if not os.path.isabs(out_path):
                                out_path = os.path.join(out_dir, rec.out_path)

                            rerender_ok = _rerender_asset(
                                pdf_path, page_num, result.bbox, out_path, dpi=dpi,
                            )
                            if rerender_ok:
                                rec_record.applied = True
                                rec_record.reason = f"applied, status={result.quality.status}"
                                report.applied += 1
                            else:
                                # 回退：几何与元数据一并恢复，避免 index 与 PNG 不一致
                                rec.final_bbox = legacy_bbox
                                rec.content_bboxes = [legacy_bbox] if legacy_bbox else []
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
                    rec_record.applied = False
                    status = result.quality.status if result.quality else "no_quality"
                    rec_record.reason = f"status={status}, kept legacy"
                    report.kept_legacy += 1

            except Exception as e:
                rec_record.applied = False
                rec_record.reason = f"error: {e}"
                report.kept_legacy += 1
                logger.warning(f"A3: refinement failed for {rec.ident} (page {rec.page}): {e}")

            report.records.append(rec_record)

    return report
