#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A3: Table 小幅精修。

与 Figure 精修类似的管道，但针对表格特性调整：
- ObjectSnapStep 启用水平联合（表格常跨多列）
- TextTrimStep 启用 skip_adjacent_sweep（保护表头）
- 保守 autocrop（表格白边通常更少）
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from ..pdf_backend import create_rect
from ..text_trim import trim_clip_head_by_text_v2
from ..object_refine import refine_clip_by_objects
from ..pixel_detect import build_text_masks_px, detect_content_bbox_pixels
from ..acceptance import detect_text_pollution
from ..quality import assess_quality, detect_truncation
from .base import (
    LegacyBoundaryGuardStep,
    RefinementContext,
    RefinementResult,
    RefinementStep,
    _DEFAULT_MAX_MOVE,
    _DEFAULT_MAX_TIGHTEN,
    _clamp_movement,
    _compute_move_amount,
    _compute_direction,
)

logger = logging.getLogger(__name__)


class TableObjectSnapStep:
    """Phase B: 表格对象边缘对齐。

    与 Figure 版本的区别：启用 use_horizontal_union（表格常跨多列）。
    """

    name = "table_object_snap"

    def __init__(
        self,
        max_move: float = _DEFAULT_MAX_MOVE,
        object_pad: float = 8.0,
        min_area_ratio: float = 0.010,
        merge_gap: float = 6.0,
    ):
        self.max_move = max_move
        self.object_pad = object_pad
        self.min_area_ratio = min_area_ratio
        self.merge_gap = merge_gap

    def apply(
        self,
        current_bbox: List[float],
        ctx: RefinementContext,
    ) -> RefinementResult:
        old_clip = create_rect(*current_bbox)

        new_clip = refine_clip_by_objects(
            old_clip,
            ctx.caption_bbox,
            ctx.direction,
            ctx.image_rects,
            ctx.vector_rects,
            object_pad=self.object_pad,
            min_area_ratio=self.min_area_ratio,
            merge_gap=self.merge_gap,
            near_edge_only=True,
            use_axis_union=True,
            use_horizontal_union=True,  # 表格：启用水平联合
        )

        new_bbox = [new_clip.x0, new_clip.y0, new_clip.x1, new_clip.y1]
        clamped = _clamp_movement(current_bbox, new_bbox, self.max_move, max_tighten=0.0)
        move = _compute_move_amount(current_bbox, clamped)
        direction = _compute_direction(current_bbox, clamped)

        return RefinementResult(
            bbox=clamped,
            step_name=self.name,
            moved=move > 0.5,
            move_amount=move,
            direction=direction,
            notes=f"horizontal_union=True",
        )


class TableTextTrimStep:
    """Phase A: 表格文本裁切。

    与 Figure 版本的区别：skip_adjacent_sweep=True（保护表头不被误裁）。
    """

    name = "table_text_trim"

    def __init__(
        self,
        max_tighten: float = _DEFAULT_MAX_TIGHTEN,
        width_ratio: float = 0.5,
        font_min: float = 7.0,
        font_max: float = 16.0,
        gap: float = 6.0,
        adjacent_th: float = 24.0,
    ):
        self.max_tighten = max_tighten
        self.width_ratio = width_ratio
        self.font_min = font_min
        self.font_max = font_max
        self.gap = gap
        self.adjacent_th = adjacent_th

    def apply(
        self,
        current_bbox: List[float],
        ctx: RefinementContext,
    ) -> RefinementResult:
        if ctx.caption_bbox is None or ctx.page_rect is None:
            return RefinementResult(
                bbox=current_bbox,
                step_name=self.name,
                moved=False,
                notes="skipped: no caption_bbox or page_rect",
            )

        old_clip = create_rect(*current_bbox)

        new_clip = trim_clip_head_by_text_v2(
            old_clip,
            ctx.page_rect,
            ctx.caption_bbox,
            ctx.direction,
            ctx.text_lines,
            width_ratio=self.width_ratio,
            font_min=self.font_min,
            font_max=self.font_max,
            gap=self.gap,
            adjacent_th=self.adjacent_th,
            # 保守：关闭远距离文本激进裁切
            far_text_th=0.0,
            far_text_para_min_ratio=1.0,
            far_text_trim_mode="skip",
            far_side_min_dist=99999.0,
            far_side_para_min_ratio=1.0,
            # 表格保护：跳过 adjacent sweep 保护表头
            skip_adjacent_sweep=True,
            debug=False,
        )

        new_bbox = [new_clip.x0, new_clip.y0, new_clip.x1, new_clip.y1]
        clamped = _clamp_movement(
            current_bbox, new_bbox, max_move=0.0, max_tighten=self.max_tighten,
        )
        move = _compute_move_amount(current_bbox, clamped)
        direction = _compute_direction(current_bbox, clamped)

        return RefinementResult(
            bbox=clamped,
            step_name=self.name,
            moved=move > 0.5,
            move_amount=move,
            direction=direction,
            notes=f"skip_adjacent_sweep=True, far_text=disabled",
        )


class TableAutocropStep:
    """Phase D: 表格保守白边裁切。

    表格白边通常比 figure 少，但仍需保守裁切。
    """

    name = "table_autocrop"

    def __init__(
        self,
        max_tighten: float = _DEFAULT_MAX_TIGHTEN,
        white_threshold: int = 250,
        pad_px: int = 30,
        min_height_ratio: float = 0.35,
        mask_text: bool = True,
        mask_font_max: float = 14.0,
        mask_width_ratio: float = 0.5,
        mask_top_frac: float = 0.6,
    ):
        self.max_tighten = max_tighten
        self.white_threshold = white_threshold
        self.pad_px = pad_px
        self.min_height_ratio = min_height_ratio
        self.mask_text = mask_text
        self.mask_font_max = mask_font_max
        self.mask_width_ratio = mask_width_ratio
        self.mask_top_frac = mask_top_frac

    def apply(
        self,
        current_bbox: List[float],
        ctx: RefinementContext,
    ) -> RefinementResult:
        if ctx.page is None:
            return RefinementResult(
                bbox=current_bbox,
                step_name=self.name,
                moved=False,
                notes="skipped: no page object",
            )

        old_clip = create_rect(*current_bbox)

        try:
            pix = ctx.page.get_pixmap(dpi=ctx.dpi, clip=old_clip)
        except Exception as e:
            logger.warning(f"TableAutocropStep: pixmap failed: {e}")
            return RefinementResult(
                bbox=current_bbox,
                step_name=self.name,
                moved=False,
                notes=f"pixmap failed: {e}",
            )

        mask_rects_px = None
        if self.mask_text:
            mask_rects_px = build_text_masks_px(
                old_clip,
                ctx.text_lines,
                scale=ctx.scale,
                direction=ctx.direction,
                near_frac=self.mask_top_frac,
                width_ratio=self.mask_width_ratio,
                font_max=self.mask_font_max,
                mask_mode='auto',
            )

        try:
            cx0_px, cy0_px, cx1_px, cy1_px = detect_content_bbox_pixels(
                pix,
                white_threshold=self.white_threshold,
                pad=self.pad_px,
                mask_rects_px=mask_rects_px,
            )
        except Exception as e:
            logger.warning(f"TableAutocropStep: detect_content_bbox failed: {e}")
            return RefinementResult(
                bbox=current_bbox,
                step_name=self.name,
                moved=False,
                notes=f"detect failed: {e}",
            )

        new_x0 = old_clip.x0 + cx0_px / ctx.scale
        new_y0 = old_clip.y0 + cy0_px / ctx.scale
        new_x1 = old_clip.x0 + cx1_px / ctx.scale
        new_y1 = old_clip.y0 + cy1_px / ctx.scale

        new_bbox = [new_x0, new_y0, new_x1, new_y1]

        old_h = current_bbox[3] - current_bbox[1]
        new_h = new_bbox[3] - new_bbox[1]
        if new_h < old_h * self.min_height_ratio:
            return RefinementResult(
                bbox=current_bbox,
                step_name=self.name,
                moved=False,
                notes=f"rejected: new_h={new_h:.1f} < {old_h * self.min_height_ratio:.1f}",
            )

        clamped = _clamp_movement(
            current_bbox, new_bbox, max_move=0.0, max_tighten=self.max_tighten,
        )
        move = _compute_move_amount(current_bbox, clamped)
        direction = _compute_direction(current_bbox, clamped)

        return RefinementResult(
            bbox=clamped,
            step_name=self.name,
            moved=move > 0.5,
            move_amount=move,
            direction=direction,
            notes=f"white_th={self.white_threshold}, pad={self.pad_px}px",
        )


class TableRefiner:
    """Table 精修器：组合多个 RefinementStep。

    管道顺序（从候选框出发）：
    0. LegacyBoundaryGuardStep: 候选框边界守卫（仅扩展显著内缩于 legacy 的边界）
    1. TableObjectSnapStep: 对象边缘对齐（水平联合）
    2. TableTextTrimStep: 保守文本裁切（保护表头）
    3. TableAutocropStep: 保守白边裁切
    """

    def __init__(
        self,
        max_move: float = _DEFAULT_MAX_MOVE,
        max_tighten: float = _DEFAULT_MAX_TIGHTEN,
        steps: Optional[List[RefinementStep]] = None,
    ):
        if steps is not None:
            self.steps = steps
        else:
            self.steps: List[RefinementStep] = [
                LegacyBoundaryGuardStep(),
                TableObjectSnapStep(max_move=max_move),
                TableTextTrimStep(max_tighten=max_tighten),
                TableAutocropStep(max_tighten=max_tighten),
            ]

    def refine(
        self,
        ctx: RefinementContext,
    ) -> RefinementResult:
        """执行完整精修管道。

        Args:
            ctx: 精修上下文（必须包含 candidate_bbox）

        Returns:
            最终 RefinementResult（含质量评估）
        """
        if ctx.candidate_bbox is None:
            return RefinementResult(
                bbox=[0, 0, 0, 0],
                step_name="table_refiner",
                moved=False,
                notes="no candidate_bbox",
            )

        current_bbox = list(ctx.candidate_bbox)
        step_results: List[RefinementResult] = []

        for step in self.steps:
            result = step.apply(current_bbox, ctx)
            step_results.append(result)
            current_bbox = result.bbox

        try:
            clip = create_rect(*current_bbox)
            polluted, _pollution_reason = detect_text_pollution(clip, ctx.text_lines or [])
        except Exception:
            polluted = any("text_pollution" in (r.notes or "") for r in step_results)

        object_rects = list(ctx.image_rects or []) + list(ctx.vector_rects or [])
        truncated, _trunc_reason = detect_truncation(
            final_bbox=current_bbox,
            candidate_bbox=ctx.candidate_bbox,
            object_rects=object_rects,
        )

        quality = assess_quality(
            final_bbox=current_bbox,
            candidate_bbox=ctx.candidate_bbox,
            text_pollution=bool(polluted),
            truncation=bool(truncated),
            warnings=[f"{r.step_name}: {r.direction}({r.move_amount:.1f}pt)" for r in step_results if r.moved],
        )

        total_move = sum(r.move_amount for r in step_results)

        return RefinementResult(
            bbox=current_bbox,
            step_name="table_refiner",
            moved=total_move > 0.5,
            move_amount=total_move,
            direction=_compute_direction(ctx.candidate_bbox, current_bbox),
            quality=quality,
            notes="; ".join(
                f"{r.step_name}({'moved' if r.moved else 'skip'})"
                for r in step_results
            ),
        )
