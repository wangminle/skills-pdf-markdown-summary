#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""独立公式（display equation）区域检测与分组。

扫描版 PDF 的 OCR 文本层会把一个公式拆成多个碎片段落（例如 Kappa 公式被拆成
`P(A) - P(E)` / `K--` / `1 - P(E)` 三段），直接序列化进 Markdown 不可可靠消费；
数字排版文档的独立公式也常被行内符号破坏 Markdown 语法（`*`/`_`/`^`）。

本模块只做「检测与分组」，不猜测公式内容：命中的区域由调用方按原页证据
截图保留，或在禁用图片时整块合并为代码块。宁可漏检（公式保持原文段落），
不可误检（正文被截图后文本丢失检索能力）。

种子命中后，再按同一栏内的实际成员框补全竖向分子/分母、求和限、高括号和
混在相邻 OCR 块里的公式部分。补全同时受同栏、资产排除区和中间正文屏障约束。
无法补成完整公式的悬挂碎片（例如孤立的 `k=0`）标记为待复核，调用方不得把它
包装成图片。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# 强数学信号：等号族 / 求和积分族 / 比例号。命中任一即可构成强信号。
_STRONG_MATH_RE = re.compile(r"[=≈≠≤≥±×÷√∑∏∫∞∝→⇒]")

# OCR 分式线：`K--`（分子 K、分数线被识别为两个连字符）。
_FRACTION_BAR_RE = re.compile(r"[A-Za-z0-9)\]]--|--[A-Za-z0-9(\[]")

# 函数式记号 + 算术运算符：`P(A) - P(E)`、`1 - P(E)`。
_FUNC_APPLY_RE = re.compile(r"[A-Za-z]\([A-Za-z0-9, ]+\)")
_ARITH_OP_RE = re.compile(r"[=+\-*/−–]")

# 题注/列表/页码等排除模式。右对齐公式编号 `(2)` 另判，不走列表排除。
_CAPTION_START_RE = re.compile(r"(?i)^(?:figure|fig\.?|table|tab\.?|equation|eq\.?|图|表)\s*\d")
_LIST_START_RE = re.compile(r"^(?:[•·*]|\(\d+\)|\([a-z]\)|\d+\.\s)")
_PAGE_NUMBER_RE = re.compile(r"^\d{1,4}$")
_EQ_NUMBER_RE = re.compile(r"^\(\d{1,3}\)$")
_PROSE_WORD_RE = re.compile(r"[A-Za-z]{2,}")
# 中文正文：中文排版不会把独立公式写成纯中文句，含 CJK 字符的块按自然语言处理。
_CJK_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
# 以「英文词 + 空白」开头且该词不是等号左侧（`def = ...`）的块按正文处理：
# `Assume x=1.` 只有一个英文词，词数守卫保护不了它。负向检查必须放在前瞻里
# 跳过全部空白再找等号（`(?!\s*=)`，前瞻不回溯）：`\s+(?!=)` 这种写法在
# `def  = ...` 的双空格上会回退一个空格、看到第二个空格而误判成正文；
# `(?=\s)` 则保住「词后至少一个空白」的前提，`hm(t)` 这类紧跟非空白的词
# 不会被当成前导词。
_LEADING_PROSE_RE = re.compile(r"^[A-Za-z]{2,}\b(?=\s)(?!\s*=)")
_DANGLING_LIMIT_RE = re.compile(r"[A-Za-z]\s*=\s*\d+")
_DANGLING_LHS_RE = re.compile(r"[A-Za-z0-9^_\\()'′.+\-−–*∑∫∏]+\s*=")
# 特殊放行仅针对「起始变量 + 乘除符号」，变量可带下标或幂。
# BUG-153：不能在全文任意位置搜索，`We set x × y = 1.` 中也有数学子串，
# 但整块仍是正文。其他符号式碎片（如 `w^T x × b`）继续走既有判据。
# 刻意不含 `=`（BUG-147）和 `•`（OCR列表符）。
_INFIX_WORD_OP_RE = re.compile(r"^[A-Za-z0-9_]+(?:\^[A-Za-z0-9_+.\-−]+)?\s*[·×÷]\s*\S")

_SYMBOL_CHARS = set("()[]{}=+−–-*/^_%<>|~\\≈≠≤≥±×÷√∑∏∫∞∝→⇒")

# 判定公式主体时先剥掉的首尾装饰字符：括号、运算符与分隔标点。它们不影响
# 主体有无，`k=0 )` 与 `k=0)` 都必须先去掉括号再看 `k=0`。
_ACCESSORY_TRIM_CHARS = "".join(sorted(_SYMBOL_CHARS | set(",.;:")))
# 整块就是这些字符（`=`、`)`、`--`）时没有任何主体内容。
_PUNCT_ONLY_RE = re.compile(r"^[" + re.escape(_ACCESSORY_TRIM_CHARS) + r"]+$")
# 自成一块的关系运算符（`ℓj = g` 里的 `=`），说明两侧词是公式主体而非残片。
_RELATION_TOKEN_RE = re.compile(r"(?:^|\s)[=≈≠≤≥](?:\s|$)")

_MAX_TEXT_LEN = 200
_MAX_LINES = 5
_MIN_SYMBOL_RATIO = 0.08
_MAX_WIDTH_RATIO = 0.72
_MIN_INDENT_PT = 6.0
_GROUP_GAP_PT = 20.0
_MAX_GROUP_HEIGHT_PT = 240.0
_EXCLUSION_OVERLAP_RATIO = 0.3
_NEIGHBOR_GAP_PT = 10.0
_VERTICAL_ATTACH_PT = 8.0
# 续块哨兵的右侧扫描窗口。比邻接吸收的 _NEIGHBOR_GAP_PT（10pt）宽：
# 溢出窗口的续块既然吸收不进来，就该把分组标记为不完整，而不是放行一个
# 截断的公式还报告完整（Attention p7 公式 (3) 的排版间隙约 20pt）。
_CONTINUATION_SCAN_PT = 30.0


@dataclass
class EquationGroup:
    """一组构成同一独立公式区域的段落碎片。"""

    page: int
    bbox: List[float]
    member_keys: List[Any] = field(default_factory=list)
    member_bboxes: List[List[float]] = field(default_factory=list)
    # False：只检出悬挂碎片，边界不完整，调用方应保留原文并报告待复核。
    complete: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page": self.page,
            "bbox": list(self.bbox),
            "members": len(self.member_keys),
            "complete": self.complete,
        }


def _symbol_ratio(text: str) -> float:
    t = text.strip()
    if not t:
        return 0.0
    return sum(1 for c in t if c in _SYMBOL_CHARS) / len(t)


def _prose_word_count(text: str) -> int:
    return len(_PROSE_WORD_RE.findall(text))


def _is_short_math_token(text: str) -> bool:
    """单行短碎片：求和限、分母、符号、公式编号，而不是英文词。"""
    t = " ".join(text.split())
    if not t or len(t) > 24:
        return False
    if _prose_word_count(t) >= 2:
        return False
    if _EQ_NUMBER_RE.match(t):
        return True
    if _STRONG_MATH_RE.search(t) or (len(t) <= 12 and _FRACTION_BAR_RE.search(t)):
        return True
    if re.fullmatch(r"[A-Za-z]", t):
        return True
    if _prose_word_count(t) == 0 and len(t) <= 8:
        return True
    if len(t) <= 12 and _symbol_ratio(t) >= 0.2:
        return True
    return False


def _is_prose_block(text: str) -> bool:
    """自然语言块。含等号的短句（`We set a=1.`）也算正文。

    只数英文词会漏掉两类正文：只有一个英文词的祈使/陈述句（`Assume x=1.`）
    与零英文词的中文句（`温度≥20℃时停止。`）。因此先按「含中文」和
    「英文词 + 空格开头且该词不是等号左侧」两条判据识别正文；`def = ...`
    这类公式左侧不受影响。

    OCR 偶尔把分式首行和紧随的 where 句粘进同一块。首行仍是公式碎片、
    且整块带强数学信号时，不把整块当成正文，以便补全分母。
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    blob = " ".join(lines)
    words = _prose_word_count(blob)
    first = lines[0]
    if len(_CJK_RE.findall(blob)) >= 2:
        return True
    if _LEADING_PROSE_RE.match(blob):
        return True
    if _is_short_math_token(first) and len(blob) <= 180 and words < 12:
        if _STRONG_MATH_RE.search(blob) or words <= 3:
            return False
    if words >= 8:
        return True
    if words >= 2 and not _STRONG_MATH_RE.search(blob):
        return True
    if words >= 2 and blob.endswith(".") and _symbol_ratio(blob) < 0.2:
        return True
    return False


def _is_math_continuation(text: str) -> bool:
    """多字母变量开头的数学续块（`model · min(...)`）。

    前导词规则（`_LEADING_PROSE_RE`）按「英文词 + 空白」开头拦正文；公式
    右侧续块同样可能以多字母变量开头，词形上无法区分（BUG-152）。续块的
    仅在文本开头是一个变量（可含下标或幂）、直接接 `·`/`×`/`÷` 时
    特殊放行；正文中的数学子串不构成续块（BUG-153）。符号密度守卫
    拦住 `Müller · Berlin` 这类含间隔号的人名行；含 CJK 的正文直接排除。
    """
    t = " ".join(text.split())
    if not t or len(t) > _MAX_TEXT_LEN:
        return False
    if _CJK_RE.search(t):
        return False
    if not _INFIX_WORD_OP_RE.match(t):
        return False
    return _symbol_ratio(t) >= _MIN_SYMBOL_RATIO


def _is_attachable_component(
    text: str,
    bbox: Sequence[float],
    *,
    allow_bare_number: bool = False,
) -> bool:
    """种子公式旁边可以并入的块：符号、分母、高括号、公式编号、含公式的窄 OCR 块。

    纯数字块既可能是页面边距上的页码，也可能是被 OCR 拆成独立块的数字分母
    （`2`）。两者文本形态相同，只能靠位置区分，因此这里默认仍按页码排除；
    调用方确认该块与公式成员上下紧贴且横向对齐后，可用
    `allow_bare_number=True` 放行（见 `_stacked_number_component`）。
    """
    raw = text.strip()
    if _CAPTION_START_RE.match(raw):
        return False
    if _PAGE_NUMBER_RE.match(raw) and not allow_bare_number:
        return False
    if _LIST_START_RE.match(raw) and not _EQ_NUMBER_RE.match(raw):
        return False
    if not raw:
        return (bbox[2] - bbox[0]) <= 20.0
    # 多字母变量开头的续块先于前导词规则放行，避免公式右半边被误判正文。
    if _is_math_continuation(raw):
        return True
    if _is_prose_block(text):
        return False
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines and (_is_short_math_token(lines[0]) or _is_short_math_token(raw)):
        return True
    if _EQ_NUMBER_RE.match(raw):
        return True
    if _STRONG_MATH_RE.search(raw) and _prose_word_count(raw) <= 4 and len(raw) <= 160:
        return True
    if len(raw) <= 40 and _prose_word_count(raw) <= 1:
        return True
    return False


def _is_dangling_fragment(text: str) -> bool:
    """只有求和下标或等号左侧、没有公式主体的碎片。"""
    t = " ".join(text.split())
    if _DANGLING_LIMIT_RE.fullmatch(t):
        return True
    if _DANGLING_LHS_RE.fullmatch(t):
        return True
    return False


def _is_equation_fragment(text: str) -> bool:
    """判断短文本块是否像独立公式碎片（保守：多重信号同时满足）。"""
    t = text.strip()
    if not t or len(t) > _MAX_TEXT_LEN:
        return False
    lines = [ln for ln in t.splitlines() if ln.strip()]
    if not (1 <= len(lines) <= _MAX_LINES):
        return False
    # 句末标点：公式引导句（"1988):"）与正文残句不是公式。
    # 以句点结尾但含等号的（"E = mc^2."）仍算公式；两个以上英文词的句子不算。
    if _is_prose_block(t):
        return False
    if t.endswith((",", ";", ":")):
        return False
    if t.endswith(".") and not _STRONG_MATH_RE.search(t):
        return False
    if _PAGE_NUMBER_RE.match(t) or _LIST_START_RE.match(t) or _CAPTION_START_RE.match(t):
        return False
    strong = bool(_STRONG_MATH_RE.search(t))
    # OCR 分式线（`K--`）只在短文本里才是强信号：作者单位、页眉里的
    # 连字符（`AT&T Labs--Research`，LaTeX en-dash）同样命中该模式，
    # 长文本一律不算。
    if not strong and len(t) <= 12:
        strong = bool(_FRACTION_BAR_RE.search(t))
    strong = strong or (bool(_FUNC_APPLY_RE.search(t)) and bool(_ARITH_OP_RE.search(t)))
    if not strong:
        return False
    if _symbol_ratio(t) < _MIN_SYMBOL_RATIO:
        return False
    return True


def _page_columns(page_items: Sequence[Tuple[Sequence[float], str]]) -> List[Tuple[float, float]]:
    """由宽正文块估计本页文本栏的 x 范围（单栏或双栏）。

    按左缘聚类宽块；双栏判定要求最左、最右两个聚类各 ≥2 块且横向分离，
    中间聚类（扫描件常见的跨栏 OCR 表头块）不参与栏边界估计。
    """
    if not page_items:
        return []
    widths = [b[2] - b[0] for b, _t in page_items]
    max_w = max(widths) if widths else 0.0
    if max_w <= 0:
        return []
    wide = [b for b, _t in page_items if (b[2] - b[0]) >= 0.6 * max_w]
    if not wide:
        wide = [b for b, _t in page_items]
    wide = sorted(wide, key=lambda b: b[0])
    clusters: List[List[Sequence[float]]] = [[wide[0]]]
    for b in wide[1:]:
        if b[0] - clusters[-1][-1][0] <= 40.0:
            clusters[-1].append(b)
        else:
            clusters.append([b])
    if len(clusters) >= 2 and len(clusters[0]) >= 2 and len(clusters[-1]) >= 2:
        left_x1 = max(b[2] for b in clusters[0])
        right_x0 = min(b[0] for b in clusters[-1])
        # 扫描件 OCR 栏间距可能只有十几 pt（PARADISE 实测 ~14pt），阈值不能太严
        if right_x0 - left_x1 > 8.0:
            return [
                (min(b[0] for b in clusters[0]), left_x1),
                (right_x0, max(b[2] for b in clusters[-1])),
            ]
    return [(min(b[0] for b in wide), max(b[2] for b in wide))]


def _column_of(columns: Sequence[Tuple[float, float]], bbox: Sequence[float]) -> Optional[Tuple[float, float]]:
    center = (bbox[0] + bbox[2]) / 2.0
    best: Optional[Tuple[float, float]] = None
    best_dist = float("inf")
    for col in columns:
        col_center = (col[0] + col[1]) / 2.0
        dist = abs(center - col_center)
        if dist < best_dist:
            best, best_dist = col, dist
    return best


def _inside_column_geometry(bbox: Sequence[float], column: Tuple[float, float]) -> bool:
    """独立公式的几何特征：明显窄于栏宽且相对栏左缘有缩进。"""
    col_x0, col_x1 = column
    col_w = col_x1 - col_x0
    if col_w <= 0:
        return False
    width = bbox[2] - bbox[0]
    if width > _MAX_WIDTH_RATIO * col_w:
        return False
    if bbox[0] < col_x0 + _MIN_INDENT_PT:
        return False
    if bbox[2] > col_x1 + 2.0:
        return False
    return True


def _excluded_by_assets(page: int, bbox: Sequence[float],
                        exclusions: Sequence[Tuple[int, Sequence[float]]]) -> bool:
    """与图表资产区域重叠的块跳过——截图资产已覆盖该区域。"""
    area = max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])
    if area <= 0:
        return True
    for ex_page, ex_bbox in exclusions:
        if ex_page != page:
            continue
        iw = min(bbox[2], ex_bbox[2]) - max(bbox[0], ex_bbox[0])
        ih = min(bbox[3], ex_bbox[3]) - max(bbox[1], ex_bbox[1])
        if iw > 0 and ih > 0 and (iw * ih) / area >= _EXCLUSION_OVERLAP_RATIO:
            return True
    return False


def _h_gap(a: Sequence[float], b: Sequence[float]) -> float:
    return max(0.0, max(a[0] - b[2], b[0] - a[2]))


def _h_overlap(a: Sequence[float], b: Sequence[float]) -> float:
    return min(a[2], b[2]) - max(a[0], b[0])


def _v_gap(a: Sequence[float], b: Sequence[float]) -> float:
    return max(0.0, max(a[1] - b[3], b[1] - a[3]))


def _v_overlap(a: Sequence[float], b: Sequence[float]) -> float:
    return min(a[3], b[3]) - max(a[1], b[1])


def _spatially_attached(bbox: Sequence[float], members: Sequence[Sequence[float]], text: str) -> bool:
    """相对某个已有成员框邻接，而不是相对多行区域的总包围框。"""
    t = " ".join(text.split())
    neighbor_h = max(1.0, bbox[3] - bbox[1])
    number = bool(_EQ_NUMBER_RE.match(t))
    for member in members:
        vertical_gap = _v_gap(bbox, member)
        vertical_overlap = _v_overlap(bbox, member)
        horizontal_gap = _h_gap(bbox, member)
        horizontal_overlap = _h_overlap(bbox, member)
        if vertical_gap <= _VERTICAL_ATTACH_PT and (horizontal_overlap > 0 or horizontal_gap <= _NEIGHBOR_GAP_PT):
            return True
        if vertical_overlap >= 0.5 * neighbor_h and horizontal_gap <= _NEIGHBOR_GAP_PT:
            return True
        if number and vertical_overlap >= 0.35 * neighbor_h and bbox[0] >= member[0] - 2.0:
            return True
    return False


def _stacked_number_component(bbox: Sequence[float], members: Sequence[Sequence[float]]) -> bool:
    """纯数字块是不是分式的数字分母，而不是页面边距上的页码。

    数字分母紧贴在分子或分数线的正上/正下方，且横向与它基本重合；页码在
    纵向留白区，横向也不与公式主体对齐。两个条件同时满足才放行，避免把
    靠近公式的页码并进截图。
    """
    for member in members:
        if _v_gap(bbox, member) > _VERTICAL_ATTACH_PT:
            continue
        narrower = min(bbox[2] - bbox[0], member[2] - member[0])
        if narrower <= 0:
            continue
        if _h_overlap(bbox, member) >= 0.5 * narrower:
            return True
    return False


def _has_prose_barrier(
    page_items: Sequence[Tuple[Any, Sequence[float], str]],
    upper: Sequence[float],
    lower: Sequence[float],
    column: Tuple[float, float],
    columns: Sequence[Tuple[float, float]],
    page: int,
    exclusions: Sequence[Tuple[int, Sequence[float]]],
) -> bool:
    """两个公式种子之间若隔着同栏正文，就不能合成一组。"""
    for _key, bbox, text in page_items:
        if bbox[3] <= upper[3] + 0.5:
            continue
        if bbox[1] >= lower[1] - 0.5:
            continue
        if _column_of(columns, bbox) != column:
            continue
        if _h_overlap(bbox, upper) <= 0 and _h_overlap(bbox, lower) <= 0:
            continue
        if _excluded_by_assets(page, bbox, exclusions):
            continue
        if not _is_attachable_component(text, bbox):
            return True
    return False


def _absorb_line_neighbors(
    group: "EquationGroup",
    page_items: Sequence[Tuple[Any, Sequence[float], str]],
    columns: Sequence[Tuple[float, float]],
    taken_keys: set,
    *,
    page: int,
    exclusions: Sequence[Tuple[int, Sequence[float]]] = (),
) -> None:
    """把同一栏里构成同一公式的邻块并入区域。

    并入按每个已有成员的框判断，不用多行并集代替视觉行。条件：

    - 与公式种子属于同一栏（栏间距只有数 pt 时也不能把邻栏正文吸进来）；
    - 不落在图表排除框内；
    - 不是正文句、题注或列表；
    - 与某个成员横向紧邻，或在其上下 8pt 内且水平范围相交（分母、求和限、高括号）。
    右对齐的公式编号 `(2)` 可以离公式主体更远，但必须落在同一视觉行。

    纯数字块默认按页码排除；只有确认它紧贴在某个成员正上/正下方且横向基本
    重合（分式的数字分母）时才并入。
    """
    if not group.member_bboxes:
        return
    column = _column_of(columns, group.member_bboxes[0])
    if column is None:
        return
    changed = True
    while changed:
        changed = False
        for key, bbox, text in page_items:
            if key in group.member_keys or key in taken_keys:
                continue
            if _column_of(columns, bbox) != column:
                continue
            if _excluded_by_assets(page, bbox, exclusions):
                continue
            bare_number = bool(_PAGE_NUMBER_RE.match(" ".join(text.split())))
            if not _is_attachable_component(text, bbox, allow_bare_number=bare_number):
                continue
            if bare_number and not _stacked_number_component(bbox, group.member_bboxes):
                continue
            if not _spatially_attached(bbox, group.member_bboxes, text):
                continue
            group.bbox[0] = min(group.bbox[0], bbox[0])
            group.bbox[1] = min(group.bbox[1], bbox[1])
            group.bbox[2] = max(group.bbox[2], bbox[2])
            group.bbox[3] = max(group.bbox[3], bbox[3])
            group.member_keys.append(key)
            group.member_bboxes.append(list(bbox))
            taken_keys.add(key)
            changed = True


def _is_accessory_token(token: str) -> bool:
    """单个词是否是公式的边角料：纯符号、公式编号、页码或悬挂下标。"""
    if not token:
        return True
    if _PUNCT_ONLY_RE.match(token):
        return True
    if _EQ_NUMBER_RE.match(token) or _PAGE_NUMBER_RE.match(token):
        return True
    return _is_dangling_fragment(token)


def _equation_body_core(text: str) -> str:
    """去掉附属成分后剩下的主体文本，空串表示整块都是边角料。

    OCR/PyMuPDF 会把相邻的边角料合进同一个文本块（`k=0 )`），此时块长度
    不再能反映主体有无，必须按内容判断：先剥掉首尾括号与运算符，再逐个
    剔除纯符号、公式编号、页码和悬挂下标，看还剩不剩东西。
    """
    t = " ".join(text.split())
    if not t:
        return ""
    if _EQ_NUMBER_RE.match(t) or _PAGE_NUMBER_RE.match(t):
        return ""
    if _is_dangling_fragment(t):
        return ""
    core = t.strip(_ACCESSORY_TRIM_CHARS).strip()
    if not core or _is_dangling_fragment(core):
        return ""
    return " ".join(tok for tok in core.split() if not _is_accessory_token(tok))


def _is_equation_accessory(text: str) -> bool:
    """成员是否只是公式的附属碎片，而不是承载内容的主体。

    附属碎片即使被吸收进分组、甚至自己带强数学符号（孤立的 `∝`、`=`、
    `k=0`），也撑不起一个独立公式：只有 `n`、`)`、`+` 这类残片加公式编号
    `(2)`、页码时，公式主体仍然缺失，区域不得标记完整。同块合并的边角料
    （`k=0 )`、`k=0)`、`n k=0`）同样按内容判定，不能靠块长度放行。
    """
    t = " ".join(text.split())
    if not t:
        return True
    core = _equation_body_core(t)
    if not core:
        return True
    if len(t) <= 3:
        return True
    # 剩下的全是短残片时，只有块内存在独立关系运算符（`ℓj = g`）或函数应用
    # （`hm(t)`）才算主体；`n k=0`、`x + y` 这类无关系式的短串仍是边角料。
    if all(len(tok) <= 3 for tok in core.split()):
        if not _RELATION_TOKEN_RE.search(t) and not _FUNC_APPLY_RE.search(t):
            return True
    return False


def _is_equation_body(text: str) -> bool:
    """成员是否是公式主体，而不是附属碎片。

    附属碎片的判定见 `_is_equation_accessory`：公式编号、页码、悬挂下标
    与过短残片都只是公式的边角料，同块合并的边角料同样不算主体。
    """
    t = " ".join(text.split())
    if not t:
        return False
    return not _is_equation_accessory(t)


def _mark_completeness(group: EquationGroup, text_of: Dict[Any, str]) -> None:
    """组内至少有一个成员是公式主体，才认为边界完整。

    成员数量本身不是完整性证据：两个各自悬挂的碎片（`k=0` 与 `n=1`）合组、
    或悬挂下标又吸收了一个公式编号 `(2)`，成员数都会变成两个，但公式主体
    仍然缺失，必须继续标记待复核，不能被调用方包装成图片。单成员组同理：
    孤立的 `∝`、`=` 虽能以强符号身份种子分组，但只是附属碎片，主体缺失。
    """
    group.complete = any(
        _is_equation_body(text_of.get(key, "")) for key in group.member_keys
    )


def _has_unabsorbed_continuation(
    group: EquationGroup,
    page_items: Sequence[Tuple[Any, Sequence[float], str]],
    columns: Sequence[Tuple[float, float]],
    taken_keys: set,
    *,
    page: int,
    exclusions: Sequence[Tuple[int, Sequence[float]]] = (),
) -> bool:
    """分组右边界之外是否还有未并入的数学续块（BUG-152）。

    排版可能把同一行公式拆成左右两块（Attention p7 公式 (3)：`lrate = d−0.5`
    与 `model · min(...)`）。续块一旦被前导词规则拒绝、邻接吸收又够不着，
    左半边就会单独截图——输出半截公式却报告完整。这里在吸收结束后兜底：
    同栏、与分组纵向有交叠、左端落在分组右界扩展窗口内、右端超出分组、
    且内容不是正文的块，说明公式还在往右延伸，分组不得标记完整。
    """
    if not group.member_bboxes:
        return False
    column = _column_of(columns, group.member_bboxes[0])
    if column is None:
        return False
    member_keys = set(group.member_keys)
    for key, bbox, text in page_items:
        if key in member_keys or key in taken_keys:
            continue
        if _column_of(columns, bbox) != column:
            continue
        if _excluded_by_assets(page, bbox, exclusions):
            continue
        t = " ".join(text.split())
        if not t or _EQ_NUMBER_RE.fullmatch(t) or _PAGE_NUMBER_RE.fullmatch(t):
            continue
        if _v_overlap(bbox, group.bbox) <= 0:
            continue
        if bbox[0] > group.bbox[2] + _CONTINUATION_SCAN_PT:
            continue
        if bbox[2] <= group.bbox[2]:
            continue
        if _is_prose_block(t) and not _is_math_continuation(t):
            continue
        return True
    return False


def detect_equation_groups(
    items: Sequence[Tuple[Any, int, Sequence[float], str]],
    *,
    exclusions: Sequence[Tuple[int, Sequence[float]]] = (),
) -> List[EquationGroup]:
    """把构成同一独立公式的碎片段落分组。

    Args:
        items: (key, page, bbox, text) 序列，通常为正文段落块；
            key 原样回填到 EquationGroup.member_keys 供调用方定位。
        exclusions: (page, bbox) 序列，图表资产区域（重叠的块跳过，
            邻块吸收阶段同样生效）。

    Returns:
        按页面与纵坐标排序的 EquationGroup 列表。`complete=False` 的组
        只是悬挂碎片，调用方应保留原文并报告待复核。
    """
    by_page: Dict[int, List[Tuple[Any, Sequence[float], str]]] = {}
    for key, page, bbox, text in items:
        if not bbox or len(bbox) != 4:
            continue
        by_page.setdefault(page, []).append((key, bbox, text))

    groups: List[EquationGroup] = []
    for page in sorted(by_page):
        page_items = by_page[page]
        columns = _page_columns([(bbox, text) for _k, bbox, text in page_items])
        if not columns:
            continue
        candidates: List[Tuple[Any, List[float], str, Tuple[float, float]]] = []
        for key, bbox, text in page_items:
            if not _is_equation_fragment(text):
                continue
            column = _column_of(columns, bbox)
            if column is None or not _inside_column_geometry(bbox, column):
                continue
            if _excluded_by_assets(page, bbox, exclusions):
                continue
            candidates.append((key, list(bbox), text, column))
        candidates.sort(key=lambda c: (c[1][1], c[1][0]))

        # 分组必须按栏独立进行：双栏页面上左右栏的公式碎片在纵向上
        # 常常交错（左栏分子、右栏求和限、左栏分母），单趟顺序遍历会在
        # 每次栏切换时错误地断组。先把候选归入各自栏，再在栏内按纵向
        # 间隙合并；中间隔着正文时断开。
        by_column: Dict[Tuple[float, float], List[Tuple[Any, List[float], str]]] = {}
        for key, bbox, text, column in candidates:
            by_column.setdefault(column, []).append((key, bbox, text))

        page_groups: List[EquationGroup] = []
        for column, column_members in by_column.items():
            current: Optional[EquationGroup] = None
            for key, bbox, _text in column_members:
                blocked = (
                    current is not None
                    and _has_prose_barrier(page_items, current.bbox, bbox, column, columns, page, exclusions)
                )
                if (
                    current is not None
                    and not blocked
                    and bbox[1] - current.bbox[3] <= _GROUP_GAP_PT
                    and bbox[3] - current.bbox[1] <= _MAX_GROUP_HEIGHT_PT
                ):
                    current.bbox[0] = min(current.bbox[0], bbox[0])
                    current.bbox[1] = min(current.bbox[1], bbox[1])
                    current.bbox[2] = max(current.bbox[2], bbox[2])
                    current.bbox[3] = max(current.bbox[3], bbox[3])
                    current.member_keys.append(key)
                    current.member_bboxes.append(list(bbox))
                else:
                    if current is not None:
                        page_groups.append(current)
                    current = EquationGroup(
                        page=page,
                        bbox=list(bbox),
                        member_keys=[key],
                        member_bboxes=[list(bbox)],
                    )
            if current is not None:
                page_groups.append(current)

        # 公式行内未被碎片判据选中的邻块（被定义量、分母、编号等）并入截图范围
        taken_keys = {k for g in page_groups for k in g.member_keys}
        text_of = {key: text for key, _bbox, text in page_items}
        for g in page_groups:
            _absorb_line_neighbors(
                g, page_items, columns, taken_keys, page=page, exclusions=exclusions,
            )
            _mark_completeness(g, text_of)
            # 右边界之外还挂着吸收不进来的数学续块时，公式没有收全：
            # 保持原文待复核，不得把左半边当完整公式截图。
            if g.complete and _has_unabsorbed_continuation(
                g, page_items, columns, taken_keys, page=page, exclusions=exclusions,
            ):
                g.complete = False
        groups.extend(page_groups)
    groups.sort(key=lambda g: (g.page, g.bbox[1], g.bbox[0]))
    return groups


__all__ = [
    "EquationGroup",
    "detect_equation_groups",
]
