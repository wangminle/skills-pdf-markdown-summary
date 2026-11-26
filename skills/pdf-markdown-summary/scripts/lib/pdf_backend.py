#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Commit 01B: PDF 后端适配层（薄适配 + 可选 pdfplumber）

设计原则（MVP）：
1. 不改变任何算法/阈值/默认值/输出字段（仍以现有 PyMuPDF 行为为准）
2. 主路径只用 PyMuPDF；pdfplumber 仅在显式调用 helper 时按需 import
3. MVP 阶段不做"统一数据结构转换"，直接透传 PyMuPDF 原始返回
4. 封装层保留 .raw（doc/page）以便渐进迁移

坐标约定：
- 内部统一使用 pt 单位的 (x0, y0, x1, y1)，原点在页面左上（与 PyMuPDF Rect 一致）
- pdfplumber 的 top/bottom 同样以页面顶部为 0，可直接映射

使用示例：
    from lib.pdf_backend import open_pdf, try_extract_tables_with_pdfplumber

    with open_pdf("paper.pdf") as doc:
        print(f"Pages: {doc.page_count}")
        page = doc[0]
        text_dict = page.get_text_dict()
        images = page.get_images()
        drawings = page.get_drawings()

        # 渲染区域
        pix = page.get_pixmap(dpi=300, clip=(0, 0, 500, 500))
        pix.save("region.png")

    # 可选：表格结构分析（需要 pdfplumber）
    tables = try_extract_tables_with_pdfplumber("paper.pdf", page_number=1)
"""

from __future__ import annotations

import os
import sys
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union
from pathlib import Path

# PyMuPDF 导入（保持与现有代码一致的入口名 'fitz'）
try:
    import fitz  # PyMuPDF
except ImportError as e:
    raise ImportError(
        "PyMuPDF (pymupdf) is required: pip install pymupdf"
    ) from e


# ============================================================================
# 按页解析缓存
# ============================================================================

# 一次转换里同一份 PDF 会被打开十几次（预验证、原生块扫描、版式模型、资产提取、
# 题注对账各开各的），同一页的 get_text("dict") 用相同参数被解析十来次。
# 这里把解析结果按「文件 + 页 + 调用」缓存在进程内，跨多次打开共享。
#
# 返回的是缓存对象本身，不做拷贝：调用方必须把它当只读。静态审计没有发现原地
# 修改的调用方；需要确认时打开 PDF_SKILL_CACHE_MUTATION_CHECK=1，命中前会
# 校验缓存内容未被改动，改动即报错。
#
# get_text("dict") 有一条例外：它只在同一文档实例内复用，每个实例的每一页首次
# 调用仍然真实执行。原因是 MuPDF 的副作用——对某页做过一次 get_text("dict")
# 之后，该文档实例里这一页随后的渲染像素会有细微变化（提取要读每个 span 的字体
# 信息，触发字体加载）。提取链路里每张图都在结构化文本提取之后渲染，Golden
# 基准也是这个状态的产物；若后续实例直接命中缓存，页面保持「干净」状态，渲染
# 就会与基准不同（Gemini 第 3 页 Figure 1 实测如此）。get_text("text") 与
# get_drawings() 没有这个副作用，照常跨实例共享。
_PARSE_CACHE_MB_ENV = "PDF_SKILL_PARSE_CACHE_MB"
_PARSE_CACHE_MUTATION_CHECK_ENV = "PDF_SKILL_CACHE_MUTATION_CHECK"
_DEFAULT_PARSE_CACHE_BYTES = 1024 * 1024 * 1024
# 只有这两种模式被反复调用；其余模式直接透传
_CACHED_TEXT_MODES = ("dict", "text")


def _env_int(name: str, default: int) -> int:
    """读整数环境变量：缺省或不是整数取默认值，负值按 0 处理。"""
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _estimate_bytes(value: Any) -> int:
    """递归估算解析结果占用的 Python 内存；fitz 对象只计代理本身。"""
    seen: set = set()
    total = 0
    stack = [value]
    while stack:
        obj = stack.pop()
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        total += sys.getsizeof(obj)
        if isinstance(obj, dict):
            stack.extend(obj.keys())
            stack.extend(obj.values())
        elif isinstance(obj, (list, tuple, set, frozenset)):
            stack.extend(obj)
    return total


class _ParseCache:
    """按页解析结果的进程内缓存：最近最少使用淘汰 + 内存预算。

    一个「文件 + 页 + 调用」只保留最新页面状态的一条；页面内容变了（内容流、
    旋转或页面框变化）就视为未命中并覆盖，所以调用方改过页面再读不会拿到旧结果。
    """

    def __init__(self, byte_budget: int, mutation_check: bool = False) -> None:
        self._byte_budget = byte_budget
        self._mutation_check = mutation_check
        self._entries: "OrderedDict[tuple, tuple]" = OrderedDict()  # slot -> (state, value, size, fingerprint)
        self._total_bytes = 0
        self._lock = threading.RLock()
        self.hits = 0
        self.misses = 0

    def get(self, slot: tuple, state: tuple, *, count_hit: bool = True) -> Tuple[bool, Any]:
        """按槽位与页面状态取缓存。

        count_hit=False 用于「调用方这次其实做了真实解析、只是想复用已有对象」的读取：
        命中也不计 hit，而计一次 miss。hits 只统计没有解析就直接返回的次数，
        misses 等于底层真实解析的次数。
        """
        with self._lock:
            entry = self._entries.get(slot)
            if entry is None or entry[0] != state:
                self.misses += 1
                return False, None
            self._entries.move_to_end(slot)
            if count_hit:
                self.hits += 1
            else:
                self.misses += 1
            if self._mutation_check:
                _state, value, _size, fingerprint = entry
                if hash(repr(value)) != fingerprint:
                    raise RuntimeError(
                        "按页解析缓存被调用方原地修改："
                        f"{os.path.basename(str(slot[0][0]))} 第 {slot[1] + 1} 页 {slot[2]}{slot[3]}"
                    )
            return True, entry[1]

    def put(self, slot: tuple, state: tuple, value: Any) -> None:
        with self._lock:
            previous = self._entries.pop(slot, None)
            if previous is not None:
                self._total_bytes -= previous[2]
            size = _estimate_bytes(value)
            if size > self._byte_budget:
                return  # 单条就超过预算：不缓存
            fingerprint = hash(repr(value)) if self._mutation_check else 0
            self._entries[slot] = (state, value, size, fingerprint)
            self._total_bytes += size
            while self._total_bytes > self._byte_budget and len(self._entries) > 1:
                _slot, (_state, _value, dropped, _fp) = self._entries.popitem(last=False)
                self._total_bytes -= dropped

    def drop_file(self, file_id: Optional[tuple]) -> None:
        if file_id is None:
            return
        with self._lock:
            for slot in [s for s in self._entries if s[0] == file_id]:
                self._total_bytes -= self._entries.pop(slot)[2]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._total_bytes = 0
            self.hits = 0
            self.misses = 0

    def snapshot(self) -> Dict[str, int]:
        with self._lock:
            return {
                "entries": len(self._entries),
                "bytes": self._total_bytes,
                "budget_bytes": self._byte_budget,
                "hits": self.hits,
                "misses": self.misses,
            }


_parse_cache = _ParseCache(
    _env_int(_PARSE_CACHE_MB_ENV, _DEFAULT_PARSE_CACHE_BYTES // (1024 * 1024)) * 1024 * 1024,
    mutation_check=bool(os.environ.get(_PARSE_CACHE_MUTATION_CHECK_ENV)),
)


def clear_parse_cache() -> None:
    """清空按页解析缓存（页面被程序改写、或测试需要时调用）。"""
    _parse_cache.clear()


def parse_cache_stats() -> Dict[str, int]:
    """缓存当前条目数、估算内存与命中计数，供诊断与测试。"""
    return _parse_cache.snapshot()


def _page_state(raw_page: Any) -> tuple:
    """页面内容状态：内容流对象号、旋转与页面框，任何一项变化都使缓存失效。"""
    return (
        tuple(raw_page.get_contents()),
        raw_page.rotation,
        tuple(raw_page.cropbox),
        tuple(raw_page.mediabox),
    )


# ============================================================================
# 核心数据结构（MVP: 薄封装，透传 PyMuPDF 原始结构）
# ============================================================================

@dataclass
class PDFDocument:
    """
    PDF 文档封装。

    Attributes:
        raw: 底层 PyMuPDF 文档对象 (fitz.Document)
        path: PDF 文件路径
    """
    raw: Any  # fitz.Document
    path: str
    # 文件身份（规范路径、大小、修改时间），按页解析缓存按它跨多次打开共享；
    # 内存文档或无法取文件状态时为 None，不缓存
    cache_id: Optional[tuple] = None
    # 本实例内已真实执行过 get_text("dict") 的页号：该提取会改变这一页随后的
    # 渲染，每个实例每页的首次调用必须真实执行，之后才允许命中缓存
    dict_extracted_pages: set = field(default_factory=set)

    @property
    def page_count(self) -> int:
        """文档页数"""
        return self.raw.page_count

    @property
    def metadata(self) -> Dict[str, str]:
        """文档元数据"""
        return dict(self.raw.metadata or {})

    def __getitem__(self, index: int) -> "PDFPage":
        """获取页面（0-based 索引）"""
        return PDFPage(raw=self.raw[index], doc=self)

    def __iter__(self) -> Iterator["PDFPage"]:
        """迭代所有页面"""
        for i in range(self.page_count):
            yield self[i]

    def __len__(self) -> int:
        """文档页数"""
        return self.page_count

    def extract_image(self, xref: int) -> Dict[str, Any]:
        """
        提取嵌入图像内容。

        Args:
            xref: 图像内部引用 ID

        Returns:
            包含 'image' (bytes), 'ext' (str), 等字段的字典
        """
        return self.raw.extract_image(xref)

    def close(self) -> None:
        """关闭文档"""
        if not getattr(self.raw, "is_closed", False):
            self.raw.close()

    def __enter__(self) -> "PDFDocument":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


@dataclass
class PDFPage:
    """
    PDF 页面封装。

    Attributes:
        raw: 底层 PyMuPDF 页面对象 (fitz.Page)
        doc: 所属文档
    """
    raw: Any  # fitz.Page
    doc: PDFDocument

    @property
    def page_number(self) -> int:
        """页码（1-based）"""
        return self.raw.number + 1

    @property
    def page_index(self) -> int:
        """页面索引（0-based）"""
        return self.raw.number

    @property
    def rect(self) -> "fitz.Rect":
        """
        页面边界框。

        Returns:
            fitz.Rect 对象，包含 (x0, y0, x1, y1)
        """
        return self.raw.rect

    @property
    def width(self) -> float:
        """页面宽度（pt）"""
        return self.raw.rect.width

    @property
    def height(self) -> float:
        """页面高度（pt）"""
        return self.raw.rect.height

    def _cache_slot(self, kind: str, args: tuple) -> Optional[tuple]:
        """解析缓存的槽位：文件 + 页 + 调用；不缓存时返回 None。"""
        file_id = getattr(self.doc, "cache_id", None)
        if file_id is None:
            return None
        return (file_id, int(self.raw.number), kind, args)

    def _cached(self, kind: str, args: tuple, parse) -> Any:
        slot = self._cache_slot(kind, args)
        if slot is None:
            return parse()
        state = _page_state(self.raw)
        hit, value = _parse_cache.get(slot, state)
        if hit:
            return value
        value = parse()
        _parse_cache.put(slot, state, value)
        return value

    def get_text(self, mode: str = "text") -> Union[str, Dict, List]:
        """
        提取文本。

        Args:
            mode: 提取模式
                - "text": 纯文本字符串
                - "dict": 完整结构（blocks, lines, spans）
                - "blocks": 文本块列表
                - "words": 单词列表
                - "html": HTML 格式

        Returns:
            根据 mode 返回不同格式的文本内容

        Note:
            "text" 的结果按页缓存并跨多次打开共享，调用方须当作只读；
            "dict" 只在同一文档实例内复用，每个实例每页的首次调用真实执行
            （它会改变这一页随后的渲染，见文件头的说明）。
        """
        if mode == "dict":
            return self._dict_text()
        if mode in _CACHED_TEXT_MODES:
            return self._cached("text", (mode,), lambda: self.raw.get_text(mode))
        return self.raw.get_text(mode)

    def _dict_text(self) -> Dict[str, Any]:
        parse = lambda: self.raw.get_text("dict")  # noqa: E731 - 绑定模式，供 _cached 无参调用
        extracted = getattr(self.doc, "dict_extracted_pages", None)
        page_index = int(self.raw.number)
        slot = self._cache_slot("text", ("dict",))
        if extracted is None or slot is None:
            return parse()  # 内存文档或伪造的文档对象：不缓存，行为与没有缓存时一致
        if page_index not in extracted:
            # 首次调用真实执行：保持与没有缓存时相同的页面渲染状态。
            # 解析成功后才记入已提取集合，中途抛错不会被误标成已做过
            value = parse()
            extracted.add(page_index)
            state = _page_state(self.raw)
            # 这一次是真实解析，命中已有条目也不算 hit
            hit, cached = _parse_cache.get(slot, state, count_hit=False)
            if hit:
                return cached  # 别的实例已放入同一页的结果，不再重复估算内存
            _parse_cache.put(slot, state, value)
            return value
        return self._cached("text", ("dict",), parse)

    def get_text_dict(self) -> Dict[str, Any]:
        """
        获取结构化文本（透传 PyMuPDF 的 get_text("dict")）。

        Returns:
            包含 'blocks', 'width', 'height' 等字段的字典（按页缓存，调用方须当作只读）
        """
        return self.get_text("dict")

    def get_images(self, full: bool = True) -> List[Tuple]:
        """
        获取页面上的嵌入图像列表。

        Args:
            full: 是否返回完整信息

        Returns:
            图像信息元组列表，每个元组包含 (xref, smask, width, height, ...)
        """
        return self.raw.get_images(full=full)

    def get_image_rects(self, xref: int) -> List["fitz.Rect"]:
        """
        获取指定图像在页面上的位置。

        Args:
            xref: 图像引用 ID

        Returns:
            图像边界框列表
        """
        return self.raw.get_image_rects(xref)

    def get_drawings(self) -> List[Dict[str, Any]]:
        """
        获取页面上的矢量图形（路径、线条、矩形等）。

        Returns:
            矢量图形信息列表，每个元素包含 'rect', 'items', 'fill', 'color' 等字段
            （按页缓存并跨多次打开共享，调用方须当作只读）
        """
        return self._cached("drawings", (), self.raw.get_drawings)

    def get_pixmap(
        self,
        dpi: int = 150,
        clip: Optional[Union[Tuple[float, float, float, float], "fitz.Rect"]] = None,
        alpha: bool = False,
    ) -> "fitz.Pixmap":
        """
        渲染页面为位图。

        Args:
            dpi: 渲染分辨率
            clip: 裁剪区域 (x0, y0, x1, y1) 或 fitz.Rect
            alpha: 是否包含透明通道

        Returns:
            fitz.Pixmap 对象
        """
        mat = fitz.Matrix(dpi / 72, dpi / 72)

        # 处理 clip 参数
        clip_rect = None
        if clip is not None:
            if isinstance(clip, (tuple, list)):
                clip_rect = fitz.Rect(clip)
            else:
                clip_rect = clip

        return self.raw.get_pixmap(matrix=mat, clip=clip_rect, alpha=alpha)

    def get_bboxlog(self) -> List[Tuple[str, Tuple[float, float, float, float]]]:
        """
        获取页面元素边界框日志（PyMuPDF 新 API）。

        Returns:
            元素类型和边界框的列表
        """
        if hasattr(self.raw, "get_bboxlog"):
            return self.raw.get_bboxlog()
        return []

    def draw_rect(
        self,
        rect: Union[Tuple[float, float, float, float], "fitz.Rect"],
        color: Tuple[float, float, float] = (1, 0, 0),
        width: float = 1.0,
        fill: Optional[Tuple[float, float, float]] = None,
    ) -> None:
        """
        在页面上绘制矩形（用于调试可视化）。

        Args:
            rect: 矩形边界框
            color: 边框颜色 (R, G, B)，范围 0-1
            width: 线宽
            fill: 填充颜色（可选）
        """
        if isinstance(rect, (tuple, list)):
            rect = fitz.Rect(rect)

        # 页面内容被改写：这份文件的解析缓存全部作废
        _parse_cache.drop_file(getattr(self.doc, "cache_id", None))
        shape = self.raw.new_shape()
        shape.draw_rect(rect)
        shape.finish(color=color, width=width, fill=fill)
        shape.commit()


# ============================================================================
# 工厂函数
# ============================================================================

def open_pdf(pdf_path: Union[str, Path]) -> PDFDocument:
    """
    打开 PDF 文档。

    Args:
        pdf_path: PDF 文件路径

    Returns:
        PDFDocument 实例

    Raises:
        FileNotFoundError: 文件不存在
        RuntimeError: PDF 打开失败

    Example:
        with open_pdf("paper.pdf") as doc:
            for page in doc:
                print(page.get_text())
    """
    path_str = str(pdf_path)

    if not Path(path_str).exists():
        raise FileNotFoundError(f"PDF not found: {path_str}")

    try:
        raw_doc = fitz.open(path_str)
    except Exception as e:
        raise RuntimeError(f"Failed to open PDF: {path_str}") from e

    # 旋转页上 get_text/get_drawings 返回 MediaBox（未旋转）坐标，而
    # get_pixmap(clip=...) 使用 page.rect（旋转后）坐标，直接裁剪会得到纯白图。
    # 打开时去掉 /Rotate，统一到内容坐标系，文本、对象、渲染与评估一致。
    for page_index in range(raw_doc.page_count):
        page = raw_doc[page_index]
        if page.rotation:
            page.set_rotation(0)

    try:
        stat = os.stat(path_str)
        cache_id = (os.path.realpath(path_str), stat.st_size, stat.st_mtime_ns)
    except OSError:
        cache_id = None
    return PDFDocument(raw=raw_doc, path=path_str, cache_id=cache_id)


def managed_pdf_document(func):
    """为接收 ``pdf_path`` 的函数注入并可靠关闭 PDFDocument。"""
    @wraps(func)
    def wrapper(pdf_path, *args, **kwargs):
        with open_pdf(pdf_path) as doc:
            return func(pdf_path, *args, _doc=doc, **kwargs)

    return wrapper


# ============================================================================
# 可选：pdfplumber 表格提取辅助（按需加载，不影响主流程）
# ============================================================================

def try_extract_tables_with_pdfplumber(
    pdf_path: str,
    page_number: int,
    table_settings: Optional[Dict[str, Any]] = None,
) -> Optional[List[List[List[str]]]]:
    """
    可选：使用 pdfplumber 提取表格结构。

    仅用于"表格结构分析/调试"，不影响现有表格截图主流程。

    Args:
        pdf_path: PDF 文件路径
        page_number: 页码（1-based）
        table_settings: pdfplumber 表格设置（可选）

    Returns:
        表格数据列表，每个表格是二维字符串列表；
        如果 pdfplumber 不可用或提取失败，返回 None

    Example:
        tables = try_extract_tables_with_pdfplumber("paper.pdf", page_number=3)
        if tables:
            for table in tables:
                for row in table:
                    print(row)
    """
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        # pdfplumber 不可用，静默返回 None
        return None

    try:
        with pdfplumber.open(pdf_path) as pdf:
            if page_number < 1 or page_number > len(pdf.pages):
                return None

            page = pdf.pages[page_number - 1]

            # 默认设置
            settings = {
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
                "snap_tolerance": 3,
            }
            if table_settings:
                settings.update(table_settings)

            return page.extract_tables(table_settings=settings)
    except Exception:
        return None


def try_debug_tablefinder_with_pdfplumber(
    pdf_path: str,
    page_number: int,
    output_path: str,
    table_settings: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    可选：使用 pdfplumber 生成表格调试可视化图像。

    Args:
        pdf_path: PDF 文件路径
        page_number: 页码（1-based）
        output_path: 输出图像路径
        table_settings: pdfplumber 表格设置（可选）

    Returns:
        True 如果成功生成，False 如果失败或 pdfplumber 不可用
    """
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        return False

    try:
        with pdfplumber.open(pdf_path) as pdf:
            if page_number < 1 or page_number > len(pdf.pages):
                return False

            page = pdf.pages[page_number - 1]
            im = page.to_image(resolution=150)

            settings = {
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
            }
            if table_settings:
                settings.update(table_settings)

            im.debug_tablefinder(table_settings=settings)
            im.save(output_path)
            return True
    except Exception:
        return False


# ============================================================================
# 便捷函数（兼容现有代码）
# ============================================================================

def rect_to_list(r: "fitz.Rect") -> List[float]:
    """
    将 fitz.Rect 转换为列表。

    Args:
        r: fitz.Rect 对象

    Returns:
        [x0, y0, x1, y1] 列表，保留一位小数
    """
    return [round(float(r.x0), 1), round(float(r.y0), 1),
            round(float(r.x1), 1), round(float(r.y1), 1)]


def create_rect(
    x0: float, y0: float, x1: float, y1: float
) -> "fitz.Rect":
    """
    创建 fitz.Rect 对象。

    Args:
        x0, y0: 左上角坐标
        x1, y1: 右下角坐标

    Returns:
        fitz.Rect 对象
    """
    return fitz.Rect(x0, y0, x1, y1)


def intersect_rects(r1: "fitz.Rect", r2: "fitz.Rect") -> "fitz.Rect":
    """
    计算两个矩形的交集。

    Args:
        r1, r2: fitz.Rect 对象

    Returns:
        交集 fitz.Rect（可能为空）
    """
    return r1 & r2


def union_rects(r1: "fitz.Rect", r2: "fitz.Rect") -> "fitz.Rect":
    """
    计算两个矩形的并集。

    Args:
        r1, r2: fitz.Rect 对象

    Returns:
        并集 fitz.Rect
    """
    return r1 | r2


def is_rect_empty(r: "fitz.Rect") -> bool:
    """
    检查矩形是否为空。

    Args:
        r: fitz.Rect 对象

    Returns:
        True 如果矩形为空或无效
    """
    return r.is_empty or r.is_infinite
