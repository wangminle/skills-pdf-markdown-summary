#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Commit 07+: 精裁与验收

从 extract_pdf_assets.py 抽离的精裁和验收相关代码。

V0.4.0 更新：迁移完整的文本裁切逻辑 (Phase A/B/C)

包含：
- detect_content_bbox_pixels: 像素级内容包围盒检测
- estimate_ink_ratio: 墨迹密度估算
- merge_rects: 合并重叠矩形
- refine_clip_by_objects: 基于对象的裁剪优化
- build_text_masks_px: 构建文本遮罩
- detect_far_side_text_evidence: 远端正文检测
- trim_far_side_text_post_autocrop: 远端正文后处理裁切
- adaptive_acceptance_thresholds: 动态验收阈值
- snap_clip_edges: 对齐裁剪边缘到绘图线
- is_caption_text: 检查文本行是否属于图注
- detect_exact_n_lines_of_text: 检测精确行数
- trim_clip_head_by_text: 文本裁切（Phase A 基础版）
- trim_clip_head_by_text_v2: 增强文本裁切（Phase A/B/C 完整版）
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

# 尝试导入 fitz
try:
    import fitz
except ImportError:
    fitz = None  # type: ignore

# 避免循环导入
if TYPE_CHECKING:
    from .models import AcceptanceThresholds, DrawItem

# 模块日志器
logger = logging.getLogger(__name__)


# ============================================================================
# 像素级内容检测
# ============================================================================

def detect_content_bbox_pixels(
    pix: "fitz.Pixmap",
    white_threshold: int = 250,
    pad: int = 30,
    mask_rects_px: Optional[List[Tuple[int, int, int, int]]] = None,
) -> Tuple[int, int, int, int]:
    """
    在像素级估计非白色区域包围盒（带少量 padding），用于 autocrop 去除白边。

    Args:
        pix: PyMuPDF 位图对象
        white_threshold: 白色阈值（0-255）
        pad: 边界 padding（像素）
        mask_rects_px: 可选的掩码矩形列表（像素坐标），这些区域将被忽略

    Returns:
        (left, top, right, bottom) 像素坐标的边界框
    """
    if fitz is None:
        return (0, 0, pix.width, pix.height) if pix else (0, 0, 0, 0)

    w, h = pix.width, pix.height
    n = pix.n

    # 转换为 RGB 避免 alpha 复杂性
    if pix.alpha:
        tmp = fitz.Pixmap(fitz.csRGB, pix)
        pix = tmp
        n = pix.n

    samples = memoryview(pix.samples)
    stride = pix.stride

    def in_mask(x: int, y: int) -> bool:
        if not mask_rects_px:
            return False
        for (lx, ty, rx, by) in mask_rects_px:
            if lx <= x < rx and ty <= y < by:
                return True
        return False

    def row_has_ink(y: int) -> bool:
        row = samples[y * stride:(y + 1) * stride]
        step = max(1, w // 1000)
        for x in range(0, w, step):
            off = x * n
            r = row[off + 0]
            g = row[off + 1] if n > 1 else r
            b = row[off + 2] if n > 2 else r
            if in_mask(x, y):
                continue
            if r < white_threshold or g < white_threshold or b < white_threshold:
                return True
        return False

    def col_has_ink(x: int) -> bool:
        step = max(1, h // 1000)
        off0 = x * n
        for y in range(0, h, step):
            row = samples[y * stride:(y + 1) * stride]
            r = row[off0 + 0]
            g = row[off0 + 1] if n > 1 else r
            b = row[off0 + 2] if n > 2 else r
            if in_mask(x, y):
                continue
            if r < white_threshold or g < white_threshold or b < white_threshold:
                return True
        return False

    top = 0
    while top < h and not row_has_ink(top):
        top += 1
    bottom = h - 1
    while bottom >= 0 and not row_has_ink(bottom):
        bottom -= 1
    left = 0
    while left < w and not col_has_ink(left):
        left += 1
    right = w - 1
    while right >= 0 and not col_has_ink(right):
        right -= 1

    if left >= right or top >= bottom:
        return (0, 0, w, h)

    # pad & clamp
    left = max(0, left - pad)
    top = max(0, top - pad)
    right = min(w, right + 1 + pad)
    bottom = min(h, bottom + 1 + pad)
    return (left, top, right, bottom)


def estimate_ink_ratio(pix: "fitz.Pixmap", white_threshold: int = 250) -> float:
    """
    估计位图中"有墨迹"的像素比例（0~1），通过子采样快速近似。
    值越大表示内容越密集。

    Args:
        pix: PyMuPDF 位图对象
        white_threshold: 白色阈值（0-255）

    Returns:
        墨迹比例（0.0~1.0）
    """
    if fitz is None:
        return 0.0

    w, h = pix.width, pix.height
    n = pix.n

    if pix.alpha:
        tmp = fitz.Pixmap(fitz.csRGB, pix)
        pix = tmp
        n = pix.n

    samples = memoryview(pix.samples)
    stride = pix.stride
    step_x = max(1, w // 800)
    step_y = max(1, h // 800)
    nonwhite = 0
    total = 0

    for y in range(0, h, step_y):
        row = samples[y * stride:(y + 1) * stride]
        for x in range(0, w, step_x):
            off = x * n
            r = row[off + 0]
            g = row[off + 1] if n > 1 else r
            b = row[off + 2] if n > 2 else r
            if r < white_threshold or g < white_threshold or b < white_threshold:
                nonwhite += 1
            total += 1

    if total == 0:
        return 0.0
    return nonwhite / float(total)


# ============================================================================
# 矩形合并
# ============================================================================

def merge_rects(rects: List[Any], merge_gap: float = 6.0) -> List[Any]:
    """
    合并重叠的矩形。

    通过先扩展再合并相交框的方式迭代处理。

    Args:
        rects: fitz.Rect 列表
        merge_gap: 合并间隙（pt）

    Returns:
        合并后的矩形列表
    """
    if not rects or fitz is None:
        return []

    # 扩展后合并相交框
    expanded = [fitz.Rect(r.x0 - merge_gap, r.y0 - merge_gap, r.x1 + merge_gap, r.y1 + merge_gap) for r in rects]
    changed = True
    while changed:
        changed = False
        out: List[Any] = []
        for r in expanded:
            merged = False
            for i, o in enumerate(out):
                if (r & o).width > 0 and (r & o).height > 0:
                    out[i] = o | r
                    merged = True
                    changed = True
                    break
            if not merged:
                out.append(r)
        expanded = out
    return expanded


# ============================================================================
# 基于对象的裁剪优化
# ============================================================================

def refine_clip_by_objects(
    clip: Any,
    caption_rect: Any,
    direction: str,
    image_rects: List[Any],
    vector_rects: List[Any],
    *,
    object_pad: float = 8.0,
    min_area_ratio: float = 0.015,
    merge_gap: float = 6.0,
    near_edge_only: bool = True,
    use_axis_union: bool = True,
    use_horizontal_union: bool = False,
) -> Any:
    """
    使用对象组件优化裁剪区域。

    Args:
        clip: 当前裁剪区域
        caption_rect: 图注边界框
        direction: 方向 ('above' | 'below')
        image_rects: 图像边界框列表
        vector_rects: 矢量图形边界框列表
        object_pad: 对象 padding
        min_area_ratio: 最小面积比
        merge_gap: 合并间隙
        near_edge_only: 是否只调整靠近图注的边界
        use_axis_union: 是否使用垂直轴联合
        use_horizontal_union: 是否使用水平轴联合

    Returns:
        优化后的裁剪区域
    """
    if fitz is None:
        return clip

    area = max(1.0, clip.width * clip.height)
    cand: List[Any] = []

    for r in image_rects + vector_rects:
        inter = r & clip
        if inter.width > 0 and inter.height > 0:
            if (inter.width * inter.height) / area >= min_area_ratio:
                cand.append(inter)

    if not cand:
        return clip

    comps = merge_rects(cand, merge_gap=merge_gap)
    if not comps:
        return clip

    # 选择最靠近图注的组件
    def comp_score(r: Any) -> float:
        if direction == 'above':
            dist = max(0.0, caption_rect.y0 - r.y1)
        else:
            dist = max(0.0, r.y0 - caption_rect.y1)
        return dist + (-0.0001 * r.width * r.height)

    comps.sort(key=comp_score)
    chosen = comps[0]

    # 垂直堆叠组件联合
    if use_axis_union and len(comps) >= 2:
        overlaps = []
        for r in comps:
            inter_w = max(0.0, min(r.x1, chosen.x1) - max(r.x0, chosen.x0))
            overlaps.append(inter_w / max(1.0, min(r.width, chosen.width)))
        if sum(1 for v in overlaps if v >= 0.6) >= 2:
            union = comps[0]
            for r in comps[1:]:
                union = union | r
            chosen = union

    # 水平并列组件联合
    if use_horizontal_union and len(comps) >= 2:
        y_overlaps = []
        for r in comps:
            inter_h = max(0.0, min(r.y1, chosen.y1) - max(r.y0, chosen.y0))
            y_overlaps.append(inter_h / max(1.0, min(r.height, chosen.height)))
        if sum(1 for v in y_overlaps if v >= 0.6) >= 2:
            union = comps[0]
            for r in comps[1:]:
                union = union | r
            chosen = union

    # 应用 padding
    chosen = fitz.Rect(
        chosen.x0 - object_pad,
        chosen.y0 - object_pad,
        chosen.x1 + object_pad,
        chosen.y1 + object_pad,
    )

    # 非对称更新：只调整靠近图注的边界
    result = fitz.Rect(clip)
    if near_edge_only:
        if direction == 'above':
            result.y1 = min(clip.y1, max(chosen.y1, clip.y0 + 40.0))
        else:
            result.y0 = max(clip.y0, min(chosen.y0, clip.y1 - 40.0))
        result.x0 = min(result.x0, chosen.x0)
        result.x1 = max(result.x1, chosen.x1)
        result = result & clip
        return result if result.height >= 40 else clip
    else:
        result = (chosen & clip)
        return result if result.height >= 40 else clip


# ============================================================================
# 文本遮罩构建
# ============================================================================

def build_text_masks_px(
    clip: Any,
    text_lines: List[Tuple[Any, float, str]],
    *,
    scale: float,
    direction: str = 'above',
    near_frac: float = 0.6,
    width_ratio: float = 0.5,
    font_max: float = 14.0,
    mask_mode: str = 'auto',
    far_edge_zone: float = 40.0,
) -> List[Tuple[int, int, int, int]]:
    """
    将选定的文本行转换为像素空间遮罩。

    Args:
        clip: 裁剪区域
        text_lines: 文本行列表 [(rect, font_size, text), ...]
        scale: 缩放比例（pt -> px）
        direction: 方向 ('above' | 'below')
        near_frac: 近端区域比例
        width_ratio: 宽度比例阈值
        font_max: 最大字号
        mask_mode: 遮罩模式 ('near' | 'both' | 'auto')
        far_edge_zone: 远端边缘检测区域（pt）

    Returns:
        像素坐标的遮罩矩形列表 [(left, top, right, bottom), ...]
    """
    if fitz is None:
        return []

    masks: List[Tuple[int, int, int, int]] = []
    y_thresh_top = clip.y0 + near_frac * clip.height
    y_thresh_bot = clip.y1 - near_frac * clip.height

    mask_near = True
    mask_far = (mask_mode == 'both')

    # 'auto' 模式：检测远端是否有正文行
    far_side_lines: List[Tuple[Any, float, str]] = []
    if mask_mode == 'auto':
        far_is_top = (direction == 'above')
        for (lb, fs, text) in text_lines:
            txt = text.strip()
            if not txt:
                continue
            if fs > font_max:
                continue
            inter = lb & clip
            if inter.width <= 0 or inter.height <= 0:
                continue
            if (inter.width / max(1.0, clip.width)) < width_ratio:
                continue
            if len(txt) < 10:
                continue
            if far_is_top:
                dist = lb.y0 - clip.y0
                if dist < far_edge_zone:
                    far_side_lines.append((lb, fs, text))
            else:
                dist = clip.y1 - lb.y1
                if dist < far_edge_zone:
                    far_side_lines.append((lb, fs, text))

        mask_far = len(far_side_lines) > 0

    for (lb, fs, text) in text_lines:
        if not text.strip():
            continue
        if fs > font_max:
            continue
        inter = lb & clip
        if inter.width <= 0 or inter.height <= 0:
            continue
        if (inter.width / max(1.0, clip.width)) < width_ratio:
            continue

        in_near_side = False
        in_far_side = False

        if direction == 'above':
            if inter.y0 >= y_thresh_bot:
                in_near_side = True
            if inter.y1 <= y_thresh_top:
                in_far_side = True
        else:
            if inter.y1 <= y_thresh_top:
                in_near_side = True
            if inter.y0 >= y_thresh_bot:
                in_far_side = True

        should_mask = False
        if mask_near and in_near_side:
            should_mask = True
        if mask_far and in_far_side:
            should_mask = True

        if not should_mask:
            continue

        # 转换为像素坐标
        l = int(max(0, (inter.x0 - clip.x0) * scale))
        t = int(max(0, (inter.y0 - clip.y0) * scale))
        r = int(min((clip.x1 - clip.x0) * scale, (inter.x1 - clip.x0) * scale))
        b = int(min((clip.y1 - clip.y0) * scale, (inter.y1 - clip.y0) * scale))
        if r - l > 1 and b - t > 1:
            masks.append((l, t, r, b))

    return masks


# ============================================================================
# 远端正文检测
# ============================================================================

def detect_far_side_text_evidence(
    clip: Any,
    text_lines: List[Tuple[Any, float, str]],
    direction: str,
    edge_zone: float = 40.0,
    min_width_ratio: float = 0.30,
    font_min: float = 7.0,
    font_max: float = 16.0,
) -> Tuple[bool, float]:
    """
    检测远端边缘附近是否有正文行证据。

    用于单调性约束：当远端附近有正文行时，Phase D 不应该扩展到这些行的区域。

    Args:
        clip: 当前裁剪区域
        text_lines: 文本行列表 [(rect, font_size, text), ...]
        direction: 方向 ('above' | 'below')
        edge_zone: 远端边缘检测范围（pt）
        min_width_ratio: 正文行最小宽度比例
        font_min/font_max: 正文字号范围

    Returns:
        (has_evidence, suggested_limit):
        - has_evidence: 是否检测到正文证据
        - suggested_limit: 建议的边界限制
    """
    if fitz is None or clip.height <= 1 or clip.width <= 1:
        return False, 0.0

    far_is_top = (direction == 'above')
    evidence_lines: List[Any] = []

    for (lb, fs, text) in text_lines:
        txt = text.strip()
        if not txt:
            continue

        inter = lb & clip
        if inter.width <= 0 or inter.height <= 0:
            continue

        width_ratio = inter.width / max(1.0, clip.width)
        if width_ratio < min_width_ratio:
            continue

        if not (font_min <= fs <= font_max):
            continue

        if len(txt) < 10:
            continue

        if far_is_top:
            dist_to_far_edge = lb.y0 - clip.y0
            if dist_to_far_edge < edge_zone:
                evidence_lines.append(lb)
        else:
            dist_to_far_edge = clip.y1 - lb.y1
            if dist_to_far_edge < edge_zone:
                evidence_lines.append(lb)

    if evidence_lines:
        gap = 6.0
        if far_is_top:
            suggested_limit = max(lb.y1 for lb in evidence_lines) + gap
        else:
            suggested_limit = min(lb.y0 for lb in evidence_lines) - gap
        return True, suggested_limit

    return False, 0.0


def trim_far_side_text_post_autocrop(
    clip: Any,
    text_lines: List[Tuple[Any, float, str]],
    direction: str,
    *,
    typical_line_h: Optional[float] = None,
    scan_lines: int = 3,
    min_width_ratio: float = 0.30,
    min_text_len: int = 15,
    font_min: float = 7.0,
    font_max: float = 16.0,
    gap: float = 6.0,
) -> Tuple[Any, bool]:
    """
    Phase D 后的轻量去正文后处理。

    在 autocrop 完成后，扫描远端边缘附近的正文行，如果检测到明确的正文，
    向内推 y0/y1（只动 y，不动 x）。

    Args:
        clip: 当前裁剪区域
        text_lines: 文本行列表
        direction: 方向 ('above' | 'below')
        typical_line_h: 典型行高
        scan_lines: 扫描行数
        min_width_ratio: 正文最小宽度比例
        min_text_len: 正文最小长度
        font_min/font_max: 正文字号范围
        gap: 裁剪后的间隙

    Returns:
        (new_clip, was_trimmed): 新的裁剪区域和是否进行了裁剪
    """
    if fitz is None or clip.height <= 1 or clip.width <= 1:
        return clip, False

    if typical_line_h and typical_line_h > 0:
        scan_range = typical_line_h * scan_lines
    else:
        scan_range = 45.0

    far_is_top = (direction == 'above')
    text_to_trim: List[Any] = []

    for (lb, fs, text) in text_lines:
        txt = text.strip()
        if not txt:
            continue

        inter = lb & clip
        if inter.width <= 0 or inter.height <= 0:
            continue

        width_ratio = inter.width / max(1.0, clip.width)
        if width_ratio < min_width_ratio:
            continue
        if len(txt) < min_text_len:
            continue
        if not (font_min <= fs <= font_max):
            continue

        if far_is_top:
            dist = lb.y0 - clip.y0
            if dist < scan_range:
                text_to_trim.append(lb)
        else:
            dist = clip.y1 - lb.y1
            if dist < scan_range:
                text_to_trim.append(lb)

    if not text_to_trim:
        return clip, False

    new_clip = fitz.Rect(clip)
    if far_is_top:
        max_y1 = max(lb.y1 for lb in text_to_trim)
        new_y0 = max_y1 + gap
        if new_y0 < clip.y0 + 0.5 * clip.height:
            new_clip = fitz.Rect(clip.x0, new_y0, clip.x1, clip.y1)
    else:
        min_y0 = min(lb.y0 for lb in text_to_trim)
        new_y1 = min_y0 - gap
        if new_y1 > clip.y0 + 0.5 * clip.height:
            new_clip = fitz.Rect(clip.x0, clip.y0, clip.x1, new_y1)

    was_trimmed = (new_clip != clip)
    return new_clip, was_trimmed


def trim_far_side_text_iterative(
    clip: Any,
    text_lines: List[Tuple[Any, float, str]],
    direction: str,
    *,
    typical_line_h: Optional[float] = None,
    max_passes: int = 8,
) -> Tuple[Any, bool]:
    """有限迭代清理远端连续正文，遇到非正文内容后停止。"""
    current = clip
    changed = False

    for _ in range(max_passes):
        next_clip, was_trimmed = trim_far_side_text_post_autocrop(
            current,
            text_lines,
            direction,
            typical_line_h=typical_line_h,
            scan_lines=3,
        )
        if not was_trimmed or next_clip == current:
            break
        current = next_clip
        changed = True

    return current, changed


def refine_clip_to_table_band(
    clip: Any,
    caption_rect: Any,
    text_lines: List[Tuple[Any, float, str]],
    direction: str,
    *,
    typical_line_h: Optional[float] = None,
    min_cells_per_row: int = 2,
    pad: float = 6.0,
) -> Tuple[Any, bool]:
    """从图注一侧识别连续多单元格行带，并收紧表格远端边界。"""
    if fitz is None or clip.width <= 1 or clip.height <= 1:
        return clip, False

    row_tolerance = max(2.0, (typical_line_h or 10.0) * 0.45)
    candidates: List[Tuple[Any, str]] = []
    for line_rect, _font_size, text in text_lines:
        txt = text.strip()
        inter = line_rect & clip
        if not txt or inter.width <= 0 or inter.height <= 0:
            continue
        candidates.append((inter, txt))

    if not candidates:
        return clip, False

    candidates.sort(key=lambda item: (item[0].y0, item[0].x0))
    rows: List[List[Tuple[Any, str]]] = []
    row_centers: List[float] = []
    for item in candidates:
        center = (item[0].y0 + item[0].y1) / 2.0
        if rows and abs(center - row_centers[-1]) <= row_tolerance:
            rows[-1].append(item)
            row_centers[-1] = sum((r.y0 + r.y1) / 2.0 for r, _ in rows[-1]) / len(rows[-1])
        else:
            rows.append([item])
            row_centers.append(center)

    def classify_table_row(row: List[Tuple[Any, str]]) -> str:
        distinct_cells = []
        for rect, text in sorted(row, key=lambda item: item[0].x0):
            if distinct_cells and rect.x0 <= distinct_cells[-1][0].x1 + 2.0:
                previous_rect, previous_text = distinct_cells[-1]
                distinct_cells[-1] = (previous_rect | rect, previous_text + " " + text)
            else:
                distinct_cells.append((rect, text))
        if len(distinct_cells) > min_cells_per_row:
            return "strong"
        row_rect = distinct_cells[0][0]
        row_text = distinct_cells[0][1]
        for rect, _text in distinct_cells[1:]:
            row_rect = row_rect | rect
            row_text += " " + _text
        if len(distinct_cells) == min_cells_per_row:
            if row_rect.width >= clip.width * 0.55:
                return "strong"
            if row_rect.width >= clip.width * 0.20 and len(row_text) <= 160:
                return "weak"
            return "none"
        if len(distinct_cells) == 1:
            word_count = len(row_text.split())
            sentence_like = (
                len(row_text) > 100
                or word_count > 18
                or (len(row_text) > 70 and row_text.rstrip().endswith((".", "。", "!", "?", "；", ";")))
            )
            if (
                not sentence_like
                and clip.width * 0.12 <= row_rect.width <= clip.width * 0.92
            ):
                return "weak"
        return "none"

    row_kinds = [classify_table_row(row) for row in rows]
    use_weak_rows = not any(kind == "strong" for kind in row_kinds)
    if direction == "above":
        ordered_indices = list(range(len(rows) - 1, -1, -1))
    else:
        ordered_indices = list(range(len(rows)))

    def summarize_row(idx: int) -> Tuple[Any, str]:
        row_rect = None
        row_text = ""
        for rect, text in sorted(rows[idx], key=lambda item: item[0].x0):
            row_rect = fitz.Rect(rect) if row_rect is None else row_rect | rect
            row_text += " " + text
        return row_rect, row_text.strip()

    row_summaries = [summarize_row(idx) for idx in range(len(rows))]
    max_bridge_gap = max(80.0, (typical_line_h or 10.0) * 7.0)

    def has_future_table_evidence(position: int) -> bool:
        current_idx = ordered_indices[position]
        current_rect, _current_text = row_summaries[current_idx]
        if current_rect is None:
            return False
        for future_position in range(position + 1, min(len(ordered_indices), position + 9)):
            future_idx = ordered_indices[future_position]
            future_rect, future_text = row_summaries[future_idx]
            if future_rect is None:
                continue
            if direction == "above":
                distance = current_rect.y0 - future_rect.y1
            else:
                distance = future_rect.y0 - current_rect.y1
            if distance > max_bridge_gap:
                break
            if (
                row_kinds[future_idx] == "strong"
                or (
                    row_kinds[future_idx] == "weak"
                    and bool(re.search(r"\d", future_text))
                    and future_rect.width <= clip.width * 0.70
                )
            ):
                return True
        return False

    selected: List[int] = []
    started = False
    sparse_rows = 0
    strong_rows = 0
    weak_rows = 0
    max_row_gap = max(18.0, (typical_line_h or 10.0) * 2.25)
    for position, idx in enumerate(ordered_indices):
        if started and selected:
            previous_idx = selected[-1]
            if direction == "above":
                gap = min(r.y0 for r, _ in rows[previous_idx]) - max(r.y1 for r, _ in rows[idx])
            else:
                gap = min(r.y0 for r, _ in rows[idx]) - max(r.y1 for r, _ in rows[previous_idx])
            if gap > max_row_gap:
                break

        row_rect, row_text = row_summaries[idx]
        is_numbered_section = bool(re.match(r"^\s*\d+(?:\.\d+)+\s+\S", row_text))
        has_numeric_evidence = bool(re.search(r"\d", row_text))
        weak_has_table_evidence = (
            row_kinds[idx] == "weak"
            and not is_numbered_section
            and (
                use_weak_rows
                or (
                    has_numeric_evidence
                    and row_rect is not None
                    and row_rect.width <= clip.width * 0.70
                )
                or has_future_table_evidence(position)
            )
        )
        if row_kinds[idx] == "strong" or weak_has_table_evidence:
            selected.append(idx)
            started = True
            sparse_rows = 0
            if row_kinds[idx] == "strong":
                strong_rows += 1
            else:
                weak_rows += 1
            continue
        if started:
            is_sparse_label = (
                row_rect is not None
                and row_rect.width < clip.width * 0.35
                and len(row_text) <= 30
                and not is_numbered_section
                and sparse_rows < 2
                and has_future_table_evidence(position)
            )
            if is_sparse_label:
                selected.append(idx)
                sparse_rows += 1
                continue
            break

    if len(selected) < 2 or (strong_rows == 0 and weak_rows < 3):
        return clip, False

    table_rect = None
    for idx in selected:
        for rect, _text in rows[idx]:
            table_rect = fitz.Rect(rect) if table_rect is None else table_rect | rect

    if table_rect is None:
        return clip, False

    new_clip = fitz.Rect(clip)
    if direction == "above":
        new_y0 = max(clip.y0, table_rect.y0 - pad)
        if new_y0 >= caption_rect.y0 or new_y0 <= clip.y0 + 0.5:
            return clip, False
        new_clip = fitz.Rect(clip.x0, new_y0, clip.x1, clip.y1)
    elif direction == "below":
        new_y1 = min(clip.y1, table_rect.y1 + pad)
        if new_y1 <= caption_rect.y1 or new_y1 >= clip.y1 - 0.5:
            return clip, False
        new_clip = fitz.Rect(clip.x0, clip.y0, clip.x1, new_y1)

    return new_clip, new_clip != clip


def restore_table_clip_width(
    clip: Any,
    base_clip: Any,
    *,
    table_band_changed: bool,
    min_width_ratio: float = 0.40,
) -> Any:
    """可靠表格行带成立时，恢复被对象裁切误缩成局部列的 X 范围。"""
    if fitz is None or not table_band_changed or base_clip.width <= 1:
        return clip
    if clip.width >= base_clip.width * min_width_ratio:
        return clip
    return fitz.Rect(base_clip.x0, clip.y0, base_clip.x1, clip.y1)


# ============================================================================
# 动态验收阈值
# ============================================================================

def adaptive_acceptance_thresholds(
    base_height: float,
    *,
    is_table: bool = False,
    far_cov: float = 0.0,
) -> "AcceptanceThresholds":
    """
    根据基线高度和远侧覆盖率动态计算验收阈值。

    策略：
    - 大图（>400pt）：允许更激进的精裁
    - 中等图（200-400pt）：使用默认阈值
    - 小图（<200pt）：更保守
    - 远侧文字覆盖率越高，允许缩小得越多

    Args:
        base_height: 基线窗口高度（pt）
        is_table: 是否为表格
        far_cov: 远侧文字覆盖率（0.0-1.0）

    Returns:
        AcceptanceThresholds 对象
    """
    from .models import AcceptanceThresholds as AT

    # 基础阈值（根据尺寸分层）
    if base_height > 400:
        base_h, base_a = (0.50, 0.45) if is_table else (0.55, 0.50)
        base_ink, base_cov, base_text = 0.85, 0.80, 0.70
        desc = "large"
    elif base_height > 200:
        base_h, base_a = (0.50, 0.45) if is_table else (0.60, 0.55)
        base_ink, base_cov, base_text = 0.90, 0.85, 0.75
        desc = "medium"
    else:
        base_h, base_a = (0.65, 0.60) if is_table else (0.70, 0.65)
        base_ink, base_cov, base_text = 0.92, 0.88, 0.80
        desc = "small"

    # 根据远侧覆盖率进一步调整
    if far_cov >= 0.60:
        base_h = min(base_h, 0.35)
        base_a = min(base_a, 0.25)
        base_ink = min(base_ink, 0.70)
        base_cov = min(base_cov, 0.70)
        base_text = min(base_text, 0.55)
        desc += "+high_far_cov"
    elif far_cov >= 0.30:
        base_h = min(base_h, 0.45)
        base_a = min(base_a, 0.35)
        base_ink = min(base_ink, 0.75)
        base_cov = min(base_cov, 0.75)
        base_text = min(base_text, 0.60)
        desc += "+med_far_cov"
    elif far_cov >= 0.18:
        base_h = min(base_h, 0.50)
        base_a = min(base_a, 0.40)
        base_ink = min(base_ink, 0.80)
        base_cov = min(base_cov, 0.80)
        base_text = min(base_text, 0.65)
        desc += "+low_far_cov"

    return AT(
        height_ratio=base_h,
        area_ratio=base_a,
        object_coverage=base_cov,
        ink_density=base_ink,
    )


# ============================================================================
# 正文污染检测
# ============================================================================

def detect_text_pollution(
    clip: Any,
    text_lines: List[Tuple[Any, float, str]],
    *,
    max_wide_lines: int = 5,
    max_wide_ratio: float = 0.60,
    width_ratio: float = 0.70,
    min_text_len: int = 30,
    font_min: float = 7.0,
    font_max: float = 16.0,
) -> Tuple[bool, str]:
    """
    检测裁剪区域是否主要由正文段落构成。

    如果返回 True，上层应拒绝当前候选，而不是退回 baseline 后继续保存。
    baseline 通常仍以同一个错误 caption 为锚点，会把误截结果写入 index。
    """
    if fitz is None or clip.width <= 1 or clip.height <= 1:
        return False, ""

    text_in_clip = 0
    wide_text_in_clip = 0

    for (line_rect, font_size, text) in text_lines:
        txt = text.strip()
        if len(txt) < min_text_len:
            continue
        if not (font_min <= font_size <= font_max):
            continue

        inter = line_rect & clip
        if inter.width <= 0 or inter.height <= 0:
            continue

        text_in_clip += 1
        if (inter.width / max(1.0, clip.width)) > width_ratio:
            wide_text_in_clip += 1

    if wide_text_in_clip > max_wide_lines:
        pollution_ratio = wide_text_in_clip / max(1, text_in_clip)
        if pollution_ratio > max_wide_ratio:
            return True, f"text_pollution={wide_text_in_clip}/{text_in_clip} wide_lines"

    return False, ""


def looks_like_table_text(
    clip: Any,
    text_lines: List[Tuple[Any, float, str]],
    *,
    min_lines: int = 8,
    min_short_ratio: float = 0.65,
    max_wide_long_ratio: float = 0.25,
    short_text_len: int = 40,
    wide_ratio: float = 0.55,
) -> bool:
    """判断候选框是否以短单元格文本为主，而不是连续正文段落。"""
    if fitz is None or clip.width <= 1 or clip.height <= 1:
        return False

    lines_in_clip: List[Tuple[Any, str]] = []
    for line_rect, _font_size, text in text_lines:
        txt = text.strip()
        if not txt:
            continue
        inter = line_rect & clip
        if inter.width <= 0 or inter.height <= 0:
            continue
        lines_in_clip.append((inter, txt))

    if len(lines_in_clip) < 3:
        return False

    short_like = 0
    wide_long = 0
    for line_rect, text in lines_in_clip:
        if len(text) <= short_text_len or line_rect.width < clip.width * wide_ratio:
            short_like += 1
        if len(text) > short_text_len and line_rect.width >= clip.width * wide_ratio:
            wide_long += 1

    short_ratio = short_like / len(lines_in_clip)
    wide_long_ratio = wide_long / len(lines_in_clip)
    if len(lines_in_clip) < min_lines:
        compact_rows = sum(
            1
            for line_rect, text in lines_in_clip
            if (
                len(text) <= 100
                and len(text.split()) <= 18
                and line_rect.width <= clip.width * 0.92
                and not text.rstrip().endswith((".", "。", "!", "?", "；", ";"))
            )
        )
        return compact_rows >= 3
    return short_ratio >= min_short_ratio and wide_long_ratio <= max_wide_long_ratio


# ============================================================================
# 同页相邻 caption 边界限制
# ============================================================================

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
            if vertical_gap <= 60.0 and _looks_like_content_block(other):
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
            if _rect(item).y0 > clip.y0 and _rect(item).y0 < clip.y1
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
            if _rect(item).y1 > clip.y0 and _rect(item).y1 < clip.y1
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


# ============================================================================
# X 方向列感知裁剪
# ============================================================================

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

    # 策略1：版式模型双栏检测
    if layout_model is not None and layout_model.num_columns >= 2:
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


# ============================================================================
# 边缘对齐
# ============================================================================

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


# ============================================================================
# 文本裁切辅助函数
# ============================================================================

def is_caption_text(
    lines: List[Any],
    caption_rect: Any,
    tolerance: float = 10.0
) -> bool:
    """
    检查给定的文本行是否与图注 caption_rect 重叠或非常接近。

    用于防止"两行检测"误裁图注本身（尤其是长标题换行的情况）。

    Args:
        lines: 待检查的文本行边界框列表 (fitz.Rect)
        caption_rect: 图注的边界框
        tolerance: 容差（pt），行与图注距离小于此值视为图注的一部分

    Returns:
        True 如果任何一行被判定为属于图注
    """
    if fitz is None:
        return False

    for line_rect in lines:
        # 检查是否与图注重叠
        if line_rect.intersects(caption_rect):
            return True
        # 检查垂直距离是否在容差范围内
        # 图注可能在行的上方或下方
        v_dist_above = abs(line_rect.y0 - caption_rect.y1)  # 行在图注下方
        v_dist_below = abs(caption_rect.y0 - line_rect.y1)  # 行在图注上方
        if min(v_dist_above, v_dist_below) < tolerance:
            # 还需检查水平方向是否有重叠
            h_overlap = min(line_rect.x1, caption_rect.x1) - max(line_rect.x0, caption_rect.x0)
            if h_overlap > 0:
                return True
    return False


def detect_exact_n_lines_of_text(
    clip_rect: Any,
    text_lines: List[Tuple[Any, float, str]],
    typical_line_h: float,
    n: int = 2,
    tolerance: float = 0.35
) -> Tuple[bool, List[Any]]:
    """
    检测 clip_rect 中是否恰好包含 n 行文字。

    Args:
        clip_rect: 待检测的矩形区域
        text_lines: 文本行列表 (bbox, font_size, text)
        typical_line_h: 典型行高
        n: 期望的行数
        tolerance: 容差（相对于期望值的比例）

    Returns:
        (is_exact_n_lines, matched_line_bboxes)
    """
    if fitz is None:
        return False, []

    # 筛选在区域内的文本行
    text_in_region = []
    for bbox, size_est, text in text_lines:
        if bbox.intersects(clip_rect) and bbox.height < typical_line_h * 1.5:
            text_in_region.append((bbox, size_est, text))

    if not text_in_region:
        return False, []

    # 按 y 坐标排序
    text_in_region.sort(key=lambda x: x[0].y0)

    # 计算实际行数（根据 y 间距判断是否为同一行）
    actual_lines: List[Any] = []
    current_line_bboxes = [text_in_region[0][0]]

    for i in range(1, len(text_in_region)):
        prev_bbox = text_in_region[i-1][0]
        curr_bbox = text_in_region[i][0]
        gap = curr_bbox.y0 - prev_bbox.y1

        if gap < typical_line_h * 0.8:  # 认为是同一行
            current_line_bboxes.append(curr_bbox)
        else:  # 新的一行
            # 合并当前行的所有 bbox
            merged_bbox = current_line_bboxes[0]
            for bbox in current_line_bboxes[1:]:
                merged_bbox = merged_bbox | bbox
            actual_lines.append(merged_bbox)
            current_line_bboxes = [curr_bbox]

    # 添加最后一行
    if current_line_bboxes:
        merged_bbox = current_line_bboxes[0]
        for bbox in current_line_bboxes[1:]:
            merged_bbox = merged_bbox | bbox
        actual_lines.append(merged_bbox)

    # 检查行数是否匹配
    if abs(len(actual_lines) - n) > 1:
        return False, []

    # 检查总高度是否约等于 n 倍行高
    if len(actual_lines) > 0:
        total_height = actual_lines[-1].y1 - actual_lines[0].y0
        expected_height = n * typical_line_h

        if abs(total_height - expected_height) / expected_height > tolerance:
            return False, []

    return True, actual_lines


# ============================================================================
# Phase A: 基础文本裁切
# ============================================================================

def trim_clip_head_by_text(
    clip: Any,
    page_rect: Any,
    caption_rect: Any,
    direction: str,
    text_lines: List[Tuple[Any, float, str]],
    *,
    width_ratio: float = 0.5,
    font_min: float = 7.0,
    font_max: float = 16.0,
    gap: float = 6.0,
    adjacent_th: float = 24.0,
) -> Any:
    """
    Phase A 基础版：裁切靠近图注侧的段落类文本。

    只调整靠近图注的边缘：
    - 'above': 近端是 BOTTOM (y1)
    - 'below': 近端是 TOP (y0)

    Args:
        clip: 当前裁剪区域 (fitz.Rect)
        page_rect: 页面边界 (fitz.Rect)
        caption_rect: 图注边界 (fitz.Rect)
        direction: 方向 ('above' | 'below')
        text_lines: 文本行列表 [(rect, font_size, text), ...]
        width_ratio: 段落判定宽度比（默认 0.5）
        font_min: 正文最小字号
        font_max: 正文最大字号
        gap: 裁切后保留的间隙
        adjacent_th: 相邻判定阈值（pt）

    Returns:
        裁切后的 clip (fitz.Rect)
    """
    if fitz is None:
        return clip

    if clip.height <= 1 or clip.width <= 1:
        return clip

    # 哪个边缘靠近图注？above: 近端底部; below: 近端顶部
    near_is_top = (direction == 'below')
    frac = 0.35
    new_top, new_bottom = clip.y0, clip.y1

    for (lb, size_est, text) in text_lines:
        if not text.strip():
            continue
        # 仅考虑水平重叠且在 clip 头部区域内的行
        inter = lb & clip
        if inter.width <= 0 or inter.height <= 0:
            continue
        # 段落启发式过滤
        width_ok = (inter.width / max(1.0, clip.width)) >= width_ratio
        size_ok = (font_min <= size_est <= font_max)
        if not (width_ok and size_ok):
            continue
        # 近端判定：'below' 只考虑顶部区域，'above' 只考虑底部区域
        if near_is_top:
            top_thresh = clip.y0 + max(40.0, frac * clip.height)
            if lb.y1 > top_thresh:
                continue
        else:
            bot_thresh = clip.y1 - max(40.0, frac * clip.height)
            if lb.y0 < bot_thresh:
                continue
        # 邻接图注判定：靠近图注的文本很可能是正文
        near_caption = False
        if near_is_top:
            dist = caption_rect.y0 - lb.y1
            if 0 <= dist <= adjacent_th:
                near_caption = True
        else:
            dist = lb.y0 - caption_rect.y1
            if 0 <= dist <= adjacent_th:
                near_caption = True
        if not near_caption:
            # 即使不相邻，如果行紧贴页边距，也考虑裁切
            if abs(lb.x0 - page_rect.x0) < 6.5 or abs(page_rect.x1 - lb.x1) < 6.5:
                near_caption = True
        if not near_caption:
            continue

        if near_is_top:
            new_top = max(new_top, lb.y1 + gap)
        else:
            new_bottom = min(new_bottom, lb.y0 - gap)

    # 强制最小高度
    min_h = 40.0
    max_trim_ratio = 0.25
    base_h = clip.height
    if near_is_top and new_top > clip.y0:
        new_top = min(new_top, clip.y0 + max(min_h, max_trim_ratio * base_h))
        if new_bottom - new_top >= min_h:
            clip = fitz.Rect(clip.x0, new_top, clip.x1, clip.y1)
    if (not near_is_top) and new_bottom < clip.y1:
        new_bottom = max(new_bottom, clip.y1 - max(min_h, max_trim_ratio * base_h))
        if new_bottom - new_top >= min_h:
            clip = fitz.Rect(clip.x0, clip.y0, clip.x1, new_bottom)
    # 限制在页面范围内
    clip = fitz.Rect(clip.x0, max(page_rect.y0, clip.y0), clip.x1, min(page_rect.y1, clip.y1))
    return clip


# ============================================================================
# Phase A/B/C: 增强文本裁切
# ============================================================================

def trim_clip_head_by_text_v2(
    clip: Any,
    page_rect: Any,
    caption_rect: Any,
    direction: str,
    text_lines: List[Tuple[Any, float, str]],
    *,
    width_ratio: float = 0.5,
    font_min: float = 7.0,
    font_max: float = 16.0,
    gap: float = 6.0,
    adjacent_th: float = 24.0,
    far_text_th: float = 300.0,
    far_text_para_min_ratio: float = 0.30,
    far_text_trim_mode: str = "aggressive",
    # Phase C tuners (far-side paragraphs)
    far_side_min_dist: float = 50.0,
    far_side_para_min_ratio: float = 0.12,
    # Adaptive line height
    typical_line_h: Optional[float] = None,
    # 表格保护 - 跳过 adjacent sweep
    skip_adjacent_sweep: bool = False,
    # Debug
    debug: bool = False,
) -> Any:
    """
    Phase A/B/C 完整版：增强双阈值文本裁切。

    Phase A: 裁切相邻文本 (<adjacent_th, 默认 24pt)
    Phase B: 检测并移除远距离文本块 (adjacent_th ~ far_text_th)
    Phase C: 检测并移除远端大段落

    Args:
        clip: 当前裁剪区域
        page_rect: 页面边界
        caption_rect: 图注边界
        direction: 方向 ('above' | 'below')
        text_lines: 文本行列表 [(rect, font_size, text), ...]
        width_ratio: 段落判定宽度比
        font_min/font_max: 正文字号范围
        gap: 裁切后保留的间隙
        adjacent_th: 相邻判定阈值
        far_text_th: 远距离文本检测最大距离
        far_text_para_min_ratio: 触发远距离裁切的最小段落覆盖率
        far_text_trim_mode: 'aggressive' 或 'conservative'
        far_side_min_dist: 远端段落最小距离
        far_side_para_min_ratio: 远端段落最小覆盖率
        typical_line_h: 典型行高（用于自适应检测）
        skip_adjacent_sweep: 跳过相邻扫描（表格保护）
        debug: 调试输出

    Returns:
        裁切后的 clip
    """
    if fitz is None:
        return clip

    if clip.height <= 1 or clip.width <= 1:
        return clip

    # 保存原始 clip 用于后续检测
    original_clip = fitz.Rect(clip)

    # === Phase A: 应用基础相邻文本裁切 ===
    clip = trim_clip_head_by_text(
        clip, page_rect, caption_rect, direction, text_lines,
        width_ratio=width_ratio, font_min=font_min, font_max=font_max,
        gap=gap, adjacent_th=adjacent_th
    )

    # === Phase A+: 增强"精确两行"检测 ===
    if typical_line_h is not None and typical_line_h > 0:
        near_is_top_a = (direction == 'below')
        # 定义近端检测条带
        if near_is_top_a:
            check_strip = fitz.Rect(
                original_clip.x0,
                original_clip.y0,
                original_clip.x1,
                min(original_clip.y1, original_clip.y0 + 3.5 * typical_line_h)
            )
        else:
            check_strip = fitz.Rect(
                original_clip.x0,
                max(original_clip.y0, original_clip.y1 - 3.5 * typical_line_h),
                original_clip.x1,
                original_clip.y1
            )

        # 检测是否恰好有 2 行文字
        is_exact_two, matched_lines = detect_exact_n_lines_of_text(
            check_strip, text_lines, typical_line_h, n=2, tolerance=0.35
        )

        if is_exact_two and len(matched_lines) == 2:
            # 检查匹配到的文字是否属于图注本身
            if is_caption_text(matched_lines, caption_rect, tolerance=10.0):
                pass  # 跳过裁切，保留图注
            else:
                # 使用更激进的裁切
                if near_is_top_a:
                    new_y0 = matched_lines[-1].y1 + gap
                    clip = fitz.Rect(clip.x0, max(clip.y0, new_y0), clip.x1, clip.y1)
                else:
                    new_y1 = matched_lines[0].y0 - gap
                    clip = fitz.Rect(clip.x0, clip.y0, clip.x1, min(clip.y1, new_y1))

    # === Phase B: 检测并裁切远距离文本 ===
    near_is_top = (direction == 'below')

    # 收集远距离段落行（使用原始 clip）
    far_para_lines: List[Tuple[Any, float, str]] = []
    for (lb, size_est, text) in text_lines:
        if not text.strip():
            continue
        inter = lb & original_clip
        if inter.width <= 0 or inter.height <= 0:
            continue
        width_ok = (inter.width / max(1.0, original_clip.width)) >= width_ratio
        size_ok = (font_min <= size_est <= font_max)
        if not (width_ok and size_ok):
            continue

        # 到图注的距离（远距离范围：adjacent_th ~ far_text_th）
        if near_is_top:
            dist = caption_rect.y0 - lb.y1
        else:
            dist = lb.y0 - caption_rect.y1

        if adjacent_th < dist <= far_text_th:
            if near_is_top:
                top_thresh = original_clip.y0 + max(40.0, 0.5 * original_clip.height)
                if lb.y1 <= top_thresh:
                    far_para_lines.append((lb, size_est, text))
            else:
                bot_thresh = original_clip.y1 - max(40.0, 0.5 * original_clip.height)
                if lb.y0 >= bot_thresh:
                    far_para_lines.append((lb, size_est, text))

    # 计算近端段落覆盖率
    para_coverage_ratio = 0.0
    if far_para_lines:
        if near_is_top:
            region_start = original_clip.y0
            region_end = original_clip.y0 + max(40.0, 0.5 * original_clip.height)
            region_h = max(1.0, region_end - region_start)
            para_h = sum(lb.height for (lb, _, _) in far_para_lines)
            para_coverage_ratio = para_h / region_h
        else:
            region_start = original_clip.y1 - max(40.0, 0.5 * original_clip.height)
            region_end = original_clip.y1
            region_h = max(1.0, region_end - region_start)
            para_h = sum(lb.height for (lb, _, _) in far_para_lines)
            para_coverage_ratio = para_h / region_h

    # === Phase C: 检测并裁切远端大段落 ===
    far_is_top = not near_is_top
    far_side_para_lines: List[Tuple[Any, float, str]] = []

    for (lb, size_est, text) in text_lines:
        if not text.strip():
            continue
        inter = lb & original_clip
        if inter.width <= 0 or inter.height <= 0:
            continue
        width_ok = (inter.width / max(1.0, original_clip.width)) >= width_ratio
        size_ok = (font_min <= size_est <= font_max)
        if not (width_ok and size_ok):
            continue

        if far_is_top:
            dist = caption_rect.y0 - lb.y1
        else:
            dist = lb.y0 - caption_rect.y1

        if dist > far_side_min_dist:
            if far_is_top:
                mid_point = original_clip.y0 + 0.5 * original_clip.height
                if lb.y0 < mid_point:
                    far_side_para_lines.append((lb, size_est, text))
            else:
                mid_point = original_clip.y0 + 0.5 * original_clip.height
                if lb.y1 > mid_point:
                    far_side_para_lines.append((lb, size_est, text))

    # 处理远端段落
    if far_side_para_lines:
        far_side_para_lines.sort(key=lambda x: x[0].y0)
        if far_is_top:
            far_side_region_start = original_clip.y0
            far_side_region_end = original_clip.y0 + 0.5 * original_clip.height
        else:
            far_side_region_start = original_clip.y0 + 0.5 * original_clip.height
            far_side_region_end = original_clip.y1

        far_side_region_height = max(1.0, far_side_region_end - far_side_region_start)
        far_side_total_para_height = sum(lb.height for (lb, _, _) in far_side_para_lines)
        far_side_para_coverage = far_side_total_para_height / far_side_region_height

        if far_side_para_coverage >= far_side_para_min_ratio:
            if debug:
                print(f"[DBG] Far-side trim: coverage={far_side_para_coverage:.3f} th={far_side_para_min_ratio}")

            trim_ratio = 0.65 if far_side_para_coverage >= 0.15 else 0.50

            if far_is_top:
                last_para_y1 = max(lb.y1 for (lb, _, _) in far_side_para_lines)
                new_y0 = last_para_y1 + gap
                max_trim = original_clip.y0 + trim_ratio * original_clip.height
                clip = fitz.Rect(clip.x0, min(new_y0, max_trim), clip.x1, clip.y1)

                # 邻近短行清扫
                if not skip_adjacent_sweep:
                    adjacent_zone = max(40.0, 4.0 * (typical_line_h or 12.0))
                    for (lb, size_est, txt) in text_lines:
                        if not txt.strip() or len(txt.strip()) < 3:
                            continue
                        inter = lb & clip
                        if inter.width <= 0 or inter.height <= 0:
                            continue
                        if lb.y0 >= clip.y0 and lb.y0 < clip.y0 + adjacent_zone:
                            w_ok = (inter.width / max(1.0, clip.width)) >= 0.05
                            s_ok = (font_min <= size_est <= font_max)
                            if w_ok and s_ok:
                                candidate_y0 = lb.y1 + gap
                                if candidate_y0 > clip.y0 and candidate_y0 <= max_trim:
                                    clip = fitz.Rect(clip.x0, candidate_y0, clip.x1, clip.y1)
            else:
                first_para_y0 = min(lb.y0 for (lb, _, _) in far_side_para_lines)
                new_y1 = first_para_y0 - gap
                min_trim = original_clip.y1 - trim_ratio * original_clip.height
                clip = fitz.Rect(clip.x0, clip.y0, clip.x1, max(new_y1, min_trim))

                if not skip_adjacent_sweep:
                    adjacent_zone = max(40.0, 4.0 * (typical_line_h or 12.0))
                    for (lb, size_est, txt) in text_lines:
                        if not txt.strip() or len(txt.strip()) < 3:
                            continue
                        inter = lb & clip
                        if inter.width <= 0 or inter.height <= 0:
                            continue
                        if lb.y1 <= clip.y1 and lb.y1 > clip.y1 - adjacent_zone:
                            w_ok = (inter.width / max(1.0, clip.width)) >= 0.05
                            s_ok = (font_min <= size_est <= font_max)
                            if w_ok and s_ok:
                                candidate_y1 = lb.y0 - gap
                                if candidate_y1 < clip.y1 and candidate_y1 >= min_trim:
                                    clip = fitz.Rect(clip.x0, clip.y0, clip.x1, candidate_y1)

            # 迭代扫描短行文字
            if not skip_adjacent_sweep:
                max_iterations = 5
                for _iter in range(max_iterations):
                    _extra_short_lines: List[Any] = []
                    for (lb, size_est, text) in text_lines:
                        txt = text.strip()
                        if not txt or len(txt) < 5:
                            continue
                        inter = lb & clip
                        if inter.width <= 0 or inter.height <= 0:
                            continue
                        if far_is_top:
                            far_region_end = clip.y0 + 0.5 * clip.height
                            in_far = (lb.y0 < far_region_end)
                        else:
                            far_region_start = clip.y1 - 0.5 * clip.height
                            in_far = (lb.y1 > far_region_start)
                        if not in_far:
                            continue
                        w_ratio_extra = inter.width / max(1.0, clip.width)
                        if w_ratio_extra < 0.08:
                            continue
                        if not (font_min <= size_est <= font_max):
                            continue
                        _extra_short_lines.append(lb)

                    if not _extra_short_lines:
                        break

                    if far_is_top:
                        new_y0 = max(lb.y1 for lb in _extra_short_lines) + gap
                        max_trim2 = original_clip.y0 + trim_ratio * original_clip.height
                        if new_y0 > clip.y0 + 1e-3:
                            clip = fitz.Rect(clip.x0, min(new_y0, max_trim2), clip.x1, clip.y1)
                        else:
                            break
                    else:
                        new_y1 = min(lb.y0 for lb in _extra_short_lines) - gap
                        min_trim2 = original_clip.y1 - trim_ratio * original_clip.height
                        if new_y1 < clip.y1 - 1e-3:
                            clip = fitz.Rect(clip.x0, clip.y0, clip.x1, max(new_y1, min_trim2))
                        else:
                            break
        else:
            # Fallback: 处理散落的远端文字
            fallback_lines: List[Any] = []
            for (lb, size_est, text) in text_lines:
                if not text.strip():
                    continue
                inter = lb & original_clip
                if inter.width <= 0 or inter.height <= 0:
                    continue
                txt = text.strip()
                has_bullet = txt.startswith('•') or txt.startswith('·') or txt.startswith('- ') or txt.startswith('○') or txt.startswith('–')
                is_very_long_line = len(txt) > 60
                is_long_line = len(txt) > 30

                if has_bullet or is_very_long_line:
                    pass
                else:
                    width_ok_small = (inter.width / max(1.0, original_clip.width)) >= max(0.10, width_ratio * 0.3)
                    size_ok = (font_min <= size_est <= font_max)
                    if not (width_ok_small and size_ok):
                        continue

                if far_is_top:
                    dist = caption_rect.y0 - lb.y1
                    in_far_region = (lb.y0 < original_clip.y0 + 0.50 * original_clip.height)
                else:
                    dist = lb.y0 - caption_rect.y1
                    in_far_region = (lb.y1 > original_clip.y0 + 0.50 * original_clip.height)

                should_trim = False
                if has_bullet:
                    should_trim = (dist > 15.0 and in_far_region)
                elif is_very_long_line:
                    should_trim = (dist > 18.0 and in_far_region)
                elif is_long_line:
                    should_trim = (dist > 20.0 and in_far_region)
                else:
                    should_trim = (dist > max(25.0, far_side_min_dist * 0.7) and in_far_region)

                if should_trim:
                    fallback_lines.append(lb)

            if fallback_lines:
                if far_is_top:
                    new_y0 = max(lb.y1 for lb in fallback_lines) + gap
                    max_trim = original_clip.y0 + 0.5 * original_clip.height
                    clip = fitz.Rect(clip.x0, min(new_y0, max_trim), clip.x1, clip.y1)
                else:
                    new_y1 = min(lb.y0 for lb in fallback_lines) - gap
                    min_trim = original_clip.y1 - 0.5 * original_clip.height
                    clip = fitz.Rect(clip.x0, clip.y0, clip.x1, max(new_y1, min_trim))

    # 处理 Phase B（近端远距离文本）
    if far_para_lines and para_coverage_ratio >= far_text_para_min_ratio:
        if far_text_trim_mode == "aggressive":
            if near_is_top:
                last_para_y1 = max(lb.y1 for (lb, _, _) in far_para_lines)
                new_y0 = last_para_y1 + gap
                max_trim = original_clip.y0 + 0.6 * original_clip.height
                clip = fitz.Rect(clip.x0, min(new_y0, max_trim), clip.x1, clip.y1)
            else:
                first_para_y0 = min(lb.y0 for (lb, _, _) in far_para_lines)
                new_y1 = first_para_y0 - gap
                min_trim = original_clip.y1 - 0.6 * original_clip.height
                clip = fitz.Rect(clip.x0, clip.y0, clip.x1, max(new_y1, min_trim))
        elif far_text_trim_mode == "conservative":
            is_continuous = True
            for i in range(len(far_para_lines) - 1):
                gap_between = far_para_lines[i+1][0].y0 - far_para_lines[i][0].y1
                if gap_between > 20.0:
                    is_continuous = False
                    break
            if is_continuous:
                if near_is_top:
                    last_para_y1 = max(lb.y1 for (lb, _, _) in far_para_lines)
                    new_y0 = last_para_y1 + gap
                    max_trim = original_clip.y0 + 0.6 * original_clip.height
                    clip = fitz.Rect(clip.x0, min(new_y0, max_trim), clip.x1, clip.y1)
                else:
                    first_para_y0 = min(lb.y0 for (lb, _, _) in far_para_lines)
                    new_y1 = first_para_y0 - gap
                    min_trim = original_clip.y1 - 0.6 * original_clip.height
                    clip = fitz.Rect(clip.x0, clip.y0, clip.x1, max(new_y1, min_trim))

    # 强制最小高度
    min_h = 40.0
    if clip.height < min_h:
        return trim_clip_head_by_text(
            fitz.Rect(page_rect.x0, caption_rect.y0 - 600, page_rect.x1, caption_rect.y1 + 600) & page_rect,
            page_rect, caption_rect, direction, text_lines,
            width_ratio=width_ratio, font_min=font_min, font_max=font_max,
            gap=gap, adjacent_th=adjacent_th
        )

    # 限制在页面范围内
    clip = fitz.Rect(clip.x0, max(page_rect.y0, clip.y0), clip.x1, min(page_rect.y1, clip.y1))
    return clip


# ============================================================================
# 向后兼容别名
# ============================================================================

_merge_rects = merge_rects
_refine_clip_by_objects = refine_clip_by_objects
_build_text_masks_px = build_text_masks_px
_detect_far_side_text_evidence = detect_far_side_text_evidence
_trim_far_side_text_post_autocrop = trim_far_side_text_post_autocrop
_adaptive_acceptance_thresholds = adaptive_acceptance_thresholds
_is_caption_text = is_caption_text
_detect_exact_n_lines_of_text = detect_exact_n_lines_of_text
_trim_clip_head_by_text = trim_clip_head_by_text
_trim_clip_head_by_text_v2 = trim_clip_head_by_text_v2


# ============================================================================
# 模块导出
# ============================================================================

__all__ = [
    # 像素级内容检测
    "detect_content_bbox_pixels",
    "estimate_ink_ratio",
    # 矩形合并
    "merge_rects",
    # 对象裁剪优化
    "refine_clip_by_objects",
    # 文本遮罩
    "build_text_masks_px",
    # 远端正文检测
    "detect_far_side_text_evidence",
    "trim_far_side_text_post_autocrop",
    # 验收阈值
    "adaptive_acceptance_thresholds",
    "detect_text_pollution",
    "looks_like_table_text",
    "limit_clip_by_text_blocks",
    "limit_clip_by_neighbor_captions",
    # 边缘对齐
    "snap_clip_edges",
    # X 方向列感知裁剪
    "refine_clip_x_range",
    "refine_clip_to_table_band",
    "restore_table_clip_width",
    # 文本裁切辅助
    "is_caption_text",
    "detect_exact_n_lines_of_text",
    # Phase A 文本裁切
    "trim_clip_head_by_text",
    "trim_clip_head_by_text_v2",
]
