#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown data structures and rendering helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote


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
    # paragraph 专用的行内 Markdown 粗斜体文本，只在渲染时使用；
    # text 保持纯文本，题注匹配等逻辑一律读 text。
    rich_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "text": self.text,
            "rich_text": self.rich_text,
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


def _escape_paragraph_line_starts(text: str) -> str:
    if text.lstrip().startswith("```"):
        return text
    text = re.sub(
        r"^([ \t]{0,3})(\d{1,9})([.)])(?=[ \t]|$)",
        lambda match: f"{match.group(1)}{match.group(2)}\\{match.group(3)}",
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"^([ \t]{0,3})([+*-])(?=[ \t]|$)",
        lambda match: f"{match.group(1)}\\{match.group(2)}",
        text,
        flags=re.MULTILINE,
    )
    return re.sub(
        r"^([ \t]{0,3})(>)",
        lambda match: f"{match.group(1)}\\{match.group(2)}",
        text,
        flags=re.MULTILINE,
    )


_UNICODE_LIST_BULLET_LINE_RE = re.compile(r"^([ \t]*)[•▪▫◦‣⁃➢➣➤]\s*")


def _render_list_block(text: str) -> str:
    lines = [
        _UNICODE_LIST_BULLET_LINE_RE.sub(r"\1- ", line)
        for line in text.splitlines()
    ]
    return "\n".join(lines).strip()


def render_block(block: MarkdownBlock) -> str:
    if block.type == "heading":
        level = min(max(block.level or 2, 1), 6)
        # 标题块内部可能带换行（OCR/排版把编号与标题文本拆成两行）；
        # 直接序列化会把后半段漏到正文。仅在标题渲染时归一为单行，
        # 段落换行策略保持不变。
        text = " ".join(block.text.split())
        return f"{'#' * level} {text}".strip()

    if block.type == "image":
        alt = block.caption.strip() or block.text.strip() or "PDF image"
        # alt 来自 PDF 原文，反斜杠与方括号必须作为字面字符保留。
        alt = alt.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
        # path 是原始文件路径；空格、#、?、% 与括号不能参与 Markdown/URI 语法。
        path = quote(block.path, safe="/")
        return f"![{alt}]({path})"

    if block.type == "table":
        return block.text.strip()

    if block.type == "page_break":
        page = block.page if block.page is not None else ""
        return f"<!-- page {page} -->".strip()

    if block.type == "list":
        text = block.rich_text.strip() if block.rich_text.strip() else block.text.strip()
        return _render_list_block(text)

    if block.type == "paragraph":
        text = block.rich_text.strip() if block.rich_text.strip() else block.text.strip()
        return _escape_paragraph_line_starts(text)
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
