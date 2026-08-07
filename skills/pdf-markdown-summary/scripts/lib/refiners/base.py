#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A3: RefinementStep 协议与基础设施。

L3 层：以 L1/L2 候选框为种子做小幅校正，不再从大窗收缩。
校正方向偏"包全"不偏"收紧"：宁可留白，不冒截断风险。
唯一的收紧动力来自 §2.3 第 4 类硬失败（>1 行混正文）。

每个 RefinementStep 限制单步允许移动的最大边界，防止小幅校正
再次演化成大窗口规则链。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from ..quality import QualityAssessment, assess_quality


# 单步最大边界移动（pt）：防止精修步骤越界演化为大窗口
_DEFAULT_MAX_MOVE = 30.0

# 收紧方向额外限制（更保守）：收紧操作只允许小幅移动
_DEFAULT_MAX_TIGHTEN = 15.0

# 候选框边界守卫阈值（pt）：候选框边界比 legacy 内缩超过此值时触发扩展
_DEFAULT_GUARD_THRESHOLD = 20.0

# 边界守卫扩展比例：关闭差距的比例（0~1）
_DEFAULT_GUARD_EXPAND_RATIO = 0.5


@dataclass
class RefinementContext:
    """精修上下文：携带候选框和页面数据。

    Attributes:
        page: PyMuPDF page 对象
        page_rect: 页面矩形
        candidate_bbox: Layout 候选内容框（精修起点）
        candidate_bboxes: 多框候选（multi-frame），并集为 candidate_bbox
        caption_bbox: caption 框（用于方向判断和剔除）
        direction: caption 相对内容方向 ('above' / 'below')
        kind: 资产类型 ('figure' / 'table')
        text_lines: 页面文本行列表
        image_rects: 页面图像矩形列表
        vector_rects: 页面向量绘制矩形列表
        dpi: 渲染 DPI
        scale: dpi / 72
        page_num: 页码（0-based）
        extra: 额外参数字典
    """
    page: Any = None
    page_rect: Any = None
    candidate_bbox: Optional[List[float]] = None
    candidate_bboxes: Optional[List[List[float]]] = None
    caption_bbox: Optional[Any] = None
    direction: str = "above"
    kind: str = "figure"
    text_lines: List[Any] = field(default_factory=list)
    image_rects: List[Any] = field(default_factory=list)
    vector_rects: List[Any] = field(default_factory=list)
    dpi: int = 300
    scale: float = 300 / 72
    page_num: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RefinementResult:
    """精修单步结果。

    Attributes:
        bbox: 精修后的裁剪框 [x0, y0, x1, y1]
        step_name: 执行此步的名称
        moved: 是否发生了边界移动
        move_amount: 总边界偏移量（pt）
        direction: 移动方向 ('expand' / 'tighten' / 'none')
        quality: 质量评估（如果有候选框可对比）
        notes: 附加说明
    """
    bbox: List[float]
    step_name: str = ""
    moved: bool = False
    move_amount: float = 0.0
    direction: str = "none"
    quality: Optional[QualityAssessment] = None
    notes: str = ""


@runtime_checkable
class RefinementStep(Protocol):
    """精修步骤协议：可组合的小幅校正单元。

    每个步骤接收当前裁剪框和上下文，返回精修后的结果。
    步骤必须遵守 max_move 约束，不得越界移动。
    """

    name: str

    def apply(
        self,
        current_bbox: List[float],
        ctx: RefinementContext,
    ) -> RefinementResult:
        """执行精修步骤。

        Args:
            current_bbox: 当前裁剪框 [x0, y0, x1, y1]
            ctx: 精修上下文

        Returns:
            RefinementResult
        """
        ...


def _clamp_movement(
    old_bbox: List[float],
    new_bbox: List[float],
    max_move: float,
    max_tighten: Optional[float] = None,
) -> List[float]:
    """限制边界移动量，防止越界。

    expand 方向（向外扩大）受 max_move 约束；
    tighten 方向（向内收缩）受 max_tighten（默认 = max_move）约束，
    通常更严格以贯彻"宁可留白"原则。

    Args:
        old_bbox: 原始框
        new_bbox: 目标框
        max_move: 扩大方向最大移动
        max_tighten: 收紧方向最大移动（默认 = max_move）

    Returns:
        裁剪后的框
    """
    if max_tighten is None:
        max_tighten = max_move

    result = list(old_bbox)

    for i in range(4):
        delta = new_bbox[i] - old_bbox[i]
        # x0/y0: 减小=expand, 增大=tighten
        # x1/y1: 增大=expand, 减小=tighten
        is_expand = (i < 2 and delta < 0) or (i >= 2 and delta > 0)
        limit = max_move if is_expand else max_tighten

        if abs(delta) > limit:
            result[i] = old_bbox[i] + (limit if delta > 0 else -limit)
        else:
            result[i] = new_bbox[i]

    return result


def _compute_move_amount(old_bbox: List[float], new_bbox: List[float]) -> float:
    """计算总边界偏移量。"""
    return sum(abs(new_bbox[i] - old_bbox[i]) for i in range(4))


def _compute_direction(old_bbox: List[float], new_bbox: List[float]) -> str:
    """判断移动方向：expand / tighten / none。"""
    move = _compute_move_amount(old_bbox, new_bbox)
    if move < 0.5:
        return "none"

    # 计算面积变化
    old_area = max(0, (old_bbox[2] - old_bbox[0]) * (old_bbox[3] - old_bbox[1]))
    new_area = max(0, (new_bbox[2] - new_bbox[0]) * (new_bbox[3] - new_bbox[1]))

    if new_area > old_area + 1:
        return "expand"
    elif new_area < old_area - 1:
        return "tighten"
    else:
        return "shift"


class LegacyBoundaryGuardStep:
    """候选框边界守卫：仅扩展显著内缩于 legacy 的边界。

    Layout 候选框可能在某些维度上比 legacy 框显著偏紧（如右侧少 50pt），
    直接从候选框精修会导致该维度截断。此步骤逐边界检测：
    如果候选框某边界比 legacy 对应边界内缩超过 threshold pt，
    则向 legacy 方向扩展 expand_ratio 比例的差距。

    对于候选框与 legacy 接近的边界（差距 <= threshold），不做任何调整，
    保留候选框的精度。这样在防止截断的同时不牺牲纯度。
    """

    name = "legacy_boundary_guard"

    def __init__(
        self,
        threshold: float = _DEFAULT_GUARD_THRESHOLD,
        expand_ratio: float = _DEFAULT_GUARD_EXPAND_RATIO,
    ):
        self.threshold = threshold
        self.expand_ratio = expand_ratio

    def apply(
        self,
        current_bbox: List[float],
        ctx: RefinementContext,
    ) -> RefinementResult:
        legacy_bbox = ctx.extra.get("legacy_bbox")
        if legacy_bbox is None:
            return RefinementResult(
                bbox=current_bbox,
                step_name=self.name,
                moved=False,
                notes="skipped: no legacy_bbox in extra",
            )

        old_bbox = list(current_bbox)
        new_bbox = list(current_bbox)

        # 逐边界检测：候选框比 legacy 内缩多少
        # x0: 候选框左边比 legacy 左边偏右 -> 需要向左扩展
        gap_x0 = current_bbox[0] - legacy_bbox[0]
        if gap_x0 > self.threshold:
            new_bbox[0] = current_bbox[0] - gap_x0 * self.expand_ratio

        # y0: 候选框上边比 legacy 上边偏下 -> 需要向上扩展
        gap_y0 = current_bbox[1] - legacy_bbox[1]
        if gap_y0 > self.threshold:
            new_bbox[1] = current_bbox[1] - gap_y0 * self.expand_ratio

        # x1: 候选框右边比 legacy 右边偏左 -> 需要向右扩展
        gap_x1 = legacy_bbox[2] - current_bbox[2]
        if gap_x1 > self.threshold:
            new_bbox[2] = current_bbox[2] + gap_x1 * self.expand_ratio

        # y1: 候选框下边比 legacy 下边偏上 -> 需要向下扩展
        gap_y1 = legacy_bbox[3] - current_bbox[3]
        if gap_y1 > self.threshold:
            new_bbox[3] = current_bbox[3] + gap_y1 * self.expand_ratio

        move = _compute_move_amount(old_bbox, new_bbox)
        direction = _compute_direction(old_bbox, new_bbox)

        gaps = []
        if gap_x0 > self.threshold:
            gaps.append(f"x0:{gap_x0:.0f}")
        if gap_y0 > self.threshold:
            gaps.append(f"y0:{gap_y0:.0f}")
        if gap_x1 > self.threshold:
            gaps.append(f"x1:{gap_x1:.0f}")
        if gap_y1 > self.threshold:
            gaps.append(f"y1:{gap_y1:.0f}")

        return RefinementResult(
            bbox=new_bbox,
            step_name=self.name,
            moved=move > 0.5,
            move_amount=move,
            direction=direction,
            notes=f"expanded: {', '.join(gaps)}" if gaps else "no significant gaps",
        )
