#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Commit 10: 文本提取

从 extract_pdf_assets.py 抽离的文本提取相关代码。

包含：
- try_extract_text: 尝试提取 PDF 文本
- pre_validate_pdf: PDF 预验证
- gather_structured_text: 结构化文本提取
- estimate_body_font_size: 正文字号估计（字符加权的并簇众数，标题层级判定用）
- extract_text_with_format: 带格式的文本提取（构建版式模型）

注：图表上下文构建（build_figure_contexts）已迁移至 figure_contexts.py。
"""

from __future__ import annotations

import json
import logging
import os
import re
import string
import unicodedata
from bisect import bisect_right
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from statistics import median
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Tuple

from .pdf_backend import PDFDocument, create_rect, managed_pdf_document, open_pdf

# 避免循环导入
if TYPE_CHECKING:
    from .models import (
        AttachmentRecord,
        DocumentLayoutModel,
        EnhancedTextUnit,
        FigureContext,
        FigureMention,
        GatheredParagraph,
        GatheredText,
        PDFValidationResult,
    )

# 模块日志器
logger = logging.getLogger(__name__)

_SECTION_HEADING_RE = re.compile(r"^\d+(?:\.\d+)*\.?\s+[A-Za-z].{2,}")

# 中文编号模式：第X章/第X节、一、（一）等；数字编号后允许直接跟中文
# （要求编号与正文之间有空白或编号分隔符，避免把「2023年」误判为标题）
_CJK_SECTION_HEADING_RE = re.compile(
    r"^(?:第[0-9一二三四五六七八九十百]+[章节篇部]"
    r"|[0-9一二三四五六七八九十]+[、.．]"
    r"|[（(][0-9一二三四五六七八九十]+[）)]"
    # 数字编号+空白后，下一个字符必须是字母或 CJK——「1 - P(E)」这类
    # 粗体公式片段的编号后紧跟标点，不能算标题
    r"|\d+(?:\.\d+)*\.?\s+(?=[A-Za-z\u4e00-\u9fff]))"
    r"\s*\S"
)

# CJK 统一表意文字区间（基本区），用于把中文字计入标题「字母」计数
_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")

# 罗马数字/字母编号标题（IEEE 会议论文常见格式）：I. Introduction、
# IV. Experiments、A. Appendix。句点+空格后须跟字母；没有这条放行，
# 这些标题会走到句点检查被当成普通句子误杀（基准 8 份全是阿拉伯数字
# 编号，golden 覆盖不到）。
_ROMAN_ALPHA_HEADING_RE = re.compile(r"^(?:[IVXLCDM]{1,5}|[A-Z])\.\s+[A-Za-z]")

# 正文字号的粗体统计表头常写成「P. Value」「N. Samples」
# 「M. Mean」，外形与 A. Appendix / IV. Experiments 相同。编号标题
# 需要保留小字号支持，因此只对明确的度量名称做定向排除。
_SMALL_TABLE_METRIC_RE = re.compile(
    r"^[A-Z]\.\s+(?:p[- ]?values?|values?|means?|medians?|modes?|samples?"
    r"|counts?|scores?|std\.?|stdev|variances?|errors?|rates?)\b",
    re.IGNORECASE,
)


def looks_like_structural_heading(
    text: str,
    *,
    is_bold: bool,
    font_size: float,
    body_font_size: float = 0.0,
    has_paragraph_spacing: bool = False,
) -> bool:
    """短粗体不一定是章节标题。

    页码、公式、单字母、裸节号，以及正文字号的表头（FEELING ITEMS）
    会把 Markdown 切碎。粗体编号标题任何字号都保留；非粗体数字/CJK 编号标题需明显大于正文；
    其余标题要求明显大于正文，或略大于正文且具有独立行与明显段间距的联合排版证据。
    中文字符计入标题长度计数，编号后允许直接跟中文（如「1 绪论」「第一章 绪论」）。
    """
    stripped = (text or "").strip()
    if not stripped or len(stripped) >= 120:
        return False
    cjk_chars = _CJK_CHAR_RE.findall(stripped)
    if len(stripped) <= 2 and not cjk_chars:
        return False
    if stripped[0] in ".,;:)]}-–—":
        return False
    if re.fullmatch(r"\d{1,4}", stripped) or re.fullmatch(r"\d+(?:\.\d+)*", stripped):
        return False
    numbered = bool(
        _SECTION_HEADING_RE.match(stripped)
        or _CJK_SECTION_HEADING_RE.match(stripped)
        or _ROMAN_ALPHA_HEADING_RE.match(stripped)
    )
    if sum(_has_list_marker_line(line) for line in stripped.splitlines()) >= 2:
        return False
    if not is_bold and not (
        (_SECTION_HEADING_RE.match(stripped) or _CJK_SECTION_HEADING_RE.match(stripped))
        and font_size >= max(11.5, body_font_size * 1.12)
    ):
        return False
    if font_size < 11.5 and _SMALL_TABLE_METRIC_RE.match(stripped):
        return False
    if numbered:
        if len(stripped) < 50:
            return True
        # BUG-190：长度放宽到 120 后，表格数据行与算法伪代码（如
        # 「33.2 (MuQ-MuLan) …」「6 return x with xi,j = 1 if …」）也会命中
        # 编号前缀。长编号标题要求字号不低于正文字号的 90%；正文里的数据行、
        # 伪代码通常明显小于正文字号，正确恢复的长章节标题则与正文同号或更大。
        if body_font_size > 0 and font_size < body_font_size * 0.9:
            return False
        title = re.sub(r"^\S+\s+", "", stripped, count=1)
        return not (
            title.endswith((".", "。", "!", "！", "?", "？", ";", "；"))
            or re.search(r"[.!?。！？]\s+\S", title)
        )
    if re.match(r"^\d", stripped) or len(stripped) >= 50:
        return False
    min_unnumbered_size = max(10.5, body_font_size * 1.12) if body_font_size > 0 else 11.5
    if font_size < min_unnumbered_size:
        if not (
            has_paragraph_spacing
            and body_font_size > 0
            and font_size >= 10.5
            and font_size > body_font_size
        ):
            return False
    letters = re.findall(r"[A-Za-z]", stripped)
    if cjk_chars:
        # 中文标题通常 2-8 字，至少 2 个 CJK 字符即可
        if len(cjk_chars) < 2:
            return False
    elif len(letters) < 4:
        return False
    if re.search(r"[.。]\s+\S", stripped):
        return False
    return True


_NUMBERED_HEADING_LEVEL_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+\S")
_CJK_CHAPTER_LEVEL_RE = re.compile(r"^第[0-9一二三四五六七八九十百]+[章节篇部]")
_ROMAN_HEADING_LEVEL_RE = re.compile(r"^[IVXLCDM]{1,5}\.\s+[A-Za-z]")
_ALPHA_HEADING_LEVEL_RE = re.compile(r"^[A-Z]\.\s+[A-Za-z]")


def infer_heading_level(
    text: str,
    *,
    font_size: float = 10.0,
    typical_font_size: float = 10.0,
) -> int:
    """从编号深度或字号比推断 Markdown 标题层级（1..6）。

    阿拉伯数字：``3``→2、``3.2``→3、``3.2.1``→4（深度+1，文档标题留给 H1）。
    罗马章节 ``I.``→2；字母小节 ``A.``→3。无编号时按相对正文字号回退。

    typical_font_size 是无编号标题比较字号比的正文基准；gather_structured_text
    传入的是 body_font_size（字符加权并簇众数），不是按 span 计数的算术平均。
    """
    stripped = (text or "").strip()
    if not stripped:
        return 2
    numbered = _NUMBERED_HEADING_LEVEL_RE.match(stripped)
    if numbered:
        depth = len(numbered.group(1).split("."))
        return min(6, max(2, depth + 1))
    if _CJK_CHAPTER_LEVEL_RE.match(stripped):
        return 2
    cjk_numbered = re.match(r"^(\d+(?:\.\d+)*)\s+(?=[\u4e00-\u9fff])", stripped)
    if cjk_numbered:
        depth = len(cjk_numbered.group(1).split("."))
        return min(6, max(2, depth + 1))
    if _ROMAN_HEADING_LEVEL_RE.match(stripped):
        return 2
    if _ALPHA_HEADING_LEVEL_RE.match(stripped):
        return 3
    # 无编号标题：明显大于正文 → H1，其余默认 H2（避免字号噪声切成 H3）
    if typical_font_size > 0:
        ratio = float(font_size) / float(typical_font_size)
        if ratio > 1.45:
            return 1
    return 2


def _span_has_bold_flag(span: Dict[str, Any]) -> bool:
    """结构判定用的粗体：只认 PDF 粗体标志位（flags bit 4）。

    标题分类与版式模型字重必须用它。字体名启发式会把图内的 DejaVuSans-Bold
    标签也算作粗体，进而被分类为 title_h3 并改变裁剪依据；它只服务于
    行内 Markdown 样式（_span_is_bold）。
    """
    return bool(int(span.get("flags", 0) or 0) & (1 << 4))


# 字体名里的粗体字样（行内样式专用）
_BOLD_NAME_TOKENS = ("bold", "black", "heavy", "medi")
# LaTeX 粗体字族的名字里没有 bold 字样（CMBX10、CMMIB10、CMBSY10、SFBX1095、txbsys），
# 按去掉子集前缀后的字族前缀识别：Computer Modern、SF、TX 的粗体族
_BOLD_NAME_PREFIXES = ("cmb", "cmmib", "cmssbx", "sfbx", "txb")


def _span_is_bold(span: Dict[str, Any]) -> bool:
    """行内样式用的粗体：标志位或字体名。

    字体名只在这里使用。标题判定与版式模型的字重仍只认标志位
    （_span_has_bold_flag）：字体名启发式会把图内的 DejaVuSans-Bold 标签算成
    粗体，进而被分类为标题单元并改变裁剪依据。
    """
    flags = int(span.get("flags", 0) or 0)
    font = str(span.get("font", "") or "").strip().lower()
    if flags & (1 << 4) or any(token in font for token in _BOLD_NAME_TOKENS):
        return True
    family = font.rsplit("+", 1)[-1]  # 去掉子集前缀，如 ABCDEF+CMBX10
    return family.startswith(_BOLD_NAME_PREFIXES)


def _span_is_italic(span: Dict[str, Any]) -> bool:
    """行内样式用的斜体：标志位或字体名。"""
    flags = int(span.get("flags", 0) or 0)
    font = str(span.get("font", "") or "").lower()
    return bool(flags & (1 << 1)) or any(
        token in font for token in ("italic", "oblique")
    )


_STYLE_MARKERS = {"b": "**", "i": "*", "bi": "***"}


def _escape_literal_markdown(text: str) -> str:
    """把纯文本中的字面星号与反斜杠转义，样式标记不经过本函数。"""
    return text.replace("\\", "\\\\").replace("*", "\\*")


def _ends_with_odd_backslashes(text: str) -> bool:
    count = 0
    for ch in reversed(text):
        if ch != "\\":
            break
        count += 1
    return count % 2 == 1


def _char_class(ch: str) -> str:
    """CommonMark 侧翼判定用的字符类别。

    space（含行首、行尾）、punct（确定的标点）、symbol（数学符号、emoji 等：
    各渲染器对它们是否按标点处理并不一致）、word（字母、数字、组合符号、
    控制字符等其余非空白字符）。
    """
    if not ch or ch.isspace():
        return "space"
    category = unicodedata.category(ch)
    if ch in string.punctuation or category.startswith("P"):
        return "punct"
    if category.startswith("S"):
        return "symbol"
    return "word"


def _star_marker_is_unambiguous(
    prev: str, first: str, last: str, after: str, joined_last: str = ""
) -> bool:
    """样式 run 的星号标记能否被 CommonMark 唯一解析。

    prev / after 是标记外的相邻字符（行首、行尾为空串）；joined_last 非空表示
    本 run 紧跟在一个不同样式的星号 run 之后，两个标记会连成 "***"。

    - 开标记后不是文字字符时，外侧须是间隔或确定的标点；
    - 闭标记前不是文字字符时，后面须是间隔或确定的标点；
    - 与另一个星号 run 紧邻时，交界两侧必须都是文字字符。
    """
    if joined_last and not (
        _char_class(joined_last) == "word" and _char_class(first) == "word"
    ):
        return False
    opener_ok = _char_class(first) == "word" or _char_class(prev) in ("space", "punct")
    closer_ok = _char_class(last) == "word" or _char_class(after) in ("space", "punct")
    return opener_ok and closer_ok


def _trailing_marker_char_needs_escape(text: str) -> str:
    """段尾紧贴开标记的字面星号/下划线（已转义的除外），无需转义时返回空串。"""
    if not text or text[-1] not in "*_" or _ends_with_odd_backslashes(text[:-1]):
        return ""
    return text[-1]


def strip_inline_markdown(rich: str) -> str:
    """还原 format_spans_as_markdown 输出对应的纯文本（保真自检用，不参与渲染）。"""
    out: List[str] = []
    i, n = 0, len(rich)
    while i < n:
        ch = rich[i]
        if ch == "\\" and i + 1 < n and rich[i + 1] in "\\*_":
            out.append(rich[i + 1])
            i += 2
            continue
        if ch == "*":
            j = i
            while j < n and rich[j] == "*":
                j += 1
            before = rich[i - 1] if i else ""
            after = rich[j] if j < n else ""
            touches_text = (after and not after.isspace()) or (before and not before.isspace())
            if j - i <= 3 and touches_text:
                i = j  # 样式标记
                continue
        out.append(ch)
        i += 1
    return "".join(out)


# 剔除 PDF 文本层中偶发的 C0 控制字符与 DEL（如 NUL/SOH/DLE/DC1），保留 \t/\n/\r。
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# 单次运行内的只读扫描复用上下文（按规范化后的 pdf_path 隔离）
_SCAN_CONTEXT: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "pdf_summary_scan_context", default=None
)


def sanitize_extracted_text(text: str) -> str:
    """剔除提取文本中的 C0 控制字符与 DEL，保留换行、回车与制表符。"""
    if not text:
        return ""
    return _CONTROL_CHARS_RE.sub("", text)


@contextmanager
def reuse_scan_context(
    pdf_path: str,
    *,
    validation: Optional[Any] = None,
    gathered: Optional["GatheredText"] = None,
    native_blocks: Optional[List[Dict[str, Any]]] = None,
) -> Iterator[None]:
    """在单次转换进程内临时共享同一 PDF 的预验证、结构化文本与原生块扫描结果。"""
    payload = {
        "pdf_path": os.path.abspath(pdf_path),
        "validation": validation,
        "gathered": gathered,
        "native_blocks": native_blocks,
    }
    token = _SCAN_CONTEXT.set(payload)
    try:
        yield
    finally:
        _SCAN_CONTEXT.reset(token)


def get_reusable_scan_context(pdf_path: str) -> Optional[Dict[str, Any]]:
    """若当前上下文存在且匹配目标 pdf_path，返回共享扫描结果；否则返回 None。"""
    ctx = _SCAN_CONTEXT.get()
    if ctx is None:
        return None
    if ctx.get("pdf_path") != os.path.abspath(pdf_path):
        return None
    return ctx


def format_spans_as_markdown(spans: List[Dict[str, Any]]) -> str:
    """将同行 spans 序列化为带行内粗斜体的 Markdown 片段。

    渲染后的文字必须与 spans 原文逐字一致，只多出样式：
    - 相邻同样式的 span 先合并，避免「* d**k*」这类断裂标记；
    - 标记只包住非空白字符，span 自带的首尾空白留在标记外
      （CommonMark 不把「** x **」识别为粗体）；
    - 标记会与相邻字符粘连、无法被唯一解析的 run 退回纯文本
      （见 _star_marker_is_unambiguous）：只丢样式，不丢字；
    - 样式 run 内的字面星号与反斜杠做转义；常规文本里紧贴标记的星号、下划线
      与反斜杠同样转义，否则标记会改变它们在 CommonMark 中的含义。
    """
    runs: List[List[Any]] = []
    for span in spans or []:
        text = str(span.get("text", "") or "")
        if not text:
            continue
        style = ("b" if _span_is_bold(span) else "") + ("i" if _span_is_italic(span) else "")
        if runs and runs[-1][0] == style:
            runs[-1][1] += text
        else:
            runs.append([style, text])

    parts: List[str] = []
    open_marker = False  # 输出正好停在一个样式 run 的闭标记上

    for idx, (style, raw) in enumerate(runs):
        lead = trail = ""
        core = raw
        if style:
            core = raw.strip()
            if core:
                lead = raw[: len(raw) - len(raw.lstrip())]
                trail = raw[len(raw.rstrip()):]
            else:
                style = ""  # 纯空白的样式 span 原样输出
                core = raw

        if lead:
            parts.append(lead)
            open_marker = False

        if style:
            # run 之后紧跟的字符：自身尾随空白，否则是下一个 run 的首字符
            after = trail[:1]
            if not after and idx + 1 < len(runs):
                after = runs[idx + 1][1][:1]
            prev = parts[-1][-1] if parts and parts[-1] else ""
            joined_last = ""
            if not lead and open_marker:
                joined_last = runs[idx - 1][1].rstrip()[-1:]
            if _star_marker_is_unambiguous(prev, core[0], core[-1], after, joined_last):
                core = _escape_literal_markdown(core)
                marker = _STYLE_MARKERS[style]
                if parts and _ends_with_odd_backslashes(parts[-1]):
                    parts[-1] += "\\"  # 行尾反斜杠会转义开标记
                elif not open_marker and parts:
                    ch = _trailing_marker_char_needs_escape(parts[-1])
                    if ch:
                        parts[-1] = parts[-1][:-1] + "\\" + ch  # 会并入开标记
                parts.append(marker + core + marker)
                open_marker = True
                core = ""

        if core:
            # 未进入样式标记的文本仍是 PDF 原文，星号/反斜杠按字面转义；
            # 与标记相邻的星号已由转义本身隔开，不再手工补反斜杠。
            escaped = _escape_literal_markdown(core)
            if open_marker and escaped.startswith("_"):
                escaped = "\\" + escaped  # 会并入闭标记
            parts.append(escaped)
            open_marker = False

        if trail:
            parts.append(trail)
            open_marker = False

    return "".join(parts)


def plain_text_from_lines(lines: List[Dict[str, Any]]) -> str:
    """拼接块内各行为纯文本（无 Markdown 标记，并剔除 C0 控制字符）。"""
    chunks: List[str] = []
    for line in lines or []:
        line_text = "".join(
            sanitize_extracted_text(str(sp.get("text", "") or ""))
            for sp in line.get("spans", [])
        )
        if line_text.strip():
            chunks.append(line_text)
    return "\n".join(chunks).strip()


def rich_text_from_lines(lines: List[Dict[str, Any]]) -> str:
    """拼接块内各行为行内 Markdown 文本（同步剔除 C0 控制字符）。"""
    chunks: List[str] = []
    for line in lines or []:
        clean_spans = [
            {**sp, "text": sanitize_extracted_text(str(sp.get("text", "") or ""))}
            for sp in line.get("spans", [])
        ]
        line_text = format_spans_as_markdown(clean_spans)
        if line_text.strip():
            chunks.append(line_text)
    return "\n".join(chunks).strip()


def iter_native_text_blocks(doc: Any) -> List[Dict[str, Any]]:
    """共享底层：按页收集原生文本块（bbox / lines / spans）。

    Markdown gathering 与版式模型提取共用此入口，避免各走一套 get_text('dict')。
    """
    blocks_out: List[Dict[str, Any]] = []
    page_count = len(doc)
    for pno in range(page_count):
        page = doc[pno]
        page_dict = page.get_text("dict") if hasattr(page, "get_text") else page.raw.get_text("dict")
        page_rect = page.rect if hasattr(page, "rect") else page.raw.rect
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            lines = block.get("lines", [])
            if not lines:
                continue
            plain = plain_text_from_lines(lines)
            if not plain:
                continue
            bbox = tuple(block.get("bbox", (0, 0, 0, 0)))
            blocks_out.append({
                "page": pno + 1,
                "page_index": pno,
                "bbox": bbox,
                "text": plain,
                "rich_text": rich_text_from_lines(lines),
                "lines": lines,
                "page_width": float(page_rect.width),
                "page_height": float(page_rect.height),
            })
    return blocks_out


def _block_has_paragraph_spacing(
    block: Dict[str, Any],
    all_blocks: List[Dict[str, Any]],
    font_size: float,
) -> bool:
    """独立行与前后重叠文本块之间是否有明显的段落间距。"""
    x0, y0, x1, y1 = (float(value) for value in block["bbox"])
    previous_gaps: List[float] = []
    following_gaps: List[float] = []
    for other in all_blocks:
        if other is block or int(other.get("page", 0)) != int(block.get("page", 0)):
            continue
        ox0, oy0, ox1, oy1 = (float(value) for value in other["bbox"])
        if min(x1, ox1) <= max(x0, ox0):
            continue
        if oy1 <= y0:
            previous_gaps.append(y0 - oy1)
        if oy0 >= y1:
            following_gaps.append(oy0 - y1)
    nearest_gaps = []
    if previous_gaps:
        nearest_gaps.append(min(previous_gaps))
    if following_gaps:
        nearest_gaps.append(min(following_gaps))
    return bool(nearest_gaps) and max(nearest_gaps) >= max(8.0, font_size * 0.75)


def classify_block_column(
    bbox: Tuple[float, float, float, float],
    page_width: float,
    *,
    is_dual_column: bool,
) -> Tuple[int, bool]:
    """返回 (column, is_full_width)。双栏通栏记 column=-1。"""
    if not is_dual_column or page_width <= 0:
        return -1, False
    x0, _y0, x1, _y1 = bbox
    width = max(0.0, x1 - x0)
    mid = page_width * 0.5
    spans_mid = x0 < mid - 8.0 and x1 > mid + 8.0
    wide = width >= page_width * 0.55
    if spans_mid and wide:
        return -1, True
    x_center = (x0 + x1) / 2.0
    return (0 if x_center < mid else 1), False


def _promote_centered_headings(
    paragraphs: List[Any],
    page_widths: Dict[int, float],
) -> None:
    """把下方确有左右两栏的页首居中短标题提升为通栏块。"""
    from collections import defaultdict

    by_page: Dict[int, List[Any]] = defaultdict(list)
    for para in paragraphs:
        by_page[para.page].append(para)
    for page, page_paras in by_page.items():
        page_width = float(page_widths.get(page, 0.0) or 0.0)
        if page_width <= 0:
            continue
        mid = page_width * 0.5
        for para in page_paras:
            if not para.is_heading or para.is_full_width:
                continue
            x0, _y0, x1, y1 = para.bbox
            if not (x0 < mid - 8.0 and x1 > mid + 8.0):
                continue
            below_columns = {
                column: any(
                    other is not para
                    and other.column == column
                    and not other.is_full_width
                    and other.bbox[1] >= y1 - 2.0
                    for other in page_paras
                )
                for column in (0, 1)
            }
            if all(below_columns.values()):
                para.column = -1
                para.is_full_width = True


def _promote_centered_interruptions(
    paragraphs: List[Any],
    page_widths: Dict[int, float],
) -> None:
    """上下均有双栏内容的居中显示块可作为栏带边界。"""
    from collections import defaultdict

    by_page: Dict[int, List[Any]] = defaultdict(list)
    for para in paragraphs:
        by_page[para.page].append(para)
    for page, page_paras in by_page.items():
        page_width = float(page_widths.get(page, 0.0) or 0.0)
        if page_width <= 0:
            continue
        mid = page_width * 0.5
        for para in page_paras:
            if para.is_heading or para.is_full_width or para.para_type != "paragraph":
                continue
            x0, y0, x1, y1 = para.bbox
            if not (x0 < mid - 8.0 and x1 > mid + 8.0):
                continue
            if abs((x0 + x1) / 2.0 - mid) > page_width * 0.15:
                continue
            evidence = {
                column: (
                    any(
                        other is not para and other.column == column
                        and not other.is_full_width and other.bbox[3] <= y0 + 2.0
                        for other in page_paras
                    ),
                    any(
                        other is not para and other.column == column
                        and not other.is_full_width and other.bbox[1] >= y1 - 2.0
                        for other in page_paras
                    ),
                )
                for column in (0, 1)
            }
            if all(above and below for above, below in evidence.values()):
                para.column = -1
                para.is_full_width = True


def sort_paragraphs_reading_order(
    paragraphs: List[Any],
    *,
    is_dual_column: bool,
    dual_column_pages: Optional[set[int]] = None,
    table_positions: Optional[Dict[int, Tuple[float, float]]] = None,
) -> List[Any]:
    """按栏带排序；网格内使用单元格行、列坐标代替文字坐标。"""
    table_positions = table_positions or {}

    def position(para: Any) -> Tuple[float, float, float, float]:
        y, x = table_positions.get(id(para), (para.bbox[1], para.bbox[0]))
        return y, x, para.bbox[1], para.bbox[0]

    if not is_dual_column or not paragraphs:
        return sorted(paragraphs, key=lambda p: (p.page, *position(p)))

    from collections import defaultdict

    by_page: Dict[int, List[Any]] = defaultdict(list)
    for para in paragraphs:
        by_page[para.page].append(para)

    ordered: List[Any] = []
    for page in sorted(by_page):
        page_paras = by_page[page]
        if dual_column_pages is not None and page not in dual_column_pages:
            ordered.extend(sorted(page_paras, key=position))
            continue
        tagged: List[Tuple[Any, int]] = []
        for para in page_paras:
            col = getattr(para, "column", -1)
            if getattr(para, "is_full_width", False):
                col = -1
            tagged.append((para, col))
        tagged.sort(key=lambda item: position(item[0]))

        idx = 0
        while idx < len(tagged):
            para, col = tagged[idx]
            if col == -1:
                ordered.append(para)
                idx += 1
                continue
            band: List[Tuple[Any, int]] = []
            while idx < len(tagged) and tagged[idx][1] != -1:
                band.append(tagged[idx])
                idx += 1
            left = sorted(
                (p for p, c in band if c == 0),
                key=position,
            )
            right = sorted(
                (p for p, c in band if c == 1),
                key=position,
            )
            ordered.extend(left)
            ordered.extend(right)
    return ordered


def collect_structure_warnings(paragraphs: List[Any], *, is_dual_column: bool) -> List[str]:
    """结构质量告警：编号标题层级塌缩、双栏通栏疑似错序。"""
    warnings: List[str] = []
    headings = [p for p in paragraphs if getattr(p, "is_heading", False)]
    depths: List[int] = []
    levels: List[int] = []
    for para in headings:
        text = (para.text or "").strip()
        match = _NUMBERED_HEADING_LEVEL_RE.match(text)
        if not match:
            continue
        depths.append(len(match.group(1).split(".")))
        levels.append(int(getattr(para, "heading_level", 0) or 0))
    if len(set(depths)) >= 2 and levels and len(set(levels)) == 1:
        warnings.append("heading_level_collapsed")

    if is_dual_column:
        from collections import defaultdict

        by_page: Dict[int, List[Any]] = defaultdict(list)
        for para in paragraphs:
            by_page[para.page].append(para)
        for page, page_paras in by_page.items():
            full = [p for p in page_paras if getattr(p, "is_full_width", False)]
            left = [
                p for p in page_paras
                if getattr(p, "column", None) == 0 and not getattr(p, "is_full_width", False)
            ]
            if not full or not left:
                continue
            # 通栏块 y 明显在左栏之上，却排在任一左栏段落后 → 阅读顺序告警
            min_left_y = min(p.bbox[1] for p in left)
            page_order = {id(p): i for i, p in enumerate(page_paras)}
            for span in full:
                if span.bbox[1] + 2.0 < min_left_y:
                    left_before = [
                        p for p in left
                        if page_order.get(id(p), 0) < page_order.get(id(span), 0)
                    ]
                    if left_before:
                        warnings.append(f"reading_order_full_width_page_{page}")
                        break
    return warnings


# ============================================================================
# PDF 文本提取
# ============================================================================

def try_extract_text(pdf_path: str, out_text: Optional[str]) -> Optional[str]:
    """
    尝试提取 PDF 的纯文本内容。

    Args:
        pdf_path: PDF 文件路径
        out_text: 输出文本文件路径（可选）

    Returns:
        输出文件路径，如果提取失败则返回 None
    """
    try:
        text_parts = []
        with open_pdf(pdf_path) as doc:
            for page in doc:
                text_parts.append(sanitize_extracted_text(page.get_text("text")))
        full_text = sanitize_extracted_text("\n\n".join(text_parts))

        if out_text:
            out_dir = os.path.dirname(out_text)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            with open(out_text, "w", encoding="utf-8") as f:
                f.write(full_text)
            logger.info(f"Wrote text: {out_text} ({len(full_text)} chars)")
            return out_text
        return None
    except Exception as e:
        logger.warning(f"Text extraction failed: {e}")
        return None


# ============================================================================
# PDF 预验证
# ============================================================================

def pre_validate_pdf(pdf_path: str) -> "PDFValidationResult":
    """
    预验证 PDF 文件，检测潜在问题。

    检测内容：
    - 文件是否存在且可读
    - 是否加密
    - 是否有文本层
    - 页数和文件大小

    Args:
        pdf_path: PDF 文件路径

    Returns:
        PDFValidationResult 对象
    """
    from .models import PDFValidationResult

    warnings: List[str] = []
    errors: List[str] = []

    if not os.path.exists(pdf_path):
        return PDFValidationResult(
            is_valid=False, page_count=0, has_text_layer=False,
            text_layer_ratio=0.0, is_encrypted=False, pdf_version="",
            file_size_mb=0.0, warnings=[], errors=["File not found"]
        )

    file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)

    try:
        doc: PDFDocument = open_pdf(pdf_path)
    except Exception as e:
        return PDFValidationResult(
            is_valid=False, page_count=0, has_text_layer=False,
            text_layer_ratio=0.0, is_encrypted=False, pdf_version="",
            file_size_mb=file_size_mb, warnings=[], errors=[f"Cannot open PDF: {e}"]
        )

    try:
        raw_doc = doc.raw
        page_count = doc.page_count
        is_encrypted = bool(getattr(raw_doc, "is_encrypted", False))

        try:
            pdf_version = raw_doc.metadata.get("format", "unknown") if raw_doc.metadata else "unknown"
        except Exception as e:
            logger.warning(f"Failed to read PDF metadata: {e}", extra={'stage': 'pre_validate_pdf'})
            pdf_version = "unknown"

        if is_encrypted:
            try:
                unlock_result = raw_doc.authenticate("")
                if unlock_result:
                    warnings.append("PDF was encrypted but accessible with empty password")
                    is_encrypted = False
                else:
                    try:
                        _ = doc[0].get_text("text")[:100]
                        warnings.append("PDF is marked as encrypted but content is readable")
                    except Exception as e:
                        # 空密码也解不开且连第 0 页都读不出：后续必然在 doc[pno]
                        # 抛裸异常，必须升级为 error 让预检判定为无效。
                        errors.append(f"PDF is encrypted and cannot be opened: {e}")
            except Exception as e:
                warnings.append(f"PDF is encrypted; extraction may be incomplete. detail={e}")

        if page_count == 0:
            # 0 页 PDF 会通过后续所有采样循环，直到 doc[0] 才炸；提前判无效。
            errors.append("PDF has no pages")

        pages_with_text = 0
        scan_text_pages = []
        sample_pages = min(10, page_count)

        for pno in range(sample_pages):
            try:
                page = doc[pno]
                text = page.get_text("text").strip()
                if len(text) > 50:
                    pages_with_text += 1
                    from .extract_helpers import is_page_background_image
                    if any(is_page_background_image(create_rect(*image["bbox"]), page.rect)
                           for image in page.raw.get_image_info()):
                        scan_text_pages.append(pno + 1)
            except Exception as e:
                logger.warning(
                    f"Failed to read text layer on page {pno + 1}: {e}",
                    extra={'page': pno + 1, 'stage': 'pre_validate_pdf'}
                )

        text_layer_ratio = pages_with_text / sample_pages if sample_pages > 0 else 0.0
        has_text_layer = text_layer_ratio > 0.3

        if not has_text_layer:
            warnings.append("PDF may be scanned/image-only (limited text layer detected)")
        if scan_text_pages:
            warnings.append(
                "Possible scanned pages with OCR text layer (sample pages: "
                + ", ".join(map(str, scan_text_pages))
                + "); text presence does not guarantee OCR accuracy"
            )

        if page_count > 100:
            warnings.append(f"Large document ({page_count} pages), extraction may be slow")

        if file_size_mb > 50:
            warnings.append(f"Large file ({file_size_mb:.1f} MB), processing may be slow")

        is_valid = len(errors) == 0

        return PDFValidationResult(
            is_valid=is_valid,
            page_count=page_count,
            has_text_layer=has_text_layer,
            text_layer_ratio=text_layer_ratio,
            is_encrypted=is_encrypted,
            pdf_version=pdf_version,
            file_size_mb=file_size_mb,
            warnings=warnings,
            errors=errors
        )

    except Exception as e:
        return PDFValidationResult(
            is_valid=False, page_count=0, has_text_layer=False,
            text_layer_ratio=0.0, is_encrypted=False, pdf_version="",
            file_size_mb=file_size_mb, warnings=[], errors=[f"Validation error: {e}"]
        )
    finally:
        try:
            doc.close()
        except Exception as close_e:
            logger.warning(f"Failed to close PDF after validation error: {close_e}", extra={'stage': 'pre_validate_pdf'})


# ============================================================================
# 正文字号估计
# ============================================================================

# 参与估计的字号范围（pt）：上标、脚注编号、封面美术字都排除在外
BODY_FONT_SIZE_RANGE_PT = (6.0, 20.0)
# 并簇容差（pt）：LaTeX 的同一个名义字号在 PyMuPDF 里会拆成相差约 0.1pt 的两个值
FONT_SIZE_CLUSTER_TOLERANCE_PT = 0.15


def estimate_body_font_size(chars_by_size: Dict[float, int]) -> float:
    """正文字号：按字符数加权的众数，取之前先把相近字号并成一簇。

    typical_font_size 是 8-14pt 全部 span 字号的算术平均，按 span 计数；表格和
    脚注里的小字号 span 又多又短，会把均值拉偏。这里改按字符数加权，并在取众数前
    把相差不超过 0.15pt 的字号并簇（单值众数会在 9.96 与 10.06 这类拆分的名义
    字号之间随意选一个）。返回字符最多的一簇的字符加权中心，并列时取字号小的一簇。

    只用于 Markdown 标题层级判定，不进入版式模型（图表裁剪的依据）。

    Args:
        chars_by_size: 字号（保留两位小数）到该字号 span 字符总数的映射

    Returns:
        正文字号估计值；没有任何可用字号时返回 0.0
    """
    low, high = BODY_FONT_SIZE_RANGE_PT
    usable = {
        size: chars for size, chars in chars_by_size.items()
        if chars > 0 and low <= size <= high
    }
    if not usable:
        return 0.0
    tolerance = round(FONT_SIZE_CLUSTER_TOLERANCE_PT * 100)
    clusters: List[List[Tuple[float, int]]] = []
    for size in sorted(usable):
        if clusters and round(size * 100) - round(clusters[-1][-1][0] * 100) <= tolerance:
            clusters[-1].append((size, usable[size]))
        else:
            clusters.append([(size, usable[size])])
    best = max(
        clusters,
        key=lambda cluster: (sum(chars for _size, chars in cluster), -cluster[0][0]),
    )
    total = sum(chars for _size, chars in best)
    return round(sum(size * chars for size, chars in best) / total, 4)


def _page_line_samples(
    all_blocks: List[Dict[str, Any]],
    page_width: float,
) -> Dict[int, Dict[str, Any]]:
    """按页采样行级宽度、起点与字号，供文档级和页级双栏判定共用。"""
    page_samples: Dict[int, Dict[str, Any]] = {}
    for block in all_blocks:
        page_index = int(block.get("page_index", 0))
        sample = page_samples.setdefault(page_index, {
            "x0": [], "widths": [], "wide_chars": 0, "narrow_chars": 0, "wide_lines": 0,
            "wide_sizes": [], "narrow_sizes": [], "narrow_line_chars": [],
            "narrow_line_counts": [], "page_width": page_width,
        })
        pw = float(block.get("page_width") or page_width)
        ph = float(block.get("page_height") or 792.0)
        sample["page_width"] = pw
        block_line_count = len([
            line for line in block.get("lines") or []
            if any(
                str(span.get("text", "") or "").strip()
                for span in line.get("spans", [])
            )
        ])
        for line in block.get("lines") or []:
            lb = line.get("bbox")
            if not lb or len(lb) < 4:
                continue
            y_center = (float(lb[1]) + float(lb[3])) / 2.0
            if y_center < ph * 0.05 or y_center > ph * 0.95:
                continue
            line_text = "".join(
                sanitize_extracted_text(str(sp.get("text", "") or ""))
                for sp in line.get("spans", [])
            ).strip()
            if not line_text:
                continue
            spans = line.get("spans") or []
            main_span = max(spans, key=lambda sp: len(str(sp.get("text", "") or "")))
            font_size = float(main_span.get("size", 0) or 0)
            width = max(0.0, float(lb[2]) - float(lb[0]))
            if width >= pw * 0.55:
                sample["wide_chars"] += len(line_text)
                sample["wide_lines"] += 1
                sample["wide_sizes"].append(font_size)
            elif pw * 0.12 <= width < pw * 0.52 and len(line_text) >= 8:
                sample["narrow_chars"] += len(line_text)
                sample["x0"].append(float(lb[0]))
                sample["widths"].append(width)
                sample["narrow_sizes"].append(font_size)
                sample["narrow_line_chars"].append(len(line_text))
                sample["narrow_line_counts"].append(block_line_count)

    for sample in page_samples.values():
        if sample["wide_lines"] < 5 or not sample["narrow_sizes"]:
            continue
        body_size = float(median(sample["wide_sizes"]))
        keep = [
            index for index, size in enumerate(sample["narrow_sizes"])
            if size >= body_size * 0.85
        ]
        if len(keep) != len(sample["narrow_sizes"]):
            sample["x0"] = [sample["x0"][index] for index in keep]
            sample["widths"] = [sample["widths"][index] for index in keep]
            sample["narrow_line_chars"] = [sample["narrow_line_chars"][index] for index in keep]
            sample["narrow_line_counts"] = [sample["narrow_line_counts"][index] for index in keep]
            sample["narrow_chars"] = sum(sample["narrow_line_chars"])
    return page_samples


def _page_is_wide_dominated(sample: Dict[str, Any]) -> bool:
    """满宽正文主导的页不提供双栏证据。

    字符占比之外再看窄行来源：表格/并排标签通常是大量单行块，而双栏正文
    段落一般由多行组成。仅靠 1.5 倍字符阈值会让「五行通栏正文 + 五行双列
    表格」通过双栏检测（CHK-094）。
    """
    if sample["wide_lines"] < 5:
        return False
    if sample["wide_chars"] > sample["narrow_chars"] * 1.5:
        return True
    line_counts = sample.get("narrow_line_counts") or []
    if not line_counts:
        return False
    median_lines = float(median(line_counts))
    return median_lines <= 1.5 and sample["narrow_chars"] >= sample["wide_chars"] * 0.5


# 两列之间的留白超过它（pt 与页宽比例取大者）就远超正常栏距：双栏正文的栏距
# 一般在 10～30pt，并排的表格列、左右分列的标签之间才留这么宽的空白。
_TABLE_COLUMN_GAP_MIN_PT = 40.0
_TABLE_COLUMN_GAP_PAGE_RATIO = 0.08
# 表格页上方的通栏正文至少这么多行；通栏标题通常只有一两行，且字号明显更大。
_TABLE_WIDE_BODY_LINES_MIN = 2
_TABLE_WIDE_BODY_SIZE_RATIO = 1.15


def _min_column_gap(
    x0_values: List[float],
    width_values: List[float],
    peaks: Tuple[float, float],
    page_width: float,
) -> Optional[float]:
    """两列之间的最小水平留白：右列最小起点减左列最大右缘。

    只统计起点落在左右栏位置附近的窄行，栏内的居中公式、右对齐编号等
    不参与；左列取最大右缘，所以右不齐的正文不会被当成宽留白。

    起点在左栏位置、右缘却越过右栏起点的行横跨两栏（通栏图的题注、跨栏
    的表头），两栏并排的正文里不会有这种行，不计入左列。计入的话，一条
    中等宽度的题注就能把留白拉成负数，让下面的并排内容被当成双栏正文。
    """
    left_peak, right_peak = peaks
    tolerance = max(12.0, page_width * 0.04)
    left_edges = [
        x0 + width for x0, width in zip(x0_values, width_values)
        if abs(x0 - left_peak) <= tolerance and x0 + width <= right_peak
    ]
    right_starts = [x0 for x0 in x0_values if abs(x0 - right_peak) <= tolerance]
    if not left_edges or not right_starts:
        return None
    return min(right_starts) - max(left_edges)


def _page_is_side_by_side_table(
    sample: Dict[str, Any],
    peaks: Optional[Tuple[float, float]] = None,
) -> bool:
    """同页有通栏正文、且两列之间留白远大于正常栏距：这是单栏排版里的并列表格。

    通栏正文指与窄行同量级字号的通栏行；通栏标题字号更大、只有一两行，不算。
    双栏正文的栏距窄，不会触发；没有通栏正文的页一律返回 False，交给原有
    判据（CHK-094 的稀疏双栏尾页左右两段之间留白也很大，不能只看留白）。
    """
    narrow_sizes = sample.get("narrow_sizes") or []
    body_size = float(median(narrow_sizes)) if narrow_sizes else 0.0
    wide_body_lines = sum(
        1 for size in sample.get("wide_sizes") or []
        if body_size <= 0 or size <= body_size * _TABLE_WIDE_BODY_SIZE_RATIO
    )
    if wide_body_lines < _TABLE_WIDE_BODY_LINES_MIN:
        return False
    page_width = float(sample.get("page_width") or 0.0)
    if page_width <= 0:
        return False
    if peaks is None:
        peaks = _column_peaks(sample["x0"], sample["widths"], page_width)
    if peaks is None:
        return False
    gap = _min_column_gap(sample["x0"], sample["widths"], peaks, page_width)
    return gap is not None and gap > max(_TABLE_COLUMN_GAP_MIN_PT, page_width * _TABLE_COLUMN_GAP_PAGE_RATIO)


def _page_offers_column_evidence(sample: Dict[str, Any]) -> bool:
    """这一页的窄行能否作为双栏正文的证据。"""
    if _page_is_wide_dominated(sample):
        return False
    return not _page_is_side_by_side_table(sample)


def _column_peaks(
    x0_values: List[float],
    width_values: List[float],
    page_width: float,
) -> Optional[Tuple[float, float]]:
    """20 桶 bisect_right 直方图 + 栏距/峰距校验，返回左右峰位置。"""
    if len(x0_values) < 6:
        return None

    bin_count = 20
    first_edge = min(x0_values)
    last_edge = max(x0_values)
    if first_edge == last_edge:
        return None
    bin_width = (last_edge - first_edge) / bin_count
    bins = [first_edge + i * bin_width for i in range(bin_count)] + [last_edge]
    hist = [0] * bin_count
    bin_values: List[List[float]] = [[] for _ in range(bin_count)]
    for value in x0_values:
        bin_idx = max(0, min(bin_count - 1, bisect_right(bins, value) - 1))
        hist[bin_idx] += 1
        bin_values[bin_idx].append(value)

    threshold = (sum(hist) / bin_count) * 1.5
    peaks_idx = [i for i, count in enumerate(hist) if count > threshold]
    if len(peaks_idx) < 2:
        return None

    top_peaks = sorted(peaks_idx, key=lambda i: hist[i], reverse=True)[:2]
    top_peaks.sort()
    left_count = hist[top_peaks[0]]
    right_count = hist[top_peaks[1]]
    if left_count < 3 or right_count < 3:
        return None
    if (left_count + right_count) < len(x0_values) * 0.40:
        return None

    # BUG-188：峰位置取桶内样本均值，而不是桶左边界。取桶左边界会把右峰最多
    # 左移一个桶宽（约峰间距/20）；两端对齐时中位行宽≈栏宽，等价于把栏距少算
    # 一个桶宽，栏距 10～18pt 的标准双栏会被判成单栏。
    peak1_x = sum(bin_values[top_peaks[0]]) / len(bin_values[top_peaks[0]])
    peak2_x = sum(bin_values[top_peaks[1]]) / len(bin_values[top_peaks[1]])
    peak_sep = peak2_x - peak1_x
    med_line_width = float(median(width_values))
    candidate_gap = peak_sep - med_line_width
    valid_gap = 0 < candidate_gap <= 0.30 * page_width
    valid_sep = 0.18 * page_width <= peak_sep <= 0.60 * page_width
    if not (valid_gap and valid_sep):
        return None
    return peak1_x, peak2_x


def detect_dual_column_from_blocks(
    all_blocks: List[Dict[str, Any]],
    page_width: float,
) -> bool:
    """基于各页行级宽度与 x0 双峰几何判定文档是否为双栏。

    与 layout_model.detect_columns 采用同源的 20 桶 bisect_right 直方图与
    栏间距/峰距校验，并加入满宽正文字符占比守卫，避免单栏论文中的图内、
    表内左右分布窄标签触发双栏误判（BUG-170）。前五页均为单栏前置页时，
    后续正文页仍能提供双栏证据。
    """
    if not all_blocks or page_width <= 0:
        return False

    page_samples = _page_line_samples(all_blocks, page_width)
    wide_dominated_pages = sum(
        1 for sample in page_samples.values() if _page_is_wide_dominated(sample)
    )
    # 通栏正文 + 宽留白两列的表格页与满宽主导页一样，不提供双栏证据（CHK-095/BUG-226）。
    eligible = [
        sample for sample in page_samples.values()
        if _page_offers_column_evidence(sample)
    ]
    dual_candidate_pages = sum(1 for sample in eligible if len(sample["x0"]) >= 6)
    if wide_dominated_pages >= 8 and wide_dominated_pages >= dual_candidate_pages * 6:
        return False
    x0_values = [value for sample in eligible for value in sample["x0"]]
    width_values = [value for sample in eligible for value in sample["widths"]]
    return _column_peaks(x0_values, width_values, page_width) is not None


def detect_dual_column_pages(
    all_blocks: List[Dict[str, Any]],
    page_width: float,
) -> set[int]:
    """返回可确认双栏的 1-based 页号集合。

    文档级判定为双栏后，证据不足（窄行少于 6 条）的页不直接判单栏，而是
    用已确认页学习到的左右栏起点验证；只有明确落在栏位上的页才继承双栏
    （CHK-094 稀疏尾页）。
    """
    if not all_blocks or page_width <= 0:
        return set()
    if not detect_dual_column_from_blocks(all_blocks, page_width):
        return set()

    page_samples = _page_line_samples(all_blocks, page_width)
    confirmed: Dict[int, Tuple[float, float]] = {}
    for page_index, sample in page_samples.items():
        if not _page_offers_column_evidence(sample):
            continue
        peaks = _column_peaks(sample["x0"], sample["widths"], sample["page_width"])
        if peaks is not None:
            confirmed[page_index] = peaks
    if not confirmed:
        return set()

    left_peak = float(median([peaks[0] for peaks in confirmed.values()]))
    right_peak = float(median([peaks[1] for peaks in confirmed.values()]))
    for page_index, sample in page_samples.items():
        if page_index in confirmed or not _page_offers_column_evidence(sample):
            continue
        if not 2 <= len(sample["x0"]) < 6:
            continue
        tolerance = max(6.0, sample["page_width"] * 0.03)
        left_hits = sum(1 for x0 in sample["x0"] if abs(x0 - left_peak) <= tolerance)
        right_hits = sum(1 for x0 in sample["x0"] if abs(x0 - right_peak) <= tolerance)
        # 两栏都至少两条独立窄行才算「证据不足的双栏页」；单栏页里偶发
        # 一条右对齐签名不能据此把整页改成栏内先左后右的顺序。
        if left_hits < 2 or right_hits < 2:
            continue
        # 页上有通栏正文、两列之间又是表格式的宽留白：按学到的栏位看也一样，
        # 这是单栏页里的并排内容，不继承栏位（CHK-095/BUG-226）。
        if _page_is_side_by_side_table(sample, (left_peak, right_peak)):
            continue
        confirmed[page_index] = (left_peak, right_peak)
    return {page_index + 1 for page_index in confirmed}


def write_gathered_text_json(
    result: "GatheredText",
    out_json: str,
    debug: bool = False,
) -> None:
    """将 GatheredText 序列化写入 JSON 文件（向后兼容旧字段并写出扩展渲染属性）。"""
    output = {
        "version": result.version,
        "is_dual_column": result.is_dual_column,
        "num_columns": int(getattr(result, "num_columns", 2 if result.is_dual_column else 1)),
        "headers_removed": result.headers_removed,
        "footers_removed": result.footers_removed,
        "structure_warnings": result.structure_warnings,
        "typical_font_size": result.typical_font_size,
        "body_font_size": result.body_font_size,
        "toc": list(getattr(result, "toc", None) or []),
        "paragraphs": [
            {
                "text": p.text,
                "rich_text": p.rich_text,
                "page": p.page,
                "bbox": list(p.bbox),
                "is_heading": p.is_heading,
                "heading_level": p.heading_level,
                "para_type": p.para_type,
                "column": p.column,
                "font_size": p.font_size,
                "font_name": getattr(p, "font_name", ""),
                "is_bold": p.is_bold,
                "is_full_width": p.is_full_width,
                "line_count": int(getattr(p, "line_count", 0)),
                "continues_previous_page": bool(
                    getattr(p, "continues_previous_page", False)
                ),
            }
            for p in result.paragraphs
        ],
    }
    out_dir = os.path.dirname(out_json)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    if debug:
        logger.info(f"Wrote gathered text: {out_json} ({len(result.paragraphs)} paragraphs)")


# ============================================================================
# 结构化文本提取
# ============================================================================

_CONTENTS_ENTRY_RE = re.compile(
    r"^(?:[A-Z](?:\.\d+)*|\d+(?:\.\d+)*)\.?\s+.+?\s*\b[0-9]{1,4}$"
)
_CONTENTS_LEADERS_RE = re.compile(r"(?:[.·]\s*){3,}[0-9]{1,4}$")
_CONTENTS_HEADINGS = {"contents", "table of contents", "目录", "目 录"}


_CAPTION_KIND_PREFIX_RE = re.compile(
    r"^(?:(?:extended\s+data\s+figure|supplementary\s+(?:figure|table)|"
    r"figure|fig\.?|table|tab\.?)\b|图|图表|附图|表)",
    re.IGNORECASE,
)
_UNICODE_LIST_BULLET_RE = re.compile(r"^[•▪▫◦‣⁃➢➣➤]\s*\S")
_ASCII_LIST_BULLET_RE = re.compile(r"^[-*+]\s+\S")
_ORDERED_LIST_ITEM_RE = re.compile(
    r"^(?:\d{1,3}[.)]|(?:\(|\[)(?:\d{1,3}|[A-Za-z]|[ivxlcdm]{1,4})(?:\)|\])|[A-Za-z]\))\s+\S"
)
_ORDERED_MARKER_RE = re.compile(r"^([0-9]{1,3})([.)])(?=[ \t])")


def _looks_like_caption_block(text: str) -> bool:
    """仅将符合正式题注格式的块判为 caption，避免把正文陈述句误标。"""
    from .caption_detection import is_bare_caption_label, is_explicit_caption_format

    stripped = (text or "").strip()
    if not stripped or not _CAPTION_KIND_PREFIX_RE.match(stripped):
        return False
    return is_explicit_caption_format(stripped) or is_bare_caption_label(stripped)


def _has_list_marker_line(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped:
        return False
    if re.match(r"^(?:[-*+]\s*[-*+]{2,}|-\s*\d)", stripped):
        return False
    return bool(
        _UNICODE_LIST_BULLET_RE.match(stripped)
        or _ASCII_LIST_BULLET_RE.match(stripped)
        or _ORDERED_LIST_ITEM_RE.match(stripped)
    )


def _looks_like_list_item(text: str, *, allow_single_non_unicode: bool = False) -> bool:
    """区分真实列表项与孤立编号句、负数(-0.69)、小数(1.000)、版本号(2.0 Flash)。

    Unicode 项目符号（如 `•`/`▪`）无歧义，单行即可判作 list；
    ASCII 列表标记（`1.`/`-`/`*`）要求块内至少出现 2 条列表项，或经由相邻紧凑
    列表项证实（allow_single_non_unicode=True），避免把行首打印的 `1. Reported...`
    孤立段落误判成有序列表。
    """
    stripped = (text or "").strip()
    if not stripped:
        return False
    if re.match(r"^(?:[-*+]\s*[-*+]{2,}|-\s*\d)", stripped):
        return False
    if _UNICODE_LIST_BULLET_RE.match(stripped):
        return True
    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    if not lines:
        return False
    marker_lines = sum(1 for ln in lines if _has_list_marker_line(ln))
    if marker_lines == 0:
        return False
    if _has_list_marker_line(lines[0]):
        if marker_lines >= 2:
            return True
        return bool(allow_single_non_unicode)
    # BUG-189：引导语与列表项落在同一个 PDF 文本块时首行没有标记，但后续行是
    # 真实列表项（如「System prompt extraction」+「- realistic attacks …」）。
    # 标记不少于 2 行直接算列表；只有 1 行时要求引导语是短标签且无句末标点，
    # 避免把普通正文里的破折号续行误判成列表。
    if marker_lines >= 2:
        return True
    if allow_single_non_unicode and any(
        _ORDERED_LIST_ITEM_RE.match(line) for line in lines[1:]
    ):
        return True
    lead = lines[0]
    return len(lead) <= 40 and not lead.endswith((".", "。", "!", "！", "?", "？", ";", "；"))


def _confirm_ordered_lists(paragraphs: List[GatheredParagraph]) -> None:
    """在已剔除确认页眉、页脚和页码的正文中识别有序列表。"""
    candidates: Dict[int, Tuple[Tuple[int, str], Tuple[int, str]]] = {}
    confirmed: set[int] = set()
    for index, paragraph in enumerate(paragraphs):
        if paragraph.para_type not in ("paragraph", "list"):
            continue
        markers = [
            (int(match[1]), match[2])
            for line in paragraph.text.splitlines()
            if (match := _ORDERED_MARKER_RE.match(line.strip()))
        ]
        if not markers:
            continue
        candidates[index] = (markers[0], markers[-1])
        if any((number + 1, marker) == next_marker for (number, marker), next_marker in zip(markers, markers[1:])):
            confirmed.add(index)
        previous = candidates.get(index - 1)
        if previous is None or markers[0] != (previous[1][0] + 1, previous[1][1]):
            continue
        last = paragraphs[index - 1]
        font_size = max(last.font_size, paragraph.font_size)
        gap = paragraph.bbox[1] - last.bbox[3]
        # BUG-189：与相邻列表升级循环共用同一套邻接阈值。此前这里用
        # font_size 作上限、升级循环用 max(14, font_size×1.3)，行距 11.6pt 的
        # 编号列表先被升级，又在这里降回 paragraph，行首标记随后被转义。
        if (
            paragraph.page == last.page
            and paragraph.column == last.column
            and abs(paragraph.bbox[0] - last.bbox[0]) <= 18.0
            and -4.0 <= gap <= max(14.0, font_size * 1.3)
        ):
            confirmed.update((index - 1, index))

    for index, (_first, last) in candidates.items():
        paragraph = paragraphs[index]
        same_page = [
            next_index for next_index in candidates
            if next_index > index and paragraphs[next_index].page == paragraph.page
        ]
        if not same_page:
            continue
        next_index = same_page[0]
        following = paragraphs[next_index]
        between = paragraphs[index + 1:next_index]
        if candidates[next_index][0] != (last[0] + 1, last[1]):
            continue
        if (
            following.column != paragraph.column
            or abs(following.bbox[0] - paragraph.bbox[0]) > 18.0
            or not between
        ):
            continue
        if all(
            mid.para_type == "list"
            and mid.column == paragraph.column
            and mid.bbox[0] > paragraph.bbox[0] + 4.0
            and mid.bbox[1] >= paragraph.bbox[1]
            and mid.bbox[3] <= following.bbox[3]
            and all(
                _ORDERED_LIST_ITEM_RE.match(line.strip())
                and not _ORDERED_MARKER_RE.match(line.strip())
                for line in mid.text.splitlines() if line.strip()
            )
            for mid in between
        ):
            confirmed.update((index, next_index))

    # 已确认的页码（含左右交替）不会进入正文。任何保留的中间块会打断
    # CommonMark 列表，因此这里和渲染端都要求相邻，数字也不例外。
    for index, (_first, last) in candidates.items():
        paragraph = paragraphs[index]
        next_index = index + 1
        if next_index not in candidates:
            continue
        next_first, _next_last = candidates[next_index]
        following = paragraphs[next_index]
        if (
            following.page != paragraph.page + 1
            or next_first != (last[0] + 1, last[1])
            or following.column != paragraph.column
            or abs(following.bbox[0] - paragraph.bbox[0]) > 18.0
            or paragraph.font_size <= 0
            or not 0.9 <= following.font_size / paragraph.font_size <= 1.1
        ):
            continue
        confirmed.update((index, next_index))
        following.continues_previous_page = True

    for index in confirmed:
        paragraphs[index].para_type = "list"

    for index in candidates.keys() - confirmed:
        lines = [ln.strip() for ln in paragraphs[index].text.splitlines() if ln.strip()]
        has_bullet = any(
            _UNICODE_LIST_BULLET_RE.match(ln) or _ASCII_LIST_BULLET_RE.match(ln)
            for ln in lines
        )
        if not has_bullet:
            paragraphs[index].para_type = "paragraph"


def _extract_pdf_toc(doc: Any) -> List[Dict[str, Any]]:
    """提取 PDF 内嵌书签目录（1-based 页码，与 GatheredParagraph.page 一致），不可用时返回空列表。"""
    raw_doc = getattr(doc, "raw", doc)
    get_toc = getattr(raw_doc, "get_toc", None)
    if not callable(get_toc):
        return []
    try:
        entries = get_toc(simple=True) or []
    except Exception:
        return []
    toc: List[Dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        try:
            level = int(item[0])
            page_1based = int(item[2])
        except (TypeError, ValueError):
            continue
        title = sanitize_extracted_text(str(item[1] or "")).strip()
        if not title or level <= 0 or page_1based <= 0:
            continue
        toc.append({
            "level": level,
            "title": title,
            "page": page_1based,
        })
    return toc


def _normalize_toc_title(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).casefold()


def _strip_heading_prefix(norm_text: str) -> str:
    return re.sub(r"^(?:\d+(?:\.\d+)*\.?|[ivxlcdm]{1,5}\.|[a-z]\.?)\s+", "", norm_text)


def _has_explicit_heading_numbering(text: str) -> bool:
    stripped = (text or "").strip()
    return bool(
        _NUMBERED_HEADING_LEVEL_RE.match(stripped)
        or _CJK_CHAPTER_LEVEL_RE.match(stripped)
        or _ROMAN_HEADING_LEVEL_RE.match(stripped)
        or _ALPHA_HEADING_LEVEL_RE.match(stripped)
    )


def _apply_toc_fallback(
    paragraphs: List[Any],
    toc_entries: List[Dict[str, Any]],
    *,
    body_font_size: float,
) -> None:
    """保守用 PDF 书签回退校正同页唯一标题层级或提升大字/粗体未编号小节。"""
    if not toc_entries or not paragraphs:
        return

    page_title_counts: Counter = Counter()
    by_page_title: Dict[Tuple[int, str], Dict[str, Any]] = {}
    for entry in toc_entries:
        norm = _normalize_toc_title(entry.get("title", ""))
        if len(norm) < 2:
            continue
        key = (int(entry["page"]), norm)
        page_title_counts[key] += 1
        by_page_title.setdefault(key, entry)

    for para in paragraphs:
        if getattr(para, "para_type", "") == "caption":
            continue
        norm_para = _normalize_toc_title(para.text)
        key = (int(para.page), norm_para)
        if page_title_counts.get(key, 0) != 1:
            stripped_norm = _strip_heading_prefix(norm_para)
            alt_key = (int(para.page), stripped_norm)
            if stripped_norm == norm_para or page_title_counts.get(alt_key, 0) != 1:
                continue
            key = alt_key
        entry = by_page_title[key]
        toc_level = int(entry.get("level", 1) or 1)
        mapped_level = min(6, max(2, toc_level + 1))

        if para.is_heading:
            if not _has_explicit_heading_numbering(para.text):
                if (
                    toc_level == 1
                    and body_font_size > 0
                    and float(para.font_size) / float(body_font_size) > 1.45
                ):
                    para.heading_level = 1
                else:
                    para.heading_level = mapped_level
            continue

        stripped = (para.text or "").strip()
        if (
            para.para_type in ("paragraph", "list")
            and len(stripped) <= 100
            and int(getattr(para, "line_count", 0) or 1) <= 2
            and not stripped.endswith((".", "。", "!", "！", "?", "？", ";", "；"))
            and not re.fullmatch(r"\d+(?:\.\d+)*", stripped)
            and (
                bool(para.is_bold)
                or float(para.font_size) >= max(11.0, float(body_font_size) * 1.12)
            )
        ):
            para.is_heading = True
            para.para_type = "heading"
            if _has_explicit_heading_numbering(para.text):
                para.heading_level = infer_heading_level(
                    para.text, font_size=para.font_size, typical_font_size=body_font_size,
                )
            else:
                para.heading_level = (
                    1
                    if (
                        toc_level == 1
                        and body_font_size > 0
                        and float(para.font_size) / float(body_font_size) > 1.45
                    )
                    else mapped_level
                )


def _contents_entry_indices(blocks: List[Dict[str, Any]]) -> set[int]:
    """从目录标题或多条点引导线确认目录页，并识别有独立页码栏的条目。"""
    named_pages: set[int] = set()
    leader_counts: Counter = Counter()
    candidates: Dict[int, int] = {}
    for index, block in enumerate(blocks):
        page = int(block["page"])
        text = " ".join(sanitize_extracted_text(block["text"]).split())
        if text.casefold() in _CONTENTS_HEADINGS:
            named_pages.add(page)
        if not _CONTENTS_ENTRY_RE.match(text):
            continue
        if _CONTENTS_LEADERS_RE.search(text):
            leader_counts[page] += 1
            candidates[index] = page
            continue
        lines = block.get("lines") or []
        if len(lines) < 2 or not re.fullmatch(r"[0-9]{1,4}", plain_text_from_lines(lines[-1:])):
            continue
        page_width = float(block.get("page_width") or 0)
        first_bbox, last_bbox = lines[0].get("bbox"), lines[-1].get("bbox")
        if not (page_width and first_bbox and last_bbox):
            continue
        x0, y0, _, y1 = first_bbox
        page_x, page_y0, _, page_y1 = last_bbox
        if page_x - x0 >= page_width * 0.35 and max(y0, page_y0) < min(y1, page_y1):
            candidates[index] = page

    return {index for index, page in candidates.items() if page in named_pages or leader_counts[page] >= 3}


def _find_page_number_blocks(
    all_blocks: List[Dict[str, Any]], table_blocks: Optional[set[int]] = None,
) -> set[int]:
    """仅接受跨页同位置、与正文隔离且页码值随页号固定偏移的纯数字块。

    页脚区的独立数字可能是页码，也可能是表格末行/统计值；只凭「数字跨页
    连续」会把 42、43 这类表格值删掉（CHK-094）。这里额外要求数字块与
    同页其他文本有明显纵向间距，或位于极页边（>96%）的页脚带。
    极页边也不能单独作数：表格末行同样可能贴到页边，数字与标签各成一块
    且纵向完全重叠（CHK-095）。所以数字所在行上若还有别的文字，只有当
    那些文字是跨页重复的页眉页脚（两端式页脚）时才保留页码候选。
    已知表格单元格不参与；相邻页的候选还可以用镜像页边位置确认。
    """
    table_blocks = table_blocks or set()
    by_page: Dict[int, List[int]] = {}
    edge_text_pages: Dict[str, set[int]] = {}
    for index, block in enumerate(all_blocks):
        page = int(block.get("page") or int(block.get("page_index", 0)) + 1)
        by_page.setdefault(page, []).append(index)
        if index in table_blocks:
            continue
        block_bbox = block.get("bbox") or (0, 0, 0, 0)
        block_height = float(block.get("page_height") or 0.0)
        if block_height <= 0:
            continue
        block_y_center = (float(block_bbox[1]) + float(block_bbox[3])) / 2.0
        if block_y_center <= block_height * 0.10 or block_y_center >= block_height * 0.90:
            edge_text_pages.setdefault(str(block.get("text", "") or "").strip(), set()).add(page)

    def _vertical_gap(first: Tuple[float, float, float, float], second: Tuple[float, float, float, float]) -> float:
        return max(0.0, float(second[1]) - float(first[3]), float(first[1]) - float(second[3]))

    def _shares_line(
        first: Tuple[float, float, float, float],
        second: Tuple[float, float, float, float],
    ) -> bool:
        """两个块是否落在同一视觉行（纵向重叠超过较矮者的一半）。"""
        overlap = min(float(first[3]), float(second[3])) - max(float(first[1]), float(second[1]))
        shorter = min(float(first[3]) - float(first[1]), float(second[3]) - float(second[1]))
        return shorter > 0 and overlap >= shorter * 0.5

    candidates: List[Tuple[int, int, int, int, int, bool]] = []
    for index, block in enumerate(all_blocks):
        if index in table_blocks:
            continue
        text = str(block.get("text", "") or "").strip()
        if not re.fullmatch(r"\d{1,4}", text):
            continue
        bbox = block.get("bbox") or (0, 0, 0, 0)
        page_height = float(block.get("page_height") or 0.0)
        page_width = float(block.get("page_width") or 0.0)
        if page_height <= 0 or page_width <= 0:
            continue
        y_center = (float(bbox[1]) + float(bbox[3])) / 2.0
        relative_y = y_center / page_height
        depth = min(relative_y, 1.0 - relative_y)
        if not 0.0 <= depth < 0.10:
            continue
        page = int(block.get("page") or int(block.get("page_index", 0)) + 1)
        row_text_is_repeated_footer = all(
            other not in table_blocks
            and len(edge_text_pages.get(str(all_blocks[other].get("text", "") or "").strip(), ())) >= 2
            for other in by_page.get(page, [])
            if other != index
            and _shares_line(bbox, all_blocks[other].get("bbox") or bbox)
        )
        if not row_text_is_repeated_footer:
            continue
        height = max(0.0, float(bbox[3]) - float(bbox[1]))
        min_gap = min(
            (
                _vertical_gap(bbox, all_blocks[other].get("bbox") or bbox)
                for other in by_page.get(page, [])
                if other != index
            ),
            default=float("inf"),
        )
        isolated = min_gap >= max(8.0, height * 0.75)
        forced_margin = depth <= 0.04
        if not (isolated or forced_margin):
            continue
        offset = int(text) - page
        x_center = (float(bbox[0]) + float(bbox[2])) / 2.0
        candidates.append((
            index,
            page,
            offset,
            round(x_center / page_width * 20),
            round(depth * 20),
            relative_y > 0.5,
        ))

    groups: Dict[Tuple[int, int, int], List[Tuple[int, int]]] = {}
    by_page_and_offset: Dict[Tuple[int, int], List[Tuple[int, int, int]]] = {}
    for index, page, offset, x_bucket, depth_bucket, is_footer in candidates:
        if is_footer:
            groups.setdefault((offset, x_bucket, depth_bucket), []).append((index, page))
        by_page_and_offset.setdefault((page, offset), []).append((index, x_bucket, depth_bucket))

    confirmed: set[int] = set()
    for indices in groups.values():
        if len({page for _index, page in indices}) >= 2:
            confirmed.update(index for index, _page in indices)

    # 交替页码要求相邻页、相同的印刷页码偏移、镜像侧边及近似的页边距离。
    # 单个恰好等于页序的正文数字，或相邻页中部的连续数值，都没有这组证据。
    for index, page, offset, x_bucket, depth_bucket, _is_footer in candidates:
        for other, other_x, other_depth in by_page_and_offset.get((page + 1, offset), ()):
            if (
                (x_bucket - 10) * (other_x - 10) < 0
                and abs(x_bucket - other_x) >= 6
                and abs(x_bucket + other_x - 20) <= 2
                and abs(depth_bucket - other_depth) <= 1
            ):
                confirmed.update((index, other))
    return confirmed


def _find_ruled_table_cells(
    doc: PDFDocument, blocks: List[Dict[str, Any]], column_pages: set[int],
    edge_removals: set[int],
) -> Dict[int, Tuple[Tuple[float, ...], Tuple[float, ...]]]:
    """只接纳与页边剔除或双栏判定直接冲突的网格。"""
    pages = column_pages | {blocks[index]["page"] for index in edge_removals}
    by_page: Dict[int, List[int]] = {}
    for index, block in enumerate(blocks):
        if block["page"] in pages:
            by_page.setdefault(block["page"], []).append(index)

    matched = {}
    for page, indices in by_page.items():
        pdf_page = doc[page - 1]
        raw = getattr(pdf_page, "raw", pdf_page)
        find_tables = getattr(raw, "find_tables", None)
        if not callable(find_tables):
            continue
        # 仅用已存在的绘制线条确认网格，避免把双栏正文的对齐文字解释成表格。
        try:
            finder = find_tables(strategy="lines_strict")
        except (RuntimeError, TypeError, ValueError) as exc:
            logger.debug("Ruled table detection skipped on page %s: %s", page, exc)
            continue
        for table in getattr(finder, "tables", ()):
            if table.col_count < 2:
                continue
            grid = tuple(table.bbox)
            cells = [tuple(cell) for row in table.rows for cell in row.cells if cell]
            hits = {}
            for index in indices:
                x0, y0, x1, y1 = blocks[index]["bbox"]
                if not (grid[0] - 2 <= x0 < x1 <= grid[2] + 2 and grid[1] - 2 <= y0 < y1 <= grid[3] + 2):
                    continue
                for cell in cells:
                    cx0, cy0, cx1, cy1 = cell
                    if (
                        cx0 - 2 <= x0 < x1 <= cx1 + 2
                        and cx0 <= (x0 + x1) / 2 < cx1 and cy0 <= (y0 + y1) / 2 < cy1
                        and min(y1, cy1) - max(y0, cy0) >= (y1 - y0) * 0.75
                    ):
                        hits[index] = cell
                        break
            if len({cell[0] for cell in hits.values()}) < 2:
                continue
            row_counts = Counter(cell[1] for cell in set(hits.values()))
            # 单栏页面的流程图和插画也可能画对齐边框。除非网格中确有即将
            # 丢失的页边文本，否则只用多条有数据的成对单元格反证双栏。
            if edge_removals.intersection(hits) or (
                page in column_pages and sum(count >= 2 for count in row_counts.values()) >= 2
            ):
                matched.update({index: (grid, cell) for index, cell in hits.items()})
    return matched


@managed_pdf_document
def gather_structured_text(
    pdf_path: str,
    out_json: Optional[str] = None,
    debug: bool = False,
    _doc: Optional[PDFDocument] = None,
    native_blocks: Optional[List[Dict[str, Any]]] = None,
) -> "GatheredText":
    """
    结构化文本提取（Gathering 阶段）。

    功能：
    1. Header/footer 检测与剔除
    2. 双栏顺序重排（与版式模型同源的行宽/双峰几何判据）
    3. 段落分类（标题/正文/图注/列表）与渲染元数据填充

    字号基准有两个：typical_font_size 是 8-14pt span 字号的算术平均（保持原口径）；
    body_font_size 是字符加权的并簇众数，只用于无编号标题的层级判定。

    Args:
        pdf_path: PDF 文件路径
        out_json: 输出 JSON 路径（可选）
        debug: 调试模式
        native_blocks: 可选预扫描的原生文本块列表（共享底层扫描避免重复读页）

    Returns:
        GatheredText 结构化结果
    """
    from .models import GatheredParagraph, GatheredText

    assert _doc is not None
    doc = _doc
    page_count = doc.page_count

    all_blocks = native_blocks if native_blocks is not None else iter_native_text_blocks(doc)
    header_candidates: List[Tuple[int, str]] = []
    footer_candidates: List[Tuple[int, str]] = []
    font_sizes: List[float] = []
    chars_by_size: Counter = Counter()

    for index, block in enumerate(all_blocks):
        block_text = block["text"]
        bbox = block["bbox"]
        page_height = float(block.get("page_height") or doc[0].rect.height)
        y_center = (bbox[1] + bbox[3]) / 2
        if y_center < page_height * 0.10:
            header_candidates.append((index, block_text))
        elif y_center > page_height * 0.90:
            footer_candidates.append((index, block_text))
        lines = block.get("lines") or []
        for line in lines:
            for span in line.get("spans", []):
                size = float(span.get("size", 0) or 0)
                if 8.0 <= size <= 14.0:
                    font_sizes.append(size)
                if BODY_FONT_SIZE_RANGE_PT[0] <= size <= BODY_FONT_SIZE_RANGE_PT[1]:
                    clean_span = sanitize_extracted_text(str(span.get("text", "") or "")).strip()
                    chars_by_size[round(size, 2)] += len(clean_span)

    page_number_blocks = _find_page_number_blocks(all_blocks)
    threshold = max(2, page_count * 0.3)
    header_counts = Counter(text for _index, text in header_candidates)
    footer_counts = Counter(text for _index, text in footer_candidates)

    edge_removals = page_number_blocks | {
        index
        for candidates, counts in ((header_candidates, header_counts), (footer_candidates, footer_counts))
        for index, text in candidates
        if counts[text] >= threshold
    }
    doc_page_width = float(all_blocks[0].get("page_width") or doc[0].rect.width) if all_blocks else 0.0
    is_dual_column = detect_dual_column_from_blocks(all_blocks, doc_page_width)
    dual_column_pages = detect_dual_column_pages(all_blocks, doc_page_width) if is_dual_column else set()
    table_cells = _find_ruled_table_cells(doc, all_blocks, dual_column_pages, edge_removals)
    if table_cells:
        page_number_blocks = _find_page_number_blocks(all_blocks, set(table_cells))
        header_counts = Counter(text for index, text in header_candidates if index not in table_cells)
        footer_counts = Counter(text for index, text in footer_candidates if index not in table_cells)
        column_blocks = [block for index, block in enumerate(all_blocks) if index not in table_cells]
        is_dual_column = detect_dual_column_from_blocks(column_blocks, doc_page_width)
        dual_column_pages = detect_dual_column_pages(column_blocks, doc_page_width) if is_dual_column else set()

    headers_to_remove = {text for text, count in header_counts.items() if count >= threshold}
    footers_to_remove = {text for text, count in footer_counts.items() if count >= threshold}

    if debug:
        print(f"[DEBUG] Detected headers to remove: {headers_to_remove}")
        print(f"[DEBUG] Detected footers to remove: {footers_to_remove}")

    num_columns = 2 if is_dual_column else 1

    typical_font_size = (
        sum(font_sizes) / len(font_sizes) if font_sizes else 10.0
    )
    # 标题层级判定的字号基准：字符加权并簇众数，不受表格、脚注里大量小字号 span 拉偏。
    # typical_font_size 保持原口径；版式模型另有自己的估算，是图表裁剪的依据，不跟着改。
    body_font_size = estimate_body_font_size(chars_by_size) or typical_font_size

    if debug:
        print(f"[DEBUG] Dual column detected: {is_dual_column} (num_columns={num_columns})")
        print(f"[DEBUG] Typical font size: {typical_font_size:.2f}")
        print(f"[DEBUG] Body font size: {body_font_size:.2f}")

    contents_entries = _contents_entry_indices(all_blocks)
    paragraphs: List[GatheredParagraph] = []
    table_positions: Dict[int, Tuple[float, float]] = {}

    for index, block in enumerate(all_blocks):
        plain = sanitize_extracted_text(block["text"])

        bbox = tuple(block["bbox"])
        page = int(block["page"])
        page_height = float(block.get("page_height") or doc[0].rect.height)
        y_center = (bbox[1] + bbox[3]) / 2.0
        in_header_zone = y_center < page_height * 0.10
        in_footer_zone = y_center > page_height * 0.90
        table_cell = table_cells.get(index)
        if (
            not plain or index in page_number_blocks or (
                table_cell is None and (
                    (in_header_zone and plain in headers_to_remove)
                    or (in_footer_zone and plain in footers_to_remove)
                )
            )
        ):
            continue

        page_width = float(block.get("page_width") or doc[0].rect.width)
        column, is_full_width = classify_block_column(
            table_cell[0] if table_cell else bbox, page_width,
            is_dual_column=page in dual_column_pages,
        )

        lines = block.get("lines", [])
        first_spans = lines[0].get("spans", []) if lines else []
        first_span = first_spans[0] if first_spans else {}
        main_span = (
            max(
                first_spans,
                key=lambda s: len(sanitize_extracted_text(str(s.get("text", "") or ""))),
            )
            if first_spans
            else {}
        )
        font_size = float(main_span.get("size", 10) or first_span.get("size", 10) or 10)
        font_name = str(main_span.get("font", "") or first_span.get("font", "") or "")
        is_bold = _span_has_bold_flag(main_span) if main_span else False
        line_count = sum(
            1
            for ln in lines
            if "".join(
                sanitize_extracted_text(str(sp.get("text", "") or ""))
                for sp in ln.get("spans", [])
            ).strip()
        ) or len(plain.splitlines())

        if index not in contents_entries and looks_like_structural_heading(
            plain, is_bold=is_bold, font_size=font_size, body_font_size=body_font_size,
            has_paragraph_spacing=(
                line_count == 1
                and _block_has_paragraph_spacing(block, all_blocks, font_size)
            ),
        ):
            para_type = "heading"
        elif _looks_like_caption_block(plain):
            para_type = "caption"
        elif index not in contents_entries and _looks_like_list_item(plain):
            para_type = "list"
        else:
            para_type = "paragraph"

        is_heading = para_type == "heading"
        heading_level = (
            infer_heading_level(
                plain, font_size=font_size, typical_font_size=body_font_size
            )
            if is_heading
            else 0
        )
        # text 始终是纯文本：题注匹配、正文引用检索等下游都按原文比对。
        # 行内样式只放在 rich_text，供 Markdown 渲染正文段落时使用；
        # 与纯文本对不上时宁可不加样式，保证正文一字不差。
        rich_text = ""
        if not is_heading:
            candidate = sanitize_extracted_text(block.get("rich_text") or "").strip()
            if (
                candidate != plain.strip()
                and strip_inline_markdown(candidate) == plain.strip()
            ):
                rich_text = candidate

        paragraph = GatheredParagraph(
            page=page,
            text=plain,
            rich_text=rich_text,
            bbox=bbox,
            is_heading=is_heading,
            heading_level=heading_level,
            column=column,
            font_size=font_size,
            is_bold=is_bold,
            is_full_width=is_full_width,
            para_type=para_type,
            font_name=font_name,
            line_count=line_count,
        )
        if table_cell:
            _, cell = table_cell
            table_positions[id(paragraph)] = (cell[1], cell[0])
        paragraphs.append(paragraph)

    toc_entries = _extract_pdf_toc(doc)
    _apply_toc_fallback(paragraphs, toc_entries, body_font_size=body_font_size)
    if is_dual_column:
        page_widths = {
            int(block["page"]): float(block.get("page_width") or doc[0].rect.width)
            for block in all_blocks
        }
        dual_page_paragraphs = [p for p in paragraphs if p.page in dual_column_pages]
        _promote_centered_headings(dual_page_paragraphs, page_widths)
        _promote_centered_interruptions(dual_page_paragraphs, page_widths)

    paragraphs = sort_paragraphs_reading_order(
        paragraphs, is_dual_column=is_dual_column, dual_column_pages=dual_column_pages,
        table_positions=table_positions,
    )

    # 重排阅读顺序后再检查同页同栏相邻紧凑列表项，避免双栏交错块阻断列表升级
    for i in range(len(paragraphs) - 1):
        cur, nxt = paragraphs[i], paragraphs[i + 1]
        if (
            cur.page == nxt.page
            and cur.column == nxt.column
            and cur.para_type in ("paragraph", "list")
            and nxt.para_type in ("paragraph", "list")
            and _looks_like_list_item(cur.text, allow_single_non_unicode=True)
            and _looks_like_list_item(nxt.text, allow_single_non_unicode=True)
            and abs(float(cur.bbox[0]) - float(nxt.bbox[0])) <= 18.0
            and -4.0 <= (float(nxt.bbox[1]) - float(cur.bbox[3])) <= max(14.0, float(cur.font_size) * 1.3)
        ):
            cur.para_type = "list"
            nxt.para_type = "list"
    _confirm_ordered_lists(paragraphs)
    structure_warnings = collect_structure_warnings(
        paragraphs, is_dual_column=is_dual_column
    )

    result = GatheredText(
        version="1.1",
        is_dual_column=is_dual_column,
        headers_removed=list(headers_to_remove),
        footers_removed=list(footers_to_remove),
        paragraphs=paragraphs,
        structure_warnings=structure_warnings,
        typical_font_size=typical_font_size,
        body_font_size=body_font_size,
        num_columns=num_columns,
        toc=toc_entries,
    )

    if out_json:
        write_gathered_text_json(result, out_json, debug=debug)

    return result


# ============================================================================
# 图表上下文构建（已迁移到 figure_contexts.py，此处保留向后兼容导入）
# ============================================================================

# Commit 11: build_figure_contexts 已迁移到 figure_contexts.py
# 为保持向后兼容性，从新模块重新导出
from .figure_contexts import build_figure_contexts


# ============================================================================
# 带格式文本提取（版式模型构建）
# ============================================================================

@managed_pdf_document
def extract_text_with_format(
    pdf_path: str,
    out_json: Optional[str] = None,
    sample_pages: Optional[int] = None,
    debug: bool = False,
    _doc: Optional[PDFDocument] = None,
    native_blocks: Optional[List[Dict[str, Any]]] = None,
    include_details: bool = True,
    include_units: bool = True,
    full_text_export: bool = False,
    text_layer_dual: Optional[bool] = None,
) -> "DocumentLayoutModel":
    """
    提取文本并保留完整格式信息，构建版式模型。

    Args:
        pdf_path: PDF 文件路径
        out_json: 输出 JSON 路径（可选）
        sample_pages: 采样页数（None 表示全部）
        debug: 调试模式
        text_layer_dual: 文本层的文档级双栏判定（gather_structured_text 的
            is_dual_column）。版式模型判出双栏时须它确认；两个正式入口都会传入
            同一轮 gather 的结论。None 时用同一批原生块现算一次（不含框线表格
            单元格的剔除），仅供直接调用。

    Returns:
        DocumentLayoutModel 版式模型对象
    """
    from .models import DocumentLayoutModel, EnhancedTextUnit
    from .layout_model import (
        build_text_blocks,
        classify_text_types,
        detect_columns,
        detect_vacant_regions,
    )

    if debug:
        print("\n" + "=" * 70)
        print("LAYOUT-DRIVEN EXTRACTION: Building Document Layout Model")
        print("=" * 70)

    assert _doc is not None
    doc = _doc

    page_rect = doc[0].rect
    page_size = (page_rect.width, page_rect.height)

    # 统计典型行高和字号
    typical_font_size, typical_line_height, typical_line_gap = _estimate_typical_metrics(doc, debug)

    # 统计典型字体名
    font_name_counts = {}
    num_sample_pages = min(5, len(doc))
    for pno in range(num_sample_pages):
        page = doc[pno]
        dict_data = page.get_text("dict")
        for blk in dict_data.get("blocks", []):
            if blk.get("type") != 0:
                continue
            for ln in blk.get("lines", []):
                for sp in ln.get("spans", []):
                    font_name = sp.get("font", "unknown")
                    font_size = sp.get("size", 0)
                    if 8 <= font_size <= 14:
                        font_name_counts[font_name] = font_name_counts.get(font_name, 0) + 1

    if font_name_counts:
        typical_font_name = max(font_name_counts, key=font_name_counts.get)
    else:
        typical_font_name = "Times"

    # 提取每页的增强文本单元（与 gather 共用原生块底层）
    all_units: Dict[int, List[EnhancedTextUnit]] = {}
    num_pages = len(doc) if sample_pages is None else min(sample_pages, len(doc))
    source_blocks = native_blocks if native_blocks is not None else iter_native_text_blocks(doc)
    native_blocks_filtered = [
        block for block in source_blocks
        if int(block["page_index"]) < num_pages
    ]
    blocks_by_page: Dict[int, List[Dict[str, Any]]] = {}
    for block in native_blocks_filtered:
        blocks_by_page.setdefault(int(block["page_index"]), []).append(block)

    for pno in range(num_pages):
        units = []
        for blk_idx, blk in enumerate(blocks_by_page.get(pno, [])):
            for ln_idx, ln in enumerate(blk.get("lines", [])):
                spans = ln.get("spans", [])
                if not spans:
                    continue

                text = sanitize_extracted_text("".join(sp.get("text", "") for sp in spans))
                bbox = create_rect(*ln["bbox"])

                main_span = max(spans, key=lambda s: len(s.get("text", "")))
                font_name = main_span.get("font", "unknown")
                font_size = main_span.get("size", 10.0)
                font_flags = main_span.get("flags", 0)
                color = main_span.get("color", 0)

                font_weight = 'bold' if _span_has_bold_flag(main_span) else 'regular'

                if isinstance(color, int):
                    color_rgb = ((color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF)
                else:
                    color_rgb = (0, 0, 0)

                unit = EnhancedTextUnit(
                    bbox=bbox,
                    text=text,
                    page=pno,
                    font_name=font_name,
                    font_size=font_size,
                    font_weight=font_weight,
                    font_flags=font_flags,
                    color=color_rgb,
                    text_type='unknown',
                    confidence=0.0,
                    column=-1,
                    indent=bbox.x0,
                    block_idx=blk_idx,
                    line_idx=ln_idx
                )
                units.append(unit)

        all_units[pno] = units

    # 文本类型分类
    all_units = classify_text_types(all_units, typical_font_size, typical_font_name, page_size[0], debug=debug)

    # 双栏检测：直方图判出双栏时，还须文本层的文档级判定确认
    dual_confirmed = text_layer_dual
    if dual_confirmed is None:
        dual_confirmed = detect_dual_column_from_blocks(native_blocks_filtered, page_size[0])
    num_columns, column_gap, all_units = detect_columns(
        all_units, page_size[0], debug=debug, dual_confirmed=dual_confirmed
    )

    # 构建文本区块
    all_blocks = build_text_blocks(all_units, typical_line_height, debug=debug)

    # 识别留白区域
    vacant_regions = detect_vacant_regions(all_blocks, doc, debug=debug)

    # 创建版式模型
    layout_model = DocumentLayoutModel(
        page_size=page_size,
        num_columns=num_columns,
        margin_left=page_rect.x0,
        margin_right=page_rect.x1,
        margin_top=page_rect.y0,
        margin_bottom=page_rect.y1,
        column_gap=column_gap,
        typical_font_size=typical_font_size,
        typical_line_height=typical_line_height,
        typical_line_gap=typical_line_gap,
        text_units=all_units,
        text_blocks=all_blocks,
        vacant_regions=vacant_regions
    )

    # 保存为 JSON
    if out_json:
        out_dir = os.path.dirname(out_json)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(out_json, 'w', encoding='utf-8') as f:
            json.dump(
                layout_model.to_dict(
                    include_details=include_details,
                    include_units=include_units,
                    full_text_export=full_text_export,
                ),
                f,
                indent=2,
                ensure_ascii=False,
            )
        if debug:
            print(f"\n[INFO] Saved layout model to: {out_json}")

    if debug:
        print("\n[SUMMARY] Layout Model Built Successfully")
        print(f"  - Pages analyzed: {num_pages}")
        print(f"  - Total text units: {sum(len(v) for v in all_units.values())}")
        print(f"  - Total text blocks: {sum(len(v) for v in all_blocks.values())}")
        print(f"  - Total vacant regions: {sum(len(v) for v in vacant_regions.values())}")
        print("=" * 70)

    return layout_model


def _estimate_typical_metrics(doc: Any, debug: bool = False) -> Tuple[float, float, float]:
    """
    估算文档的典型字号、行高和行距。

    Args:
        doc: PyMuPDF 文档对象
        debug: 调试模式

    Returns:
        (typical_font_size, typical_line_height, typical_line_gap)
    """
    font_sizes = []
    line_heights = []

    sample_pages = min(5, len(doc))
    for pno in range(sample_pages):
        page = doc[pno]
        dict_data = page.get_text("dict")

        for blk in dict_data.get("blocks", []):
            if blk.get("type") != 0:
                continue

            lines = blk.get("lines", [])
            for i, ln in enumerate(lines):
                spans = ln.get("spans", [])
                for sp in spans:
                    fs = sp.get("size", 0)
                    if 6 <= fs <= 20:
                        font_sizes.append(fs)

                if i > 0:
                    prev_ln = lines[i - 1]
                    gap = ln["bbox"][1] - prev_ln["bbox"][3]
                    height = ln["bbox"][3] - ln["bbox"][1]
                    if 0 < gap < 30 and 6 < height < 30:
                        line_heights.append(height + gap)

    typical_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 10.0
    typical_line_height = sum(line_heights) / len(line_heights) if line_heights else 14.0
    typical_line_gap = max(0.0, typical_line_height - typical_font_size)

    if debug:
        print(f"[DEBUG] Estimated metrics: font={typical_font_size:.1f}pt, line_h={typical_line_height:.1f}pt, gap={typical_line_gap:.1f}pt")

    return typical_font_size, typical_line_height, typical_line_gap
