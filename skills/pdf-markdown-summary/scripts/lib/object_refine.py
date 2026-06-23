#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Object and annotation based crop refinement."""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

try:
    import fitz
except ImportError:
    fitz = None  # type: ignore

from .text_trim import _looks_like_short_figure_label


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

def _has_small_object_band_near_trimmed_edge(
    clip: Any,
    raw_rects: List[Any],
    *,
    direction: str,
    proposed_edge: float,
    min_area_ratio: float,
    min_count: int = 8,
    edge_tolerance: float = 12.0,
) -> bool:
    """Detect dense small-object bands that would be lost by near-edge trimming."""
    if fitz is None:
        return False

    trimmed = (clip.y1 - proposed_edge) if direction == "above" else (proposed_edge - clip.y0)
    if trimmed < max(12.0, 0.08 * clip.height):
        return False

    area = max(1.0, clip.width * clip.height)
    band_rect = (
        fitz.Rect(clip.x0, proposed_edge, clip.x1, clip.y1)
        if direction == "above"
        else fitz.Rect(clip.x0, clip.y0, clip.x1, proposed_edge)
    )
    smalls: List[Any] = []
    for r in raw_rects:
        inter = (r & clip) & band_rect
        if inter.width <= 0 or inter.height <= 0:
            continue
        full_inter = r & clip
        if full_inter.width <= 0 or full_inter.height <= 0:
            continue
        if (full_inter.width * full_inter.height) / area >= min_area_ratio:
            continue
        smalls.append(full_inter)

    if len(smalls) < min_count:
        return False

    union = smalls[0]
    for r in smalls[1:]:
        union = union | r

    if union.width < 0.30 * clip.width:
        return False
    if union.height < max(20.0, 0.12 * clip.height):
        return False
    if direction == "above":
        return union.y1 >= clip.y1 - edge_tolerance
    return union.y0 <= clip.y0 + edge_tolerance

def _has_text_label_band_near_trimmed_edge(
    clip: Any,
    text_lines: Optional[List[Tuple[Any, float, str]]],
    *,
    direction: str,
    proposed_edge: float,
    min_count: int = 8,
    edge_tolerance: float = 12.0,
) -> bool:
    """Detect rows of narrow figure-internal text labels cut by near-edge trimming."""
    if fitz is None or not text_lines:
        return False

    trimmed = (clip.y1 - proposed_edge) if direction == "above" else (proposed_edge - clip.y0)
    if trimmed < max(10.0, 0.04 * clip.height):
        return False

    band_rect = (
        fitz.Rect(clip.x0, proposed_edge, clip.x1, clip.y1)
        if direction == "above"
        else fitz.Rect(clip.x0, clip.y0, clip.x1, proposed_edge)
    )
    labels: List[Any] = []
    for lb, _fs, text in text_lines:
        txt = text.strip()
        if not txt:
            continue
        full_inter = lb & clip
        if full_inter.width <= 0 or full_inter.height <= 0:
            continue
        cut_inter = full_inter & band_rect
        if cut_inter.width <= 0 or cut_inter.height <= 0:
            continue
        if full_inter.width > max(36.0, 0.08 * clip.width):
            continue
        labels.append(full_inter)

    if len(labels) < min_count:
        return False

    union = labels[0]
    for r in labels[1:]:
        union = union | r

    y0_span = max(r.y0 for r in labels) - min(r.y0 for r in labels)
    y1_span = max(r.y1 for r in labels) - min(r.y1 for r in labels)
    if min(y0_span, y1_span) > max(12.0, 0.04 * clip.height):
        return False
    if union.width < 0.30 * clip.width:
        return False
    if union.height < max(18.0, 0.06 * clip.height):
        return False
    if direction == "above":
        return union.y1 >= clip.y1 - edge_tolerance
    return union.y0 <= clip.y0 + edge_tolerance

def _near_caption_annotation_text_edge(
    clip: Any,
    text_lines: Optional[List[Tuple[Any, float, str]]],
    *,
    direction: str,
    proposed_edge: float,
    caption_rect: Any,
    edge_tolerance: float = 12.0,
) -> Optional[float]:
    """Return the near edge needed to include figure-internal subcaptions or prompt text."""
    if fitz is None or not text_lines:
        return None

    trimmed = (clip.y1 - proposed_edge) if direction == "above" else (proposed_edge - clip.y0)
    if trimmed < max(8.0, 0.03 * clip.height):
        return None

    band_rect = (
        fitz.Rect(clip.x0, proposed_edge - edge_tolerance, clip.x1, clip.y1)
        if direction == "above"
        else fitz.Rect(clip.x0, clip.y0, clip.x1, proposed_edge + edge_tolerance)
    )

    candidates: List[Tuple[Any, str]] = []
    for lb, _fs, text in text_lines:
        txt = text.strip()
        if not txt:
            continue
        full_inter = lb & clip
        if full_inter.width <= 0 or full_inter.height <= 0:
            continue
        if (full_inter & band_rect).width <= 0 or (full_inter & band_rect).height <= 0:
            continue
        if (lb & caption_rect).width > 0 and (lb & caption_rect).height > 0:
            continue
        if re.match(r"^\s*(?:Figure|Table)\s+\S+", txt, re.I):
            continue
        if re.match(r"^\s*\d+(?:\.\d+)+\.?\s+\S", txt):
            continue
        candidates.append((full_inter, txt))

    if not candidates:
        return None

    union = candidates[0][0]
    for r, _txt in candidates[1:]:
        union = union | r

    touches_near_edge = (
        union.y1 >= clip.y1 - edge_tolerance
        if direction == "above"
        else union.y0 <= clip.y0 + edge_tolerance
    )
    if not touches_near_edge:
        return None

    texts = [txt for _r, txt in candidates]
    has_panel_label = any(re.match(r"^\s*\([a-z]\)\s+", txt, re.I) for txt in texts)
    protected = has_panel_label and len(candidates) >= 2

    compact_multiline = (
        len(candidates) >= 3
        and union.width <= min(180.0, 0.35 * clip.width)
        and union.height <= max(70.0, 0.35 * clip.height)
        and union.height >= max(24.0, 0.10 * clip.height)
    )
    if compact_multiline:
        protected = True

    if not protected:
        return None

    pad = 6.0
    if direction == "above":
        return min(clip.y1, max(proposed_edge, union.y1 + pad))
    return max(clip.y0, min(proposed_edge, union.y0 - pad))

def _nearby_short_label_rects(
    clip: Any,
    content_rect: Any,
    text_lines: Optional[List[Tuple[Any, float, str]]],
    caption_rect: Any,
    *,
    max_font_size: float = 10.5,
    max_gap: float = 24.0,
) -> List[Any]:
    """Collect compact axis/title labels adjacent to detected figure objects."""
    if fitz is None or not text_lines or content_rect.width <= 0 or content_rect.height <= 0:
        return []

    labels: List[Any] = []
    for lb, font_size, text in text_lines:
        txt = (text or "").strip()
        if not txt:
            continue
        if font_size > max_font_size:
            continue
        if not _looks_like_short_figure_label(txt):
            continue
        if re.match(r"^\s*(?:Figure|Table)\s+\S+", txt, re.I):
            continue
        if (lb & caption_rect).width > 0 and (lb & caption_rect).height > 0:
            continue

        inter = lb & clip
        if inter.width <= 0 or inter.height <= 0:
            continue
        if inter.width > max(120.0, 0.30 * clip.width):
            continue

        horizontal_overlap = min(inter.x1, content_rect.x1) - max(inter.x0, content_rect.x0)
        vertical_overlap = min(inter.y1, content_rect.y1) - max(inter.y0, content_rect.y0)
        horizontal_near = (
            horizontal_overlap > 0
            or content_rect.x0 - max_gap <= (inter.x0 + inter.x1) / 2 <= content_rect.x1 + max_gap
        )
        vertical_near = (
            vertical_overlap > 0
            or 0 <= content_rect.y0 - inter.y1 <= max_gap
            or 0 <= inter.y0 - content_rect.y1 <= max_gap
        )
        if horizontal_near and vertical_near:
            labels.append(inter)

    return labels

def _restore_far_side_short_labels_after_text_trim(
    original_clip: Any,
    trimmed_clip: Any,
    text_lines: Optional[List[Tuple[Any, float, str]]],
    caption_rect: Any,
    direction: str,
    *,
    pad: float = 8.0,
    max_gap: float = 28.0,
    max_font_size: float = 10.5,
) -> Any:
    """Restore compact figure labels just outside a far-side text trim boundary."""
    if fitz is None or not text_lines:
        return trimmed_clip
    if original_clip.width <= 1 or original_clip.height <= 1 or trimmed_clip.height <= 1:
        return trimmed_clip

    labels: List[Any] = []
    for lb, font_size, text in text_lines:
        txt = (text or "").strip()
        if not txt:
            continue
        if font_size > max_font_size:
            continue
        if not _looks_like_short_figure_label(txt):
            continue
        if re.match(r"^\s*(?:Figure|Table)\s+\S+", txt, re.I):
            continue
        if (lb & caption_rect).width > 0 and (lb & caption_rect).height > 0:
            continue

        inter = lb & original_clip
        if inter.width <= 0 or inter.height <= 0:
            continue
        if inter.width > max(120.0, 0.30 * original_clip.width):
            continue

        if direction == "above":
            gap_to_trim = trimmed_clip.y0 - inter.y1
            if 0 <= gap_to_trim <= max_gap and inter.y0 < trimmed_clip.y0:
                labels.append(inter)
        elif direction == "below":
            gap_to_trim = inter.y0 - trimmed_clip.y1
            if 0 <= gap_to_trim <= max_gap and inter.y1 > trimmed_clip.y1:
                labels.append(inter)

    if not labels:
        return trimmed_clip

    if direction == "above":
        new_y0 = max(original_clip.y0, min(r.y0 for r in labels) - pad)
        if new_y0 < trimmed_clip.y0 and trimmed_clip.y1 - new_y0 >= 40.0:
            return fitz.Rect(trimmed_clip.x0, new_y0, trimmed_clip.x1, trimmed_clip.y1)
    elif direction == "below":
        new_y1 = min(original_clip.y1, max(r.y1 for r in labels) + pad)
        if new_y1 > trimmed_clip.y1 and new_y1 - trimmed_clip.y0 >= 40.0:
            return fitz.Rect(trimmed_clip.x0, trimmed_clip.y0, trimmed_clip.x1, new_y1)

    return trimmed_clip

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
    text_lines: Optional[List[Tuple[Any, float, str]]] = None,
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
        text_lines: 可选文本行列表，用于保护竖排标签等图内文字

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

    object_only_chosen = fitz.Rect(chosen)
    nearby_labels = _nearby_short_label_rects(clip, chosen, text_lines, caption_rect)
    for label_rect in nearby_labels:
        chosen = chosen | label_rect

    object_only_chosen = fitz.Rect(
        object_only_chosen.x0 - object_pad,
        object_only_chosen.y0 - object_pad,
        object_only_chosen.x1 + object_pad,
        object_only_chosen.y1 + object_pad,
    )

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
            proposed_y1 = min(clip.y1, max(chosen.y1, clip.y0 + 40.0))
            annotation_probe_y1 = min(clip.y1, max(object_only_chosen.y1, clip.y0 + 40.0))
            if _has_small_object_band_near_trimmed_edge(
                clip,
                image_rects + vector_rects,
                direction=direction,
                proposed_edge=proposed_y1,
                min_area_ratio=min_area_ratio,
            ) or _has_text_label_band_near_trimmed_edge(
                clip,
                text_lines,
                direction=direction,
                proposed_edge=proposed_y1,
            ):
                proposed_y1 = clip.y1
            annotation_edge = _near_caption_annotation_text_edge(
                clip,
                text_lines,
                direction=direction,
                proposed_edge=annotation_probe_y1,
                caption_rect=caption_rect,
            )
            if annotation_edge is not None:
                proposed_y1 = max(proposed_y1, annotation_edge)
            result.y1 = proposed_y1
        else:
            proposed_y0 = max(clip.y0, min(chosen.y0, clip.y1 - 40.0))
            annotation_probe_y0 = max(clip.y0, min(object_only_chosen.y0, clip.y1 - 40.0))
            if _has_small_object_band_near_trimmed_edge(
                clip,
                image_rects + vector_rects,
                direction=direction,
                proposed_edge=proposed_y0,
                min_area_ratio=min_area_ratio,
            ) or _has_text_label_band_near_trimmed_edge(
                clip,
                text_lines,
                direction=direction,
                proposed_edge=proposed_y0,
            ):
                proposed_y0 = clip.y0
            annotation_edge = _near_caption_annotation_text_edge(
                clip,
                text_lines,
                direction=direction,
                proposed_edge=annotation_probe_y0,
                caption_rect=caption_rect,
            )
            if annotation_edge is not None:
                proposed_y0 = min(proposed_y0, annotation_edge)
            result.y0 = proposed_y0
        result.x0 = min(result.x0, chosen.x0)
        result.x1 = max(result.x1, chosen.x1)
        result = result & clip
        return result if result.height >= 40 else clip
    else:
        result = (chosen & clip)
        return result if result.height >= 40 else clip
