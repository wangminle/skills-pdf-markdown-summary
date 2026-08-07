#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A1-1: 多源候选与配对结果数据结构。

定义 L1（多源候选生成）、L2（全页配对）、L4（置信度与验收）阶段使用的
中间数据结构。这些结构为 A2/A3 的精修改造提供统一接口。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .regions import RegionBBox


@dataclass
class AssetCandidate:
    """单个资产（figure/table）的候选描述。

    一个资产由 caption（标题）+ content（正文图表区域）组成。
    在 L1 阶段，多个来源（Layout、legacy regex、image detection）各自
    生成候选；在 L2 阶段做全页配对后产出最终 AssetCandidate。

    Attributes:
        kind: 'figure' | 'table'
        page: 页码（1-based）
        caption_text: 标题文本
        caption_bbox: 标题边界框
        content_bboxes: 正文图表区域边界框列表（支持多框，如多面板 figure）
        sources: 候选来源标记集合，如 {'layout', 'legacy_regex', 'image_detect'}
        confidence: 置信度（0~1）
        source_signals: 详细的来源信号（用于 debug）
        warnings: 警告列表
    """
    kind: str = "figure"
    page: int = 0
    caption_text: str = ""
    caption_bbox: Optional[List[float]] = None
    content_bboxes: List[List[float]] = field(default_factory=list)
    sources: set = field(default_factory=set)
    confidence: float = 0.0
    source_signals: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    @property
    def has_content(self) -> bool:
        return len(self.content_bboxes) > 0

    @property
    def content_bbox_union(self) -> Optional[List[float]]:
        """所有 content_bboxes 的并集包围框。"""
        if not self.content_bboxes:
            return None
        x0 = min(b[0] for b in self.content_bboxes)
        y0 = min(b[1] for b in self.content_bboxes)
        x1 = max(b[2] for b in self.content_bboxes)
        y1 = max(b[3] for b in self.content_bboxes)
        return [x0, y0, x1, y1]

    def add_source(self, name: str) -> None:
        self.sources.add(name)

    def merge_content_bbox(self, bbox: List[float]) -> None:
        """添加一个 content bbox（去重）。"""
        rounded = [round(v, 2) for v in bbox]
        if rounded not in [[round(x, 2) for x in b] for b in self.content_bboxes]:
            self.content_bboxes.append(rounded)

    def to_region(self) -> Optional[RegionBBox]:
        """将 content 并集转为 RegionBBox（用于 IoU 比较等）。"""
        u = self.content_bbox_union
        if u is None:
            return None
        return RegionBBox(u[0], u[1], u[2], u[3], kind=self.kind, source="candidate")


@dataclass
class PairingResult:
    """L2 全页配对结果。

    记录一页内 caption 与 content 的配对决策，以及未配对的孤立项。

    Attributes:
        page: 页码（1-based）
        pairs: 配对列表，每项 (caption_candidate, content_candidates)
        orphan_captions: 未配对到 content 的 caption
        orphan_contents: 未配对到 caption 的 content
        method: 配对方法 ('greedy_nearest' | 'sequence_align' | 'layout_guided')
        confidence: 配对整体置信度
    """
    page: int = 0
    pairs: List[Tuple[AssetCandidate, List[AssetCandidate]]] = field(default_factory=list)
    orphan_captions: List[AssetCandidate] = field(default_factory=list)
    orphan_contents: List[AssetCandidate] = field(default_factory=list)
    method: str = "greedy_nearest"
    confidence: float = 0.0


@dataclass
class CropResult:
    """L3 精修后的裁剪结果。

    Attributes:
        kind: 'figure' | 'table'
        page: 页码（1-based）
        caption_text: 标题文本
        final_bbox: 最终裁剪框 [x0, y0, x1, y1]
        content_bboxes: 原始 content 区域（精修前）
        caption_bbox: 标题区域
        refinement_steps: 精修步骤记录（用于 debug）
        confidence: 最终置信度
        status: 验收状态 ('accepted' | 'accepted_with_margin' | 'review_required' | 'rejected')
        warnings: 警告列表
    """
    kind: str = "figure"
    page: int = 0
    caption_text: str = ""
    final_bbox: Optional[List[float]] = None
    content_bboxes: List[List[float]] = field(default_factory=list)
    caption_bbox: Optional[List[float]] = None
    refinement_steps: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    status: str = "accepted"
    warnings: List[str] = field(default_factory=list)


@dataclass
class ConflictRecord:
    """Layout 与 legacy 提取结果的冲突记录（A1-4 冲突检测）。

    Attributes:
        kind: 'figure' | 'table'
        page: 页码（1-based）
        caption_text: 标题文本
        legacy_bbox: legacy 提取的 bbox
        layout_bbox: Layout 提取的 bbox
        conflict_type: 'iou_low' | 'caption_mismatch' | 'content_missing' | 'extra_content'
        iou: IoU 值（如果适用）
        detail: 详细描述
    """
    kind: str = "figure"
    page: int = 0
    caption_text: str = ""
    legacy_bbox: Optional[List[float]] = None
    layout_bbox: Optional[List[float]] = None
    conflict_type: str = ""
    iou: float = 0.0
    detail: str = ""


@dataclass
class LayoutIntegrationReport:
    """A1 Layout 集成的完整报告（用于退出条件验证）。

    Attributes:
        backend: 使用的后端名称
        enabled: Layout 是否实际启用
        pdf_path: PDF 路径
        pdf_hash: PDF 哈希
        total_pages: 总页数
        total_layout_regions: Layout 提取的区域总数
        figure_regions: figure 区域数
        table_regions: table 区域数
        caption_regions: caption 区域数
        candidates_seeded: Layout 种子生成的候选数
        captions_filtered: 正文引用过滤掉的 caption 数
        conflicts: 冲突记录列表
        elapsed_sec: Layout 提取耗时
        cached: 是否命中缓存
    """
    backend: str = ""
    enabled: bool = False
    pdf_path: str = ""
    pdf_hash: str = ""
    total_pages: int = 0
    total_layout_regions: int = 0
    figure_regions: int = 0
    table_regions: int = 0
    caption_regions: int = 0
    candidates_seeded: int = 0
    captions_filtered: int = 0
    conflicts: List[ConflictRecord] = field(default_factory=list)
    elapsed_sec: float = 0.0
    cached: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """转为可序列化的字典（用于 JSON 输出）。"""
        return {
            "backend": self.backend,
            "enabled": self.enabled,
            "pdf_path": self.pdf_path,
            "pdf_hash": self.pdf_hash,
            "total_pages": self.total_pages,
            "total_layout_regions": self.total_layout_regions,
            "figure_regions": self.figure_regions,
            "table_regions": self.table_regions,
            "caption_regions": self.caption_regions,
            "candidates_seeded": self.candidates_seeded,
            "captions_filtered": self.captions_filtered,
            "conflicts_count": len(self.conflicts),
            "conflicts": [
                {
                    "kind": c.kind,
                    "page": c.page,
                    "caption_text": c.caption_text[:80],
                    "conflict_type": c.conflict_type,
                    "iou": round(c.iou, 4),
                    "detail": c.detail,
                }
                for c in self.conflicts
            ],
            "elapsed_sec": round(self.elapsed_sec, 3),
            "cached": self.cached,
        }
