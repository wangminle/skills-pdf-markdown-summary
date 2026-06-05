#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Markdown document data structures for PDF-to-Markdown conversion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MarkdownBlock:
    """A single renderable Markdown block."""

    type: str
    text: str = ""
    level: int = 0
    page: Optional[int] = None
    path: str = ""
    caption: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "text": self.text,
            "level": self.level,
            "page": self.page,
            "path": self.path,
            "caption": self.caption,
            "meta": self.meta,
        }


@dataclass
class MarkdownDocument:
    """A Markdown document built from PDF content blocks."""

    title: str
    source_pdf: str
    blocks: List[MarkdownBlock] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "source_pdf": self.source_pdf,
            "meta": self.meta,
            "blocks": [block.to_dict() for block in self.blocks],
        }

