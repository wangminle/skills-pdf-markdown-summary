#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compatibility re-export layer for crop refinement helpers.

The implementation has been split into focused modules. Import from those modules
for new code; this module preserves the historical public API.
"""

from __future__ import annotations

from .acceptance import (
    adaptive_acceptance_thresholds,
    detect_text_pollution,
    looks_like_table_text,
)
from .clip_limit import (
    limit_clip_by_neighbor_captions,
    limit_clip_by_text_blocks,
    refine_clip_x_range,
    snap_clip_edges,
)
from .far_side import (
    detect_far_side_text_evidence,
    trim_far_side_text_iterative,
    trim_far_side_text_post_autocrop,
)
from .figure_post import (
    expand_clip_to_nearby_figure_objects,
    expand_clip_to_nearby_figure_title,
    pad_figure_clip_near_caption,
    trim_far_side_noise_before_content,
)
from .object_refine import (
    merge_rects,
    refine_clip_by_objects,
)
from .pixel_detect import (
    build_text_masks_px,
    detect_content_bbox_pixels,
    estimate_ink_ratio,
)
from .table_refine import (
    expand_clip_to_nearby_table_header,
    expand_clip_to_rendered_horizontal_rule,
    expand_table_clip_to_text_bounds,
    refine_clip_to_table_band,
    restore_table_clip_width,
    restore_table_tail_after_layout_trim,
    trim_table_far_side_section_heading,
)
from .text_trim import (
    detect_exact_n_lines_of_text,
    is_caption_text,
    trim_clip_head_by_text,
    trim_clip_head_by_text_v2,
)

# Historical private aliases kept for compatibility with older callers.
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

__all__ = [
    "adaptive_acceptance_thresholds",
    "build_text_masks_px",
    "detect_content_bbox_pixels",
    "detect_exact_n_lines_of_text",
    "detect_far_side_text_evidence",
    "detect_text_pollution",
    "estimate_ink_ratio",
    "expand_clip_to_nearby_figure_objects",
    "expand_clip_to_nearby_figure_title",
    "expand_clip_to_nearby_table_header",
    "expand_clip_to_rendered_horizontal_rule",
    "expand_table_clip_to_text_bounds",
    "is_caption_text",
    "limit_clip_by_neighbor_captions",
    "limit_clip_by_text_blocks",
    "looks_like_table_text",
    "merge_rects",
    "pad_figure_clip_near_caption",
    "refine_clip_by_objects",
    "refine_clip_to_table_band",
    "refine_clip_x_range",
    "restore_table_clip_width",
    "restore_table_tail_after_layout_trim",
    "snap_clip_edges",
    "trim_clip_head_by_text",
    "trim_clip_head_by_text_v2",
    "trim_far_side_noise_before_content",
    "trim_far_side_text_iterative",
    "trim_far_side_text_post_autocrop",
    "trim_table_far_side_section_heading",
]
