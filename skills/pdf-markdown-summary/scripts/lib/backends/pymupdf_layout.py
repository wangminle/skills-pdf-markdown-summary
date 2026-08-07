#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A1-2: PyMuPDF4LLM Layout 后端适配器。

通过 pymupdf4llm.to_markdown(page_chunks=True) API 提取语义区域，
输出统一 PageRegion 结构。实现 L0 缓存（key = PDF hash + 后端版本 + 参数版本）。

依赖可选：pymupdf4llm 未安装时 is_available() 返回 False，
get_backend() 工厂会回退到 off。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..regions import (
    CAPTION_CLASSES,
    FIGURE_CLASSES,
    TABLE_CLASSES,
    LayoutResult,
    PageRegion,
    RegionBBox,
    classify_region,
)

logger = logging.getLogger(__name__)

# 参数版本：当 to_markdown 调用参数变更时递增
_PARAM_VERSION = "v1"


def _compute_pdf_hash(pdf_path: str) -> str:
    """计算 PDF 文件的 sha256 哈希（与 output.py 保持一致格式）。"""
    hasher = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()[:16]}"


def _cache_dir() -> Path:
    """L0 缓存目录。"""
    base = os.environ.get("PDF_SUMMARY_LAYOUT_CACHE_DIR", "")
    if base:
        p = Path(base)
    else:
        p = Path.home() / ".cache" / "pdf-summary-layout"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_key(pdf_hash: str, backend_version: str) -> str:
    """L0 缓存 key = PDF hash + 后端版本 + 参数版本。"""
    raw = f"{pdf_hash}|{backend_version}|{_PARAM_VERSION}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class PyMuPDFLayoutBackend:
    """PyMuPDF4LLM Layout 后端。

    使用 pymupdf4llm.to_markdown(page_chunks=True) 提取语义区域。
    每页的 page_boxes 包含 {class, bbox, index, pos} 字段。
    """

    @property
    def name(self) -> str:
        return "pymupdf4llm"

    @property
    def version(self) -> str:
        try:
            import pymupdf4llm

            return getattr(pymupdf4llm, "__version__", "unknown")
        except ImportError:
            return "unavailable"

    def is_available(self) -> bool:
        try:
            import pymupdf4llm  # noqa: F401

            return True
        except ImportError:
            return False

    def extract(
        self, pdf_path: str, pdf_hash: str = "", pages: Optional[List[int]] = None
    ) -> LayoutResult:
        """提取 PDF 的 Layout 语义区域。

        Args:
            pdf_path: PDF 文件路径
            pdf_hash: PDF 内容哈希（传入空字符串时自动计算）
            pages: 指定页码列表（1-based），None 表示全部页

        Returns:
            LayoutResult
        """
        if not pdf_hash:
            pdf_hash = _compute_pdf_hash(pdf_path)

        backend_ver = self.version
        cache_key = _cache_key(pdf_hash, backend_ver)
        cache_file = _cache_dir() / f"{cache_key}.json"

        # 尝试命中 L0 缓存
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                result = self._from_cache(cached, pdf_path, pdf_hash)
                logger.debug(
                    "Layout cache hit: %s (key=%s)", pdf_path, cache_key[:12]
                )
                # 缓存命中后同样需要按需过滤页码
                if pages is not None:
                    page_set = set(pages)
                    result.pages = {p: pr for p, pr in result.pages.items() if p in page_set}
                return result
            except Exception as e:
                logger.warning("Layout cache read failed, re-extracting: %s", e)

        # 实际调用 pymupdf4llm
        t0 = time.time()
        import pymupdf4llm

        chunks = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=True)
        elapsed = time.time() - t0

        result = self._parse_chunks(
            chunks, pdf_path, pdf_hash, backend_ver, elapsed, cached=False
        )

        # 写入 L0 缓存
        try:
            self._write_cache(result, cache_file)
        except Exception as e:
            logger.warning("Layout cache write failed: %s", e)

        # 按需过滤页码
        if pages is not None:
            page_set = set(pages)
            result.pages = {p: pr for p, pr in result.pages.items() if p in page_set}

        return result

    def _parse_chunks(
        self,
        chunks: List[Dict[str, Any]],
        pdf_path: str,
        pdf_hash: str,
        backend_ver: str,
        elapsed: float,
        cached: bool = False,
    ) -> LayoutResult:
        """解析 pymupdf4llm 的 page_chunks 输出为 LayoutResult。"""
        pages: Dict[int, PageRegion] = {}

        for chunk in chunks:
            meta = chunk.get("metadata") or {}
            page_no = int(meta.get("page_number") or 0)
            if page_no <= 0:
                continue

            boxes = chunk.get("page_boxes") or []
            regions: List[RegionBBox] = []

            for b in boxes:
                cls = str(b.get("class", ""))
                bbox = b.get("bbox")
                if not bbox or len(bbox) != 4:
                    continue
                kind = classify_region(cls)
                # 跳过非语义区域（text/other 不用于候选生成，但保留 figure/table/caption）
                regions.append(
                    RegionBBox(
                        x0=float(bbox[0]),
                        y0=float(bbox[1]),
                        x1=float(bbox[2]),
                        y1=float(bbox[3]),
                        kind=kind,
                        source="pymupdf4llm",
                        raw_class=cls,
                        confidence=1.0,
                    )
                )

            pages[page_no] = PageRegion.from_regions(page_no, regions)

        total_regions = sum(len(pr.regions) for pr in pages.values())
        logger.debug(
            "Layout extract: %s, %d pages, %d regions, %.3fs",
            pdf_path,
            len(pages),
            total_regions,
            elapsed,
        )

        return LayoutResult(
            pdf_path=pdf_path,
            pdf_hash=pdf_hash,
            backend=self.name,
            backend_version=backend_ver,
            pages=pages,
            elapsed_sec=round(elapsed, 3),
            cached=cached,
        )

    def _from_cache(
        self, cached: Dict[str, Any], pdf_path: str, pdf_hash: str
    ) -> LayoutResult:
        """从缓存 JSON 恢复 LayoutResult。"""
        pages: Dict[int, PageRegion] = {}
        for page_no_str, pr_data in cached.get("pages", {}).items():
            page_no = int(page_no_str)
            regions = [
                RegionBBox(
                    x0=r["x0"],
                    y0=r["y0"],
                    x1=r["x1"],
                    y1=r["y1"],
                    kind=r.get("kind", "other"),
                    source=r.get("source", "pymupdf4llm"),
                    raw_class=r.get("raw_class", ""),
                    confidence=r.get("confidence", 1.0),
                )
                for r in pr_data.get("regions", [])
            ]
            pages[page_no] = PageRegion.from_regions(page_no, regions)

        return LayoutResult(
            pdf_path=pdf_path,
            pdf_hash=pdf_hash,
            backend=cached.get("backend", "pymupdf4llm"),
            backend_version=cached.get("backend_version", "unknown"),
            pages=pages,
            elapsed_sec=cached.get("elapsed_sec", 0.0),
            cached=True,
        )

    def _write_cache(self, result: LayoutResult, cache_file: Path) -> None:
        """将 LayoutResult 写入 L0 缓存。"""
        data = {
            "backend": result.backend,
            "backend_version": result.backend_version,
            "pdf_hash": result.pdf_hash,
            "elapsed_sec": result.elapsed_sec,
            "pages": {
                str(p): {
                    "regions": [
                        {
                            "x0": r.x0,
                            "y0": r.y0,
                            "x1": r.x1,
                            "y1": r.y1,
                            "kind": r.kind,
                            "source": r.source,
                            "raw_class": r.raw_class,
                            "confidence": r.confidence,
                        }
                        for r in pr.regions
                    ]
                }
                for p, pr in result.pages.items()
            },
        }
        cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
