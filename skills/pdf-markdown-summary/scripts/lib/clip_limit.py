#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Text-block and column-aware crop boundary limiting."""

from __future__ import annotations

import re
from typing import Any, List, Optional

try:
    import fitz
except ImportError:
    fitz = None  # type: ignore


def limit_clip_by_text_blocks(
    clip: Any,
    caption_rect: Any,
    direction: str,
    text_block_rects: List[Any],
    *,
    gap: float = 6.0,
    min_height: float = 40.0,
    min_near_distance: float = 80.0,
) -> Any:
    """
    使用远离当前 caption 一侧的正文/标题文本块限制 baseline 高度。

    baseline 由 caption + 固定 clip_height 生成时，容易越过目标图表后继续吞入
    下一节标题、正文段落或下一张表的 caption。相邻 caption 限制只能处理已识别为
    Figure/Table caption 的块；这里补充普通版式文本块边界。

    只收紧远离 caption 的一侧：
    - direction == below：目标在 caption 下方，限制 clip.y1
    - direction == above：目标在 caption 上方，限制 clip.y0

    min_near_distance 用来跳过 caption 附近的目标图表文本行/表格行带，避免把真实内容
    当作边界；min_height 防止裁剪窗口被压得过小。
    """
    if fitz is None or not text_block_rects:
        return clip

    def _rect(item: Any) -> Any:
        return getattr(item, "bbox", item)

    def _text(item: Any) -> str:
        units = getattr(item, "units", None) or []
        if units:
            return " ".join((getattr(u, "text", "") or "").strip() for u in units).strip()
        return ""

    def _block_type(item: Any) -> str:
        return getattr(item, "block_type", "") or ""

    caption_center = (caption_rect.x0 + caption_rect.x1) / 2.0
    clip_center = (clip.x0 + clip.x1) / 2.0
    caption_column_guess = 0 if caption_center <= clip_center else 1
    caption_is_narrow = caption_rect.width <= clip.width * 0.65
    column_band_pad = max(24.0, min(72.0, caption_rect.width * 0.35))
    caption_band_x0 = max(clip.x0, caption_rect.x0 - column_band_pad)
    caption_band_x1 = min(clip.x1, caption_rect.x1 + column_band_pad)

    def _item_column(item: Any) -> Optional[int]:
        column = getattr(item, "column", None)
        if isinstance(column, int):
            return column
        units = getattr(item, "units", None) or []
        unit_columns = {
            getattr(unit, "column", None)
            for unit in units
            if isinstance(getattr(unit, "column", None), int)
        }
        if len(unit_columns) == 1:
            return next(iter(unit_columns))
        return None

    def _shares_caption_column(item: Any) -> bool:
        if not caption_is_narrow:
            return True

        item_column = _item_column(item)
        if item_column in (0, 1):
            return item_column == caption_column_guess
        if item_column == -1:
            return True

        r = _rect(item)
        overlap = min(r.x1, caption_band_x1) - max(r.x0, caption_band_x0)
        if overlap > 0:
            return True
        return r.x0 <= caption_center <= r.x1

    def _looks_like_content_block(item: Any) -> bool:
        r = _rect(item)
        text = _text(item)
        words = text.split()
        word_count = len(words)
        width_ratio = r.width / max(1.0, clip.width)
        numeric_count = len(re.findall(r"\d+(?:\.\d+)?%?|[-–]|/", text))
        has_sentence_end = bool(re.search(r"[.!?。！？；;:,，]$", text.strip()))
        block_type = _block_type(item)
        if not text and not block_type:
            return False

        # 表格/图内部的行带常表现为较短、较窄、多数字或无句末标点；
        # layout_model 可能把表头误标成 title_h3，因此短标题也先作为内容簇保护，
        # 后续遇到远端正文/章节标题再收紧。
        if numeric_count >= 2:
            return True
        if word_count <= 10 and not has_sentence_end:
            return True
        if width_ratio <= 0.75 and word_count <= 16 and not has_sentence_end:
            return True
        if block_type.startswith("title_") and word_count <= 6:
            return True
        return False

    def _looks_like_blocker(item: Any) -> bool:
        r = _rect(item)
        text = _text(item)
        words = text.split()
        word_count = len(words)
        width_ratio = r.width / max(1.0, clip.width)
        numeric_count = len(re.findall(r"\d+(?:\.\d+)?%?|[-–]|/", text))
        block_type = _block_type(item)
        if not text and not block_type:
            return True
        if numeric_count >= 2 and width_ratio <= 0.75:
            return False
        if block_type.startswith("title_") and not _looks_like_content_block(item):
            return True
        if width_ratio >= 0.55 and word_count >= 8:
            return True
        return False

    def _is_supported_short_title(candidates: List[Any], position: int) -> bool:
        item = candidates[position]
        if not _block_type(item).startswith("title_") or not _looks_like_content_block(item):
            return False
        current = _rect(item)
        nearby_short_titles = 0
        for other in candidates:
            if other is item or not _block_type(other).startswith("title_"):
                continue
            other_rect = _rect(other)
            vertical_gap = max(0.0, current.y0 - other_rect.y1, other_rect.y0 - current.y1)
            if vertical_gap <= max(60.0, min_near_distance) and _looks_like_content_block(other):
                nearby_short_titles += 1
        if nearby_short_titles >= 2:
            return True
        if direction == "below":
            supporting_candidates = candidates[position + 1:position + 3]
        else:
            supporting_candidates = candidates[max(0, position - 2):position]
        for future in supporting_candidates:
            future_rect = _rect(future)
            if direction == "below":
                distance = future_rect.y0 - current.y1
            else:
                distance = future_rect.y0 - current.y1
            if distance > min_near_distance:
                continue
            if (
                not _block_type(future).startswith("title_")
                and _looks_like_content_block(future)
                and not _looks_like_blocker(future)
            ):
                return True
        return False

    if direction == "below":
        candidates = [
            item for item in text_block_rects
            if _rect(item).y0 > clip.y0 and _rect(item).y0 < clip.y1 and _shares_caption_column(item)
        ]
        candidates.sort(key=lambda item: _rect(item).y0)
        blocker = None
        for position, item in enumerate(candidates):
            r = _rect(item)
            if r.y0 < caption_rect.y1 + min_near_distance:
                continue
            if _block_type(item).startswith("title_") and not _is_supported_short_title(candidates, position):
                blocker = r
                break
            if _looks_like_content_block(item) and not _looks_like_blocker(item):
                continue
            if _looks_like_blocker(item):
                blocker = r
                break
        if blocker is None:
            return clip
        limited = fitz.Rect(clip.x0, clip.y0, clip.x1, blocker.y0 - gap)
    elif direction == "above":
        candidates = [
            item for item in text_block_rects
            if _rect(item).y1 > clip.y0 and _rect(item).y1 < clip.y1 and _shares_caption_column(item)
        ]
        candidates.sort(key=lambda item: _rect(item).y1, reverse=True)
        blocker = None
        for position, item in enumerate(candidates):
            r = _rect(item)
            if r.y1 > caption_rect.y0 - min_near_distance:
                continue
            if _block_type(item).startswith("title_") and not _is_supported_short_title(candidates, position):
                blocker = r
                break
            if _looks_like_content_block(item) and not _looks_like_blocker(item):
                continue
            if _looks_like_blocker(item):
                blocker = r
                break
        if blocker is None:
            return clip
        limited = fitz.Rect(clip.x0, blocker.y1 + gap, clip.x1, clip.y1)
    else:
        return clip

    if limited.height < min_height:
        return clip
    return limited

def limit_clip_by_neighbor_captions(
    clip: Any,
    caption_rect: Any,
    direction: str,
    neighbor_caption_rects: List[Any],
    *,
    gap: float = 6.0,
    min_height: float = 40.0,
) -> Any:
    """
    使用同页相邻 caption 限制裁剪窗口的 y 范围。

    连续 Figure/Table 场景中，baseline 窗口可能越过上一条或下一条 caption，
    把相邻图表也截入当前结果。这里只收紧远离当前 caption 的一侧，不改变 x 范围。
    """
    if fitz is None or not neighbor_caption_rects:
        return clip

    if direction == "above":
        previous_caps = [r for r in neighbor_caption_rects if r.y1 <= caption_rect.y0]
        if not previous_caps:
            return clip
        nearest_prev = max(previous_caps, key=lambda r: r.y1)
        limited = fitz.Rect(clip.x0, max(clip.y0, nearest_prev.y1 + gap), clip.x1, clip.y1)
    elif direction == "below":
        next_caps = [r for r in neighbor_caption_rects if r.y0 >= caption_rect.y1]
        if not next_caps:
            return clip
        nearest_next = min(next_caps, key=lambda r: r.y0)
        limited = fitz.Rect(clip.x0, clip.y0, clip.x1, min(clip.y1, nearest_next.y0 - gap))
    else:
        return clip

    if limited.height < min_height:
        return clip
    return limited

def refine_clip_x_range(
    clip: Any,
    caption_rect: Any,
    direction: str,
    image_rects: List[Any],
    vector_rects: List[Any],
    page_rect: Any,
    layout_model: Optional[Any] = None,
    page_num: int = 0,
    *,
    x_margin: float = 15.0,
    min_width_ratio: float = 0.25,
    debug: bool = False,
) -> Any:
    """
    根据图注所在列和对象边界框缩小裁剪区域的 x 方向范围。

    解决双栏/半栏场景下截取全页宽度导致混入另一栏正文的问题。

    策略：
    1. 如果有版式模型且检测到双栏，使用栏边界缩小 x 范围
    2. 根据图注 x 位置确定所属列
    3. 筛选在裁剪区域 y 范围内的对象，用其 x union 缩小范围
    4. 确保 x 范围不小于页面宽度的 min_width_ratio

    Args:
        clip: 当前裁剪区域 (fitz.Rect)
        caption_rect: 图注边界框
        direction: 方向 ('above' | 'below')
        image_rects: 图像边界框列表
        vector_rects: 矢量对象边界框列表
        page_rect: 页面边界框
        layout_model: 版式模型（可选）
        page_num: 页码（0-based）
        x_margin: x 方向额外 padding（pt）
        min_width_ratio: 最小宽度比（相对于页面宽度）
        debug: 调试输出

    Returns:
        调整 x 范围后的裁剪区域
    """
    if fitz is None:
        return clip

    page_width = page_rect.width
    min_width = page_width * min_width_ratio

    x_left = clip.x0
    x_right = clip.x1

    def _has_trustworthy_column_geometry(model: Any) -> bool:
        column_gap = float(getattr(model, 'column_gap', 0.0) or 0.0)
        if column_gap <= 0 or column_gap > 0.30 * page_width:
            return False

        margin_left = float(getattr(model, 'margin_left', page_rect.x0) or page_rect.x0)
        margin_right = float(getattr(model, 'margin_right', page_rect.x1) or page_rect.x1)
        page_aligned_margins = (
            abs(margin_left - page_rect.x0) <= 2.0
            and abs(margin_right - page_rect.x1) <= 2.0
        )
        if page_aligned_margins and column_gap > 0.25 * page_width:
            return False

        col_width = (page_width - column_gap) / 2.0
        return col_width >= page_width * 0.20

    # 策略1：版式模型双栏检测
    if (
        layout_model is not None
        and layout_model.num_columns >= 2
        and _has_trustworthy_column_geometry(layout_model)
    ):
        page_center = page_rect.x0 + page_width / 2
        caption_center = (caption_rect.x0 + caption_rect.x1) / 2

        if caption_center < page_center:
            col_left = layout_model.margin_left if hasattr(layout_model, 'margin_left') else page_rect.x0 + 30
            col_right = page_center - (layout_model.column_gap / 2 if hasattr(layout_model, 'column_gap') else 10)
            x_left = max(x_left, col_left - x_margin)
            x_right = min(x_right, col_right + x_margin)
        else:
            col_left = page_center + (layout_model.column_gap / 2 if hasattr(layout_model, 'column_gap') else 10)
            col_right = layout_model.margin_right if hasattr(layout_model, 'margin_right') else page_rect.x1 - 30
            x_left = max(x_left, col_left - x_margin)
            x_right = min(x_right, col_right + x_margin)

    # 策略2：根据图注 x 位置判断列归属
    caption_width = caption_rect.width
    if caption_width > 0 and caption_width < page_width * 0.6:
        page_center = page_rect.x0 + page_width / 2
        if caption_rect.x1 < page_center:
            if x_right > page_center + 20:
                x_right = min(x_right, page_center - 5)
        elif caption_rect.x0 > page_center:
            if x_left < page_center - 20:
                x_left = max(x_left, page_center + 5)

    # 策略3：用裁剪区域 y 范围内的对象 x 边界缩小范围
    objects_in_y = []
    for r in image_rects + vector_rects:
        inter = r & clip
        if inter.width > 0 and inter.height > 0:
            y_overlap = inter.height / max(1.0, r.height)
            if y_overlap > 0.3:
                objects_in_y.append(r)

    if len(objects_in_y) >= 1:
        obj_x0 = min(r.x0 for r in objects_in_y)
        obj_x1 = max(r.x1 for r in objects_in_y)

        obj_width = obj_x1 - obj_x0
        if obj_width > min_width and obj_width < (x_right - x_left) * 0.95:
            candidate_left = obj_x0 - x_margin
            candidate_right = obj_x1 + x_margin

            caption_in_candidate = (caption_rect.x0 >= candidate_left - x_margin and
                                     caption_rect.x1 <= candidate_right + x_margin)
            if caption_in_candidate:
                x_left = max(x_left, candidate_left)
                x_right = min(x_right, candidate_right)

    # 确保最小宽度
    new_width = x_right - x_left
    if new_width < min_width:
        center_x = (x_left + x_right) / 2
        x_left = center_x - min_width / 2
        x_right = center_x + min_width / 2

    new_clip = fitz.Rect(x_left, clip.y0, x_right, clip.y1)

    new_clip = new_clip & page_rect
    if new_clip.width < min_width or new_clip.height < 40:
        return clip

    return new_clip

def snap_clip_edges(
    clip: Any,
    draw_items: List["DrawItem"],
    *,
    snap_px: float = 14.0,
) -> Any:
    """
    将裁剪区域的上下边缘对齐到最近的水平线。

    Args:
        clip: 裁剪区域
        draw_items: 绘图元素列表
        snap_px: 对齐距离阈值（pt）

    Returns:
        对齐后的裁剪区域
    """
    if fitz is None:
        return clip

    top = clip.y0
    bottom = clip.y1
    best_top = top
    best_bot = bottom
    best_top_dist = snap_px + 1
    best_bot_dist = snap_px + 1

    for it in draw_items:
        if it.orient != 'H':
            continue
        y_mid = 0.5 * (it.rect.y0 + it.rect.y1)

        d_top = abs(y_mid - top)
        if d_top <= snap_px and d_top < best_top_dist:
            best_top_dist = d_top
            best_top = y_mid

        d_bot = abs(y_mid - bottom)
        if d_bot <= snap_px and d_bot < best_bot_dist:
            best_bot_dist = d_bot
            best_bot = y_mid

    if best_bot - best_top >= 40.0:
        return fitz.Rect(clip.x0, best_top, clip.x1, best_bot)
    return clip
