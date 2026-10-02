#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pixel-level crop detection helpers."""

from __future__ import annotations

import math
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


def region_has_ink(
    page: "fitz.Page",
    rect: Any,
    *,
    mask_rects: Optional[List[Any]] = None,
    dpi: int = 72,
    white_threshold: int = 250,
    min_ratio: float = 0.005,
) -> bool:
    """
    判断页面某个区域内是否存在可见墨迹（可排除若干遮罩区域）。

    用于区分「对象路径外框超出裁剪框」与「真的有内容被裁掉」：
    PDF 的路径外框包含被 clip path 裁掉的部分，位图块外框包含白边，
    两者都系统性大于实际可见范围，只能靠渲染判定。

    Args:
        page: PyMuPDF 页面对象
        rect: 待检测区域（页面坐标）
        mask_rects: 忽略的区域列表（页面坐标），通常为文本行
        dpi: 渲染精度
        white_threshold: 白色阈值（0-255）
        min_ratio: 非白像素占比达到该值才算有墨迹

    Returns:
        区域内是否存在可见墨迹
    """
    if fitz is None:
        return False

    r = fitz.Rect(rect) & page.rect
    if r.is_empty or r.width <= 0.5 or r.height <= 0.5:
        return False

    try:
        pix = page.get_pixmap(clip=r, dpi=dpi, alpha=False)
    except Exception:
        return True  # 渲染失败时不敢放行，保持原有的保守判定

    w, h = pix.width, pix.height
    if w <= 0 or h <= 0:
        return False
    n = pix.n
    samples = memoryview(pix.samples)
    stride = pix.stride
    scale = dpi / 72.0

    # 位图边界对齐到整数像素，不能假定 r.x0 就是第 0 列，必须按 pix 原点换算；
    # 再外扩若干像素吸收字形抗锯齿，否则遮罩边缘残留的一列会被当成墨迹。
    pad_px = int(math.ceil(scale)) + 1
    ox, oy = tuple(pix.irect)[:2]
    masks_px: List[Tuple[int, int, int, int]] = []
    for m in (mask_rects or []):
        mr = fitz.Rect(m)
        if (mr & r).is_empty:
            continue
        masks_px.append((
            int(math.floor(mr.x0 * scale)) - ox - pad_px,
            int(math.floor(mr.y0 * scale)) - oy - pad_px,
            int(math.ceil(mr.x1 * scale)) - ox + pad_px,
            int(math.ceil(mr.y1 * scale)) - oy + pad_px,
        ))

    def masked(x: int, y: int) -> bool:
        for (lx, ty, rx, by) in masks_px:
            if lx <= x < rx and ty <= y < by:
                return True
        return False

    step_x = max(1, w // 400)
    step_y = max(1, h // 400)
    nonwhite = 0
    total = 0
    for y in range(0, h, step_y):
        row = samples[y * stride:(y + 1) * stride]
        for x in range(0, w, step_x):
            if masked(x, y):
                continue
            total += 1
            off = x * n
            r_ = row[off + 0]
            g_ = row[off + 1] if n > 1 else r_
            b_ = row[off + 2] if n > 2 else r_
            if r_ < white_threshold or g_ < white_threshold or b_ < white_threshold:
                nonwhite += 1
    if total == 0:
        return False
    return nonwhite / float(total) >= min_ratio


def estimate_region_ink_ratio(
    page: "fitz.Page",
    rect: Any,
    *,
    mask_rects: Optional[List[Any]] = None,
    dpi: int = 72,
    white_threshold: int = 200,
    step_px: int = 2,
) -> float:
    """
    区域内非白像素占比（可排除遮罩区域）。

    与 estimate_ink_ratio 的区别：支持文本行遮罩，因而能测量「结构墨迹」——
    扫描页上遮掉 OCR 文字后剩下的图形边框/连线/箭头。区域无效或渲染失败
    返回 0.0（视为无证据）。

    Args:
        page: PyMuPDF 页面对象
        rect: 待测量区域（页面坐标）
        mask_rects: 忽略的区域列表（页面坐标），通常为文本行
        dpi: 渲染精度
        white_threshold: 白色阈值（0-255）
        step_px: 像素采样步长

    Returns:
        遮罩后非白像素占比（0.0~1.0）
    """
    if fitz is None:
        return 0.0

    r = fitz.Rect(rect) & page.rect
    if r.is_empty or r.width <= 0.5 or r.height <= 0.5:
        return 0.0

    try:
        pix = page.get_pixmap(clip=r, dpi=dpi, alpha=False)
    except Exception:
        return 0.0

    w, h = pix.width, pix.height
    if w <= 0 or h <= 0:
        return 0.0
    n = pix.n
    samples = memoryview(pix.samples)
    stride = pix.stride
    scale = dpi / 72.0
    pad_px = int(math.ceil(scale)) + 1
    ox, oy = tuple(pix.irect)[:2]

    masks_px: List[Tuple[int, int, int, int]] = []
    for m in (mask_rects or []):
        mr = fitz.Rect(m)
        if (mr & r).is_empty:
            continue
        masks_px.append((
            int(math.floor(mr.x0 * scale)) - ox - pad_px,
            int(math.floor(mr.y0 * scale)) - oy - pad_px,
            int(math.ceil(mr.x1 * scale)) - ox + pad_px,
            int(math.ceil(mr.y1 * scale)) - oy + pad_px,
        ))

    def masked(x: int, y: int) -> bool:
        for (lx, ty, rx, by) in masks_px:
            if lx <= x < rx and ty <= y < by:
                return True
        return False

    step = max(1, step_px)
    nonwhite = 0
    total = 0
    for y in range(0, h, step):
        row = samples[y * stride:(y + 1) * stride]
        for x in range(0, w, step):
            if masked(x, y):
                continue
            total += 1
            off = x * n
            r_ = row[off + 0]
            g_ = row[off + 1] if n > 1 else r_
            b_ = row[off + 2] if n > 2 else r_
            if r_ < white_threshold or g_ < white_threshold or b_ < white_threshold:
                nonwhite += 1
    if total == 0:
        return 0.0
    return nonwhite / float(total)


def make_ink_probe(
    page: "fitz.Page",
    text_lines: List[Tuple[Any, float, str]],
    *,
    dpi: int = 72,
    min_ratio: float = 0.005,
):
    """
    构造按页缓存的墨迹探测器，供截断判定排除「路径外框大于可见范围」的误报。

    文本行整体作为遮罩排除：对象截断判定只关心图形内容，正文与题注的墨迹
    不应被算作被裁掉的图形。

    Args:
        page: PyMuPDF 页面对象
        text_lines: 该页文本行 [(rect, font_size, text), ...]
        dpi: 渲染精度
        min_ratio: 非白像素占比阈值

    Returns:
        接受矩形、返回该区域是否有可见墨迹的函数
    """
    mask_rects = [lb for (lb, _fs, txt) in text_lines if str(txt).strip()]
    cache: dict = {}

    def probe(rect: Any) -> bool:
        key = tuple(round(float(v), 1) for v in tuple(rect)[:4])
        if key not in cache:
            cache[key] = region_has_ink(
                page, key, mask_rects=mask_rects, dpi=dpi, min_ratio=min_ratio
            )
        return cache[key]

    return probe


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


def autocrop_x_range_with_object_support(
    clip: "fitz.Rect",
    autocrop_clip: "fitz.Rect",
    object_rects: List["fitz.Rect"],
    min_width_ratio: float = 0.30,
    min_saving: float = 10.0,
    support_ratio: float = 0.50,
    text_lines: Optional[List[Tuple["fitz.Rect", float, str]]] = None,
) -> Optional["fitz.Rect"]:
    """autocrop 被高度守卫整体否决时，尝试只保留其 x 收窄分量。

    栏位几何（refine_clip_x_range）只能夹栏的内侧缘（朝页中心一侧），
    外侧缘始终落到页边距，右栏图的 x1、左栏图的 x0 只有像素证据能
    收紧。高度守卫否决的是 y 收缩，x 分量可能依然正确；但像素噪声
    也可能把图切窄，因此仅当收窄带得到原生对象（图像/矢量）面积
    支撑（≥ support_ratio）时才采用。无原生对象的扫描页返回 None，
    维持原行为。原框内的文字也必须保留：像素文字遮罩可能把图旁
    或图底的标签隐藏，面积支撑本身不能证明文字完整。
    """
    if fitz is None or not object_rects:
        return None
    nx0 = max(clip.x0, autocrop_clip.x0)
    nx1 = min(clip.x1, autocrop_clip.x1)
    if nx1 - nx0 < clip.width * min_width_ratio:
        return None
    if clip.width - (nx1 - nx0) < min_saving:
        return None
    band = fitz.Rect(nx0, clip.y0, nx1, clip.y1)
    total = 0.0
    supported = 0.0
    for rect in object_rects:
        inter = rect & clip
        if inter.is_empty or inter.width <= 0 or inter.height <= 0:
            continue
        total += inter.width * inter.height
        inner = rect & band
        if not inner.is_empty and inner.width > 0 and inner.height > 0:
            supported += inner.width * inner.height
    if total <= 0 or supported / total < support_ratio:
        return None
    for rect, _size, text in (text_lines or []):
        visible = rect & clip
        if not text.strip() or visible.is_empty:
            continue
        if visible.x0 < band.x0 - 1.0 or visible.x1 > band.x1 + 1.0:
            return None
    return fitz.Rect(nx0, clip.y0, nx1, clip.y1)
