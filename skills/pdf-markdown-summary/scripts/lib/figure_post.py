#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Figure-specific final crop post-processing helpers."""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

try:
    import fitz
except ImportError:
    fitz = None  # type: ignore

from .direction import captions_share_column
from .text_trim import _looks_like_short_figure_label


def trim_far_side_noise_before_content(
    clip: Any,
    candidate_clip: Any,
    direction: str,
    image_rects: List[Any],
    vector_rects: List[Any],
    text_lines: Optional[List[Tuple[Any, float, str]]] = None,
    *,
    pad: float = 8.0,
    min_gap: float = 18.0,
    ink_probe: Optional[Any] = None,
) -> Any:
    """Trim isolated far-side noise before the first real figure content.

    ink_probe: 可选的墨迹探测器（见 pixel_detect.make_ink_probe，文字行
    已被遮罩）。待裁带内若仍有可见墨迹，说明那是无 OCR 文字的图形结构
    （扫描页的节点边框等），不是白边噪声，保持 autocrop 边界不动。

    该否决只应作用于对象模型失效的页面：扫描页的整页位图被当作页面载体
    过滤掉，矢量也全无，带内墨迹只能靠像素判断。原生页则由调用方传
    None——其页眉分隔横线是 0.4pt 描边路径，对象集合里根本看不到，像素
    探针会把它误判成「无文字的图形边界」而否决页眉裁切，把页眉线框进
    截图；原生页的对象证据本就可靠，交给它决定即可。

    带内已识别出页眉/页脚文本时同样不适用该否决：此时带内墨迹来自版面
    边距的装饰（页眉分隔横线、出版方图标），裁掉的是页眉而非图形边界。
    """
    if fitz is None:
        return candidate_clip

    evidence: List[Any] = []
    header_separators: List[Any] = []
    running_margin_text: List[Any] = []

    def _add_rect(r: Any) -> None:
        inter = r & clip
        if inter.width > 0 and inter.height > 0:
            evidence.append(inter)

    for line_rect, _font_size, text in text_lines or []:
        txt = (text or "").strip()
        if not txt:
            continue
        relative_top = (line_rect.y0 - clip.y0) / max(1.0, clip.height)
        relative_bottom = (clip.y1 - line_rect.y1) / max(1.0, clip.height)
        # 页眉/页脚的文本特征两侧必须一致：只有全大写（len>=8）才行会把
        # "NeurIPS 2024: Foo et al." 这类带冒号、非全大写的页眉漏判，
        # 使它在 below 方向仍被当作图内文字证据、把页脚框进截图。
        looks_like_running_margin = (":" in txt) or (len(txt) >= 8 and txt == txt.upper())
        if direction == "above" and relative_top <= 0.18 and looks_like_running_margin:
            running_margin_text.append(line_rect)
        elif direction == "below" and relative_bottom <= 0.18 and looks_like_running_margin:
            running_margin_text.append(line_rect)

    for r in image_rects:
        # Running headers may include a tiny raster logo immediately beside
        # their text. Keep ordinary figure images, including small subplots.
        if r.width < 20.0 and r.height < 20.0:
            adjacent_to_header = any(
                min(r.y1, line.y1) - max(r.y0, line.y0)
                >= 0.40 * min(r.height, line.height)
                and max(line.x0 - r.x1, r.x0 - line.x1, 0.0) <= 24.0
                for line in running_margin_text
            )
            if adjacent_to_header:
                continue
        _add_rect(r)

    for r in vector_rects:
        inter = r & clip
        # Page separator/header rules are often thin and very wide. They can be
        # zero-height PDF paths, so recognize them before rejecting empty rects.
        overlap_x = max(0.0, min(r.x1, clip.x1) - max(r.x0, clip.x0))
        if (
            overlap_x >= 0.70 * clip.width
            and r.height <= 4.0
            and clip.y0 <= r.y0 <= clip.y1
        ):
            header_separators.append(fitz.Rect(
                max(r.x0, clip.x0), r.y0, min(r.x1, clip.x1), r.y1
            ))
            continue
        if inter.width <= 0 or inter.height <= 0:
            continue
        # Tiny glyph paths (for example a publisher/logo mark in a running
        # header) should not establish the far edge of an entire figure.
        if inter.width < 14.0 and inter.height < 14.0:
            continue
        _add_rect(r)

    for line_rect, _font_size, text in text_lines or []:
        txt = (text or "").strip()
        if not txt:
            continue
        inter = line_rect & clip
        if inter.width <= 0 or inter.height <= 0:
            continue
        if line_rect in running_margin_text:
            continue
        # Keep figure-internal labels and compact annotations as content
        # evidence, but avoid using full-width body/caption text as a far edge.
        sentence_tail = (
            txt.rstrip().endswith((".", "。", "!", "?", "；", ";"))
            or (txt[:1].islower() and len(txt.split()) >= 2)
        )
        compact_annotation = (
            inter.width <= 0.45 * clip.width
            and len(txt) <= 80
            and not sentence_tail
            and not re.match(r"^\s*\d+(?:\.\d+)+\s+\S", txt)
        )
        if _looks_like_short_figure_label(txt) or compact_annotation:
            evidence.append(inter)

    # A running header may contain a vector logo made from many tiny paths. Once
    # a wide separator identifies that header band, ignore all evidence on its
    # page-edge side so the logo cannot keep the header in the final crop.
    if direction == "above":
        separators = [
            r for r in header_separators
            if r.y0 <= clip.y0 + 0.30 * clip.height
        ]
        if separators:
            boundary = max(r.y1 for r in separators) + 2.0
            evidence = [r for r in evidence if r.y1 > boundary]
    elif direction == "below":
        separators = [
            r for r in header_separators
            if r.y1 >= clip.y1 - 0.30 * clip.height
        ]
        if separators:
            boundary = min(r.y0 for r in separators) - 2.0
            evidence = [r for r in evidence if r.y0 < boundary]

    if not evidence:
        return candidate_clip

    def _band_is_running_margin(y0: float, y1: float) -> bool:
        """待裁带内是否有被识别为页眉/页脚的文本行。"""
        return any(
            line.y1 > y0 + 0.5 and line.y0 < y1 - 0.5
            for line in running_margin_text
        )

    if direction == "above":
        content_edge = min(r.y0 for r in evidence)
        if content_edge - candidate_clip.y0 < min_gap:
            return candidate_clip
        new_y0 = max(clip.y0, content_edge - pad)
        if new_y0 >= candidate_clip.y1:
            return candidate_clip
        if (ink_probe is not None
                and not _band_is_running_margin(candidate_clip.y0, new_y0)
                and ink_probe(fitz.Rect(
                    candidate_clip.x0, candidate_clip.y0, candidate_clip.x1, new_y0,
                ))):
            return candidate_clip
        return fitz.Rect(candidate_clip.x0, new_y0, candidate_clip.x1, candidate_clip.y1)

    if direction == "below":
        content_edge = max(r.y1 for r in evidence)
        if candidate_clip.y1 - content_edge < min_gap:
            return candidate_clip
        new_y1 = min(clip.y1, content_edge + pad)
        if new_y1 <= candidate_clip.y0:
            return candidate_clip
        if (ink_probe is not None
                and not _band_is_running_margin(new_y1, candidate_clip.y1)
                and ink_probe(fitz.Rect(
                    candidate_clip.x0, new_y1, candidate_clip.x1, candidate_clip.y1,
                ))):
            return candidate_clip
        return fitz.Rect(candidate_clip.x0, candidate_clip.y0, candidate_clip.x1, new_y1)

    return candidate_clip

def expand_clip_to_nearby_figure_title(
    original_clip: Any,
    limited_clip: Any,
    text_lines: List[Tuple[Any, float, str]],
    direction: str,
    *,
    pad: float = 4.0,
    max_gap: float = 12.0,
    max_title_font_size: float = 11.0,
    page_rect: Optional[Any] = None,
) -> Any:
    """恢复紧贴图主体的图内标题，避免被 layout 标题 blocker 排除。"""
    if fitz is None or original_clip.width <= 1 or original_clip.height <= 1:
        return limited_clip
    if limited_clip.width <= 1 or limited_clip.height <= 1:
        return limited_clip

    def _is_page_header(line_rect: Any, text: str) -> bool:
        # 页面顶部 5% 带内的行一律视为运行页眉/页眉区：Kimi K3 的居中页眉
        # （"Kimi K3: Open Frontier Intelligence" 等）各元素只占窗口宽约 26%，
        # 旧的「宽 >=70% 且含冒号」判据对它失效，曾被当 chart title 扩进图。
        if page_rect is not None and line_rect.y0 <= page_rect.y0 + 0.05 * page_rect.height:
            return True
        width_ratio = line_rect.width / max(1.0, original_clip.width)
        return width_ratio >= 0.70 and line_rect.y0 <= original_clip.y0 + 80.0 and ":" in text

    def _is_numbered_section(text: str) -> bool:
        return bool(re.match(r"^\s*\d+(?:\.\d+)*\.?\s+\S", text))

    def _is_section_number_only(text: str) -> bool:
        return bool(re.match(r"^\s*(?:\d+(?:\.\d+)+\.?|\d+\.)\s*$", text))

    def _is_body_tail_fragment(text: str) -> bool:
        txt = text.strip()
        return (
            len(txt.split()) >= 2
            and txt.rstrip().endswith((".", "。", "!", "?", "；", ";"))
        )

    def _links_to_wrapped_tail_below(line_rect: Any, text: str) -> bool:
        # 本行不带句末标点、紧邻下方一行以小写开头（≥2 字符）：这是一对被
        # 排版拆开的正文行（"Gordon, 1997). Figure 6 presents one dialogue
        # from" + "domain."），上行的非完整句形态不是图内标题。≥2 字符
        # 守卫避免 OCR 单字伪块（PARADISE p2 的 'l'）与真行配对。
        if text.rstrip().endswith((".", "。", "!", "?", "；", ";")):
            return False
        for other, _other_size, other_text in text_lines:
            other_txt = (other_text or "").strip()
            if len(other_txt) < 2 or not other_txt[:1].islower():
                continue
            gap = other.y0 - line_rect.y1
            if -2.0 <= gap <= 4.0 and abs(other.x0 - line_rect.x0) <= 16.0:
                return True
        return False

    section_number_lines = [
        line_rect
        for line_rect, _font_size, text in text_lines
        if _is_section_number_only((text or "").strip())
    ]

    def _has_adjacent_section_number(line_rect: Any) -> bool:
        for number_rect in section_number_lines:
            vertical_overlap = min(line_rect.y1, number_rect.y1) - max(line_rect.y0, number_rect.y0)
            if vertical_overlap <= 0:
                continue
            overlap_ratio = vertical_overlap / max(1.0, min(line_rect.height, number_rect.height))
            horizontal_gap = line_rect.x0 - number_rect.x1
            if overlap_ratio >= 0.60 and 0 <= horizontal_gap <= 24.0:
                return True
        return False

    def _is_wrapped_body_line(rect: Any, size: float) -> bool:
        # A short last line may have no extracted punctuation. Link it to the
        # preceding body-width line instead of treating it as a figure title.
        # 55 字符的半行正文（PARADISE 扫描件 "Gordon, 1997). Figure 6
        # presents one dialogue from this"）同样能接出换行尾巴，阈值取 50；
        # 扫描行框常有 1-2pt 交叠，gap 下界放到 -2。
        for other, other_size, other_text in text_lines:
            if len((other_text or "").strip()) < 50:
                continue
            gap = rect.y0 - other.y1
            if (-2.0 <= gap <= 6 and abs(size - other_size) <= 1.5
                    and abs(rect.x0 - other.x0) <= 16
                    and other.width >= original_clip.width * 0.65):
                return True
        return False

    current = fitz.Rect(limited_clip)
    while True:
        candidates: List[Any] = []
        for line_rect, font_size, text in text_lines:
            txt = (text or "").strip()
            if not txt:
                continue
            if font_size > max_title_font_size:
                continue
            if (_is_body_tail_fragment(txt) or len(txt) > 100
                    or _is_wrapped_body_line(line_rect, font_size)
                    or _links_to_wrapped_tail_below(line_rect, txt)):
                continue
            if _is_numbered_section(txt) or _is_section_number_only(txt) or _is_page_header(line_rect, txt):
                continue
            if _has_adjacent_section_number(line_rect):
                continue
            overlap = min(line_rect.x1, current.x1) - max(line_rect.x0, current.x0)
            if overlap < 0.2 * min(line_rect.width, current.width):
                continue
            inter = line_rect & original_clip
            if inter.width <= 0 or inter.height <= 0:
                continue

            if direction == "above":
                gap = current.y0 - line_rect.y1
                if line_rect.y0 < current.y0 and -line_rect.height <= gap <= max_gap and line_rect.y1 >= original_clip.y0:
                    candidates.append(line_rect)
            elif direction == "below":
                gap = line_rect.y0 - current.y1
                if line_rect.y1 > current.y1 and -line_rect.height <= gap <= max_gap and line_rect.y0 <= original_clip.y1:
                    candidates.append(line_rect)

        if not candidates:
            break

        if direction == "above":
            new_y0 = max(original_clip.y0, min(r.y0 for r in candidates) - pad)
            if new_y0 >= current.y0 - 0.1:
                break
            current = fitz.Rect(current.x0, new_y0, current.x1, current.y1)
        elif direction == "below":
            new_y1 = min(original_clip.y1, max(r.y1 for r in candidates) + pad)
            if new_y1 <= current.y1 + 0.1:
                break
            current = fitz.Rect(current.x0, current.y0, current.x1, new_y1)
        else:
            break

    return current

def expand_clip_to_nearby_figure_objects(
    limited_clip: Any,
    caption_rect: Any,
    direction: str,
    image_rects: List[Any],
    vector_rects: List[Any],
    page_rect: Any,
    neighbor_caption_rects: Optional[List[Any]] = None,
    *,
    gap: float = 6.0,
    pad: float = 6.0,
    max_gap: float = 18.0,
    max_expand: float = 140.0,
) -> Any:
    """Recover connected figure objects clipped off at the far side of the baseline.

    Some architecture diagrams have small modules slightly beyond the fixed baseline
    height. They are real figure objects, not text blockers, and should be pulled
    back only when they touch the current far edge or are very close to it.
    """
    if fitz is None or limited_clip.width <= 1 or limited_clip.height <= 1:
        return limited_clip
    if page_rect is None:
        return limited_clip

    # 扩边停止线只由同栏题注给出：双栏页面上邻栏题注在纵向上同样可能落在
    # 当前 clip 之外，不加栏位检查会把本栏扩边卡在邻栏题注处
    # （实测 y0 由 244 卡到 318，图顶部 74pt 内容被切）。
    neighbor_caption_rects = [
        rect for rect in (neighbor_caption_rects or [])
        if rect is not None and captions_share_column(rect, caption_rect)
    ]
    page_width = max(1.0, page_rect.width)

    def _is_object_candidate(rect: Any) -> bool:
        if rect.width <= 0 or rect.height <= 0:
            return False
        if rect.width < 20.0 or rect.height < 14.0:
            return False
        if rect.width * rect.height < 120.0:
            return False
        if rect.width >= page_width * 0.65 and rect.height <= 2.0:
            return False
        if rect.width * rect.height < 24.0 and min(rect.width, rect.height) < 4.0:
            return False
        horizontal_overlap = min(rect.x1, limited_clip.x1) - max(rect.x0, limited_clip.x0)
        if horizontal_overlap <= 0:
            return False
        return True

    objects = [
        fitz.Rect(rect)
        for rect in list(image_rects) + list(vector_rects)
        if _is_object_candidate(rect)
    ]
    if not objects:
        return limited_clip

    current = fitz.Rect(limited_clip)

    if direction == "above":
        boundary = page_rect.y0
        # 邻题注只要与当前 clip 有任何重叠（含落在 clip 内部）都要当停止线：
        # 只取「完全在 clip 之上」的题注，会在题注已被部分框进来时放任扩边，
        # 把邻题注剩下的部分一起吞掉。
        previous_caps = [
            rect for rect in neighbor_caption_rects
            if rect.y1 <= caption_rect.y0 and rect.y0 < limited_clip.y0 - 0.5
        ]
        if previous_caps:
            boundary = max(boundary, max(rect.y1 for rect in previous_caps) + gap)
        boundary = max(boundary, limited_clip.y0 - max_expand)

        while True:
            edge = current.y0
            candidates = [
                rect for rect in objects
                if rect.y0 < edge
                and rect.y1 >= edge - max_gap
                and rect.y1 <= caption_rect.y0 - gap
                and rect.y1 >= boundary
            ]
            if not candidates:
                break
            new_y0 = max(boundary, min(rect.y0 for rect in candidates) - pad)
            if new_y0 >= current.y0 - 0.5:
                break
            current = fitz.Rect(current.x0, new_y0, current.x1, current.y1)

    elif direction == "below":
        boundary = page_rect.y1
        next_caps = [
            rect for rect in neighbor_caption_rects
            if rect.y0 >= caption_rect.y1 and rect.y1 > limited_clip.y1 + 0.5
        ]
        if next_caps:
            boundary = min(boundary, min(rect.y0 for rect in next_caps) - gap)
        boundary = min(boundary, limited_clip.y1 + max_expand)

        while True:
            edge = current.y1
            candidates = [
                rect for rect in objects
                if rect.y1 > edge
                and rect.y0 <= edge + max_gap
                and rect.y0 >= caption_rect.y1 + gap
                and rect.y0 <= boundary
            ]
            if not candidates:
                break
            new_y1 = min(boundary, max(rect.y1 for rect in candidates) + pad)
            if new_y1 <= current.y1 + 0.5:
                break
            current = fitz.Rect(current.x0, current.y0, current.x1, new_y1)

    return current

def recover_clip_label_columns_without_objects(
    clip: Any,
    text_lines: List[Tuple[Any, float, str]],
    caption_rect: Any,
    base_clip: Any,
    *,
    pad: float = 3.0,
    max_extend: float = 60.0,
) -> Any:
    """对象全被过滤的 OCR 扫描页：收回被墨迹 autocrop 切掉的旁注/竖排标签列。

    仅在页面没有任何图形对象（矢量与位图全无）时由调用方启用；这类页面
    的裁剪几何只能靠 OCR 文本行兜底。与裁剪框纵向 ≥50% 重叠、x 向与框
    搭接、落在题注 x 范围 ±8pt 内且单侧延伸 ≤60pt 的非正文行，视为图内
    标签列收回（PARADISE F6 右侧 x488-543 的语音行为标签）。宽度达到
    基线 70% 的行是栏内正文，不收回。扩展不越过 base_clip。
    """
    if fitz is None or clip.width <= 1 or clip.height <= 1:
        return clip
    if caption_rect is None or base_clip is None:
        return clip
    cap = fitz.Rect(caption_rect)
    base = fitz.Rect(base_clip)
    body_width = 0.70 * max(1.0, base.width)
    grew_left = grew_right = False
    new_x0, new_x1 = clip.x0, clip.x1
    for line_rect, _font_size, text in text_lines or []:
        if not (text or "").strip():
            continue
        r = fitz.Rect(line_rect)
        if r.width <= 0 or r.height <= 0 or r.width >= body_width:
            continue
        inter_y = min(r.y1, clip.y1) - max(r.y0, clip.y0)
        if inter_y < 0.5 * r.height:
            continue
        inter_x = min(r.x1, clip.x1) - max(r.x0, clip.x0)
        if inter_x <= 0:
            continue
        if r.x0 < cap.x0 - 8.0 or r.x1 > cap.x1 + 8.0:
            continue
        if r.x0 < clip.x0 - 1.0 and clip.x0 - r.x0 <= max_extend:
            new_x0 = min(new_x0, r.x0)
            grew_left = True
        if r.x1 > clip.x1 + 1.0 and r.x1 - clip.x1 <= max_extend:
            new_x1 = max(new_x1, r.x1)
            grew_right = True
    if not (grew_left or grew_right):
        return clip
    if grew_left:
        new_x0 = max(base.x0, new_x0 - pad)
    if grew_right:
        new_x1 = min(base.x1, new_x1 + pad)
    if new_x1 - new_x0 <= clip.width + 0.1:
        return clip
    return fitz.Rect(new_x0, clip.y0, new_x1, clip.y1)

def pad_figure_clip_near_caption(
    clip: Any,
    caption_rect: Any,
    direction: str,
    *,
    pad: float = 4.0,
    min_caption_gap: float = 2.0,
) -> Any:
    """Add a tiny final-side padding near the caption without touching the caption."""
    if fitz is None or clip.width <= 1 or clip.height <= 1:
        return clip
    if direction == "above":
        max_y1 = caption_rect.y0 - min_caption_gap
        new_y1 = min(max_y1, clip.y1 + pad)
        if new_y1 > clip.y1 + 0.1:
            return fitz.Rect(clip.x0, clip.y0, clip.x1, new_y1)
    elif direction == "below":
        min_y0 = caption_rect.y1 + min_caption_gap
        new_y0 = max(min_y0, clip.y0 - pad)
        if new_y0 < clip.y0 - 0.1:
            return fitz.Rect(clip.x0, new_y0, clip.x1, clip.y1)
    return clip
