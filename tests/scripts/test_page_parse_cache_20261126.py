# -*- coding: utf-8 -*-
"""按页解析缓存回归（2026-11-26，WP-2.3 可选项）。

对应 lib/pdf_backend.py 的 _ParseCache：同一页的 get_text("dict")/get_text("text")
与 get_drawings() 在进程内按「文件 + 页 + 调用」缓存，跨同一文件的多次打开共享。

守住的性质：
- 命中缓存不再触发底层解析，返回内容与首次解析一致；
- 页面内容、旋转或文件本身变了，不会读到旧结果；
- 内存文档不缓存；预算为 0 等于关闭；超预算按最近最少使用淘汰；
- 变异检测开关能抓到调用方原地修改缓存；
- 正式转换链路在变异检测下不报错，且题注检测对裸 PyMuPDF 页保持兼容。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import fitz
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "skills" / "pdf-markdown-summary" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import lib.pdf_backend as pb  # noqa: E402 - local script path is set above
from lib import caption_detection  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_cache():
    """每个用例独享一个缓存实例，结束后还原，不污染进程内的全局缓存。"""
    original = pb._parse_cache
    pb._parse_cache = pb._ParseCache(64 * 1024 * 1024)
    try:
        yield pb._parse_cache
    finally:
        pb._parse_cache = original


def _make_pdf(path: Path, pages: int = 2) -> Path:
    with fitz.open() as doc:
        for page_index in range(pages):
            page = doc.new_page(width=400, height=300)
            page.insert_text((40, 60), f"Page {page_index + 1} body text.", fontsize=11)
            page.draw_rect(fitz.Rect(60, 100, 200, 180), color=(0, 0, 0), width=1.0)
        doc.save(path)
    return path


def _count_underlying_parses(monkeypatch) -> dict[str, int]:
    """在类上把底层解析方法换成计数桩（每次取页都是新的底层对象，桩不能装在实例上）。"""
    counts = {"dict": 0, "text": 0, "drawings": 0}
    original_get_text = fitz.Page.get_text
    original_get_drawings = fitz.Page.get_drawings

    def get_text(self, option="text", *args, **kwargs):
        if option in ("dict", "text") and not args and not kwargs:
            counts[option] += 1
        return original_get_text(self, option, *args, **kwargs)

    def get_drawings(self, *args, **kwargs):
        counts["drawings"] += 1
        return original_get_drawings(self, *args, **kwargs)

    monkeypatch.setattr(fitz.Page, "get_text", get_text)
    monkeypatch.setattr(fitz.Page, "get_drawings", get_drawings)
    return counts


def test_plain_text_and_drawings_are_shared_across_opens(tmp_path: Path, monkeypatch) -> None:
    pdf = _make_pdf(tmp_path / "shared.pdf")

    with pb.open_pdf(str(pdf)) as first:
        for page in first:
            page.get_text("text")
            page.get_drawings()
    counts = _count_underlying_parses(monkeypatch)
    with pb.open_pdf(str(pdf)) as second:
        for page in second:
            page.get_text("text")
            page.get_text("text")
            page.get_drawings()

    # 纯文本与矢量图没有渲染副作用：再次打开后全部命中，不再触发底层解析
    assert counts == {"dict": 0, "text": 0, "drawings": 0}
    assert pb.parse_cache_stats()["hits"] == 6


def test_dict_is_reparsed_once_per_page_per_open(tmp_path: Path, monkeypatch) -> None:
    """get_text("dict") 会改变该页随后的渲染，每个文档实例的每一页首次调用必须真实执行。"""
    pdf = _make_pdf(tmp_path / "dict.pdf")

    with pb.open_pdf(str(pdf)) as first:
        first_result = [page.get_text("dict") for page in first]
    counts = _count_underlying_parses(monkeypatch)
    with pb.open_pdf(str(pdf)) as second:
        page = second[0]
        page.get_text("dict")  # 本实例第 1 页首次调用：真实执行
        assert pb.parse_cache_stats()["hits"] == 0
        assert pb.parse_cache_stats()["misses"] == 3
        page.get_text("dict")  # 本实例内重复调用：命中
        second_result = [page.get_text("dict"), second[1].get_text("dict")]

    assert second_result == first_result
    # 第二个实例只真实解析了第 1 页一次；第 2 页的首次调用同样真实执行
    assert counts == {"dict": 2, "text": 0, "drawings": 0}
    assert pb.parse_cache_stats()["hits"] == 2


def test_failed_first_dict_parse_does_not_skip_next_real_parse(tmp_path: Path, monkeypatch) -> None:
    pdf = _make_pdf(tmp_path / "retry.pdf", pages=1)
    with pb.open_pdf(str(pdf)) as first:
        expected = first[0].get_text("dict")

    original = fitz.Page.get_text
    attempts = 0

    def fail_once(page, mode, *args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary parse failure")
        return original(page, mode, *args, **kwargs)

    monkeypatch.setattr(fitz.Page, "get_text", fail_once)
    with pb.open_pdf(str(pdf)) as second:
        page = second[0]
        with pytest.raises(RuntimeError, match="temporary parse failure"):
            page.get_text("dict")
        assert page.get_text("dict") == expected
    assert attempts == 2
    assert pb.parse_cache_stats()["hits"] == 0


def test_negative_cache_budget_is_zero(monkeypatch) -> None:
    monkeypatch.setenv("PDF_SKILL_PARSE_CACHE_MB", "-5")
    assert pb._env_int("PDF_SKILL_PARSE_CACHE_MB", 1024) == 0


def test_same_file_opens_twice_returns_equal_results(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "twice.pdf")

    def read_all(doc):
        return [(page.get_text("dict"), page.get_text("text"), page.get_drawings()) for page in doc]

    with pb.open_pdf(str(pdf)) as first:
        first_result = read_all(first)
    with pb.open_pdf(str(pdf)) as second:
        second_result = read_all(second)

    assert second_result == first_result
    assert pb.parse_cache_stats()["entries"] == 6


def test_repeated_reads_in_one_open_skip_underlying_parse(tmp_path: Path, monkeypatch) -> None:
    pdf = _make_pdf(tmp_path / "hit.pdf", pages=1)

    with pb.open_pdf(str(pdf)) as first:
        first[0].get_text("dict")
        first[0].get_drawings()
    counts = _count_underlying_parses(monkeypatch)
    with pb.open_pdf(str(pdf)) as doc:
        page = doc[0]
        page.get_text("dict")
        page.get_text("dict")
        page.get_text("text")  # 首轮没读过纯文本：这一页需要解析一次
        page.get_text("text")
        page.get_drawings()
        page.get_drawings()

    # 结构化文本在每个实例只真实解析首次那一次；纯文本解析一次后命中；矢量图直接命中
    assert counts == {"dict": 1, "text": 1, "drawings": 0}


def test_uncached_text_modes_are_passed_through(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "modes.pdf")

    with pb.open_pdf(str(pdf)) as doc:
        words = doc[0].get_text("words")
        blocks = doc[0].get_text("blocks")
        words_again = doc[0].get_text("words")

    assert words and blocks
    assert [w[4] for w in words] == ["Page", "1", "body", "text."]
    assert words_again is not words  # 每次重新解析，不进缓存
    assert pb.parse_cache_stats()["entries"] == 0


def test_page_modified_through_wrapper_invalidates_cache(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "modified-wrapper.pdf", pages=1)

    with pb.open_pdf(str(pdf)) as doc:
        before = len(doc[0].get_drawings())
        doc[0].draw_rect(fitz.Rect(230, 40, 300, 90))
        after = len(doc[0].get_drawings())

    assert before == 1
    assert pb.parse_cache_stats()["entries"] > 0
    # 画矩形时这份文件的缓存被作废；随后的读取重新解析并只保留新状态
    assert after == 2
    assert pb.parse_cache_stats()["entries"] == 1


def test_page_modified_through_raw_object_is_not_served_stale(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "modified-raw.pdf", pages=1)

    with pb.open_pdf(str(pdf)) as doc:
        page = doc[0]
        assert "added later" not in page.get_text("text")
        page.raw.insert_text((40, 250), "added later")
        assert "added later" in page.get_text("text")
        # 同一页同一调用只保留最新状态的条目
        page.get_text("text")
        assert pb.parse_cache_stats()["entries"] == 1


def test_rewritten_file_is_not_served_stale(tmp_path: Path) -> None:
    pdf = tmp_path / "rewritten.pdf"
    _make_pdf(pdf, pages=1)

    with pb.open_pdf(str(pdf)) as doc:
        assert "REPLACEMENT" not in doc[0].get_text("text")
    stamp = pdf.stat().st_mtime_ns
    with fitz.open() as replacement:
        replacement.new_page(width=400, height=300).insert_text((40, 60), "REPLACEMENT content.", fontsize=11)
        replacement.save(pdf)
    # 文件系统的时间戳粒度不足时手动改写修改时间，保证文件身份变化
    os.utime(pdf, ns=(stamp + 1_000_000_000, stamp + 1_000_000_000))

    with pb.open_pdf(str(pdf)) as doc:
        text = doc[0].get_text("text")

    assert "REPLACEMENT" in text
    assert "Page 1" not in text


def test_in_memory_document_is_never_cached() -> None:
    with fitz.open() as raw:
        raw.new_page(width=300, height=200).insert_text((20, 40), "memory only", fontsize=10)
        doc = pb.PDFDocument(raw=raw, path="<memory>")
        page = doc[0]
        page.get_text("dict")
        page.get_drawings()
        raw[0].insert_text((20, 80), "changed")

        assert "changed" in page.get_text("text")

    assert pb.parse_cache_stats()["entries"] == 0


def test_zero_budget_disables_caching(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "no-budget.pdf", pages=1)
    pb._parse_cache = pb._ParseCache(0)

    with pb.open_pdf(str(pdf)) as doc:
        first = doc[0].get_text("dict")
        second = doc[0].get_text("dict")

    assert first is not second
    assert pb.parse_cache_stats() == {"entries": 0, "bytes": 0, "budget_bytes": 0, "hits": 0, "misses": 2}


def test_budget_evicts_least_recently_used_entries(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "budget.pdf", pages=3)
    with pb.open_pdf(str(pdf)) as doc:
        doc[0].get_text("dict")
        size = pb.parse_cache_stats()["bytes"]
        # 预算只够放大约两条
        pb._parse_cache = pb._ParseCache(size * 2 + 1024)
        doc[0].get_text("dict")
        doc[1].get_text("dict")
        doc[0].get_text("dict")  # 第 0 页重新成为最近使用
        doc[2].get_text("dict")  # 放入第 2 页时应淘汰最久未用的第 1 页
        assert pb.parse_cache_stats()["misses"] == 3  # 第 0、1、2 页各一次
        assert pb.parse_cache_stats()["hits"] == 1   # 第 0 页重新成为最近使用的那次读取
        doc[1].get_text("dict")  # 第 1 页已被淘汰：未命中，重新放入时挤掉最久未用的第 0 页
        doc[0].get_text("dict")  # 第 0 页因此未命中
        doc[0].get_text("dict")  # 刚放回来：命中
        stats = pb.parse_cache_stats()

        assert stats["bytes"] <= (size * 2 + 1024)
        assert stats["entries"] == 2
        assert stats["misses"] == 5
        assert stats["hits"] == 2


def test_single_entry_over_budget_is_not_cached(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "oversize.pdf", pages=1)
    with pb.open_pdf(str(pdf)) as doc:
        doc[0].get_text("dict")
        real_size = pb.parse_cache_stats()["bytes"]
        pb._parse_cache = pb._ParseCache(max(1, real_size - 1))
        doc[0].get_text("dict")
        again = doc[0].get_text("dict")

        assert again
        assert pb.parse_cache_stats()["entries"] == 0


def test_mutation_check_detects_in_place_edits(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "mutation.pdf", pages=1)
    pb._parse_cache = pb._ParseCache(16 * 1024 * 1024, mutation_check=True)

    with pb.open_pdf(str(pdf)) as doc:
        page = doc[0]
        page.get_text("dict")
        page.get_text("dict")  # 未改动：正常命中
        page.get_drawings()[0]["rect"].x0 = 999  # 调用方原地改了缓存里的对象

        with pytest.raises(RuntimeError, match="按页解析缓存被调用方原地修改"):
            page.get_drawings()

    with pytest.raises(RuntimeError, match="按页解析缓存被调用方原地修改"):
        # 原地排序或改字典同样会被发现
        with pb.open_pdf(str(pdf)) as doc:
            cached = doc[0].get_text("dict")
            cached["blocks"][0]["lines"][0]["spans"][0]["text"] = "tampered"
            doc[0].get_text("dict")


def test_clear_parse_cache_resets_entries_and_counters(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "clear.pdf", pages=1)

    with pb.open_pdf(str(pdf)) as doc:
        doc[0].get_text("dict")
        doc[0].get_text("dict")
        pb.clear_parse_cache()
        assert pb.parse_cache_stats() == {"entries": 0, "bytes": 0, "budget_bytes": pb._parse_cache._byte_budget, "hits": 0, "misses": 0}


def test_caption_helpers_accept_bare_pymupdf_pages(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "bare.pdf", pages=1)

    with fitz.open(str(pdf)) as raw:
        bare_page = raw[0]
        images = caption_detection.get_page_images(bare_page)
        drawings = caption_detection.get_page_drawings(bare_page)
        forms = caption_detection.collect_caption_word_forms(raw)
        index = caption_detection.build_caption_index(raw)
        with pb.open_pdf(str(pdf)) as wrapped:
            through_wrapper = caption_detection.build_caption_index(wrapped)

    assert images == []
    assert len(drawings) == 1
    assert "page" in forms
    def summary(index):
        return {key: [(c.page, c.text) for c in cands] for key, cands in sorted(index.candidates.items())}

    assert summary(index) == summary(through_wrapper) == {}
    assert pb.parse_cache_stats()["misses"] > 0


def test_conversion_runs_under_mutation_check(tmp_path: Path) -> None:
    """正式转换链路（图开、带题注对账）在变异检测下不报错，且缓存确实被复用。"""
    from core.pdf_to_markdown import main

    pdf = tmp_path / "one-figure.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=800)
        page.insert_text((60, 100), "A short paper with one figure and a caption below it.", fontsize=10)
        page.draw_rect(fitz.Rect(150, 180, 450, 380), color=(0, 0, 0), width=1.5)
        page.insert_text((60, 420), "Figure 1: A framed box used as the only figure.", fontsize=10)
        doc.save(pdf)
    pb._parse_cache = pb._ParseCache(64 * 1024 * 1024, mutation_check=True)

    out_md = tmp_path / "result" / "paper.md"
    assert main(["--pdf", str(pdf), "--out", str(out_md), "--tables", "off"]) == 0

    stats = pb.parse_cache_stats()
    assert stats["hits"] > stats["misses"] > 0
    assert "Figure 1: A framed box" in out_md.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 渲染一致性：缓存不得改变页面渲染结果
# ---------------------------------------------------------------------------

_BENCHMARK = PROJECT_ROOT / "tests" / "basic-benchmark"


def _render_fingerprint_via_cache_mode(pdf_path: Path, page_index: int, clip, dpi: int, *, cache_mb: int) -> str:
    """按提取链路的顺序（结构化文本 → 矢量图 → 渲染）走 PDFPage，返回渲染像素指纹。"""
    import hashlib

    pb._parse_cache = pb._ParseCache(cache_mb * 1024 * 1024)
    with pb.open_pdf(str(pdf_path)) as doc:
        page = doc[page_index]
        page.get_text("dict")
        page.get_text("text")
        page.get_drawings()
        pix = page.get_pixmap(dpi=dpi, clip=clip)
        # 第二个实例重复同样的读取：缓存开启时应全部命中
        with pb.open_pdf(str(pdf_path)) as again:
            again[page_index].get_text("dict")
            again[page_index].get_drawings()
            second = again[page_index].get_pixmap(dpi=dpi, clip=clip)
    assert hashlib.sha256(second.samples).digest() == hashlib.sha256(pix.samples).digest()
    return hashlib.sha256(pix.samples).hexdigest()


@pytest.mark.skipif(not (_BENCHMARK / "gemini_v2_5_report.pdf").is_file(), reason="需要 Basic Benchmark 的 Gemini 报告")
def test_cache_does_not_change_page_rendering(tmp_path: Path) -> None:
    """对同一页做过 get_text("dict") 之后，MuPDF 的渲染像素会有细微变化（字体加载的副作用）。

    提取链路里每张图都在结构化文本提取之后渲染，图表基准也是这个状态的产物。
    缓存开启时的渲染结果必须与关闭时逐像素相同，否则 Golden 基准会漂移。
    Gemini 报告第 3 页的 Figure 1 是已知会触发该副作用的真实样本。
    """
    pdf = _BENCHMARK / "gemini_v2_5_report.pdf"
    clip = fitz.Rect(57.43399688720703, 77.78414245605468, 537.9139968872071, 372.5212707519531)

    without_cache = _render_fingerprint_via_cache_mode(pdf, 2, clip, 300, cache_mb=0)
    with_cache = _render_fingerprint_via_cache_mode(pdf, 2, clip, 300, cache_mb=64)

    assert with_cache == without_cache
