#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A1-1: Layout 语义区域数据结构。

定义 Layout 后端输出的统一区域模型，供多源候选生成（L1）使用。
与 models.py 中的 DocumentLayoutModel（版式模型）互补：
- DocumentLayoutModel 描述页面几何（栏、边距、行高），用于精裁辅助；
- PageRegion 描述语义区域（picture/table/caption），用于候选生成与冲突检测。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Layout 区域分类（与实验 common.py 对齐）
FIGURE_CLASSES = {"picture", "figure", "image", "chart"}
TABLE_CLASSES = {"table"}
CAPTION_CLASSES = {
    "caption",
    "figure-caption",
    "table-caption",
    "figure_title",
    "table_title",
}


@dataclass
class RegionBBox:
    """Layout 后端输出的单个语义区域。

    Attributes:
        x0, y0, x1, y1: PDF 点坐标边界框
        kind: 语义类别 ('figure' | 'table' | 'caption' | 'text' | 'other')
        source: 来源后端 ('pymupdf4llm' | 'pymupdf_native' | ...)
        raw_class: 后端原始 class 名（如 'picture', 'figure-caption'）
        confidence: 置信度（0~1，Layout 后端无置信度时默认 1.0）
    """
    x0: float
    y0: float
    x1: float
    y1: float
    kind: str = "other"
    source: str = ""
    raw_class: str = ""
    confidence: float = 1.0

    @classmethod
    def from_list(cls, bbox: List[float], **kwargs: Any) -> "RegionBBox":
        return cls(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]), **kwargs)

    def to_list(self) -> List[float]:
        return [round(self.x0, 2), round(self.y0, 2), round(self.x1, 2), round(self.y1, 2)]

    @property
    def area(self) -> float:
        return max(0.0, self.x1 - self.x0) * max(0.0, self.y1 - self.y0)

    @property
    def width(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)

    @property
    def center(self) -> Tuple[float, float]:
        return ((self.x0 + self.x1) / 2.0, (self.y0 + self.y1) / 2.0)

    def intersect(self, other: "RegionBBox") -> Optional["RegionBBox"]:
        ix0, iy0 = max(self.x0, other.x0), max(self.y0, other.y0)
        ix1, iy1 = min(self.x1, other.x1), min(self.y1, other.y1)
        if ix1 <= ix0 or iy1 <= iy0:
            return None
        return RegionBBox(ix0, iy0, ix1, iy1)

    def iou(self, other: "RegionBBox") -> float:
        inter = self.intersect(other)
        if inter is None:
            return 0.0
        union = self.area + other.area - inter.area
        return inter.area / union if union > 0 else 0.0

    def distance_to(self, other: "RegionBBox") -> float:
        """两框中心点距离（pt）。"""
        cx1, cy1 = self.center
        cx2, cy2 = other.center
        return ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5

    def edge_distance(self, other: "RegionBBox") -> float:
        """两框边到边的最小距离（pt）。

        如果两框重叠，返回 0。比 center distance 更适合
        高瘦图框与 caption 的距离判断。
        """
        dx = max(0, max(self.x0, other.x0) - min(self.x1, other.x1))
        dy = max(0, max(self.y0, other.y0) - min(self.y1, other.y1))
        return (dx * dx + dy * dy) ** 0.5

    def vertical_gap(self, other: "RegionBBox") -> float:
        """垂直间距（pt）：other 在 self 上方或下方时均返回正值，重叠时为 0。"""
        if self.y1 <= other.y0:
            return other.y0 - self.y1
        if other.y1 <= self.y0:
            return self.y0 - other.y1
        return 0.0

    def horizontal_overlap(self, other: "RegionBBox") -> float:
        """水平投影重叠量（pt）。"""
        return max(0.0, min(self.x1, other.x1) - max(self.x0, other.x0))

    def contains(self, other: "RegionBBox", tol: float = 1.0) -> bool:
        """other 是否被本框完整包含（容差 tol pt）。"""
        return (
            other.x0 >= self.x0 - tol
            and other.y0 >= self.y0 - tol
            and other.x1 <= self.x1 + tol
            and other.y1 <= self.y1 + tol
        )


def classify_region(raw_class: str) -> str:
    """将后端原始 class 名映射为统一语义类别。"""
    c = (raw_class or "").lower()
    if c in FIGURE_CLASSES:
        return "figure"
    if c in TABLE_CLASSES:
        return "table"
    if c in CAPTION_CLASSES:
        return "caption"
    return "other"


@dataclass
class PageRegion:
    """单页的 Layout 语义区域集合。

    Attributes:
        page: 页码（1-based）
        regions: 全部区域列表
        figure_regions: 预分类的 figure-like 区域
        table_regions: 预分类的 table-like 区域
        caption_regions: 预分类的 caption-like 区域
    """
    page: int
    regions: List[RegionBBox] = field(default_factory=list)
    figure_regions: List[RegionBBox] = field(default_factory=list)
    table_regions: List[RegionBBox] = field(default_factory=list)
    caption_regions: List[RegionBBox] = field(default_factory=list)

    @classmethod
    def from_regions(cls, page: int, regions: List[RegionBBox]) -> "PageRegion":
        """根据 regions 的 kind 字段自动分类。"""
        pr = cls(page=page, regions=regions)
        for r in regions:
            if r.kind == "figure":
                pr.figure_regions.append(r)
            elif r.kind == "table":
                pr.table_regions.append(r)
            elif r.kind == "caption":
                pr.caption_regions.append(r)
        return pr


@dataclass
class LayoutResult:
    """整个 PDF 的 Layout 提取结果。

    Attributes:
        pdf_path: PDF 文件路径
        pdf_hash: PDF 文件内容哈希（用于 L0 缓存 key）
        backend: 后端名称
        backend_version: 后端版本
        pages: 按页码（1-based）索引的 PageRegion
        elapsed_sec: 提取耗时（秒）
        cached: 是否命中缓存
    """
    pdf_path: str
    pdf_hash: str
    backend: str
    backend_version: str
    pages: Dict[int, PageRegion] = field(default_factory=dict)
    elapsed_sec: float = 0.0
    cached: bool = False

    def get_page(self, page: int) -> Optional[PageRegion]:
        """获取指定页的 PageRegion（1-based）。"""
        return self.pages.get(page)

    def all_figure_regions(self) -> List[Tuple[int, RegionBBox]]:
        """返回 (page, region) 列表，包含所有页的 figure 区域。"""
        return [(p, r) for p, pr in self.pages.items() for r in pr.figure_regions]

    def all_table_regions(self) -> List[Tuple[int, RegionBBox]]:
        """返回 (page, region) 列表，包含所有页的 table 区域。"""
        return [(p, r) for p, pr in self.pages.items() for r in pr.table_regions]

    def all_caption_regions(self) -> List[Tuple[int, RegionBBox]]:
        """返回 (page, region) 列表，包含所有页的 caption 区域。"""
        return [(p, r) for p, pr in self.pages.items() for r in pr.caption_regions]
