#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A3: 置信度、warnings、验收状态。

L4 层：根据精修结果计算置信度、生成 warnings、分配验收状态。
四态验收：accepted, accepted_with_margin, review_required, rejected。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# 验收状态
STATUS_ACCEPTED = "accepted"
STATUS_ACCEPTED_WITH_MARGIN = "accepted_with_margin"
STATUS_REVIEW_REQUIRED = "review_required"
STATUS_REJECTED = "rejected"

# 置信度阈值
_CONFIDENCE_HIGH = 0.85
_CONFIDENCE_MEDIUM = 0.65
_CONFIDENCE_LOW = 0.40

# IoU 阈值：候选框与最终裁剪框的 IoU
_IOU_GOOD = 0.7
_IOU_MARGIN = 0.4


@dataclass
class QualityAssessment:
    """精修结果的质量评估。

    Attributes:
        confidence: 整体置信度（0~1）
        status: 验收状态
        warnings: 警告列表
        iou_with_candidate: 最终裁剪框与候选框的 IoU
        coverage: 对候选框的覆盖率
        purity: 裁剪框对候选框的纯净率
        boundary_shift: 边界偏移量（pt）
        text_pollution_detected: 是否检测到正文混入
        truncation_detected: 是否检测到截断
    """
    confidence: float = 0.0
    status: str = STATUS_ACCEPTED
    warnings: List[str] = field(default_factory=list)
    iou_with_candidate: float = 0.0
    coverage: float = 0.0
    purity: float = 0.0
    boundary_shift: float = 0.0
    text_pollution_detected: bool = False
    truncation_detected: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "confidence": round(self.confidence, 4),
            "status": self.status,
            "warnings": self.warnings,
            "iou_with_candidate": round(self.iou_with_candidate, 4),
            "coverage": round(self.coverage, 4),
            "purity": round(self.purity, 4),
            "boundary_shift": round(self.boundary_shift, 2),
            "text_pollution_detected": self.text_pollution_detected,
            "truncation_detected": self.truncation_detected,
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


def _bbox_coverage(pred: List[float], gt: List[float]) -> float:
    """pred 对 gt 的覆盖率 = intersection / gt.area"""
    ix0 = max(pred[0], gt[0])
    iy0 = max(pred[1], gt[1])
    ix1 = min(pred[2], gt[2])
    iy1 = min(pred[3], gt[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    gt_area = max(0.0, gt[2] - gt[0]) * max(0.0, gt[3] - gt[1])
    return inter / gt_area if gt_area > 0 else 0.0


def _boundary_shift(candidate: List[float], final: List[float]) -> float:
    """计算候选框到最终框的总边界偏移（pt）。"""
    return (
        abs(candidate[0] - final[0])
        + abs(candidate[1] - final[1])
        + abs(candidate[2] - final[2])
        + abs(candidate[3] - final[3])
    )


def assess_quality(
    final_bbox: List[float],
    candidate_bbox: Optional[List[float]] = None,
    text_pollution: bool = False,
    truncation: bool = False,
    warnings: Optional[List[str]] = None,
) -> QualityAssessment:
    """评估精修结果的质量。

    Args:
        final_bbox: 最终裁剪框
        candidate_bbox: Layout 候选框（None 时不计算 IoU/coverage）
        text_pollution: 是否检测到正文混入
        truncation: 是否检测到截断
        warnings: 额外警告列表

    Returns:
        QualityAssessment
    """
    qa = QualityAssessment(
        text_pollution_detected=text_pollution,
        truncation_detected=truncation,
        warnings=list(warnings or []),
    )

    if candidate_bbox is not None:
        qa.iou_with_candidate = _bbox_iou(final_bbox, candidate_bbox)
        qa.coverage = _bbox_coverage(final_bbox, candidate_bbox)
        qa.purity = _bbox_coverage(candidate_bbox, final_bbox)
        qa.boundary_shift = _boundary_shift(candidate_bbox, final_bbox)

    # 计算置信度
    conf = 0.5  # 基础分
    if candidate_bbox is not None:
        if qa.iou_with_candidate >= _IOU_GOOD:
            conf += 0.3
        elif qa.iou_with_candidate >= _IOU_MARGIN:
            conf += 0.15
        else:
            conf -= 0.1

        # 边界偏移越小越好
        if qa.boundary_shift < 10:
            conf += 0.1
        elif qa.boundary_shift > 50:
            conf -= 0.15

    if text_pollution:
        conf -= 0.2
        qa.warnings.append("text_pollution_detected")
    if truncation:
        conf -= 0.3
        qa.warnings.append("truncation_detected")

    qa.confidence = max(0.0, min(1.0, conf))

    # 分配验收状态
    if truncation:
        qa.status = STATUS_REJECTED
    elif text_pollution:
        qa.status = STATUS_REVIEW_REQUIRED
    elif qa.confidence >= _CONFIDENCE_HIGH:
        qa.status = STATUS_ACCEPTED
    elif qa.confidence >= _CONFIDENCE_MEDIUM:
        qa.status = STATUS_ACCEPTED_WITH_MARGIN
    else:
        qa.status = STATUS_REVIEW_REQUIRED

    return qa
