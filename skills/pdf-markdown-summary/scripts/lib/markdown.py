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


def _escape_inline_literals(
    text: str,
    *,
    has_markup: bool,
    plain_text: Optional[str] = None,
) -> str:
    """转义字面 Markdown 标记，或原样保留已生成的 rich_text。

    rich_text 由 format_spans_as_markdown 生成，生产时已经区分样式标记与
    字面字符（字面星号/反斜杠全部转义），并通过 strip_inline_markdown 与
    plain_text 做逐字校验；渲染阶段不再用字符对齐反推哪些星号是标记，
    避免 x**2、\\server 这类重复字符被错误解释（CHK-094）。
    """
    if has_markup:
        return text
    return text.replace("\\", "\\\\").replace("*", "\\*")


def _escape_html_like_text(text: str) -> str:
    """把会被 CommonMark 当作内联 HTML 的尖括号文本转义为实体。"""
    return re.sub(
        r"<(?=/?[A-Za-z][A-Za-z0-9-]*(?:\s|/?>))",
        "&lt;",
        text,
    )


def _escape_paragraph_line_starts(
    text: str, *, has_markup: bool = False, plain_text: Optional[str] = None,
) -> str:
    if text.lstrip().startswith("```"):
        return text
    text = _escape_inline_literals(
        text, has_markup=has_markup, plain_text=plain_text,
    )
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
    text = re.sub(
        r"^([ \t]{0,3})(>)",
        lambda match: f"{match.group(1)}\\{match.group(2)}",
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"^([ \t]{0,3})(#+)(?=[ \t]|$)",
        lambda match: f"{match.group(1)}\\{match.group(2)}",
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"^([ \t]{0,3})(=+)(?=[ \t]*$)",
        lambda match: f"{match.group(1)}\\{match.group(2)}",
        text,
        flags=re.MULTILINE,
    )
    return _escape_html_like_text(text)


_UNICODE_LIST_BULLET_LINE_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<open>\*{1,3}|_{1,3})?"
    r"(?P<bullet>[•▪▫◦‣⁃➢➣➤])(?P<close>(?P=open))?\s*"
)
_ALPHA_LIST_MARKER_LINE_RE = re.compile(
    r"^([ \t]*)((?:\((?:[A-Za-z]|[ivxlcdm]{1,4})\)|"
    r"(?:[A-Za-z]|[ivxlcdm]{1,4})\)))\s*",
    re.IGNORECASE,
)


def _normalize_unicode_bullet_line(line: str) -> str:
    match = _UNICODE_LIST_BULLET_LINE_RE.match(line)
    if not match:
        return line
    opening = match.group("open") or ""
    closing = match.group("close") or ""
    item_style = opening if opening and not closing else ""
    return f"{match.group('indent')}- {item_style}{line[match.end():]}"


def _render_list_block(
    text: str, *, has_markup: bool = False, plain_text: Optional[str] = None,
) -> str:
    # 行首 "* " 是列表标记而非字面星号，先统一成 "-" 再转义字面内容，
    # 否则 BUG-211 同源的转义会把项目符号本身转成正文。
    # rich_text 在生成期已把字面星号写成 "\*"（BUG-217），项目符号也不例外，
    # 带不带反斜杠都要认（CHK-095/BUG-233）。
    if has_markup:
        # 样式从圆点跨到项目文字时，先输出列表标记，再把开标记移到正文。
        # 样式只包圆点时，圆点被替换，配对标记也一起移除。
        text = re.sub(
            r"(?m)^(?P<indent>[ \t]*)(?P<style>\*{1,3})\\\*(?P<close>(?P=style))?[ \t]+",
            lambda m: m["indent"] + "- " + ("" if m["close"] else m["style"]),
            text,
        )
    text = re.sub(r"(?m)^([ \t]*)\\?\*(?=[ \t])", r"\1-", text)
    text = _escape_inline_literals(
        text, has_markup=has_markup, plain_text=plain_text,
    )
    text = _escape_html_like_text(text)
    lines = []
    for line_index, line in enumerate(text.splitlines()):
        line = _normalize_unicode_bullet_line(line)
        line = _ALPHA_LIST_MARKER_LINE_RE.sub(r"\1- \2 ", line)
        line = re.sub(
            r"^(?P<prefix>[ \t]*(?:- |\d+[.)][ \t]+)?)(?P<marker>#+)(?=[ \t]|$)",
            lambda match: f"{match.group('prefix')}\\{match.group('marker')}",
            line,
        )
        line = re.sub(
            r"^(?P<prefix>[ \t]*(?:- |\d+[.)][ \t]+)?)(?P<marker>=+)(?=[ \t]*$)",
            lambda match: f"{match.group('prefix')}\\{match.group('marker')}",
            line,
        )
        if line_index > 0 and re.match(r"^\d{1,9}[.)][ \t]", line):
            lines.append("")
        lines.append(line)
    return "\n".join(lines).strip()


def render_block(block: MarkdownBlock) -> str:
    if block.type == "heading":
        level = min(max(block.level or 2, 1), 6)
        # 标题块内部可能带换行（OCR/排版把编号与标题文本拆成两行）；
        # 直接序列化会把后半段漏到正文。仅在标题渲染时归一为单行，
        # 段落换行策略保持不变。
        text = " ".join(block.text.split())
        # 标题文字同样来自 PDF 原文：字面星号、反斜杠与 HTML 形态尖括号
        # 必须转义，否则强调/转义/内联 HTML 会吞掉原字符（BUG-221）。
        text = _escape_inline_literals(text, has_markup=False)
        return f"{'#' * level} {_escape_html_like_text(text)}".strip()

    if block.type == "image":
        alt = block.caption.strip() or block.text.strip() or "PDF image"
        # alt 来自 PDF 原文，反斜杠与方括号必须作为字面字符保留。
        alt = alt.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
        # path 是原始文件路径；空格、#、?、% 与括号不能参与 Markdown/URI 语法。
        path = quote(block.path, safe="/")
        return f"![{alt}]({path})"

    if block.type == "table":
        # 表格文本同样是 PDF 原文，按普通文本转义字面标记（BUG-221）。
        text = _escape_inline_literals(block.text.strip(), has_markup=False)
        return _escape_html_like_text(text)

    if block.type == "page_break":
        page = block.page if block.page is not None else ""
        return f"<!-- page {page} -->".strip()

    if block.type == "list":
        text = block.rich_text.strip() if block.rich_text.strip() else block.text.strip()
        return _render_list_block(
            text,
            has_markup=bool(block.rich_text.strip()),
            plain_text=block.text.strip(),
        )

    if block.type == "paragraph":
        text = block.rich_text.strip() if block.rich_text.strip() else block.text.strip()
        return _escape_paragraph_line_starts(
            text, has_markup=bool(block.rich_text.strip()), plain_text=block.text,
        )
    return block.text.strip()


def render_markdown(document: MarkdownDocument) -> str:
    parts = [f"# {document.title.strip()}", ""]
    # 同一页内连续 list 块按缩进 x0 维护栈：每个块与最近的上级比较，
    # 同级兄弟块共享同一深度（只与上一块比较会让第二个兄弟丢失缩进）。
    list_stack: List[float] = []
    last_list_page: Optional[int] = None
    last_list_column: Optional[int] = None
    last_list_bbox: List[float] = []
    for block in document.blocks:
        rendered = render_block(block)
        if block.type == "list":
            bbox = (block.meta or {}).get("bbox") or []
            column = (block.meta or {}).get("column", -1)
            column = -1 if column is None else int(column)
            # 换页或换栏都意味着新的列表上下文：右栏列表即使 x0 更大、
            # 纵向位置更低，也不能继承左栏最后一项的缩进栈（CHK-094）。
            if (
                block.page != last_list_page
                or (last_list_column is not None and column != last_list_column)
            ):
                list_stack = []
                last_list_bbox = []
            if len(bbox) >= 4:
                x0 = float(bbox[0])
                # 只有位于上一 list 块下方的块才是子项；并排的右栏列表
                # （同页、y 起点相同或更靠上）按新的顶层列表处理。
                side_by_side = (
                    len(last_list_bbox) >= 4
                    and float(bbox[1]) <= float(last_list_bbox[1]) + 2.0
                )
                if side_by_side:
                    list_stack = []
                while list_stack and x0 <= list_stack[-1] + 4.0:
                    list_stack.pop()
                depth = min(len(list_stack), 3)
                list_stack.append(x0)
                if depth:
                    rendered = "\n".join(
                        f"{'    ' * depth}{line}" for line in rendered.splitlines()
                    )
                last_list_bbox = [float(value) for value in bbox[:4]]
            else:
                list_stack = []
                last_list_bbox = []
            last_list_page = block.page
            last_list_column = column
        elif block.type != "page_break":
            list_stack = []
            last_list_page = None
            last_list_column = None
            last_list_bbox = []
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
