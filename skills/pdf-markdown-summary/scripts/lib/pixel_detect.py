#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pixel-level crop detection helpers."""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

try:
    import fitz
except ImportError:
    fitz = None  # type: ignore

def estimate_ink_ratio(pix: "fitz.Pixmap", white_threshold: int = 250) -> float:
    """
    估计位图中"有墨迹"的像素比例（0~1）。

    通过子采样快速近似；值越大表示内容越密集。

    Args:
        pix: PyMuPDF Pixmap 对象
        white_threshold: 白色阈值（默认 250）

    Returns:
        非白色像素占比（0.0~1.0）
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
