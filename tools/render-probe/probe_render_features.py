#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP-1.1 只读探测：8 份 Basic Benchmark 的渲染特征与分阶段耗时。

目的：为架构收敛 WBS 的 WP-2 / WP-3 阈值提供实证依据。本脚本只读取
tests/basic-benchmark/ 下的 PDF，调用正式 Skill 的函数取数，不修改任何
正式代码；运行前后核对 8 份 PDF 的 SHA-256 与目录清单，发生变化即判失败。

探测项：
1. 书签：doc.get_toc() 覆盖率、层级深度、与正文段落的命中率。
2. 粗体：PDF 粗体标志位（flags & 16）与字体名启发式的差异样本，以及两种口径下
   标题判定、版式单元分类的结果差异。
3. 字号：算术平均（现行 typical_font_size）与按字符数加权众数的偏移，以及改用
   众数后标题层级、版式单元分类的变化数。
4. 通栏：双栏文档中通栏块的比例、类型、纵向分布、阈值敏感性与多带页。
5. 耗时：一次 pdf_to_markdown 运行的分阶段耗时与底层 get_text 调用次数
   （每个 PDF 在独立子进程里运行，包装正式函数计时，不改源码）。

用法（在仓库根目录运行）：
  python3 tools/render-probe/probe_render_features.py                     # 全部：特征 + 耗时
  python3 tools/render-probe/probe_render_features.py --no-timing         # 只做特征探测
  python3 tools/render-probe/probe_render_features.py --no-features       # 只做耗时，沿用已有特征结果
  python3 tools/render-probe/probe_render_features.py --timing-reps 2 1   # 默认模式、表格截图模式各跑几次
  python3 tools/render-probe/probe_render_features.py --out-dir 某目录     # 产物写到别处

产物（默认写入 experiments/arch-convergence-probe-20261124/，该目录已被 gitignore；
本脚本所在的 tools/ 是受跟踪目录，不往里写运行产物）：
  probe_results.json   全量数据
  probe_brief.md       探测简报（数据表由脚本生成；「解读与建议」小节人工撰写，重跑保留）
  runs/                耗时运行的 run_summary.json（提取产物在读取报告后即删除）

要留档的简报另外拷一份带日期后缀的快照到 design/4-analysis/（2026-11-24 的快照是
架构收敛WP-1.1渲染特征探测简报-20261124.md）。
"""
from __future__ import annotations

import argparse
import functools
import gc
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "skills" / "pdf-markdown-summary" / "scripts"
BENCH_DIR = ROOT / "tests" / "basic-benchmark"
# 运行产物默认写入被忽略的 experiments/；可用 --out-dir 改到别处
DEFAULT_OUT_DIR = ROOT / "experiments" / "arch-convergence-probe-20261124"
OUT_DIR = DEFAULT_OUT_DIR
RESULTS_PATH = OUT_DIR / "probe_results.json"
BRIEF_PATH = OUT_DIR / "probe_brief.md"
RUNS_DIR = OUT_DIR / "runs"
NOTES_HEADING = "## 解读与建议（人工撰写，重跑保留）"

# AGENTS.md 第 8 节列出的 8 份 PDF，简称用于简报
LABELS = {
    "1706.03762v7-attention_is_all_you_need": "Attention",
    "2509.17765v1-Qwen3-Omni Technical Report": "Qwen3-Omni",
    "2607.24653v2-Kimi-K3": "Kimi-K3",
    "FunAudio-ASR": "FunAudio-ASR",
    "gemini_v2_5_report": "Gemini-2.5",
    "gpt-5-system-card": "GPT-5",
    "KearnsNevmyvakaHFTRiskBooks": "Kearns",
    "DeepSeek_V41_Tech_Report": "DeepSeek-V4.1",
}

# 现行行内样式启发式 _span_is_bold = 粗体标志位 或 字样命中（bold/black/heavy/medi，不含 CMBX）。
# 统计两种口径的差异时，字体名一栏必须只用字样判断，否则带标志位的 span 会被算成「两者皆有」。
NAME_BOLD_TOKENS = ("bold", "black", "heavy", "medi")
# 多列几种字样，用来观察各字样下标志位的置位率
TOKEN_GROUPS = ("cmbx", "cmbsy", "cmmib", "bold", "demi", "black", "heavy", "medi")

# looks_like_structural_heading 对非编号标题的硬编码字号门槛
HARDCODED_HEADING_MIN_PT = 11.5
RATIO_BUCKETS = ((0.0, 1.0), (1.0, 1.05), (1.05, 1.12), (1.12, 1.25), (1.25, 1.45), (1.45, 99.0))

# 一次运行里的文本解析入口（包含耗时之和 = 解析入口总耗时）
PARSE_ENTRIES = (
    "prevalidate[text_stage]",
    "pass_gather[text_stage]",
    "prevalidate[asset_stage]",
    "pass_text[asset_stage]",
    "pass_gather[asset_stage]",
    "layout_probe",
    "pass_layout",
)
# 版式模型内部的子阶段
LAYOUT_SUBPHASES = (
    "layout_metrics_first5",
    "scan_dict_all_pages",
    "layout_classify_text_types",
    "layout_detect_columns",
    "layout_build_text_blocks",
    "layout_detect_vacant_regions",
)


# ---------------------------------------------------------------------------
# 只读护栏
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def bench_state() -> Dict[str, Any]:
    entries = sorted(BENCH_DIR.iterdir())
    return {
        "entries": [p.name for p in entries],
        "sha256": {p.name: _sha256(p) for p in entries if p.is_file()},
    }


def ordered_pdfs() -> List[Path]:
    found = {p.stem: p for p in BENCH_DIR.glob("*.pdf")}
    missing = [stem for stem in LABELS if stem not in found]
    if missing or len(found) != len(LABELS):
        raise SystemExit(f"benchmark 目录与 8 份核心集不一致: 缺 {missing}，实际 {sorted(found)}")
    return [found[stem] for stem in LABELS]


def environment() -> Dict[str, Any]:
    import fitz

    env = {
        "python": platform.python_version(),
        "platform": sys.platform,
        "machine": platform.machine(),
        "pymupdf": fitz.VersionBind,
        "mupdf": fitz.VersionFitz,
    }
    try:
        import numpy

        env["numpy"] = numpy.__version__
    except ImportError:
        env["numpy"] = None
    return env


# ---------------------------------------------------------------------------
# 特征探测：通用小工具
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text or "")).strip().casefold()


def _iter_spans(blocks: Iterable[Dict[str, Any]]):
    for block in blocks:
        for line in block.get("lines") or []:
            for span in line.get("spans") or []:
                if span.get("text"):
                    yield span


def _first_span(block: Dict[str, Any]) -> Dict[str, Any]:
    lines = block.get("lines") or []
    spans = lines[0].get("spans") if lines else None
    return spans[0] if spans else {}


def _para_type(block_text: str, is_heading: bool) -> str:
    """与 gather_structured_text 的局部分类同口径（标题已判定时直接采用）。"""
    if is_heading:
        return "heading"
    low = block_text.lower()
    if low.startswith(("figure", "fig.", "table", "图", "表")):
        return "caption"
    if block_text.startswith(("•", "-", "*", "1.", "2.", "(1)", "(a)")):
        return "list"
    return "body"


# ---------------------------------------------------------------------------
# 1. 书签
# ---------------------------------------------------------------------------

def analyze_bookmarks(toc: List[List[Any]], paragraphs: List[Any]) -> Dict[str, Any]:
    valid = []
    for entry in toc:
        level, title, page = int(entry[0]), str(entry[1]).strip(), int(entry[2])
        if title and page >= 1:
            valid.append((level, title, page))

    by_page: Dict[int, List[str]] = defaultdict(list)
    for para in paragraphs:
        by_page[para.page].append(_norm(para.text))
    all_norm = Counter(_norm(p.text) for p in paragraphs)

    exact = exact_unique = prefix = no_trailing = any_page = 0
    hit_samples: List[Dict[str, Any]] = []
    for _level, title, page in valid:
        key = _norm(title)
        if not key:
            continue
        same = by_page.get(page, [])
        matches = [p for p in paragraphs if p.page == page and _norm(p.text) == key]
        n_same = len(matches)
        exact += n_same > 0
        exact_unique += n_same == 1
        if n_same == 1 and len(hit_samples) < 12:
            hit_samples.append({"level": _level, "page": page, "bookmark": title[:50],
                                "paragraph": matches[0].text.strip()[:50], "is_heading": bool(matches[0].is_heading)})
        prefix += len(key) >= 4 and any(t.startswith(key) for t in same)
        stripped = _norm(re.sub(r"\s+\d{1,4}$", "", title))
        no_trailing += bool(stripped) and any(t == stripped for t in same)
        any_page += all_norm.get(key, 0) > 0

    return {
        "total_entries": len(toc),
        "valid": len(valid),
        "level_distribution": {str(k): v for k, v in sorted(Counter(l for l, _t, _p in valid).items())},
        "max_level": max((l for l, _t, _p in valid), default=0),
        "hit_same_page_exact_unique": exact_unique,
        "hit_same_page_exact": exact,
        "hit_same_page_after_dropping_trailing_page_no": no_trailing,
        "hit_same_page_prefix": prefix,
        "hit_any_page_exact": any_page,
        "hit_samples": hit_samples,
        "samples": [{"level": l, "page": p, "title": t[:70]} for l, t, p in valid[:6]],
    }


# ---------------------------------------------------------------------------
# 2. 粗体
# ---------------------------------------------------------------------------

def _name_is_bold(font: str) -> bool:
    """只按字体名字样判断粗体（字样表与 _span_is_bold 相同，不看标志位）。"""
    low = font.lower()
    return any(token in low for token in NAME_BOLD_TOKENS)


def analyze_bold(blocks: List[Dict[str, Any]], kept_keys: set, te) -> Dict[str, Any]:
    cells = ("flag_and_name", "flag_only", "name_only", "neither")
    counts = {k: {"spans": 0, "chars": 0} for k in cells}
    cell_fonts: Dict[str, Counter] = {k: Counter() for k in cells}
    cell_samples: Dict[str, Dict[str, str]] = {k: {} for k in cells}
    fonts: Dict[str, Dict[str, int]] = {}
    token_stats = {t: {"spans": 0, "flag_spans": 0} for t in TOKEN_GROUPS}

    for sp in _iter_spans(blocks):
        text = str(sp.get("text", ""))
        font = str(sp.get("font", "") or "")
        low = font.lower()
        flag_bold = te._span_has_bold_flag(sp)
        name_bold = _name_is_bold(font)
        key = ("flag_and_name" if flag_bold else "name_only") if name_bold else ("flag_only" if flag_bold else "neither")
        counts[key]["spans"] += 1
        counts[key]["chars"] += len(text)
        cell_fonts[key][font] += 1
        cell_samples[key].setdefault(font, text.strip()[:40])
        f = fonts.setdefault(font, {"spans": 0, "chars": 0, "flag_spans": 0})
        f["spans"] += 1
        f["chars"] += len(text)
        f["flag_spans"] += int(flag_bold)
        for token in TOKEN_GROUPS:
            if token in low:
                token_stats[token]["spans"] += 1
                token_stats[token]["flag_spans"] += int(flag_bold)

    def top_fonts(cell: str, limit: int = 8) -> List[Dict[str, Any]]:
        return [{"font": font, "spans": n, "sample": cell_samples[cell][font]}
                for font, n in cell_fonts[cell].most_common(limit)]

    latex = [
        {"font": font, "spans": f["spans"], "chars": f["chars"],
         "flag_rate": round(f["flag_spans"] / f["spans"], 4)}
        for font, f in sorted(fonts.items(), key=lambda kv: -kv[1]["chars"])
        if font.upper().startswith(("CMB", "CMMIB"))
    ]
    for token, stat in token_stats.items():
        stat["flag_rate"] = round(stat["flag_spans"] / stat["spans"], 4) if stat["spans"] else None

    # 块级：首 span 两种口径是否一致，标题判定是否因此翻转（块范围与 gather 相同）
    numbered_res = (
        te._SECTION_HEADING_RE, te._CJK_SECTION_HEADING_RE, te._ROMAN_ALPHA_HEADING_RE,
    )
    first_disagree = heading_flag = heading_name = 0
    only_flag: List[Dict[str, Any]] = []
    only_name: List[Dict[str, Any]] = []
    numbered_bold_blocks = 0
    numbered_bold_name_only = 0
    for block in blocks:
        if (block["page"], tuple(block["bbox"]), block["text"]) not in kept_keys:
            continue
        sp = _first_span(block)
        if not sp:
            continue
        size = float(sp.get("size", 10) or 10)
        flag_bold = te._span_has_bold_flag(sp)
        name_bold = flag_bold or _name_is_bold(str(sp.get("font", "") or ""))  # 即 _span_is_bold 的口径
        first_disagree += int(flag_bold != name_bold)
        text = block["text"].strip()
        if any(rx.match(text) for rx in numbered_res):
            numbered_bold_blocks += int(flag_bold)
            numbered_bold_name_only += int(name_bold and not flag_bold)
        hf = te.looks_like_structural_heading(block["text"], is_bold=flag_bold, font_size=size)
        hn = te.looks_like_structural_heading(block["text"], is_bold=name_bold, font_size=size)
        heading_flag += int(hf)
        heading_name += int(hn)
        row = {"page": block["page"], "size": round(size, 2), "font": str(sp.get("font", "")), "text": text[:60]}
        if hf and not hn and len(only_flag) < 8:
            only_flag.append(row)
        if hn and not hf and len(only_name) < 8:
            only_name.append(row)

    return {
        "cells": counts,
        "flag_only_fonts": top_fonts("flag_only"),
        "name_only_fonts": top_fonts("name_only"),
        "latex_bold_fonts": latex,
        "token_flag_rates": token_stats,
        "block_first_span_disagree": first_disagree,
        "numbered_bold_blocks_by_flag": numbered_bold_blocks,
        "numbered_blocks_bold_only_by_font_name": numbered_bold_name_only,
        "headings_by_flag": heading_flag,
        "headings_by_font_name": heading_name,
        "heading_only_by_flag": only_flag,
        "heading_only_by_font_name": only_name,
    }


def _unit_types(layout) -> Counter:
    return Counter(u.text_type for units in layout.text_units.values() for u in units)


def _title_units(types: Counter) -> int:
    return sum(n for t, n in types.items() if t.startswith("title"))


def _type_diff(before, after) -> Tuple[int, Counter, Counter]:
    transitions: Counter = Counter()
    fonts: Counter = Counter()
    changed = 0
    for pno, units in before.text_units.items():
        for idx, unit in enumerate(units):
            other = after.text_units[pno][idx]
            if unit.text_type != other.text_type:
                changed += 1
                transitions[f"{unit.text_type} -> {other.text_type}"] += 1
                fonts[unit.font_name] += 1
    return changed, transitions, fonts


def analyze_layout_sensitivity(pdf_path: Path, te, baseline) -> Dict[str, Any]:
    """版式模型若改口径，单元分类会变多少。两项都是对照实验，跑完即恢复原函数。"""
    base_types = _unit_types(baseline)
    out: Dict[str, Any] = {"baseline_type_counts": dict(sorted(base_types.items())),
                           "baseline_title_units": _title_units(base_types)}

    # (a) 字重改用字体名启发式
    saved_bold = te._span_has_bold_flag
    te._span_has_bold_flag = te._span_is_bold
    try:
        renamed = te.extract_text_with_format(str(pdf_path))
    finally:
        te._span_has_bold_flag = saved_bold
    changed, transitions, fonts = _type_diff(baseline, renamed)
    out["if_bold_by_font_name"] = {
        "changed_units": changed,
        "title_units_after": _title_units(_unit_types(renamed)),
        "transitions": dict(transitions.most_common(8)),
        "fonts": dict(fonts.most_common(8)),
    }

    # (b) 典型字号改用字符加权众数（同范围 6-20pt、同前 5 页）
    saved_metrics = te._estimate_typical_metrics

    @functools.wraps(saved_metrics)
    def metrics_with_mode(doc, debug: bool = False):
        mean, line_height, gap = saved_metrics(doc, debug)
        weights: Counter = Counter()
        for pno in range(min(5, len(doc))):
            for blk in doc[pno].get_text("dict").get("blocks", []):
                if blk.get("type") != 0:
                    continue
                for ln in blk.get("lines", []):
                    for sp in ln.get("spans", []):
                        size = float(sp.get("size", 0) or 0)
                        if 6 <= size <= 20:
                            weights[round(size, 2)] += len(sp.get("text", ""))
        return (max(weights, key=weights.get) if weights else mean), line_height, gap

    te._estimate_typical_metrics = metrics_with_mode
    try:
        remoded = te.extract_text_with_format(str(pdf_path))
    finally:
        te._estimate_typical_metrics = saved_metrics
    changed, transitions, fonts = _type_diff(baseline, remoded)
    out["if_typical_size_is_char_mode"] = {
        "typical_font_size_used": round(float(remoded.typical_font_size), 4),
        "changed_units": changed,
        "title_units_after": _title_units(_unit_types(remoded)),
        "transitions": dict(transitions.most_common(8)),
        "fonts": dict(fonts.most_common(8)),
    }
    return out


# ---------------------------------------------------------------------------
# 3. 字号
# ---------------------------------------------------------------------------

def _mode(counter: Counter, low: float, high: float) -> Optional[float]:
    picked = [(n, s) for s, n in counter.items() if low <= s <= high]
    return max(picked)[1] if picked else None


# LaTeX 的同一个名义字号（如 10pt）在 PyMuPDF 里会拆成 9.96 与 10.06 两个值，
# 相差约 0.1pt；并簇容差取 0.15pt，把这种拆分合并后再取众数。
MERGE_TOLERANCE_PT = 0.15


def _merged_mode(counter: Counter, low: float, high: float, tol: float = MERGE_TOLERANCE_PT) -> Optional[Dict[str, Any]]:
    """相差不超过 tol 的字号并为一簇，取字符数最多的一簇（返回簇内字符加权中心）。"""
    clusters: List[List[Tuple[float, int]]] = []
    for size in sorted(s for s in counter if low <= s <= high):
        if clusters and size - clusters[-1][-1][0] <= tol:
            clusters[-1].append((size, counter[size]))
        else:
            clusters.append([(size, counter[size])])
    if not clusters:
        return None
    best = max(clusters, key=lambda c: sum(n for _s, n in c))
    total = sum(n for _s, n in best)
    return {
        "center": round(sum(s * n for s, n in best) / total, 4),
        "lo": best[0][0],
        "hi": best[-1][0],
        "sizes": [s for s, _n in best],
        "char_pct": round(100 * total / sum(counter.values()), 2),
    }


def analyze_font_sizes(blocks: List[Dict[str, Any]], kept_keys: set, gathered, te, layout) -> Dict[str, Any]:
    by_chars: Counter = Counter()
    by_spans: Counter = Counter()
    for sp in _iter_spans(blocks):
        size = round(float(sp.get("size", 0) or 0), 2)
        by_chars[size] += len(sp.get("text", ""))
        by_spans[size] += 1

    gather_mean = float(gathered.typical_font_size)
    layout_mean = float(layout.typical_font_size)
    mode_8_14 = _mode(by_chars, 8.0, 14.0)
    mode_6_20 = _mode(by_chars, 6.0, 20.0)
    merged_8_14 = _merged_mode(by_chars, 8.0, 14.0)
    merged_6_20 = _merged_mode(by_chars, 6.0, 20.0)
    body = (merged_6_20 or {}).get("center") or mode_6_20 or gather_mean
    numbered_res = (
        te._NUMBERED_HEADING_LEVEL_RE, te._CJK_CHAPTER_LEVEL_RE,
        te._ROMAN_HEADING_LEVEL_RE, te._ALPHA_HEADING_LEVEL_RE,
    )

    def is_numbered(text: str) -> bool:
        return any(rx.match(text) for rx in numbered_res) or bool(
            re.match(r"^\d+(?:\.\d+)*\s+(?=[\u4e00-\u9fff])", text)
        )

    typicals = {
        "gather_mean": gather_mean,
        "char_mode_8_14": mode_8_14 or gather_mean,
        "char_mode_merged_8_14": (merged_8_14 or {}).get("center") or gather_mean,
    }
    heading_count = unnumbered = level_flips = 0
    period_numbered = 0
    flip_rows: List[Dict[str, Any]] = []
    for para in gathered.paragraphs:
        if not para.is_heading:
            continue
        heading_count += 1
        text = para.text.strip()
        if is_numbered(text):
            continue
        # 「1. Introduction」「1.1. Model」这类带句点的编号不在编号正则里，层级只看字号比
        if re.match(r"^\d+(?:\.\d+)*\.\s+\S", text):
            period_numbered += 1
        unnumbered += 1
        levels = {name: te.infer_heading_level(text, font_size=para.font_size, typical_font_size=typ)
                  for name, typ in typicals.items()}
        if len(set(levels.values())) > 1:
            level_flips += 1
            if len(flip_rows) < 8:
                flip_rows.append({"page": para.page, "size": round(para.font_size, 2),
                                  "ratio_to_body": round(para.font_size / body, 3),
                                  "levels": levels, "text": text[:50]})

    # 粗体、非编号、短块：11.5pt 硬门槛相对正文字号落在哪些档位
    rows: List[Dict[str, Any]] = []
    for block in blocks:
        if (block["page"], tuple(block["bbox"]), block["text"]) not in kept_keys:
            continue
        sp = _first_span(block)
        if not sp or not te._span_has_bold_flag(sp):
            continue
        stripped = block["text"].strip()
        if not stripped or len(stripped) >= 50 or is_numbered(stripped):
            continue
        size = float(sp.get("size", 10) or 10)
        accepted = te.looks_like_structural_heading(stripped, is_bold=True, font_size=size)
        size_gate_only = (
            not accepted and size < HARDCODED_HEADING_MIN_PT
            and te.looks_like_structural_heading(
                stripped, is_bold=True, font_size=HARDCODED_HEADING_MIN_PT)
        )
        rows.append({"ratio": size / body, "size": size, "page": block["page"],
                     "font": str(sp.get("font", "")), "text": stripped[:50],
                     "accepted": accepted, "size_gate_only": size_gate_only})

    buckets: Dict[str, Dict[str, Any]] = {}
    for low, high in RATIO_BUCKETS:
        in_bucket = [r for r in rows if low <= r["ratio"] < high]
        label = f"{low:.2f}≤r<{high:.2f}" if high < 99 else f"r≥{low:.2f}"
        buckets[label] = {
            "blocks": len(in_bucket),
            "accepted": sum(1 for r in in_bucket if r["accepted"]),
            "size_gate_only": sum(1 for r in in_bucket if r["size_gate_only"]),
            "size_gate_only_samples": [
                {"page": r["page"], "size": round(r["size"], 2), "font": r["font"], "text": r["text"]}
                for r in in_bucket if r["size_gate_only"]][:4],
        }

    return {
        "layout_mean_6_20_first5_pages": round(layout_mean, 4),
        "gather_mean_8_14_all_pages": round(gather_mean, 4),
        "char_mode_8_14_all_pages": mode_8_14,
        "char_mode_6_20_all_pages": mode_6_20,
        "char_mode_merged_8_14": merged_8_14,
        "char_mode_merged_6_20": merged_6_20,
        "span_mode_6_20_all_pages": _mode(by_spans, 6.0, 20.0),
        # 偏移 = 均值 − 同范围字符众数；没有众数时记 None
        "gather_mean_offset_pt": round(gather_mean - mode_8_14, 4) if mode_8_14 else None,
        "gather_mean_offset_pct": round(100 * (gather_mean / mode_8_14 - 1), 2) if mode_8_14 else None,
        "gather_mean_offset_vs_merged_pt": round(gather_mean - merged_8_14["center"], 4) if merged_8_14 else None,
        "gather_mean_offset_vs_merged_pct": round(100 * (gather_mean / merged_8_14["center"] - 1), 2) if merged_8_14 else None,
        "layout_mean_offset_pt": round(layout_mean - mode_6_20, 4) if mode_6_20 else None,
        "layout_mean_offset_pct": round(100 * (layout_mean / mode_6_20 - 1), 2) if mode_6_20 else None,
        "layout_mean_offset_vs_merged_pt": round(layout_mean - merged_6_20["center"], 4) if merged_6_20 else None,
        "layout_mean_offset_vs_merged_pct": round(100 * (layout_mean / merged_6_20["center"] - 1), 2) if merged_6_20 else None,
        "top_sizes_by_char_share": [
            {"size": s, "char_pct": round(100 * n / sum(by_chars.values()), 2), "spans": by_spans[s]}
            for s, n in by_chars.most_common(6)],
        "headings": heading_count,
        "unnumbered_headings": unnumbered,
        "period_numbered_headings_not_depth_mapped": period_numbered,
        "unnumbered_heading_level_flips_if_typical_changes": level_flips,
        "unnumbered_heading_level_flip_samples": flip_rows,
        "bold_non_numbered_short_blocks_by_ratio_to_body": buckets,
    }


# ---------------------------------------------------------------------------
# 4. 通栏
# ---------------------------------------------------------------------------

def _fw_row(block: Dict[str, Any], para, ratio: float) -> Dict[str, Any]:
    return {
        "page": block["page"],
        "bbox": [round(v, 1) for v in block["bbox"]],
        "width_ratio": round(ratio, 4),
        "type": _para_type(block["text"], para.is_heading),
        "text": block["text"].strip()[:60],
    }


def analyze_full_width(blocks: List[Dict[str, Any]], gathered, layout) -> Dict[str, Any]:
    attr = {(p.page, tuple(p.bbox), p.text): p for p in gathered.paragraphs}
    page_width = float(blocks[0]["page_width"]) if blocks else 0.0
    x_centers = [(b["bbox"][0] + b["bbox"][2]) / 2 for b in blocks]
    left = sum(1 for x in x_centers if x < page_width * 0.45)
    right = sum(1 for x in x_centers if x > page_width * 0.55)
    out: Dict[str, Any] = {
        "gather_is_dual_column": bool(gathered.is_dual_column),
        "layout_model_num_columns": int(layout.num_columns),
        "gather_left_center_ratio": round(left / len(x_centers), 4) if x_centers else None,
        "gather_right_center_ratio": round(right / len(x_centers), 4) if x_centers else None,
    }
    if not gathered.is_dual_column:
        return out

    mid = page_width * 0.5
    thresholds = (0.50, 0.52, 0.55, 0.60, 0.65)
    by_page: Dict[int, List[Tuple[Dict[str, Any], Any]]] = defaultdict(list)
    for block in blocks:
        para = attr.get((block["page"], tuple(block["bbox"]), block["text"]))
        if para is not None:
            by_page[para.page].append((block, para))

    type_counts: Counter = Counter()
    deciles: Counter = Counter()
    widths: List[float] = []
    full_per_page: Dict[int, int] = {}
    under_threshold: Counter = Counter()
    borderline_wide: List[Dict[str, Any]] = []
    touching_mid: List[Dict[str, Any]] = []
    mid_page: List[Dict[str, Any]] = []
    multi_band_pages: List[int] = []
    kept = 0

    for page, rows in sorted(by_page.items()):
        rows.sort(key=lambda rp: (rp[0]["bbox"][1], rp[0]["bbox"][0]))
        page_height = float(rows[0][0]["page_height"])
        column_below = sum(1 for _b, p in rows if not p.is_full_width)
        column_above = 0
        full_here = 0
        for block, para in rows:
            kept += 1
            x0, y0, x1, y1 = block["bbox"]
            ratio = max(0.0, x1 - x0) / page_width
            spans_mid = x0 < mid - 8.0 and x1 > mid + 8.0
            for t in thresholds:
                under_threshold[t] += int(spans_mid or ratio >= t)
            if not para.is_full_width:
                column_above += 1
                column_below -= 1
                if ratio >= 0.45 and len(borderline_wide) < 8:
                    borderline_wide.append(_fw_row(block, para, ratio))
                if x0 < mid + 8.0 and x1 > mid - 8.0 and len(touching_mid) < 8:
                    touching_mid.append(_fw_row(block, para, ratio))
                continue
            full_here += 1
            widths.append(ratio)
            ptype = _para_type(block["text"], para.is_heading)
            type_counts[ptype] += 1
            deciles[min(9, int(((y0 + y1) / 2) / page_height * 10))] += 1
            if column_above and column_below:
                mid_page.append(_fw_row(block, para, ratio))
        if full_here:
            full_per_page[page] = full_here
        # 多带页：首尾双栏块之间夹着通栏块，把双栏正文切成上下两带及以上
        indexes = [i for i, (_b, p) in enumerate(rows) if not p.is_full_width]
        if indexes and any(rows[i][1].is_full_width for i in range(indexes[0], indexes[-1] + 1)):
            multi_band_pages.append(page)

    full_total = sum(type_counts.values())
    return {
        **out,
        "kept_blocks": kept,
        "full_width_blocks": full_total,
        "full_width_ratio": round(full_total / kept, 4) if kept else None,
        "full_width_by_type": dict(type_counts),
        "full_width_by_vertical_decile": {str(k): deciles.get(k, 0) for k in range(10)},
        "full_width_width_ratio": {
            "min": round(min(widths), 4) if widths else None,
            "median": round(sorted(widths)[len(widths) // 2], 4) if widths else None,
        },
        "pages_total": len(by_page),
        "pages_with_any_full_width": len(full_per_page),
        "full_width_blocks_per_page_distribution": {
            str(k): v for k, v in sorted(Counter(full_per_page.values()).items())},
        "max_full_width_per_page": max(full_per_page.values(), default=0),
        "full_width_count_under_wide_threshold": {f"{t:.2f}": under_threshold[t] for t in thresholds},
        "mid_page_full_width_blocks": len(mid_page),
        "mid_page_full_width_samples": mid_page[:12],
        "multi_band_pages": multi_band_pages,
        "non_full_width_blocks_with_width_ratio_ge_0_45": len(borderline_wide),
        "non_full_width_near_wide_threshold_samples": borderline_wide,
        "non_full_width_touching_mid_zone_samples": touching_mid,
    }


def _reading_order_report(gathered) -> Dict[str, Any]:
    """通栏分带后的阅读顺序与「页内按 y 再按 x」的顺序差了多少（Markdown 即按前者输出）。"""
    by_page: Dict[int, List[Any]] = defaultdict(list)
    for para in gathered.paragraphs:  # gathered.paragraphs 已是分带后的阅读顺序
        by_page[para.page].append(para)
    displaced_pages: List[int] = []
    displaced_blocks = 0
    column_blocks = 0
    samples: List[Dict[str, Any]] = []
    for page, paras in sorted(by_page.items()):
        y_order = sorted(paras, key=lambda p: (p.bbox[1], p.bbox[0]))
        column_blocks += sum(1 for p in paras if not p.is_full_width)
        if [id(p) for p in y_order] == [id(p) for p in paras]:
            continue
        displaced_pages.append(page)
        differing = [i for i, (a, b) in enumerate(zip(y_order, paras)) if a is not b]
        displaced_blocks += len(differing)

        def row(p: Any) -> str:
            return f"[{'通栏' if p.is_full_width else '左' if p.column == 0 else '右'} x0={p.bbox[0]:.0f} y0={p.bbox[1]:.0f}] {p.text.strip()[:26]!r}"

        if len(samples) < 6:
            first = differing[0]
            window = range(max(0, first - 1), min(len(paras), first + 4))
            samples.append({
                "page": page,
                "differing_positions": len(differing),
                "y_order": [row(y_order[i]) for i in window],
                "reading_order": [row(paras[i]) for i in window],
            })
    return {
        "column_blocks_left_right": column_blocks,
        "pages_total": len(by_page),
        "pages_where_order_differs_from_y_order": len(displaced_pages),
        "displaced_page_list_head": displaced_pages[:30],
        "differing_positions_total": displaced_blocks,
        "samples": samples,
    }


def _block_alignment(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """正文左缘与宽度：用来判断文档主体到底是单栏还是双栏。"""
    if not blocks:
        return {}
    page_width = float(blocks[0]["page_width"])
    x0s = Counter(round(float(b["bbox"][0])) for b in blocks)
    dominant_x0, dominant_n = x0s.most_common(1)[0]
    widths_at = sorted((b["bbox"][2] - b["bbox"][0]) / page_width for b in blocks
                       if round(float(b["bbox"][0])) == dominant_x0)
    return {
        "dominant_x0": dominant_x0,
        "dominant_x0_share": round(dominant_n / len(blocks), 4),
        "top3_x0": x0s.most_common(3),
        "median_width_ratio_at_dominant_x0": round(widths_at[len(widths_at) // 2], 4) if widths_at else None,
    }


def probe_features(pdf_path: Path) -> Dict[str, Any]:
    import fitz

    sys.path.insert(0, str(SCRIPTS_DIR))
    from lib import text_extract as te
    from lib.pdf_backend import open_pdf

    out: Dict[str, Any] = {}
    with fitz.open(str(pdf_path)) as raw:
        out["pages"] = raw.page_count
        out["page_size_pt"] = [round(raw[0].rect.width, 1), round(raw[0].rect.height, 1)]
        toc = raw.get_toc(simple=True)
        meta = raw.metadata or {}
        out["pdf_producer"] = (meta.get("producer") or "")[:70]
        out["pdf_creator"] = (meta.get("creator") or "")[:70]

    gathered = te.gather_structured_text(str(pdf_path))
    with open_pdf(str(pdf_path)) as doc:
        blocks = te.iter_native_text_blocks(doc)
    layout = te.extract_text_with_format(str(pdf_path))

    kept_keys = {(p.page, tuple(p.bbox), p.text) for p in gathered.paragraphs}
    out["blocks"] = len(blocks)
    out["spans"] = sum(1 for _ in _iter_spans(blocks))
    out["paragraphs_after_header_footer_removal"] = len(gathered.paragraphs)
    out["structure_warnings"] = list(gathered.structure_warnings or [])
    out["bookmarks"] = analyze_bookmarks(toc, gathered.paragraphs)
    out["bold"] = analyze_bold(blocks, kept_keys, te)
    out["font_sizes"] = analyze_font_sizes(blocks, kept_keys, gathered, te, layout)
    out["full_width"] = analyze_full_width(blocks, gathered, layout)
    out["block_alignment"] = _block_alignment(blocks)
    # gather 判了双栏、但块左缘集中的那一批块宽度 ≥0.6 页宽：正文实为单栏，双栏判定与版式模型冲突
    body_width = out["block_alignment"].get("median_width_ratio_at_dominant_x0") or 0.0
    out["dual_flag_conflicts_with_body_geometry"] = bool(
        gathered.is_dual_column and body_width >= 0.6)
    if gathered.is_dual_column:
        out["reading_order"] = _reading_order_report(gathered)
    out["layout_sensitivity"] = analyze_layout_sensitivity(pdf_path, te, layout)
    return out


# ---------------------------------------------------------------------------
# 5. 分阶段耗时
# ---------------------------------------------------------------------------

class PhaseRecorder:
    """按调用栈记录各阶段的包含耗时与被内层占用的时间，用于算自用时。"""

    def __init__(self) -> None:
        self.phases: Dict[str, Dict[str, Any]] = {}
        self.stack: List[str] = []

    def enter(self, name: str) -> None:
        entry = self.phases.setdefault(name, {"calls": 0, "inclusive": 0.0, "child": 0.0, "max": 0.0})
        entry["calls"] += 1
        entry["_started"] = perf_counter()
        self.stack.append(name)

    def leave(self) -> None:
        name = self.stack.pop()
        entry = self.phases[name]
        elapsed = perf_counter() - entry.pop("_started")
        entry["inclusive"] += elapsed
        entry["max"] = max(entry["max"], elapsed)
        if self.stack:
            self.phases[self.stack[-1]]["child"] += elapsed

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        return {
            name: {"calls": e["calls"], "inclusive": round(e["inclusive"], 4),
                   "exclusive": round(e["inclusive"] - e["child"], 4), "max": round(e["max"], 4)}
            for name, e in self.phases.items()
        }


def install_timing_wrappers() -> Tuple[PhaseRecorder, Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """在当前进程里包装正式函数；返回阶段记录、底层调用计数与备注字典。"""
    import fitz

    from core import extract_pdf_assets as epa
    from core import pdf_to_markdown as p2m
    from lib import layout_model as lm
    from lib import markdown as md
    from lib import text_extract as te

    recorder = PhaseRecorder()
    lowlevel: Dict[str, Dict[str, Any]] = {}
    notes: Dict[str, Any] = {}

    def timed(owner, attr: str, phase: str, capture=None, split_by_caller: bool = False):
        original = getattr(owner, attr)

        @functools.wraps(original)
        def wrapper(*args, **kwargs):
            # 共享底层被多个入口调用：按调用方分开记名，才知道每次扫描花在谁身上
            name = f"{phase}[in {recorder.stack[-1]}]" if split_by_caller and recorder.stack else phase
            recorder.enter(name)
            try:
                result = original(*args, **kwargs)
                if capture is not None:
                    capture(notes, result)
                return result
            finally:
                recorder.leave()

        setattr(owner, attr, wrapper)

    def counted(attr: str):
        original = getattr(fitz.Page, attr)

        @functools.wraps(original)
        def wrapper(self, *args, **kwargs):
            key = str(args[0] if args else kwargs.get("option", "text")) if attr == "get_text" else attr
            entry = lowlevel.setdefault(key, {"calls": 0, "sec": 0.0, "pages": set()})
            started = perf_counter()
            try:
                return original(self, *args, **kwargs)
            finally:
                entry["sec"] += perf_counter() - started
                entry["calls"] += 1
                entry["pages"].add(self.number)

        setattr(fitz.Page, attr, wrapper)

    # 同一次 pdf_to_markdown 里文本被多趟解析：预验证 2 次、gather 2 次、
    # 纯文本 1 次、版式模型 1 次（后者内部还有前 5 页统计与全页 dict 扫描）。
    for attr in ("get_text", "get_textpage", "get_drawings", "get_pixmap", "get_image_info", "get_bboxlog"):
        counted(attr)

    timed(p2m, "_paragraphs_to_document", "stage_text")
    timed(p2m, "_run_asset_extraction", "stage_assets")
    timed(p2m, "_preserve_equation_regions", "stage_equations")
    timed(p2m, "_place_assets_in_document", "stage_placement")
    timed(md, "render_markdown", "stage_render")

    # pdf_to_markdown 在函数体内延迟导入，替换 lib 源模块的属性即可
    timed(te, "pre_validate_pdf", "prevalidate[text_stage]")
    timed(te, "gather_structured_text", "pass_gather[text_stage]")
    timed(te, "extract_text_with_format", "pass_layout")
    timed(te, "_estimate_typical_metrics", "layout_metrics_first5")
    timed(te, "iter_native_text_blocks", "scan_dict_all_pages", split_by_caller=True)
    for name in ("classify_text_types", "detect_columns", "build_text_blocks", "detect_vacant_regions"):
        timed(lm, name, f"layout_{name}")

    # core.extract_pdf_assets 在模块顶部按名导入，下面这些要替换它自己命名空间里的绑定；
    # 只替换 lib 源模块的属性对它不生效（版式预扫描第一次就因此没记到）
    timed(epa, "should_enable_layout_driven", "layout_probe",
          capture=lambda n, r: n.update(layout_probe_enabled=bool(r[0]), layout_probe_reason=str(r[1])))
    timed(epa, "pre_validate_pdf", "prevalidate[asset_stage]")
    timed(epa, "try_extract_text", "pass_text[asset_stage]")
    timed(epa, "gather_structured_text", "pass_gather[asset_stage]")
    timed(epa, "extract_figures", "extract_figures")
    timed(epa, "extract_tables", "extract_tables")
    timed(epa, "build_figure_contexts", "figure_contexts")
    timed(epa, "finalize_caption_inventory", "caption_inventory")
    return recorder, lowlevel, notes


def run_timing_child(extra: List[str], timing_json: Path) -> int:
    sys.path.insert(0, str(SCRIPTS_DIR))
    from core import pdf_to_markdown as p2m

    recorder, lowlevel, notes = install_timing_wrappers()
    started = perf_counter()
    rc = int(p2m.main(list(extra)) or 0)
    total = perf_counter() - started
    payload = {
        "return_code": rc,
        "total_sec": round(total, 4),
        "phases": recorder.snapshot(),
        "lowlevel": {k: {"calls": v["calls"], "sec": round(v["sec"], 4), "pages": len(v["pages"])}
                     for k, v in lowlevel.items()},
        "notes": notes,
    }
    timing_json.parent.mkdir(parents=True, exist_ok=True)
    timing_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    return rc


def _get(phases: Dict[str, Dict[str, Any]], name: str, key: str = "inclusive") -> float:
    return float(phases.get(name, {}).get(key, 0.0))


def derive_timing(run: Dict[str, Any]) -> Dict[str, Any]:
    """从一次运行的原始计时推出汇总指标。"""
    total = float(run.get("total_sec") or 0.0)
    phases = run.get("phases") or {}
    low = run.get("lowlevel") or {}
    layout_total = _get(phases, "pass_layout")
    derived: Dict[str, Any] = {
        "parse_entries_sec": round(sum(_get(phases, n) for n in PARSE_ENTRIES), 4),
        "parse_entries_pct": round(100 * sum(_get(phases, n) for n in PARSE_ENTRIES) / total, 2) if total else None,
        "stage_text_sec": round(_get(phases, "stage_text"), 4),
        "stage_assets_sec": round(_get(phases, "stage_assets"), 4),
        "stage_other_sec": round(total - _get(phases, "stage_text") - _get(phases, "stage_assets"), 4),
        "gather_calls": sum(_get(phases, n, "calls") for n in ("pass_gather[text_stage]", "pass_gather[asset_stage]")),
        "prevalidate_calls": sum(_get(phases, n, "calls") for n in ("prevalidate[text_stage]", "prevalidate[asset_stage]")),
        "layout_pass_calls": _get(phases, "pass_layout", "calls"),
        "layout_probe_enabled": (run.get("notes") or {}).get("layout_probe_enabled"),
        "layout_probe_reason": (run.get("notes") or {}).get("layout_probe_reason"),
        "full_dict_scans": sum(
            _get(phases, n, "calls") for n in phases if n.startswith("scan_dict_all_pages")),
        # 同一份全页 dict 扫描在三个调用方里各做了一次
        "scan_in_gather_text_stage_sec": round(_get(phases, "scan_dict_all_pages[in pass_gather[text_stage]]"), 4),
        "scan_in_gather_asset_stage_sec": round(_get(phases, "scan_dict_all_pages[in pass_gather[asset_stage]]"), 4),
        "scan_in_layout_sec": round(_get(phases, "scan_dict_all_pages[in pass_layout]"), 4),
        "full_dict_scan_sec": round(sum(_get(phases, n) for n in phases if n.startswith("scan_dict_all_pages")), 4),
        "layout_metrics_first5_sec": round(_get(phases, "layout_metrics_first5"), 4),
        "get_text_calls": {k: v["calls"] for k, v in sorted(low.items()) if k in ("text", "dict", "words", "blocks", "html")},
        "get_text_sec": {k: round(v["sec"], 4) for k, v in sorted(low.items()) if k in ("text", "dict", "words", "blocks", "html")},
        "get_pixmap_calls": low.get("get_pixmap", {}).get("calls", 0),
        "get_pixmap_sec": round(low.get("get_pixmap", {}).get("sec", 0.0), 4),
        "get_drawings_calls": low.get("get_drawings", {}).get("calls", 0),
        "get_drawings_sec": round(low.get("get_drawings", {}).get("sec", 0.0), 4),
    }
    if derived["layout_pass_calls"]:
        derived["layout_breakdown_sec"] = {
            name: round(_get(phases, name), 4) for name in LAYOUT_SUBPHASES
        }
        derived["layout_breakdown_sec"]["scan_dict_all_pages"] = derived["scan_in_layout_sec"]
        derived["layout_breakdown_sec"]["other"] = round(
            layout_total - sum(derived["layout_breakdown_sec"][n] for n in LAYOUT_SUBPHASES), 4)
    # 单次扫描架构能省下的时间（估算，未扣共享数据结构的构造成本）：
    #  - 重复调用：正文阶段已经做过一次 gather 与预验证，资产阶段原样再做一遍；
    #  - 可共享扫描：版式模型内部的全页 dict 扫描与前 5 页字号统计，数据都能从同一次扫描得到。
    redundant = (
        _get(phases, "pass_gather[asset_stage]") + _get(phases, "prevalidate[asset_stage]")
    )
    shareable = derived["scan_in_layout_sec"] + derived["layout_metrics_first5_sec"]
    derived["redundant_calls_sec"] = round(redundant, 4)
    derived["redundant_calls_pct"] = round(100 * redundant / total, 2) if total else None
    derived["shareable_scan_sec"] = round(shareable, 4)
    derived["shareable_scan_pct"] = round(100 * shareable / total, 2) if total else None
    derived["single_scan_saving_pct"] = round(100 * (redundant + shareable) / total, 2) if total else None
    return derived


def run_timing(pdf_path: Path, mode: str, rep: int) -> Dict[str, Any]:
    run_dir = RUNS_DIR / mode / f"rep{rep}" / pdf_path.stem
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    extra = [
        "--pdf", str(pdf_path),
        "--out", str(run_dir / "paper.md"),
        "--asset-dir", str(run_dir / "assets"),
        "--report-json", str(run_dir / "text" / "conversion_report.json"),
        "--blocks-json", str(run_dir / "text" / "markdown_blocks.json"),
    ]
    if mode == "tables":
        extra += ["--tables", "screenshot"]
    timing_path = run_dir / "timing.json"
    cmd = [sys.executable, str(Path(__file__).resolve()), "--child", "--timing-json", str(timing_path), "--", *extra]
    started = perf_counter()
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    wall = perf_counter() - started

    summary: Dict[str, Any] = {"return_code": proc.returncode, "wall_sec": round(wall, 4)}
    if timing_path.exists():
        summary.update(json.loads(timing_path.read_text(encoding="utf-8")))
    else:
        summary["error"] = (proc.stderr or proc.stdout)[-1500:]
    report_path = run_dir / "text" / "conversion_report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        summary["report_status"] = report.get("status")
        summary["assets_embedded"] = (report.get("assets") or {}).get("embedded_count")
        summary["assets_extracted"] = (report.get("assets") or {}).get("extracted_count")
    if "phases" in summary:
        summary["derived"] = derive_timing(summary)
    (run_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    # 提取产物只为计时而生成；PNG 等大体积文件读完报告即删，避免同步到对端机器
    for name in ("paper.md", "assets", "text"):
        target = run_dir / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    return summary


def probe_timing(reps: Dict[str, int]) -> Dict[str, Any]:
    modes: Dict[str, Any] = {}
    for mode, count in reps.items():
        if count <= 0:
            continue
        per_pdf: Dict[str, Any] = {}
        for pdf in ordered_pdfs():
            runs = [run_timing(pdf, mode, rep) for rep in range(1, count + 1)]
            ok = [r for r in runs if r.get("return_code") == 0 and "phases" in r]
            best = min(ok, key=lambda r: r["total_sec"]) if ok else None
            per_pdf[pdf.stem] = {
                "runs": [{"rep": i + 1, **r} for i, r in enumerate(runs)],
                "total_sec_all": [r.get("total_sec") for r in runs],
                "best": best,
            }
            print(f"  [{mode}] {LABELS[pdf.stem]}: total={[r.get('total_sec') for r in runs]} rc={[r['return_code'] for r in runs]}", flush=True)
        modes[mode] = {"reps": count, "per_pdf": per_pdf}
    return {"environment": environment(), "modes": modes}


# ---------------------------------------------------------------------------
# 简报
# ---------------------------------------------------------------------------

def _f(value: Any, digits: int = 2) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _pct(part: Any, whole: Any) -> str:
    return "-" if not whole else f"{100 * part / whole:.1f}%"


def _md_table(headers: List[str], rows: List[List[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def build_brief(results: Dict[str, Any]) -> str:
    feats = results["features"]
    order = [stem for stem in LABELS if stem in feats]

    def label(stem: str) -> str:
        return LABELS[stem]

    out: List[str] = [
        "# WP-1.1 渲染特征探测简报",
        "",
        f"- 生成时间：{results['generated_at']}；生成脚本：`tools/render-probe/probe_render_features.py`（只读探测，输出由 `probe_results.json` 推导）。",
        f"- 环境：{results['environment']['platform']}-{results['environment']['machine']}，"
        f"Python {results['environment']['python']}，PyMuPDF {results['environment']['pymupdf']}"
        f"（MuPDF {results['environment']['mupdf']}），numpy {results['environment']['numpy'] or '未安装'}。",
        f"- 对照版本：git {results['control']['head'][:8]}（{results['control']['head_subject']}），"
        f"skills/scripts 指纹 `{results['control']['code_fingerprint'][:16]}…`。",
        f"- 只读核对：{len(results['benchmark_after']['sha256'])} 份 PDF 运行前后 SHA-256 "
        f"{'一致' if results['benchmark_unchanged'] else '不一致（已判失败）'}，目录仅含 PDF：{results['benchmark_dir_pdfs_only']}。",
        "",
        "## 1. 概览",
        "",
        _md_table(
            ["PDF", "页数", "页面(pt)", "文本块", "span", "主体左缘 x0（占块数）", "该左缘块宽中位（页宽比）",
             "gather 双栏", "版式模型栏数", "与正文几何冲突"],
            [[label(s), f["pages"], f"{f['page_size_pt'][0]}×{f['page_size_pt'][1]}", f["blocks"], f["spans"],
              f"{f['block_alignment']['dominant_x0']}（{_pct(f['block_alignment']['dominant_x0_share'], 1)}）",
              _f(f["block_alignment"]["median_width_ratio_at_dominant_x0"]),
              "是" if f["full_width"]["gather_is_dual_column"] else "否", f["full_width"]["layout_model_num_columns"],
              "是" if f["dual_flag_conflicts_with_body_geometry"] else "-"] for s in order for f in [feats[s]]],
        ),
        "",
        "「主体左缘」是块左缘 x0 取值最集中的那个值；取该值的块如果宽度中位数接近或超过 0.6 页宽，说明正文段落横贯页面，"
        "文档主体是单栏。两个栏位判定器口径不同：gather 看全部文本块中心落在页宽 45% 以左、55% 以右的占比（均需 >0.3），"
        "图内与表内的小文字块也计入；版式模型只看前 5 页 paragraph 行的 x0 直方图是否双峰。",
        "",
        "## 2. 书签（doc.get_toc）",
        "",
        _md_table(
            ["PDF", "有效书签", "层级分布", "同页精确唯一", "去尾页码后同页", "同页前缀", "任意页精确"],
            [[label(s), b["valid"], " ".join(f"L{k}×{v}" for k, v in b["level_distribution"].items()) or "-",
              b["hit_same_page_exact_unique"], b["hit_same_page_after_dropping_trailing_page_no"],
              b["hit_same_page_prefix"], b["hit_any_page_exact"]] for s in order for b in [feats[s]["bookmarks"]]],
        ),
        "",
        "「同页精确唯一」与 CHK-071 口径一致：NFKC、大小写折叠、空白归一后，书签标题与同页段落文字完全相等且只命中一段。",
        "", "书签标题样例：", "",
    ]
    for stem in order:
        samples = feats[stem]["bookmarks"]["samples"]
        if samples:
            out.append(f"- {label(stem)}：" + "；".join(f"L{s['level']} p{s['page']}「{s['title'][:34]}」" for s in samples[:3]))
    out += ["", "同页精确唯一的命中明细（书签 → 段落）：", ""]
    hit_rows = [(label(s), h) for s in order for h in feats[s]["bookmarks"]["hit_samples"]]
    out += [f"- {name}：L{h['level']} p{h['page']}「{h['bookmark'][:30]}」→「{h['paragraph'][:30]}」"
            f"{'（标题块）' if h['is_heading'] else '（非标题块）'}" for name, h in hit_rows] or ["- 无"]
    out += [
        "",
        "## 3. 粗体：标志位（flags & 16）对字体名启发式",
        "",
        _md_table(
            ["PDF", "仅标志位 span/字符", "仅字体名 span/字符", "两种皆有", "首span不一致块", "标题：标志位/字体名",
             "编号粗体块仅字体名命中", "LaTeX CMB 字体置位率"],
            [[label(s), f"{c['flag_only']['spans']}/{c['flag_only']['chars']}", f"{c['name_only']['spans']}/{c['name_only']['chars']}",
              c["flag_and_name"]["spans"], d["block_first_span_disagree"],
              f"{d['headings_by_flag']}/{d['headings_by_font_name']}", d["numbered_blocks_bold_only_by_font_name"],
              "、".join(f"{x['font']} {x['flag_rate']:.0%}({x['spans']})" for x in d["latex_bold_fonts"][:3]) or "-"]
             for s in order for d, c in [(feats[s]["bold"], feats[s]["bold"]["cells"])]],
        ),
        "",
        "仅字体名命中的字体（span 数，附样例）：", "",
    ]
    for stem in order:
        rows = feats[stem]["bold"]["name_only_fonts"]
        if rows:
            out.append(f"- {label(stem)}：" + "；".join(f"{r['font']}×{r['spans']}" for r in rows[:5]))
    flips = [(label(s), r) for s in order for r in feats[s]["bold"]["heading_only_by_font_name"]]
    out += ["", f"仅字体名口径才判为标题的块：{len(flips)} 条（每份最多列 8 条），样例：", ""]
    out += [f"- {name}：p{r['page']} {r['size']}pt {r['font']}「{r['text'][:40]}」" for name, r in flips[:12]] or ["- 无"]
    out += [
        "",
        "版式模型（图表裁剪依据）若改口径，单元分类的变化：",
        "",
        _md_table(
            ["PDF", "标题单元(现行)", "字重改字体名→变化单元/标题单元", "典型字号改众数→变化单元/标题单元", "所用众数(pt)"],
            [[label(s), v["baseline_title_units"],
              f"{v['if_bold_by_font_name']['changed_units']}/{v['if_bold_by_font_name']['title_units_after']}",
              f"{v['if_typical_size_is_char_mode']['changed_units']}/{v['if_typical_size_is_char_mode']['title_units_after']}",
              _f(v["if_typical_size_is_char_mode"]["typical_font_size_used"])]
             for s in order for v in [feats[s]["layout_sensitivity"]]],
        ),
        "",
        "## 4. 字号：算术平均对字符加权众数",
        "",
        _md_table(
            ["PDF", "gather 均值(8-14,全页)", "版式模型均值(6-20,前5页)", "单值众数(6-20)", "并簇众数(±0.15pt)",
             "gather 偏离单值/并簇 %", "版式均值偏离单值/并簇 %", "主要字号(占字符%)", "无编号标题/层级会变", "句点编号标题"],
            [[label(s), _f(v["gather_mean_8_14_all_pages"]), _f(v["layout_mean_6_20_first5_pages"]),
              _f(v["char_mode_6_20_all_pages"]), _f((v["char_mode_merged_6_20"] or {}).get("center")),
              f"{_f(v['gather_mean_offset_pct'], 1)}/{_f(v['gather_mean_offset_vs_merged_pct'], 1)}",
              f"{_f(v['layout_mean_offset_pct'], 1)}/{_f(v['layout_mean_offset_vs_merged_pct'], 1)}",
              "，".join(f"{t['size']}({t['char_pct']}%)" for t in v["top_sizes_by_char_share"][:4]),
              f"{v['unnumbered_headings']}/{v['unnumbered_heading_level_flips_if_typical_changes']}",
              v["period_numbered_headings_not_depth_mapped"]]
             for s in order for v in [feats[s]["font_sizes"]]],
        ),
        "",
        "粗体、非编号、短块（<50 字符）按「字号 ÷ 正文字符众数」分档；`size_gate_only` 指只因 11.5pt 硬门槛被拒的块数：",
        "",
        _md_table(
            ["PDF"] + [f"{lo:.2f}≤r<{hi:.2f}" if hi < 99 else f"r≥{lo:.2f}" for lo, hi in RATIO_BUCKETS],
            [[label(s)] + [f"{b['blocks']}（过 {b['accepted']}，门槛拒 {b['size_gate_only']}）"
                           for b in feats[s]["font_sizes"]["bold_non_numbered_short_blocks_by_ratio_to_body"].values()]
             for s in order],
        ),
        "",
        "只因 11.5pt 门槛被拒、但字号不低于正文的块（每份最多 4 条）：", "",
    ]
    for stem in order:
        body = (feats[stem]["font_sizes"]["char_mode_merged_6_20"] or {}).get("center") or 0.0
        rows = [r for b in feats[stem]["font_sizes"]["bold_non_numbered_short_blocks_by_ratio_to_body"].values()
                for r in b["size_gate_only_samples"] if r["size"] >= body]
        if rows:
            out.append(f"- {label(stem)}：" + "；".join(f"p{r['page']} {r['size']}pt「{r['text'][:30]}」" for r in rows[:4]))
    dual = [s for s in order if feats[s]["full_width"]["gather_is_dual_column"]]
    out += [
        "",
        "## 5. 通栏分布（仅 gather 判为双栏的文档）",
        "",
        _md_table(
            ["PDF", "保留块", "通栏块(占比)", "按类型", "每页通栏数分布", "最大/页", "宽度比 最小/中位",
             "宽阈值 0.50/0.52/0.55/0.60/0.65", "中部通栏块", "多带页"],
            [[label(s), w["kept_blocks"], f"{w['full_width_blocks']}({_pct(w['full_width_blocks'], w['kept_blocks'])})",
              " ".join(f"{k}{v}" for k, v in sorted(w["full_width_by_type"].items(), key=lambda kv: -kv[1])),
              " ".join(f"{k}块:{v}页" for k, v in w["full_width_blocks_per_page_distribution"].items()) or "-",
              w["max_full_width_per_page"],
              f"{_f(w['full_width_width_ratio']['min'])}/{_f(w['full_width_width_ratio']['median'])}",
              "/".join(str(w["full_width_count_under_wide_threshold"][k]) for k in ("0.50", "0.52", "0.55", "0.60", "0.65")),
              w["mid_page_full_width_blocks"], len(w["multi_band_pages"])] for s in dual for w in [feats[s]["full_width"]]],
        ) if dual else "（8 份中没有 gather 判为双栏的文档）",
        "",
    ]
    if dual:
        out += ["通栏块的纵向分布（页高十分位，0 为页顶）：", ""]
        for stem in dual:
            w = feats[stem]["full_width"]
            out.append(f"- {label(stem)}：" + " ".join(f"D{k}:{v}" for k, v in w["full_width_by_vertical_decile"].items() if v))
        out += ["", "多带页（首尾双栏块之间夹着通栏块）：", ""]
        for stem in dual:
            pages = feats[stem]["full_width"]["multi_band_pages"]
            out.append(f"- {label(stem)}：{len(pages)} 页" + (f"，页码 {pages[:20]}{'…' if len(pages) > 20 else ''}" if pages else ""))
        out += ["", "非通栏但宽度比 ≥0.45（接近 0.55 宽度阈值的块，每份最多 8 条）：", ""]
        for stem in dual:
            rows = feats[stem]["full_width"]["non_full_width_near_wide_threshold_samples"]
            if rows:
                out.append(f"- {label(stem)}：" + "；".join(f"p{r['page']} r={r['width_ratio']:.2f} {r['type']}「{r['text'][:26]}」" for r in rows[:5]))
            else:
                out.append(f"- {label(stem)}：无（共 {feats[stem]['full_width']['non_full_width_blocks_with_width_ratio_ge_0_45']} 块）")
        out += [""]
        conflicts = [s for s in dual if feats[s]["dual_flag_conflicts_with_body_geometry"]]
        if conflicts:
            out += [
                "**gather 的双栏判定与正文几何冲突的文档**：正文段落横贯页面（单栏），但图内、表内的小文字块把两侧占比抬过了 0.3 阈值。"
                "分带排序只在判为双栏时生效，于是这些文档的页内顺序被改成「带内先左半后右半」：",
                "",
                _md_table(
                    ["PDF", "被标左/右栏的块", "顺序不同于 y 序的页 / 总页", "错位位置数"],
                    [[label(s), r["column_blocks_left_right"],
                      f"{r['pages_where_order_differs_from_y_order']} / {r['pages_total']}",
                      r["differing_positions_total"]] for s in conflicts for r in [feats[s]["reading_order"]]],
                ),
                "",
                "错位样例（同一页同一窗口，上为「页内按 y 再按 x」，下为实际输出顺序；左/右是 gather 给块贴的栏位）：", "",
            ]
            for stem in conflicts:
                for smp in feats[stem]["reading_order"]["samples"][:3]:
                    out.append(f"- {label(stem)} 第 {smp['page']} 页（该页 {smp['differing_positions']} 个位置不同）：")
                    out.append(f"  - y 序：" + " ｜ ".join(smp["y_order"]))
                    out.append(f"  - 输出：" + " ｜ ".join(smp["reading_order"]))
            out.append("")
    single = [s for s in order if not feats[s]["full_width"]["gather_is_dual_column"]]
    if single:
        out += [
            "gather 未判双栏的文档（阈值：左、右两侧块中心占比均 >0.3）：",
            "",
            _md_table(["PDF", "左 45% 占比", "右 55% 占比", "版式模型栏数"],
                      [[label(s), _f(feats[s]["full_width"]["gather_left_center_ratio"]), _f(feats[s]["full_width"]["gather_right_center_ratio"]),
                        feats[s]["full_width"]["layout_model_num_columns"]] for s in single]),
            "",
        ]

    timing = results.get("timing")
    if timing and timing.get("modes"):
        env = timing["environment"]
        out += [
            "## 6. 分阶段耗时",
            "",
            f"环境：{env['platform']}-{env['machine']}，Python {env['python']}，PyMuPDF {env['pymupdf']}。"
            "每个 PDF 在独立子进程里按正式 CLI 原样运行一次 `pdf_to_markdown.py`；"
            "取多次重复中总耗时最短的一次列示。耗时受机器负载影响，看量级与占比，不看个位差异。",
            "",
        ]
        for index, (mode, block) in enumerate(sorted(timing["modes"].items()), 1):
            mode_label = "默认（图开、表关）" if mode == "default" else "`--tables screenshot`"
            bests = {s: (block["per_pdf"].get(s) or {}).get("best") for s in order}
            out += [f"### 6.{index} {mode_label}，重复 {block['reps']} 次", ""]

            rows = []
            for stem in order:
                best = bests[stem]
                if not best:
                    rows.append([label(stem), "失败", "-", "-", "-", "-", "-"])
                    continue
                d = best["derived"]
                rows.append([
                    label(stem), _f(best["total_sec"]),
                    "/".join(_f(x, 1) for x in (block["per_pdf"][stem].get("total_sec_all") or [])),
                    f"{_f(d['stage_text_sec'])}({_pct(d['stage_text_sec'], best['total_sec'])})",
                    f"{_f(d['stage_assets_sec'])}({_pct(d['stage_assets_sec'], best['total_sec'])})",
                    f"{_f(d['parse_entries_sec'])}({_pct(d['parse_entries_sec'], best['total_sec'])})",
                    f"{d['get_text_calls'].get('dict', 0)}",
                ])
            out += [
                _md_table(["PDF", "总耗时(s)", "各次总耗时", "文本阶段(s)", "资产阶段(s)", "解析入口合计(s)",
                           "get_text(dict) 次数"], rows),
                "",
                "解析入口 = 预验证、纯文本、gather、版式预扫描、版式模型各入口的包含耗时之和"
                "（嵌套在文本/资产阶段之内，不另加）。一次运行里 gather 2 次、预验证 2 次、版式模型 1 次，"
                "全页 dict 扫描共 3 次。各入口耗时（秒）：",
                "",
                _md_table(
                    ["PDF", "预验证·正文阶段", "gather·正文阶段", "预验证·资产阶段", "纯文本",
                     "gather·资产阶段", "版式预扫描", "版式模型", "其中 dict 扫描", "其中 前5页统计"],
                    [[label(s)] + [_f(_get(b["phases"], n)) for n in PARSE_ENTRIES]
                     + [_f(b["derived"]["scan_in_layout_sec"]), _f(b["derived"]["layout_metrics_first5_sec"])]
                     for s in order for b in [bests[s]] if b],
                ),
                "",
                "单次扫描架构可省时间的估算（未扣共享数据结构的构造成本）：",
                "",
                _md_table(
                    ["PDF", "重复调用：第 2 次 gather 与预验证(s)", "可共享：版式模型内 dict 扫描与前 5 页统计(s)",
                     "合计(s)", "合计占总耗时"],
                    [[label(s), _f(b["derived"]["redundant_calls_sec"]), _f(b["derived"]["shareable_scan_sec"]),
                      _f(b["derived"]["redundant_calls_sec"] + b["derived"]["shareable_scan_sec"]),
                      _f(b["derived"]["single_scan_saving_pct"], 1)]
                     for s in order for b in [bests[s]] if b],
                ),
                "",
                "资产阶段内部与底层调用（秒）：",
                "",
                _md_table(
                    ["PDF", "Figure 提取", "Table 提取", "题注对账", "get_text 次数 text/dict",
                     "get_text(dict) 秒", "get_drawings 次/秒", "get_pixmap 次/秒"],
                    [[label(s), _f(_get(b["phases"], "extract_figures")), _f(_get(b["phases"], "extract_tables")),
                      _f(_get(b["phases"], "caption_inventory")),
                      f"{b['derived']['get_text_calls'].get('text', 0)}/{b['derived']['get_text_calls'].get('dict', 0)}",
                      _f(b["lowlevel"].get("dict", {}).get("sec")),
                      f"{b['derived']['get_drawings_calls']}/{_f(b['derived']['get_drawings_sec'], 2)}",
                      f"{b['derived']['get_pixmap_calls']}/{_f(b['derived']['get_pixmap_sec'], 2)}"]
                     for s in order for b in [bests[s]] if b],
                ),
                "",
            ]
        out += ["版式模型的启用方式：", ""]
        for mode, block in sorted(timing["modes"].items()):
            bests = [((block["per_pdf"].get(s) or {}).get("best") or {}) for s in order]
            ran = sum(1 for b in bests if b.get("derived", {}).get("layout_pass_calls"))
            probed = [b for b in bests if "layout_probe_enabled" in (b.get("notes") or {})]
            if probed:
                reasons = sorted({str(b["notes"].get("layout_probe_reason")) for b in probed
                                  if b["notes"].get("layout_probe_enabled")})
                on = sum(1 for b in probed if b["notes"]["layout_probe_enabled"])
                out.append(f"- {mode}：经预扫描判定启用 {on}/{len(probed)}；理由：{'；'.join(reasons) or '-'}；"
                           f"版式模型实际运行 {ran}/{len(order)}。")
            else:
                out.append(
                    f"- {mode}：版式模型实际运行 {ran}/{len(order)}；预扫描函数 "
                    "should_enable_layout_driven 未被调用（当前 CLI 的 --layout-driven 默认值是 on，"
                    "直接启用；预扫描只在取值 auto 时才走）。"
                )
        out += [""]

    # 人工撰写的解读小节：重跑时原样保留
    out.append("")
    return "\n".join(out)


def merge_notes(brief_text: str, previous: str) -> str:
    if NOTES_HEADING in previous:
        notes = previous[previous.index(NOTES_HEADING):].rstrip() + "\n"
        return brief_text.rstrip() + "\n\n" + notes
    return brief_text.rstrip() + "\n\n" + NOTES_HEADING + "\n\n（待撰写）\n"


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def git_head() -> Tuple[str, str]:
    def run(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True).stdout.strip()
    return run("rev-parse", "HEAD"), run("log", "-1", "--format=%s")


def code_fingerprint() -> str:
    hasher = hashlib.sha256()
    for path in sorted(SCRIPTS_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        hasher.update(str(path.relative_to(SCRIPTS_DIR)).encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def main(argv: Optional[List[str]] = None) -> int:
    global OUT_DIR, RESULTS_PATH, BRIEF_PATH, RUNS_DIR
    parser = argparse.ArgumentParser(description="WP-1.1 只读探测")
    parser.add_argument("--child", action="store_true", help="内部使用：计时子进程")
    parser.add_argument("--timing-json", help="内部使用：子进程计时结果输出路径")
    parser.add_argument("--no-features", action="store_true", help="跳过特征探测，沿用已有结果")
    parser.add_argument("--no-timing", action="store_true", help="跳过耗时探测")
    parser.add_argument("--timing-reps", nargs=2, type=int, default=[2, 1], metavar=("DEFAULT", "TABLES"),
                        help="默认模式、表格截图模式各重复几次（默认 2 1）")
    parser.add_argument("--out-dir", help="产物目录（默认 experiments/arch-convergence-probe-20261124）")
    args, rest = parser.parse_known_args(argv)

    if args.child:
        extra = [a for a in rest if a != "--"]
        return run_timing_child(extra, Path(args.timing_json))

    OUT_DIR = Path(args.out_dir).resolve() if args.out_dir else DEFAULT_OUT_DIR
    RESULTS_PATH = OUT_DIR / "probe_results.json"
    BRIEF_PATH = OUT_DIR / "probe_brief.md"
    RUNS_DIR = OUT_DIR / "runs"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    previous_brief = BRIEF_PATH.read_text(encoding="utf-8") if BRIEF_PATH.exists() else ""
    results: Dict[str, Any] = {}
    if args.no_features:
        results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    else:
        before = bench_state()
        head, subject = git_head()
        results = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "environment": environment(),
            "control": {"head": head, "head_subject": subject, "code_fingerprint": code_fingerprint()},
            "benchmark_before": before,
        }
        features: Dict[str, Any] = {}
        for pdf in ordered_pdfs():
            started = perf_counter()
            features[pdf.stem] = probe_features(pdf)
            print(f"  [features] {LABELS[pdf.stem]}: {perf_counter() - started:.1f}s", flush=True)
            gc.collect()
        after = bench_state()
        results["features"] = features
        results["benchmark_after"] = after
        results["benchmark_unchanged"] = before == after
        results["benchmark_dir_pdfs_only"] = all(n.lower().endswith(".pdf") for n in after["entries"])
        if not (results["benchmark_unchanged"] and results["benchmark_dir_pdfs_only"]):
            print("只读核对失败：benchmark 目录或 PDF 哈希发生变化", file=sys.stderr)
            RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
            return 2

    if not args.no_timing:
        print("耗时探测开始（每个 PDF 独立子进程）", flush=True)
        timing = probe_timing({"default": args.timing_reps[0], "tables": args.timing_reps[1]})
        # 耗时探测可以按模式分几次跑：本次没有重跑的模式沿用已有结果
        merged_modes = dict((results.get("timing") or {}).get("modes") or {})
        merged_modes.update(timing["modes"])
        results["timing"] = {**timing, "modes": merged_modes}
        # 耗时运行同样只读 benchmark，收尾再核一次
        state = bench_state()
        results["benchmark_after_timing"] = state
        results["benchmark_unchanged"] = bool(results.get("benchmark_unchanged")) and state == results["benchmark_before"]

    RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    BRIEF_PATH.write_text(merge_notes(build_brief(results), previous_brief), encoding="utf-8")
    print(f"已写出 {RESULTS_PATH.name}、{BRIEF_PATH.name}")
    return 0 if results.get("benchmark_unchanged") else 2


if __name__ == "__main__":
    raise SystemExit(main())
