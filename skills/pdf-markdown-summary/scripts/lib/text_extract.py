#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Commit 10: 文本提取

从 extract_pdf_assets.py 抽离的文本提取相关代码。

包含：
- try_extract_text: 尝试提取 PDF 文本
- pre_validate_pdf: PDF 预验证
- gather_structured_text: 结构化文本提取
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
from collections import Counter
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

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

_SECTION_HEADING_RE = re.compile(r"^\d+(?:\.\d+)*\s+[A-Za-z].{2,}")

# 中文编号模式：第X章/第X节、一、（一）等；数字编号后允许直接跟中文
# （要求编号与正文之间有空白或编号分隔符，避免把「2023年」误判为标题）
_CJK_SECTION_HEADING_RE = re.compile(
    r"^(?:第[0-9一二三四五六七八九十百]+[章节篇部]"
    r"|[0-9一二三四五六七八九十]+[、.．]"
    r"|[（(][0-9一二三四五六七八九十]+[）)]"
    # 数字编号+空白后，下一个字符必须是字母或 CJK——「1 - P(E)」这类
    # 粗体公式片段的编号后紧跟标点，不能算标题
    r"|\d+(?:\.\d+)*\s+(?=[A-Za-z\u4e00-\u9fff]))"
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


def looks_like_structural_heading(text: str, *, is_bold: bool, font_size: float) -> bool:
    """短粗体不一定是章节标题。

    页码、公式、单字母、裸节号，以及正文字号的表头（FEELING ITEMS）
    会把 Markdown 切碎。编号标题任何字号都保留；其余标题要求明显大于正文。
    中文字符计入标题长度计数，编号后允许直接跟中文（如「1 绪论」「第一章 绪论」）。
    """
    if not is_bold:
        return False
    stripped = (text or "").strip()
    if not stripped or len(stripped) >= 50:
        return False
    cjk_chars = _CJK_CHAR_RE.findall(stripped)
    if len(stripped) <= 2 and not cjk_chars:
        return False
    if stripped[0] in ".,;:)]}-–—":
        return False
    if re.fullmatch(r"\d{1,4}", stripped) or re.fullmatch(r"\d+(?:\.\d+)*", stripped):
        return False
    if font_size < 11.5 and _SMALL_TABLE_METRIC_RE.match(stripped):
        return False
    if (
        _SECTION_HEADING_RE.match(stripped)
        or _CJK_SECTION_HEADING_RE.match(stripped)
        or _ROMAN_ALPHA_HEADING_RE.match(stripped)
    ):
        return True
    if re.match(r"^\d", stripped):
        return False
    if font_size < 11.5:
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


_NUMBERED_HEADING_LEVEL_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+\S")
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


def _span_is_bold(span: Dict[str, Any]) -> bool:
    """行内样式用的粗体：标志位或字体名。"""
    flags = int(span.get("flags", 0) or 0)
    font = str(span.get("font", "") or "").lower()
    return bool(flags & (1 << 4)) or any(
        token in font for token in ("bold", "black", "heavy", "medi")
    )


def _span_is_italic(span: Dict[str, Any]) -> bool:
    """行内样式用的斜体：标志位或字体名。"""
    flags = int(span.get("flags", 0) or 0)
    font = str(span.get("font", "") or "").lower()
    return bool(flags & (1 << 1)) or any(
        token in font for token in ("italic", "oblique")
    )


_STYLE_MARKERS = {"b": "**", "i": "*", "bi": "***"}


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
                core = core.replace("\\", "\\\\").replace("*", "\\*")
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
            if open_marker and core[0] in "*_":
                core = "\\" + core[0] + core[1:]  # 会并入闭标记
            parts.append(core)
            open_marker = False

        if trail:
            parts.append(trail)
            open_marker = False

    return "".join(parts)


def plain_text_from_lines(lines: List[Dict[str, Any]]) -> str:
    """拼接块内各行为纯文本（无 Markdown 标记）。"""
    chunks: List[str] = []
    for line in lines or []:
        line_text = "".join(sp.get("text", "") for sp in line.get("spans", []))
        if line_text.strip():
            chunks.append(line_text)
    return "\n".join(chunks).strip()


def rich_text_from_lines(lines: List[Dict[str, Any]]) -> str:
    """拼接块内各行为行内 Markdown 文本。"""
    chunks: List[str] = []
    for line in lines or []:
        line_text = format_spans_as_markdown(line.get("spans", []))
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
    if spans_mid or wide:
        return -1, True
    x_center = (x0 + x1) / 2.0
    return (0 if x_center < mid else 1), False


def sort_paragraphs_reading_order(
    paragraphs: List[Any],
    *,
    is_dual_column: bool,
) -> List[Any]:
    """双栏阅读顺序：通栏块按 y 切开栏带，带内先左后右。"""
    if not is_dual_column or not paragraphs:
        return sorted(paragraphs, key=lambda p: (p.page, p.bbox[1], p.bbox[0]))

    from collections import defaultdict

    by_page: Dict[int, List[Any]] = defaultdict(list)
    for para in paragraphs:
        by_page[para.page].append(para)

    ordered: List[Any] = []
    for page in sorted(by_page):
        page_paras = by_page[page]
        tagged: List[Tuple[Any, int]] = []
        for para in page_paras:
            col = getattr(para, "column", -1)
            if getattr(para, "is_full_width", False):
                col = -1
            tagged.append((para, col))
        tagged.sort(key=lambda item: (item[0].bbox[1], item[0].bbox[0]))

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
                key=lambda p: (p.bbox[1], p.bbox[0]),
            )
            right = sorted(
                (p for p, c in band if c == 1),
                key=lambda p: (p.bbox[1], p.bbox[0]),
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
                text_parts.append(page.get_text("text"))
        full_text = "\n\n".join(text_parts)

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
# 结构化文本提取
# ============================================================================

@managed_pdf_document
def gather_structured_text(
    pdf_path: str,
    out_json: Optional[str] = None,
    debug: bool = False,
    _doc: Optional[PDFDocument] = None,
) -> "GatheredText":
    """
    结构化文本提取（Gathering 阶段）。

    功能：
    1. Header/footer 检测与剔除
    2. 双栏顺序重排
    3. 段落分类（标题/正文/图注/列表）

    Args:
        pdf_path: PDF 文件路径
        out_json: 输出 JSON 路径（可选）
        debug: 调试模式

    Returns:
        GatheredText 结构化结果
    """
    from .models import GatheredParagraph, GatheredText

    assert _doc is not None
    doc = _doc
    page_count = doc.page_count

    all_blocks = iter_native_text_blocks(doc)
    header_candidates: List[str] = []
    footer_candidates: List[str] = []
    font_sizes: List[float] = []

    for block in all_blocks:
        block_text = block["text"]
        bbox = block["bbox"]
        page_height = float(block.get("page_height") or doc[0].rect.height)
        y_center = (bbox[1] + bbox[3]) / 2
        if y_center < page_height * 0.05:
            if len(block_text) < 100:
                header_candidates.append(block_text)
        elif y_center > page_height * 0.95:
            if len(block_text) < 100:
                footer_candidates.append(block_text)
        lines = block.get("lines") or []
        for line in lines:
            for span in line.get("spans", []):
                size = float(span.get("size", 0) or 0)
                if 8.0 <= size <= 14.0:
                    font_sizes.append(size)

    header_counter = Counter(header_candidates)
    footer_counter = Counter(footer_candidates)

    threshold = max(2, page_count * 0.3)
    headers_to_remove = {text for text, count in header_counter.items() if count >= threshold}
    footers_to_remove = {text for text, count in footer_counter.items() if count >= threshold}

    if debug:
        print(f"[DEBUG] Detected headers to remove: {headers_to_remove}")
        print(f"[DEBUG] Detected footers to remove: {footers_to_remove}")

    x_centers = [(b["bbox"][0] + b["bbox"][2]) / 2 for b in all_blocks]
    if x_centers:
        page_width = float(all_blocks[0].get("page_width") or doc[0].rect.width)
        left_count = sum(1 for x in x_centers if x < page_width * 0.45)
        right_count = sum(1 for x in x_centers if x > page_width * 0.55)
        is_dual_column = left_count > len(x_centers) * 0.3 and right_count > len(x_centers) * 0.3
    else:
        is_dual_column = False

    typical_font_size = (
        sum(font_sizes) / len(font_sizes) if font_sizes else 10.0
    )

    if debug:
        print(f"[DEBUG] Dual column detected: {is_dual_column}")
        print(f"[DEBUG] Typical font size: {typical_font_size:.2f}")

    paragraphs: List[GatheredParagraph] = []

    for block in all_blocks:
        plain = block["text"]

        if plain in headers_to_remove or plain in footers_to_remove:
            continue

        bbox = tuple(block["bbox"])
        page = int(block["page"])
        page_width = float(block.get("page_width") or doc[0].rect.width)
        column, is_full_width = classify_block_column(
            bbox, page_width, is_dual_column=is_dual_column
        )

        lines = block.get("lines", [])
        first_span = lines[0]["spans"][0] if lines and lines[0].get("spans") else {}
        font_size = float(first_span.get("size", 10) or 10)
        is_bold = _span_has_bold_flag(first_span) if first_span else False

        if looks_like_structural_heading(plain, is_bold=is_bold, font_size=font_size):
            para_type = "heading"
        elif plain.lower().startswith(("figure", "fig.", "table", "图", "表")):
            para_type = "caption"
        elif plain.startswith(("•", "-", "*", "1.", "2.", "(1)", "(a)")):
            para_type = "list"
        else:
            para_type = "body"

        is_heading = para_type == "heading"
        heading_level = (
            infer_heading_level(
                plain, font_size=font_size, typical_font_size=typical_font_size
            )
            if is_heading
            else 0
        )
        # text 始终是纯文本：题注匹配、正文引用检索等下游都按原文比对。
        # 行内样式只放在 rich_text，供 Markdown 渲染正文段落时使用；
        # 与纯文本对不上时宁可不加样式，保证正文一字不差。
        rich_text = ""
        if not is_heading:
            candidate = (block.get("rich_text") or "").strip()
            if (
                candidate != plain.strip()
                and strip_inline_markdown(candidate) == plain.strip()
            ):
                rich_text = candidate

        paragraphs.append(GatheredParagraph(
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
        ))

    paragraphs = sort_paragraphs_reading_order(
        paragraphs, is_dual_column=is_dual_column
    )
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
    )

    if out_json:
        output = {
            "version": result.version,
            "is_dual_column": result.is_dual_column,
            "headers_removed": result.headers_removed,
            "footers_removed": result.footers_removed,
            "structure_warnings": result.structure_warnings,
            "typical_font_size": result.typical_font_size,
            "paragraphs": [
                {
                    "text": p.text,
                    "rich_text": p.rich_text,
                    "page": p.page,
                    "bbox": list(p.bbox),
                    "is_heading": p.is_heading,
                    "heading_level": p.heading_level,
                    "column": p.column,
                    "font_size": p.font_size,
                    "is_bold": p.is_bold,
                    "is_full_width": p.is_full_width,
                }
                for p in result.paragraphs
            ]
        }
        out_dir = os.path.dirname(out_json)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(out_json, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        if debug:
            logger.info(f"Wrote gathered text: {out_json} ({len(paragraphs)} paragraphs)")

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
) -> "DocumentLayoutModel":
    """
    提取文本并保留完整格式信息，构建版式模型。

    Args:
        pdf_path: PDF 文件路径
        out_json: 输出 JSON 路径（可选）
        sample_pages: 采样页数（None 表示全部）
        debug: 调试模式

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
    native_blocks = [
        block for block in iter_native_text_blocks(doc)
        if int(block["page_index"]) < num_pages
    ]
    blocks_by_page: Dict[int, List[Dict[str, Any]]] = {}
    for block in native_blocks:
        blocks_by_page.setdefault(int(block["page_index"]), []).append(block)

    for pno in range(num_pages):
        units = []
        for blk_idx, blk in enumerate(blocks_by_page.get(pno, [])):
            for ln_idx, ln in enumerate(blk.get("lines", [])):
                spans = ln.get("spans", [])
                if not spans:
                    continue

                text = "".join(sp.get("text", "") for sp in spans)
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

    # 双栏检测
    num_columns, column_gap, all_units = detect_columns(all_units, page_size[0], debug=debug)

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
            json.dump(layout_model.to_dict(), f, indent=2, ensure_ascii=False)
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
