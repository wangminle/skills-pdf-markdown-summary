#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A1-1: 页面场景与共享解析缓存。

为 L1（多源候选生成）和 A1-4 集成逻辑提供统一的页面级上下文，
避免多个阶段重复解析同一页面。

PageScene 聚合：
- Layout 语义区域（来自 LayoutBackend）
- 页面尺寸（来自 fitz）
- Caption 候选（来自 legacy regex）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .regions import PageRegion, RegionBBox

logger = logging.getLogger(__name__)


@dataclass
class PageScene:
    """单页的解析上下文。

    Attributes:
        page: 页码（1-based）
        width: 页面宽度（pt）
        height: 页面高度（pt）
        layout: 该页的 Layout 语义区域（None 表示未启用 Layout）
    """
    page: int = 0
    width: float = 0.0
    height: float = 0.0
    layout: Optional[PageRegion] = None

    @property
    def has_layout(self) -> bool:
        return self.layout is not None

    def nearby_figure_regions(self, bbox: List[float], max_dist: float = 50.0) -> List[RegionBBox]:
        """查找给定 bbox 附近的 figure 区域。

        Args:
            bbox: 参考框 [x0, y0, x1, y1]
            max_dist: 最大距离（pt）

        Returns:
            按距离排序的 figure 区域列表
        """
        if not self.has_layout:
            return []
        ref = RegionBBox(bbox[0], bbox[1], bbox[2], bbox[3])
        result = []
        for r in self.layout.figure_regions:
            d = ref.distance_to(r)
            if d <= max_dist:
                result.append((d, r))
        result.sort(key=lambda x: x[0])
        return [r for _, r in result]

    def nearby_table_regions(self, bbox: List[float], max_dist: float = 50.0) -> List[RegionBBox]:
        """查找给定 bbox 附近的 table 区域。"""
        if not self.has_layout:
            return []
        ref = RegionBBox(bbox[0], bbox[1], bbox[2], bbox[3])
        result = []
        for r in self.layout.table_regions:
            d = ref.distance_to(r)
            if d <= max_dist:
                result.append((d, r))
        result.sort(key=lambda x: x[0])
        return [r for _, r in result]

    def nearby_caption_regions(self, bbox: List[float], max_dist: float = 50.0) -> List[RegionBBox]:
        """查找给定 bbox 附近的 caption 区域。"""
        if not self.has_layout:
            return []
        ref = RegionBBox(bbox[0], bbox[1], bbox[2], bbox[3])
        result = []
        for r in self.layout.caption_regions:
            d = ref.distance_to(r)
            if d <= max_dist:
                result.append((d, r))
        result.sort(key=lambda x: x[0])
        return [r for _, r in result]

    def has_content_nearby(self, bbox: List[float], max_dist: float = 80.0) -> bool:
        """检查给定 bbox 附近是否有 Layout content 框（figure/table）。

        用于 A1-4 正文引用过滤：caption 候选若无附近 content 框，
        可能是正文中的引用文字而非真正的标题。
        """
        return (
            len(self.nearby_figure_regions(bbox, max_dist)) > 0
            or len(self.nearby_table_regions(bbox, max_dist)) > 0
        )


class SceneCache:
    """页面场景缓存。

    避免重复创建 PageScene。在 extract_figures / extract_tables
    共享同一份页面尺寸和 Layout 区域。
    """

    def __init__(self) -> None:
        self._scenes: Dict[int, PageScene] = {}

    def get_or_create(
        self,
        page: int,
        width: float = 0.0,
        height: float = 0.0,
        layout: Optional[PageRegion] = None,
    ) -> PageScene:
        """获取或创建页面场景。"""
        if page not in self._scenes:
            self._scenes[page] = PageScene(
                page=page, width=width, height=height, layout=layout
            )
        else:
            scene = self._scenes[page]
            if width > 0 and scene.width == 0:
                scene.width = width
            if height > 0 and scene.height == 0:
                scene.height = height
            if layout is not None and scene.layout is None:
                scene.layout = layout
        return self._scenes[page]

    def get(self, page: int) -> Optional[PageScene]:
        return self._scenes.get(page)

    @property
    def pages(self) -> List[int]:
        return sorted(self._scenes.keys())
