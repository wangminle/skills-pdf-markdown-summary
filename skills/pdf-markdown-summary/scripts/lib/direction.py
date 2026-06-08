#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能方向判定与全局锚点

V0.4.0 新增：从 extract_pdf_assets.py 迁移的方向判定逻辑

包含：
- compute_global_anchor: 计算全局锚点方向
- score_direction: 评估单个 caption 的方向得分
- estimate_ink_ratio_for_clip: 估计裁剪区域的墨迹密度
"""

from __future__ import annotations

import logging
import math
import re
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from .pdf_backend import create_rect, open_pdf
from .extract_helpers import collect_draw_items, estimate_ink_ratio

if TYPE_CHECKING:
    import fitz

logger = logging.getLogger(__name__)


def compute_object_ratio(
    clip: "fitz.Rect",
    image_rects: List["fitz.Rect"],
    vector_rects: List["fitz.Rect"],
) -> float:
    """
    计算裁剪区域内的对象覆盖率。

    Args:
        clip: 裁剪区域
        image_rects: 图像边界框列表
        vector_rects: 矢量对象边界框列表

    Returns:
        对象覆盖率 (0.0~1.0)
    """
    area = max(1.0, clip.width * clip.height)
    acc = 0.0

    for r in image_rects + vector_rects:
        inter = r & clip
        if inter.width > 0 and inter.height > 0:
            acc += inter.width * inter.height

    return min(1.0, acc / area)


def score_direction_for_caption(
    page: "fitz.Page",
    caption_bbox: "fitz.Rect",
    page_rect: "fitz.Rect",
    image_rects: List["fitz.Rect"],
    vector_rects: List["fitz.Rect"],
    clip_height: float = 400.0,
    margin_x: float = 20.0,
    caption_gap: float = 3.0,
) -> Tuple[float, float]:
    """
    为单个 caption 计算 above 和 below 两个方向的得分。

    得分基于：
    - 墨迹密度（60% 权重）
    - 对象覆盖率（40% 权重）

    Args:
        page: PDF 页面对象
        caption_bbox: Caption 边界框
        page_rect: 页面边界框
        image_rects: 图像边界框列表
        vector_rects: 矢量对象边界框列表
        clip_height: 裁剪窗口高度
        margin_x: 水平边距
        caption_gap: Caption 与图像间隙

    Returns:
        (above_score, below_score) 元组
    """
    try:
        import fitz
    except ImportError:
        return 0.0, 0.0

    x_left = page_rect.x0 + margin_x
    x_right = page_rect.x1 - margin_x

    # Above clip
    y_bottom_above = caption_bbox.y0 - caption_gap
    y_top_above = max(page_rect.y0, y_bottom_above - clip_height)
    clip_above = create_rect(x_left, y_top_above, x_right, y_bottom_above)

    # Below clip
    y_top_below = caption_bbox.y1 + caption_gap
    y_bottom_below = min(page_rect.y1, y_top_below + clip_height)
    clip_below = create_rect(x_left, y_top_below, x_right, y_bottom_below)

    # 计算 above 得分
    try:
        pix_above = page.get_pixmap(dpi=72, clip=clip_above, alpha=False)
        ink_above = estimate_ink_ratio(pix_above)
    except Exception:
        ink_above = 0.0
    obj_above = compute_object_ratio(clip_above, image_rects, vector_rects)
    score_above = 0.6 * ink_above + 0.4 * obj_above

    # 计算 below 得分
    try:
        pix_below = page.get_pixmap(dpi=72, clip=clip_below, alpha=False)
        ink_below = estimate_ink_ratio(pix_below)
    except Exception:
        ink_below = 0.0
    obj_below = compute_object_ratio(clip_below, image_rects, vector_rects)
    score_below = 0.6 * ink_below + 0.4 * obj_below

    return score_above, score_below


def compute_global_anchor(
    doc: "fitz.Document",
    caption_pattern: "re.Pattern",
    *,
    clip_height: float = 400.0,
    margin_x: float = 20.0,
    caption_gap: float = 3.0,
    margin: float = 0.02,
    is_table: bool = False,
    debug: bool = False,
) -> Optional[str]:
    """
    预扫描文档，计算全局锚点方向。

    遍历所有 caption，累计 above/below 两个方向的得分，
    如果差异超过 margin 阈值，返回得分较高的方向。

    Args:
        doc: PDF 文档对象
        caption_pattern: Caption 正则表达式
        clip_height: 裁剪窗口高度
        margin_x: 水平边距
        caption_gap: Caption 与图像间隙
        margin: 判定阈值（需要超过此比例才确定方向）
        is_table: 是否为表格（表格默认 below）
        debug: 调试模式

    Returns:
        'above' | 'below' | None（无法确定）
    """
    try:
        import fitz
    except ImportError:
        return None

    above_total = 0.0
    below_total = 0.0
    caption_count = 0

    for pno in range(len(doc)):
        page = doc[pno]
        page_rect = page.rect
        dict_data = page.get_text("dict")

        # 收集对象
        draw_items = collect_draw_items(page)
        image_rects: List[fitz.Rect] = []
        vector_rects: List[fitz.Rect] = []

        for item in draw_items:
            if item.orient == 'O':
                vector_rects.append(item.rect)
            elif item.orient in ('H', 'V'):
                vector_rects.append(item.rect)

        for blk in dict_data.get("blocks", []):
            if blk.get("type") == 1:
                bbox = blk.get("bbox")
                if bbox:
                    image_rects.append(create_rect(*bbox))

        # 查找 captions
        for blk in dict_data.get("blocks", []):
            if blk.get("type", 0) != 0:
                continue

            for ln in blk.get("lines", []):
                spans = ln.get("spans", [])
                if not spans:
                    continue

                text = "".join(sp.get("text", "") for sp in spans)
                text_stripped = text.strip()

                match = caption_pattern.match(text_stripped)
                if not match:
                    continue

                caption_bbox = create_rect(*(ln.get("bbox", [0, 0, 0, 0])))

                score_above, score_below = score_direction_for_caption(
                    page, caption_bbox, page_rect,
                    image_rects, vector_rects,
                    clip_height=clip_height,
                    margin_x=margin_x,
                    caption_gap=caption_gap,
                )

                above_total += score_above
                below_total += score_below
                caption_count += 1

                if debug:
                    print(f"[GLOBAL_ANCHOR] Page {pno+1}: above={score_above:.3f}, below={score_below:.3f}")

    if caption_count == 0:
        if debug:
            print(f"[GLOBAL_ANCHOR] No captions found, returning None")
        return None

    # 归一化
    total = above_total + below_total
    if total < 1e-6:
        return None

    above_ratio = above_total / total
    below_ratio = below_total / total

    if debug:
        print(f"[GLOBAL_ANCHOR] Total: above={above_total:.3f} ({above_ratio:.1%}), "
              f"below={below_total:.3f} ({below_ratio:.1%}), "
              f"margin={margin:.1%}")

    # 判定
    if above_ratio > 0.5 + margin:
        return 'above'
    elif below_ratio > 0.5 + margin:
        return 'below'
    else:
        return None


def score_local_direction(
    caption_bbox: "fitz.Rect",
    page_rect: "fitz.Rect",
    image_rects: List["fitz.Rect"],
    vector_rects: List["fitz.Rect"],
    clip_height: float = 400.0,
    margin_x: float = 20.0,
    caption_gap: float = 3.0,
    is_table: bool = False,
    text_lines: Optional[List[Tuple["fitz.Rect", float, str]]] = None,
) -> Tuple[str, float]:
    """
    基于局部对象密度评估单个 caption 的方向。

    分析 caption 上方和下方的对象覆盖率，返回得分更高的方向。
    与全局锚点不同，这是针对单个 caption 的局部判断。

    Args:
        caption_bbox: Caption 边界框
        page_rect: 页面边界框
        image_rects: 图像边界框列表
        vector_rects: 矢量对象边界框列表
        clip_height: 预估裁剪窗口高度
        margin_x: 水平边距
        caption_gap: Caption 与图像间隙
        is_table: 是否为表格

    Returns:
        (direction, confidence) 元组
    """
    try:
        import fitz as _fitz
    except ImportError:
        _fitz = None

    if _fitz is None:
        return ('below' if is_table else 'above', 0.5)

    if is_table and text_lines:
        search_height = min(300.0, max(160.0, clip_height * 0.5))
        page_width = max(1.0, page_rect.width)

        def table_text_score(side: str) -> float:
            if side == 'above':
                nearby = [
                    line for line in text_lines
                    if line[0].y1 <= caption_bbox.y0 - 2.0
                    and line[0].y0 >= caption_bbox.y0 - search_height
                ]
                gaps = [caption_bbox.y0 - line[0].y1 for line in nearby]
            else:
                nearby = [
                    line for line in text_lines
                    if line[0].y0 >= caption_bbox.y1 + 2.0
                    and line[0].y1 <= caption_bbox.y1 + search_height
                ]
                gaps = [line[0].y0 - caption_bbox.y1 for line in nearby]

            nearby = [
                line for line in nearby
                if not re.match(
                    r"^\s*(?:table|tab\.?|figure|fig\.?)\s*[A-Z]?\d+\b",
                    line[2].strip(),
                    re.IGNORECASE,
                )
                and not (
                    line[0].width < page_width * 0.08
                    and len(line[2].strip()) <= 8
                    and line[0].y0 >= page_rect.y1 - max(80.0, page_rect.height * 0.10)
                )
            ]

            if not nearby:
                return 0.0

            rows: List[List[Tuple["fitz.Rect", float, str]]] = []
            row_centers: List[float] = []
            for line in sorted(nearby, key=lambda item: (item[0].y0, item[0].x0)):
                center = (line[0].y0 + line[0].y1) / 2.0
                if rows and abs(center - row_centers[-1]) <= 3.0:
                    rows[-1].append(line)
                    row_centers[-1] = sum(
                        (item[0].y0 + item[0].y1) / 2.0 for item in rows[-1]
                    ) / len(rows[-1])
                else:
                    rows.append([line])
                    row_centers.append(center)

            structured_gaps: List[float] = []
            for row in rows:
                row_rect = row[0][0]
                for line_rect, _font_size, _text in row[1:]:
                    row_rect = row_rect | line_rect
                if len(row) >= 3 or (len(row) >= 2 and row_rect.width >= page_width * 0.35):
                    if side == "above":
                        structured_gaps.append(caption_bbox.y0 - row_rect.y1)
                    else:
                        structured_gaps.append(row_rect.y0 - caption_bbox.y1)

            short_like = 0
            wide_long = 0
            for line_rect, _font_size, text in nearby:
                text_len = len(text.strip())
                if text_len <= 40 or line_rect.width < page_width * 0.55:
                    short_like += 1
                if text_len >= 40 and line_rect.width >= page_width * 0.55:
                    wide_long += 1

            short_ratio = short_like / len(nearby)
            wide_long_ratio = wide_long / len(nearby)
            nearest_gap = min(structured_gaps) if structured_gaps else min(gaps)
            proximity = math.exp(-nearest_gap / 20.0)
            structure_bonus = min(1.0, len(structured_gaps) / 4.0)
            return (
                0.20 * short_ratio
                + 0.15 * (1.0 - wide_long_ratio)
                + 0.50 * proximity
                + 0.15 * structure_bonus
            )

        above_text_score = table_text_score('above')
        below_text_score = table_text_score('below')
        score_diff = abs(above_text_score - below_text_score)
        if score_diff >= 0.03:
            direction = 'above' if above_text_score > below_text_score else 'below'
            confidence = min(0.95, 0.60 + score_diff * 2.0)
            return direction, confidence

    x_left = page_rect.x0 + margin_x
    x_right = page_rect.x1 - margin_x

    above_h = max(1.0, caption_bbox.y0 - page_rect.y0 - caption_gap)
    below_h = max(1.0, page_rect.y1 - caption_bbox.y1 - caption_gap)

    clip_above = create_rect(x_left, max(page_rect.y0, caption_bbox.y0 - clip_height - caption_gap), x_right, caption_bbox.y0 - caption_gap)
    clip_below = create_rect(x_left, caption_bbox.y1 + caption_gap, x_right, min(page_rect.y1, caption_bbox.y1 + clip_height + caption_gap))

    obj_above = compute_object_ratio(clip_above, image_rects, vector_rects)
    obj_below = compute_object_ratio(clip_below, image_rects, vector_rects)

    total = obj_above + obj_below
    if total < 0.001:
        return ('below' if is_table else 'above', 0.5)

    above_ratio = obj_above / total
    below_ratio = obj_below / total

    if above_ratio > 0.6:
        return ('above', above_ratio)
    elif below_ratio > 0.6:
        return ('below', below_ratio)

    return ('below' if is_table else 'above', max(above_ratio, below_ratio))


def determine_direction(
    caption_bbox: "fitz.Rect",
    page_rect: "fitz.Rect",
    ident: str,
    *,
    global_anchor: Optional[str] = None,
    forced_below: Optional[set] = None,
    forced_above: Optional[set] = None,
    is_table: bool = False,
    page_position_heuristic: bool = True,
    local_evidence: Optional[Tuple[str, float]] = None,
) -> str:
    """
    确定单个图表的提取方向。

    优先级（局部优先策略）：
    1. 用户显式指定（forced_below/forced_above）
    2. 局部方向证据（local_evidence）
    3. 页面位置启发式
    4. 全局锚点（仅作 tie-break）
    5. 默认值（Figure: above, Table: below）

    Args:
        caption_bbox: Caption 边界框
        page_rect: 页面边界框
        ident: 图表编号
        global_anchor: 全局锚点方向（仅作 tie-break）
        forced_below: 强制 below 的编号集合
        forced_above: 强制 above 的编号集合
        is_table: 是否为表格
        page_position_heuristic: 是否使用页面位置启发式
        local_evidence: 局部方向证据 (direction, confidence)
            由 score_local_direction() 返回，如果不提供则不使用

    Returns:
        'above' | 'below'
    """
    forced_below = forced_below or set()
    forced_above = forced_above or set()

    # 1. 用户显式指定
    if ident in forced_below:
        return 'below'
    if ident in forced_above:
        return 'above'

    # 2. 局部方向证据（高置信度时直接采用）
    if local_evidence is not None:
        local_dir, local_conf = local_evidence
        if local_conf >= 0.6:
            return local_dir

    # 3. 页面位置启发式
    if page_position_heuristic:
        if is_table:
            page_quarter = page_rect.height * 0.75
            if caption_bbox.y1 > page_rect.y0 + page_quarter:
                return 'above'
        else:
            page_third = page_rect.height / 3
            if caption_bbox.y0 < page_rect.y0 + page_third:
                return 'below'

    # 4. 全局锚点（仅作 tie-break：当局部证据不够强时参考）
    if global_anchor and local_evidence is not None:
        local_dir, local_conf = local_evidence
        if local_conf < 0.6:
            return global_anchor

    # 5. 全局锚点（无局部证据时使用，但不再覆盖页面位置启发式）
    if global_anchor and local_evidence is None:
        return global_anchor

    # 6. 默认值
    return 'below' if is_table else 'above'


# ============================================================================
# 向后兼容别名
# ============================================================================

_compute_global_anchor = compute_global_anchor
_determine_direction = determine_direction
_score_direction_for_caption = score_direction_for_caption


# ============================================================================
# 模块导出
# ============================================================================

__all__ = [
    "compute_global_anchor",
    "determine_direction",
    "score_direction_for_caption",
    "score_local_direction",
    "compute_object_ratio",
]
