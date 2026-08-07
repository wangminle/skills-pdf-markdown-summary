#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A1-1: Layout 后端包。

后端协议定义在 base.py，具体实现：
- pymupdf_layout.py: PyMuPDF4LLM Layout 后端（通过 pymupdf4llm.to_markdown API）
"""
from __future__ import annotations

from .base import LayoutBackend, get_backend, is_layout_available

__all__ = [
    "LayoutBackend",
    "get_backend",
    "is_layout_available",
]
