#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A1-1: Layout 后端协议与工厂。

定义 LayoutBackend 协议，所有后端实现此协议。
get_backend() 工厂根据名称返回后端实例，依赖缺失时返回 None。
"""
from __future__ import annotations

import logging
from typing import Optional, Protocol, runtime_checkable

from ..regions import LayoutResult

logger = logging.getLogger(__name__)


@runtime_checkable
class LayoutBackend(Protocol):
    """Layout 后端协议。

    所有 Layout 后端实现此协议。后端负责：
    1. 解析 PDF 的语义区域（picture/table/caption）
    2. 输出统一的 PageRegion 结构
    3. 实现 L0 缓存（key = PDF hash + 后端版本 + 参数版本）
    """

    @property
    def name(self) -> str:
        """后端名称（如 'pymupdf4llm'）。"""
        ...

    @property
    def version(self) -> str:
        """后端版本字符串。"""
        ...

    def is_available(self) -> bool:
        """检查后端依赖是否可用。"""
        ...

    def extract(self, pdf_path: str, pdf_hash: str, pages: Optional[list] = None) -> LayoutResult:
        """提取 PDF 的 Layout 语义区域。

        Args:
            pdf_path: PDF 文件路径
            pdf_hash: PDF 内容哈希（用于缓存 key）
            pages: 指定页码列表（1-based），None 表示全部页

        Returns:
            LayoutResult: Layout 提取结果
        """
        ...


def get_backend(backend_name: str) -> Optional[LayoutBackend]:
    """根据名称获取 Layout 后端实例。

    Args:
        backend_name: 后端名称 ('pymupdf4llm' | 'off')

    Returns:
        后端实例，依赖不可用时返回 None。
        backend_name='off' 或空时返回 None。
    """
    if not backend_name or backend_name.lower() == "off":
        return None

    name = backend_name.lower()

    if name == "pymupdf4llm":
        try:
            from .pymupdf_layout import PyMuPDFLayoutBackend

            backend = PyMuPDFLayoutBackend()
            if backend.is_available():
                return backend
            logger.warning(
                "Layout backend 'pymupdf4llm' requested but dependency not available; "
                "falling back to off"
            )
            return None
        except ImportError as e:
            logger.warning(
                "Failed to import PyMuPDFLayoutBackend: %s; falling back to off", e
            )
            return None

    logger.warning("Unknown layout backend: %s; falling back to off", backend_name)
    return None


def is_layout_available(backend_name: str) -> bool:
    """检查指定后端是否可用（不创建实例）。"""
    backend = get_backend(backend_name)
    return backend is not None
