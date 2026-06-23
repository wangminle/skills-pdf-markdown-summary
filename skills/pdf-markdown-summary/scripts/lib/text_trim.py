#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Text-driven crop trimming helpers."""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

try:
    import fitz
except ImportError:
    fitz = None  # type: ignore


def _looks_like_short_figure_label(text: str) -> bool:
    """Return True for short in-figure labels that should not trim crop edges."""
    txt = text.strip()
    if not txt:
        return False

    # Numbered section headings such as "3.2.1 Scaled Dot-Product Attention"
    # are document structure, not figure-internal labels.
    if re.match(r"^\d+(?:\.\d+)+\s+\S+", txt):
        return False

    tokens = re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)*|\d+(?:\.\d+)?", txt)
    if len(tokens) > 8:
        return False

    if re.search(r"[.!?。！？；;:,，]$", txt):
        return False

    return True

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
    tolerance: float = 0.35,
    min_line_width_ratio: float = 0.0,
) -> Tuple[bool, List[Any]]:
    """
    检测 clip_rect 中是否恰好包含 n 行文字。

    Args:
        clip_rect: 待检测的矩形区域
        text_lines: 文本行列表 (bbox, font_size, text)
        typical_line_h: 典型行高
        n: 期望的行数
        tolerance: 容差（相对于期望值的比例）
        min_line_width_ratio: 单行文字相对 clip 宽度的最小宽度比例

    Returns:
        (is_exact_n_lines, matched_line_bboxes)
    """
    if fitz is None:
        return False, []

    # 筛选在区域内的文本行
    text_in_region = []
    for bbox, size_est, text in text_lines:
        if not bbox.intersects(clip_rect) or bbox.height >= typical_line_h * 1.5:
            continue
        inter = bbox & clip_rect
        if min_line_width_ratio > 0 and inter.width < clip_rect.width * min_line_width_ratio:
            continue
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
            check_strip,
            text_lines,
            typical_line_h,
            n=2,
            tolerance=0.35,
            min_line_width_ratio=max(0.18, width_ratio * 0.35),
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

    from .object_refine import _restore_far_side_short_labels_after_text_trim

    clip = _restore_far_side_short_labels_after_text_trim(
        original_clip,
        clip,
        text_lines,
        caption_rect,
        direction,
        pad=max(6.0, gap),
    )

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
