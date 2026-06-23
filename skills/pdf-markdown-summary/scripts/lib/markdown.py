#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown data structures and rendering helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


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


def render_block(block: MarkdownBlock) -> str:
    if block.type == "heading":
        level = min(max(block.level or 2, 1), 6)
        return f"{'#' * level} {block.text.strip()}".strip()

    if block.type == "image":
        alt = block.caption.strip() or block.text.strip() or "PDF image"
        return f"![{alt}]({block.path})"

    if block.type == "table":
        return block.text.strip()

    if block.type == "page_break":
        page = block.page if block.page is not None else ""
        return f"<!-- page {page} -->".strip()

    return block.text.strip()


def render_markdown(document: MarkdownDocument) -> str:
    parts = [f"# {document.title.strip()}", ""]
    for block in document.blocks:
        rendered = render_block(block)
        if rendered:
            parts.append(rendered)
            parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def render_blocks(blocks: Iterable[MarkdownBlock]) -> str:
    rendered = [render_block(block) for block in blocks]
    return "\n\n".join(r for r in rendered if r).rstrip() + "\n"


__all__ = [
    "MarkdownBlock",
    "MarkdownDocument",
    "render_block",
    "render_blocks",
    "render_markdown",
]
