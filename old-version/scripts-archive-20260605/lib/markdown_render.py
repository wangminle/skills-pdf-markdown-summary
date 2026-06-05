#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Markdown rendering helpers.
"""

from __future__ import annotations

from typing import Iterable

from .markdown_models import MarkdownBlock, MarkdownDocument


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
    return "\n\n".join(render_block(block) for block in blocks if render_block(block)).rstrip() + "\n"

