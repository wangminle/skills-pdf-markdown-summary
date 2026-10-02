#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Commit 08: Caption 检测

从 extract_pdf_assets.py 抽离的智能 caption 检测相关代码。

包含：
- find_all_caption_candidates: 查找所有 caption 候选项
- score_caption_candidate: 为候选项评分
- select_best_caption: 选择最佳 caption
- build_caption_index: 构建全文 caption 索引
- 辅助函数：get_page_images, get_page_drawings, is_bold_text 等
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple, Union

from .pdf_backend import PDFDocument, PDFPage, create_rect

# 避免循环导入
if TYPE_CHECKING:
    from .models import CaptionCandidate, CaptionIndex

# 导入标识符提取函数
from .idents import (
    FIGURE_LINE_RE as DEFAULT_FIGURE_LINE_RE,
    TABLE_LINE_RE as DEFAULT_TABLE_LINE_RE,
    extract_figure_ident,
    extract_table_ident,
    line_text_skip_superscript,
)

# 正文引用句式开头（"Table 8 shows that ..."）：段首恰好以编号对象开头、
# 后接陈述动词的句子是正文引用而非题注；其后续行会被 merge_caption_lines
# 误合并成高大的假题注。
_CAPTION_DESCRIPTION_VERB_ALT = (
    r"shows?|demonstrates?|presents?|describes?|illustrates?|reports?|compares?|"
    r"summarizes?|lists?|gives?|provides?|indicates?|suggests?"
)
_BODY_CITATION_OPENER_RE = re.compile(
    r"^\s*(?:Table|Tab\.?|Figure|Fig\.?)\s+[A-Za-z]?\d+\s+"
    rf"(?:{_CAPTION_DESCRIPTION_VERB_ALT})\b",
    re.I,
)

# 跨块续行信号：题注文本以此类字符/功能词结尾说明句子明显未完（BUG-130，
# PARADISE F6 块15 以 "Gordon," 结尾、块16 为 "1997), with AVM tagging"）。
# 标点之外只放少量英文连词/介词（and/with/of 等），其余词级情况不猜，
# 配合跨块左缘对齐、字号、间距约束，避免吞正文。
# 功能词必须带词边界（BUG-132）：否则 ImageNet 命中 et、data 命中 a，
# 完整题注会被误判为未完并吞入下一块正文。
_CAPTION_CONTINUATION_END_RE = re.compile(
    r"(?:[,;:，；：、(\[（—–\-&+]|\b(?:and|or|with|of|the|a|an|to|for|in|on|by|vs|et))$",
    re.I,
)

# 题注换行断词（BUG-137）：行末 [A-Za-z]- 且下一行以小写字母开头时，
# 优先使用全文中未跨行的完整词形（BUG-140），区分 Pro-/gramBench
# 与 reasoning-/intensive。两种拼写均存在时保留连字符。
# 无词形证据时才沿用 BUG-137 的前缀启发式：一般断词去连字符，
# 常见复合前缀保留（end-to-/end、well-/known）。这一回退仍有语言歧义。
_HYPHEN_KEEP_PREFIXES = frozenset({
    "all", "anti", "bi", "co", "counter", "cross", "de", "double", "down",
    "end", "ex", "extra", "first", "fore", "full", "half", "high", "ill",
    "in", "inter", "intra", "long", "low", "mid", "multi", "non", "of",
    "off", "on", "one", "out", "over", "part", "per", "post", "pre", "pro",
    "pseudo", "quasi", "re", "real", "second", "self", "semi", "short",
    "single", "so", "state", "sub", "super", "the", "third", "to", "tri",
    "ultra", "under", "up", "well",
})
_CAPTION_WORD_RE = re.compile(r"[A-Za-z]+(?:-[A-Za-z]+)*")
_HYPHEN_BREAK_RE = re.compile(r"([A-Za-z]+(?:-[A-Za-z]+)*)-$")


def collect_caption_word_forms(doc: Union[PDFDocument, Any]) -> Set[str]:
    """收集全文已有的完整词形，不拼接换行，供题注断词判定（BUG-140）。"""
    raw_doc = _unwrap_doc(doc)
    forms: Set[str] = set()
    for pno in range(len(raw_doc)):
        forms.update(word.casefold() for word in _CAPTION_WORD_RE.findall(
            raw_doc[pno].get_text("text")
        ))
    return forms


def _join_caption_text(parts: List[str], word_forms: Optional[Set[str]] = None) -> str:
    """拼接题注各行，完整词形证据优先；无证据时沿用断词启发式。"""
    if not parts:
        return ""
    forms = word_forms or set()
    out = parts[0]
    for part in parts[1:]:
        m = _HYPHEN_BREAK_RE.search(out)
        if m and part[:1].islower():
            next_word = _CAPTION_WORD_RE.match(part)
            suffix = next_word.group() if next_word else ""
            joined = (m.group(1) + suffix).casefold()
            hyphenated = (m.group(1) + "-" + suffix).casefold()
            # 两种拼写均有证据时保留原连字符，避免有损规范化。
            if hyphenated in forms:
                out += part
            elif joined in forms:
                out = out[:-1] + part
            elif m.group(1).rsplit("-", 1)[-1].lower() in _HYPHEN_KEEP_PREFIXES:
                out += part
            else:
                out = out[:-1] + part
        else:
            out += " " + part
    return out

# 模块日志器
logger = logging.getLogger(__name__)


# ============================================================================
# 辅助函数
# ============================================================================

def _unwrap_page(page: Union[PDFPage, Any]) -> Any:
    return getattr(page, "raw", page)


def _unwrap_doc(doc: Union[PDFDocument, Any]) -> Any:
    return getattr(doc, "raw", doc)


def get_page_images(page: Union[PDFPage, Any]) -> List[Any]:
    """
    提取页面中所有图像对象的边界框。

    Args:
        page: PyMuPDF 页面对象

    Returns:
        fitz.Rect 列表
    """
    images: List[Any] = []
    try:
        raw_page = _unwrap_page(page)
        dict_data = raw_page.get_text("dict")
        from .extract_helpers import collect_image_rects
        images = collect_image_rects(dict_data, raw_page.rect)
    except Exception as e:
        page_no = getattr(_unwrap_page(page), "number", None)
        extra = {'stage': 'get_page_images'}
        if isinstance(page_no, int):
            extra['page'] = page_no + 1
        logger.warning(f"Failed to parse page images: {e}", extra=extra)
    return images


def get_page_drawings(page: Union[PDFPage, Any]) -> List[Any]:
    """
    提取页面中所有绘图对象的边界框。

    Args:
        page: PyMuPDF 页面对象

    Returns:
        fitz.Rect 列表
    """
    drawings: List[Any] = []
    try:
        raw_page = _unwrap_page(page)
        for dr in raw_page.get_drawings():
            r = dr.get("rect")
            if r:
                drawings.append(r)
    except Exception as e:
        page_no = getattr(_unwrap_page(page), "number", None)
        extra = {'stage': 'get_page_drawings'}
        if isinstance(page_no, int):
            extra['page'] = page_no + 1
        logger.warning(f"Failed to parse page drawings: {e}", extra=extra)
    return drawings


def get_next_line_text(block: Dict, current_line_idx: int) -> str:
    """
    获取当前行的下一行文本。

    Args:
        block: 文本块字典
        current_line_idx: 当前行索引

    Returns:
        下一行文本
    """
    lines = block.get("lines", [])
    if current_line_idx + 1 < len(lines):
        next_line = lines[current_line_idx + 1]
        text = "".join(sp.get("text", "") for sp in next_line.get("spans", []))
        return text.strip()
    return ""


def get_paragraph_length(block: Dict) -> int:
    """
    计算 block 中所有文本的总长度。

    Args:
        block: 文本块字典

    Returns:
        文本总长度
    """
    total_len = 0
    for ln in block.get("lines", []):
        for sp in ln.get("spans", []):
            total_len += len(sp.get("text", ""))
    return total_len


def is_bold_text(spans: List[Dict]) -> bool:
    """
    判断文本是否加粗（检查 font flags）。

    Font flags bit 4 (value 16) 表示 bold。

    Args:
        spans: spans 列表

    Returns:
        是否加粗
    """
    return any(sp.get("flags", 0) & 16 for sp in spans)


def min_distance_to_rects(rect: Any, rect_list: List[Any]) -> float:
    """
    计算 rect 到 rect_list 中所有矩形的最小距离。

    Args:
        rect: 源矩形
        rect_list: 目标矩形列表

    Returns:
        最小距离
    """
    if not rect_list:
        return float('inf')

    min_dist = float('inf')
    for r in rect_list:
        dist_above = abs(rect.y0 - r.y1)
        dist_below = abs(rect.y1 - r.y0)
        dist = min(dist_above, dist_below)
        min_dist = min(min_dist, dist)

    return min_dist


_EXPLICIT_CAPTION_PREFIX_RE = re.compile(
    # 子图尾巴（3a / 5-b / 6(c)）与 idents.py 的 FIGURE_LINE_RE 保持同一套
    # 可选模式，否则 "Figure 3a:" 会被主正则匹配、却不算显式题注，
    # 导致 inventory reconcile 系统性缺子图。
    r"^(?:figure|fig\.?|table|图|表)\s*[A-Z]?\d+"
    r"(?:\s*[-–]?\s*[A-Za-z]|\s*\([A-Za-z]\))?"
    r"\s*",
    re.IGNORECASE,
)
# 句点后能证明「这不是题注」的接续词。只有这些才算证据——它们几乎不可能
# 出现在题注开头。the/this/our 一类常见句首词不能当判据："Figure 1. The
# proposed architecture" / "Figure 1. Our proposed model" 都是论文里最常见
# 的题注写法，按句首词拒绝会让真实题注既不被提取、也不进 inventory（补裁
# 同样依赖题注识别），静默消失。
_PERIOD_BODY_OPENER_ALT = (
    r"also|we|here|note that|let us|in this|in the following"
    r"|as shown|as we|as discussed"
)
_PERIOD_BODY_OPENER_RE = re.compile(
    rf"^(?:{_PERIOD_BODY_OPENER_ALT})\b",
    re.IGNORECASE,
)
_PERIOD_BODY_CITATION_RE = re.compile(
    r"^(?:figure|fig\.?|table|图|表)\s*[A-Z]?\d+\s*\.\s*(\S.*)$",
    re.IGNORECASE | re.DOTALL,
)


def _period_tail_reads_as_body(after: str) -> bool:
    """句点之后的内容是否读作正文接续（而非题注）。"""
    tail = after.lstrip()
    # 题注描述里常见 Section/Table/Equation 交叉引用；它们不能
    # 单独推翻行首的显式题注标记。只有几乎不会开启题注的接续词
    # （we/also/in this/as shown 等）才是足够的正文证据。
    return bool(_PERIOD_BODY_OPENER_RE.match(tail))


def is_explicit_caption_format(text: str) -> bool:
    """True when the line uses a real caption marker such as ``Table 3 |`` or ``Figure 1:``.

    ``Table 6. Also, we evaluate...`` is a body citation, not a caption, even though it
    starts with a number and a period.
    """
    stripped = (text or "").strip()
    match = _EXPLICIT_CAPTION_PREFIX_RE.match(stripped)
    if not match:
        return False
    rest = stripped[match.end():]
    if rest.startswith((":", "：", "|")):
        return True
    if rest.startswith("."):
        after = rest[1:].lstrip()
        if not after or _period_tail_reads_as_body(after):
            return False
        return True
    return False


def is_bare_caption_label(text: str) -> bool:
    """True for standalone labels such as ``Figure 22`` or ``Table 3`` with no following marker."""
    stripped = (text or "").strip()
    match = _EXPLICIT_CAPTION_PREFIX_RE.match(stripped)
    if not match:
        return False
    return not stripped[match.end():].strip()


def is_caption_anchor_candidate(text: str) -> bool:
    """True for explicit captions and bare numbered labels that should stay in inventory."""
    return is_explicit_caption_format(text) or is_bare_caption_label(text)


def is_likely_reference_context(text: str) -> bool:
    """
    判断文本是否像正文引用（而非图注描述）。

    Args:
        text: 文本内容

    Returns:
        是否像正文引用
    """
    if is_explicit_caption_format(text):
        return False

    text_lower = text.lower()

    reference_patterns = [
        r'as shown in', r'see (figure|table)', r'refer to',
        r'shown in (figure|table)', r'listed in (table)',
        r'^table\s+[A-Z]?\d+\s+appendix\b',
        r'^table\s+[A-Z]?\d+\s*,\s*(?:we|this|the)\b',
        # 与 _PERIOD_BODY_OPENER_ALT 同一口径：this/the 不算正文证据
        # （"Figure 1. The proposed architecture" 是题注），只有真正的接续词才算。
        rf'^(?:table|figure|fig\.?)\s+[A-Z]?\d+\s*\.\s*(?:{_PERIOD_BODY_OPENER_ALT})\b',
        # 复数标签 + 编号并列（"Figures 3 and 4" / "Figures A9-A11"）是正文
        # 引用的强信号，真实 caption 极少以复数列举开头；连字符两侧允许零
        # 空格（"A9-A11" 是最常见的区间写法）。
        r'^(?:tables|tabs\.?|figures|figs\.?)\s+[a-z]?\d+\s*(?:and|,|;|–|-|to)\s*[a-z]?\d+\b',
        # 「标签 + 编号 + 描述动词 + that/how 从句」是正文句；限定 that/how
        # 是为了不误伤 "Figure 3 shows the architecture" 这类句式 caption。
        rf'^(?:tables?|tabs?\.?|figures?|figs?\.?)\s*[a-z]?\d+\s+(?:{_CAPTION_DESCRIPTION_VERB_ALT})\s+(?:that|how)\b',
        # 同一句式若在句号后继续写下一句，已经是正文而不是题注。
        # "Table 4 presents the results of the factor analysis. The six factors..."
        rf'^(?:tables?|tabs?\.?|figures?|figs?\.?)\s+[a-z]?\d+\s+(?:{_CAPTION_DESCRIPTION_VERB_ALT})\b.{{8,}}\.\s+\w',
        r'如.*所示', r'见.*图', r'参见', r'如.*表.*所示',
        r'according to (figure|table)', r'based on (figure|table)',
        r'from (figure|table)',
    ]

    for pat in reference_patterns:
        if re.search(pat, text_lower):
            return True

    return False


def is_likely_caption_context(text: str) -> bool:
    """
    判断文本是否像图注描述（而非正文引用）。

    Args:
        text: 文本内容

    Returns:
        是否像图注描述
    """
    if is_explicit_caption_format(text):
        return True

    text_lower = text.lower()

    caption_patterns = [
        r'shows?', r'illustrates?', r'depicts?', r'displays?',
        r'compares?', r'presents?', r'demonstrates?',
        r'显示', r'展示', r'说明', r'比较', r'给出', r'呈现',
    ]

    for pat in caption_patterns:
        if re.search(pat, text_lower):
            return True

    return False


# ============================================================================
# Caption 候选项查找
# ============================================================================

def find_all_caption_candidates(
    page: "fitz.Page",
    page_num: int,
    pattern: re.Pattern,
    kind: str = 'figure',
    word_forms: Optional[Set[str]] = None,
) -> List["CaptionCandidate"]:
    """
    在单页中找到所有匹配 pattern 的候选 caption。

    Args:
        page: PyMuPDF 页面对象
        page_num: 页码（0-based）
        pattern: 匹配 caption 的正则表达式
        kind: 'figure' 或 'table'
        word_forms: 全文完整词形；None 时从页面所属文档收集

    Returns:
        CaptionCandidate 列表
    """
    from .models import CaptionCandidate

    candidates: List[CaptionCandidate] = []

    try:
        if word_forms is None:
            word_forms = collect_caption_word_forms(_unwrap_page(page).parent)
        dict_data = page.get_text("dict")
        page_blocks = dict_data.get("blocks", [])

        for blk_idx, blk in enumerate(page_blocks):
            if blk.get("type", 0) != 0:  # 只处理文本 block
                continue

            for ln_idx, ln in enumerate(blk.get("lines", [])):
                spans = ln.get("spans", [])
                if not spans:
                    continue

                text = line_text_skip_superscript(spans)
                text_stripped = text.strip()

                match = pattern.match(text_stripped)
                if match:
                    # 根据 kind 提取正确的编号
                    if kind == 'figure':
                        number = extract_figure_ident(match)
                    elif kind == 'table':
                        number = extract_table_ident(match)
                    else:
                        try:
                            number = (match.group(1) or "").strip()
                        except IndexError:
                            number = ""

                    if not number:
                        continue

                    merged = merge_caption_lines(
                        blk, ln_idx, pattern,
                        following_blocks=page_blocks[blk_idx + 1:],
                        word_forms=word_forms,
                    )
                    candidate = CaptionCandidate(
                        rect=merged.rect if merged else create_rect(*ln.get("bbox", [0, 0, 0, 0])),
                        text=merged.text if merged else text_stripped,
                        number=number,
                        kind=kind,
                        page=page_num,
                        block_idx=blk_idx,
                        line_idx=ln_idx,
                        spans=spans,
                        block=blk,
                        score=0.0
                    )
                    candidates.append(candidate)

    except Exception as e:
        logger.warning(f"Failed to parse page {page_num + 1} for {kind} captions: {e}")

    return candidates


# ============================================================================
# Caption 候选项评分
# ============================================================================

def score_caption_candidate(
    candidate: "CaptionCandidate",
    images: List[Any],
    drawings: List[Any],
    debug: bool = False
) -> float:
    """
    为候选 caption 打分，判断其是真实图注的可能性。

    评分维度（总分 100）：
    1. 位置特征（40分）：距离图像/绘图对象的距离
    2. 格式特征（30分）：字体加粗、独立成段、后续标点
    3. 结构特征（20分）：下一行有描述、段落长度
    4. 上下文特征（10分）：语义分析

    Args:
        candidate: 候选项
        images: 页面中所有图像对象
        drawings: 页面中所有绘图对象
        debug: 是否输出调试信息

    Returns:
        得分（0-100+）
    """
    score = 0.0
    details = {}

    # === 1. 位置特征（40分）===
    all_objects = images + drawings
    min_dist = min_distance_to_rects(candidate.rect, all_objects)

    if min_dist < 10:
        position_score = 40.0
    elif min_dist < 20:
        position_score = 35.0
    elif min_dist < 40:
        position_score = 28.0
    elif min_dist < 80:
        position_score = 18.0
    elif min_dist < 150:
        position_score = 8.0
    elif min_dist < float('inf'):
        position_score = max(0, 5.0 - min_dist / 50.0)
    else:
        position_score = 0.0

    score += position_score
    details['position'] = position_score
    details['min_dist'] = min_dist

    # === 2. 格式特征（30分）===
    format_score = 0.0

    if is_bold_text(candidate.spans):
        format_score += 15.0
        details['bold'] = True
    else:
        details['bold'] = False

    num_lines = len(candidate.block.get('lines', []))
    if num_lines == 1:
        format_score += 10.0
        details['lines'] = 1
    elif num_lines == 2:
        format_score += 8.0
        details['lines'] = 2
    elif num_lines <= 4:
        format_score += 5.0
        details['lines'] = num_lines
    else:
        format_score += 0.0
        details['lines'] = num_lines

    text_prefix = candidate.text[:40]
    if ':' in text_prefix or '：' in text_prefix:
        format_score += 5.0
        details['punctuation'] = 'colon'
    elif '|' in text_prefix:
        format_score += 5.0
        details['punctuation'] = 'pipe'
    elif '.' in text_prefix and not text_prefix.endswith('et al.'):
        format_score += 3.0
        details['punctuation'] = 'period'
    elif '—' in text_prefix or '-' in text_prefix:
        format_score += 2.0
        details['punctuation'] = 'dash'
    else:
        details['punctuation'] = 'none'

    score += format_score
    details['format'] = format_score

    # === 3. 结构特征（20分）===
    structure_score = 0.0

    next_line_text = get_next_line_text(candidate.block, candidate.line_idx)
    if next_line_text:
        next_len = len(next_line_text)
        if next_len > 40:
            structure_score += 12.0
            details['next_line_len'] = next_len
        elif next_len > 15:
            structure_score += 8.0
            details['next_line_len'] = next_len
        else:
            structure_score += 3.0
            details['next_line_len'] = next_len
    else:
        details['next_line_len'] = 0

    para_length = get_paragraph_length(candidate.block)
    if para_length < 150:
        structure_score += 8.0
        details['para_length'] = para_length
    elif para_length < 300:
        structure_score += 4.0
        details['para_length'] = para_length
    elif para_length < 600:
        structure_score += 0.0
        details['para_length'] = para_length
    else:
        structure_score -= 8.0
        details['para_length'] = para_length

    score += structure_score
    details['structure'] = structure_score

    # === 4. 上下文特征（10分）===
    context_score = 0.0

    if is_explicit_caption_format(candidate.text) or is_likely_caption_context(candidate.text):
        context_score += 10.0
        details['context'] = 'caption'
    elif is_likely_reference_context(candidate.text):
        context_score -= 20.0
        details['context'] = 'reference'
    else:
        context_score += 0.0
        details['context'] = 'neutral'

    score += context_score
    details['context_score'] = context_score

    # === 总分 ===
    details['total'] = score

    if debug:
        print(f"\n=== Caption Scoring Debug ===")
        print(f"Candidate: {candidate.kind} {candidate.number} at page {candidate.page + 1}")
        print(f"Text: {candidate.text[:60].encode('utf-8', errors='replace').decode('utf-8')}...")
        print(f"Position score: {position_score:.1f} (min_dist={min_dist:.1f})")
        print(f"Format score: {format_score:.1f} (bold={details['bold']}, lines={details['lines']}, punct={details['punctuation']})")
        print(f"Structure score: {structure_score:.1f} (next_line={details['next_line_len']}, para={details['para_length']})")
        print(f"Context score: {context_score:.1f} ({details['context']})")
        print(f"Total score: {score:.1f}")

    return score


# ============================================================================
# 选择最佳 Caption
# ============================================================================

def select_best_caption(
    candidates: List["CaptionCandidate"],
    page: Union[PDFPage, Any],
    *,
    doc: Optional[Union[PDFDocument, Any]] = None,
    min_score_threshold: float = 25.0,
    debug: bool = False
) -> Optional["CaptionCandidate"]:
    """
    从候选列表中选择得分最高的真实图注。

    Args:
        candidates: 候选列表
        page: 页面对象
        doc: 文档对象（用于获取其他页面的图像/绘图对象）
        min_score_threshold: 最低得分阈值
        debug: 是否输出调试信息

    Returns:
        得分最高的候选项，如果没有合格候选则返回 None
    """
    if not candidates:
        return None

    scored_candidates: List[Tuple[float, "CaptionCandidate"]] = []

    for cand in candidates:
        score_page = page
        if doc is not None:
            try:
                raw_doc = _unwrap_doc(doc)
                score_page = raw_doc[cand.page]
            except Exception as e:
                logger.warning(
                    f"Failed to access page {cand.page + 1} for caption scoring: {e}",
                    extra={'page': cand.page + 1, 'stage': 'select_best_caption'}
                )
                score_page = page

        images = get_page_images(score_page)
        drawings = get_page_drawings(score_page)
        score = score_caption_candidate(cand, images, drawings, debug=debug)
        cand.score = score
        scored_candidates.append((score, cand))

    scored_candidates.sort(key=lambda x: x[0], reverse=True)

    if debug:
        print(f"\n=== All Candidates for {candidates[0].kind} {candidates[0].number} ===")
        for score, cand in scored_candidates:
            print(f"  Score {score:5.1f}: page {cand.page + 1}, y={cand.rect.y0:.1f}, text='{cand.text[:50]}...'")

    best_score, best_candidate = scored_candidates[0]

    if best_score < min_score_threshold:
        if debug:
            print(f"  >>> Best score {best_score:.1f} is below threshold {min_score_threshold}, rejecting all candidates")
        return None

    if debug:
        print(f"  >>> Selected: page {best_candidate.page + 1}, score {best_score:.1f}")

    return best_candidate


# ============================================================================
# 构建 Caption 索引
# ============================================================================

def build_caption_index(
    doc: Union[PDFDocument, Any],
    figure_pattern: Optional[re.Pattern] = None,
    table_pattern: Optional[re.Pattern] = None,
    debug: bool = False,
    word_forms: Optional[Set[str]] = None,
) -> "CaptionIndex":
    """
    预扫描全文，建立 caption 索引。

    Args:
        doc: PyMuPDF 文档对象
        figure_pattern: Figure caption 匹配正则。
            None 表示使用默认 Figure 正则；
            False（布尔值）表示跳过 Figure 检测。
        table_pattern: Table caption 匹配正则。
            None 表示使用默认 Table 正则；
            False（布尔值）表示跳过 Table 检测。
        debug: 是否输出调试信息
        word_forms: 可复用的全文完整词形；None 时扫描一次文档

    Returns:
        CaptionIndex 对象
    """
    from .models import CaptionIndex

    skip_figure = figure_pattern is False
    skip_table = table_pattern is False

    if not skip_figure and figure_pattern is None:
        figure_pattern = DEFAULT_FIGURE_LINE_RE

    if not skip_table and table_pattern is None:
        table_pattern = DEFAULT_TABLE_LINE_RE

    all_candidates: Dict[str, List["CaptionCandidate"]] = {}

    raw_doc = _unwrap_doc(doc)
    if word_forms is None:
        word_forms = collect_caption_word_forms(doc)
    for pno in range(len(raw_doc)):
        page = raw_doc[pno]
        images = get_page_images(page)
        drawings = get_page_drawings(page)

        if not skip_figure and figure_pattern is not None:
            figure_cands = find_all_caption_candidates(page, pno, figure_pattern, 'figure', word_forms)
            for cand in figure_cands:
                cand.score = score_caption_candidate(cand, images, drawings, debug=debug)
                key = f"figure_{cand.number}"
                if key not in all_candidates:
                    all_candidates[key] = []
                all_candidates[key].append(cand)

        if not skip_table and table_pattern is not None:
            table_cands = find_all_caption_candidates(page, pno, table_pattern, 'table', word_forms)
            for cand in table_cands:
                cand.score = score_caption_candidate(cand, images, drawings, debug=debug)
                key = f"table_{cand.number}"
                if key not in all_candidates:
                    all_candidates[key] = []
                all_candidates[key].append(cand)

    if debug:
        print(f"\n=== Caption Index Built ===")
        print(f"Total keys: {len(all_candidates)}")
        for key, cands in sorted(all_candidates.items()):
            print(f"  {key}: {len(cands)} candidates")

    return CaptionIndex(candidates=all_candidates)


# ============================================================================
# 多行 Caption 合并
# ============================================================================

def merge_caption_lines(
    block: Dict,
    start_line_idx: int,
    pattern: "re.Pattern",
    max_continuation_lines: int = 5,
    max_y_gap_ratio: float = 0.6,
    typical_line_h: Optional[float] = None,
    following_blocks: Optional[List[Dict]] = None,
    word_forms: Optional[Set[str]] = None,
) -> Optional["CaptionBlock"]:
    """
    将 caption 首行与后续续行合并为统一的 CaptionBlock。

    当图注为多行时（如 "Table 1: Summary of Results\\nfor All Models Tested"），
    需要将同一 block 中相邻续行合并到统一的 bbox 和完整文本中。

    合并条件：
    1. 续行与首行在同一个 block
    2. 续行不能匹配另一个 Figure/Table caption 正则
    3. 续行与前一行的 y 间距 < max_y_gap_ratio × typical_line_h
    4. 续行字号与首行相近（差值 < 3pt）

    跨块续行（BUG-130，仅当传入 following_blocks 且块内行已耗尽时尝试）：
    5. 当前合并文本必须以明确的未完信号结尾（逗号/分号/开括号/连字符等，
       见 _CAPTION_CONTINUATION_END_RE）；无信号不跨块
    6. 只进入阅读顺序上紧邻的下一个文本块，遇非文本块（图片等）即停
    7. 跨块行左缘与题注首行左缘差 ≤ 3pt（比块内 x 重叠更严格，
       用于排除首行缩进的正文段落）
    8. 每跨完一个整块须再次出现未完信号才能继续下一块

    Args:
        block: PyMuPDF 文本块字典
        start_line_idx: 首行在 block["lines"] 中的索引
        pattern: 当前 caption 正则（用于排除新 caption 行）
        max_continuation_lines: 最大续行数
        max_y_gap_ratio: y 间距与行高的最大比值
        typical_line_h: 典型行高（None 则自动估计）
        following_blocks: 同页阅读顺序上位于 block 之后的块列表；
            None 表示只做块内合并（旧行为）
        word_forms: 全文完整词形，用于区分排版断词与真实复合词

    Returns:
        CaptionBlock 或 None（如果首行索引无效）
    """
    from .models import CaptionBlock

    lines = block.get("lines", [])
    if not lines or start_line_idx >= len(lines):
        return None

    start_line = lines[start_line_idx]
    start_spans = start_line.get("spans", [])
    start_text = "".join(sp.get("text", "") for sp in start_spans).strip()
    start_bbox = create_rect(*start_line.get("bbox", [0, 0, 0, 0]))

    start_sizes = [float(sp.get("size", 10.0)) for sp in start_spans if "size" in sp]
    avg_font_size = sum(start_sizes) / len(start_sizes) if start_sizes else 10.0

    if typical_line_h is None or typical_line_h <= 0:
        typical_line_h = max(start_bbox.height, avg_font_size * 1.2)

    max_y_gap = max_y_gap_ratio * typical_line_h

    merged_rect = start_bbox
    merged_text_parts = [start_text]
    merged_count = 1
    prev_y1 = start_bbox.y1
    block_exhausted = True

    for i in range(start_line_idx + 1, min(start_line_idx + max_continuation_lines + 1, len(lines))):
        line = lines[i]
        line_spans = line.get("spans", [])
        line_text = "".join(sp.get("text", "") for sp in line_spans).strip()

        if not line_text:
            continue

        line_bbox = create_rect(*line.get("bbox", [0, 0, 0, 0]))

        if (pattern.match(line_text) or DEFAULT_FIGURE_LINE_RE.match(line_text)
                or DEFAULT_TABLE_LINE_RE.match(line_text)):
            block_exhausted = False
            break

        y_gap = line_bbox.y0 - prev_y1
        if y_gap > max_y_gap or line_bbox.y0 < start_bbox.y0 - 1:
            block_exhausted = False
            break
        if (min(line_bbox.x1, merged_rect.x1) <= max(line_bbox.x0, merged_rect.x0)
                and line_bbox.y0 > prev_y1 - 1.0):
            block_exhausted = False
            break

        line_sizes = [float(sp.get("size", 10.0)) for sp in line_spans if "size" in sp]
        avg_line_size = sum(line_sizes) / len(line_sizes) if line_sizes else 10.0

        if abs(avg_line_size - avg_font_size) > 3.0:
            block_exhausted = False
            break

        merged_rect = merged_rect | line_bbox
        merged_text_parts.append(line_text)
        merged_count += 1
        prev_y1 = line_bbox.y1

    # BUG-130：块内行耗尽且文本以未完信号结尾时，才尝试跨块续行
    # （PARADISE F6 题注被 PDF 生成器拆成两个块）。跨块行追加更严格的
    # 左缘对齐约束，整页正文段落首行通常缩进，进不来。
    if (following_blocks and block_exhausted
            and (merged_count - 1) < max_continuation_lines
            and _CAPTION_CONTINUATION_END_RE.search(
                " ".join(merged_text_parts).rstrip())):
        for fblk in following_blocks:
            if fblk.get("type", 0) != 0:
                break
            flines = fblk.get("lines", [])
            if not flines:
                break
            consumed_all = True
            for line in flines:
                line_spans = line.get("spans", [])
                line_text = "".join(sp.get("text", "") for sp in line_spans).strip()
                if not line_text:
                    continue
                line_bbox = create_rect(*line.get("bbox", [0, 0, 0, 0]))
                if (pattern.match(line_text) or DEFAULT_FIGURE_LINE_RE.match(line_text)
                        or DEFAULT_TABLE_LINE_RE.match(line_text)):
                    consumed_all = False
                    break
                y_gap = line_bbox.y0 - prev_y1
                if y_gap > max_y_gap or line_bbox.y0 < start_bbox.y0 - 1:
                    consumed_all = False
                    break
                if abs(line_bbox.x0 - start_bbox.x0) > 3.0:
                    consumed_all = False
                    break
                line_sizes = [float(sp.get("size", 10.0)) for sp in line_spans if "size" in sp]
                avg_line_size = sum(line_sizes) / len(line_sizes) if line_sizes else 10.0
                if abs(avg_line_size - avg_font_size) > 3.0:
                    consumed_all = False
                    break
                merged_rect = merged_rect | line_bbox
                merged_text_parts.append(line_text)
                merged_count += 1
                prev_y1 = line_bbox.y1
                if (merged_count - 1) >= max_continuation_lines:
                    consumed_all = False
                    break
            if not consumed_all:
                break
            if not _CAPTION_CONTINUATION_END_RE.search(
                    " ".join(merged_text_parts).rstrip()):
                break

    # 跨块信号检查必须看到行末原始连字符（"-" 本身是未完信号），
    # 所以只对最终文本做断词合并，上面的 " ".join 保持不变。
    full_text = _join_caption_text(merged_text_parts, word_forms)

    # 正文句 "Table 8 shows that RL plays..." 从段首开始，五条续行全部
    # 通过间距/字号/x 重叠检查，会合并成 60pt+ 的"题注"；这种假题注作为
    # 邻居参与方向判定时会把真题注的 above 证据挤掉（FunAudio T8 实测
    # 方向翻成 below）。描述动词本身也可出现在真题注中（BUG-136），
    # 只有共享引用判据确认 shows that/how 或多句正文时才拒绝合并。
    # 不能用合并高度判断：Kimi K3 F12 的四行长题注（60.6pt）是真实的。
    if (_BODY_CITATION_OPENER_RE.match(start_text)
            and is_likely_reference_context(full_text)):
        return None

    return CaptionBlock(
        rect=merged_rect,
        text=full_text,
        first_line_rect=start_bbox,
        line_count=merged_count,
        score=0.0,
    )


# ============================================================================
# Caption 引用检测
# ============================================================================

def is_caption_reference(
    text: str,
    block: Dict,
    pattern: "re.Pattern",
) -> bool:
    """
    判断一个 caption 正则匹配是否更像是正文引用而非真实图注。

    使用启发式规则：
    1. 上下文分析：如果包含 "see"、"as shown in" 等引用词
    2. 块结构：如果所在 block 包含很多行（>6），可能是正文段落中的引用
    3. 前缀分析：如果匹配文本在句子中间（前有逗号、连词等），是引用

    Args:
        text: 匹配行的完整文本
        block: 所在文本块字典
        pattern: caption 正则

    Returns:
        True 如果更像是正文引用
    """
    text_lower = text.lower()

    reference_prefixes = [
        'as shown in', 'see ', 'see figure', 'see table',
        'shown in figure', 'shown in table', 'refer to',
        'listed in table', 'according to figure', 'according to table',
        'from figure', 'from table', 'in figure', 'in table',
        'by figure', 'by table',
    ]
    for prefix in reference_prefixes:
        if text_lower.startswith(prefix):
            return True

    # 明确的冒号/竖线 caption 可能与前一段正文被 PDF 编码在同一个大文本块中；
    # 其语法本身比块行数更可靠，不能因长块上下文被误判成正文引用。
    if is_explicit_caption_format(text):
        return False
    period_citation = _PERIOD_BODY_CITATION_RE.match(text.strip())
    if period_citation and _period_tail_reads_as_body(period_citation.group(1)):
        return True

    num_lines = len(block.get("lines", []))
    total_text_len = sum(
        len("".join(sp.get("text", "") for sp in ln.get("spans", [])))
        for ln in block.get("lines", [])
    )

    if num_lines > 6 and total_text_len > 300:
        return True

    if is_likely_reference_context(text):
        return True

    return False


# ============================================================================
# 向后兼容别名
# ============================================================================

_extract_figure_ident = extract_figure_ident
_extract_table_ident = extract_table_ident
