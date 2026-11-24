#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""附录探测：一次 pdf_to_markdown 运行里，按页解析类调用的重复程度。

主探测（probe_render_features.py）显示 get_text("dict") 的累计耗时远大于几个文本
解析入口的去重空间。本脚本回答「同一页、同一参数被解析了几次」：重复越多，按页缓存
解析结果的收益越大。做法与主探测相同：每个 PDF 在独立子进程里包装 PyMuPDF 的
Page 方法后原样运行一次正式 CLI，不修改源码，只读 benchmark。

统计对象：get_text（按 mode、clip、flags、sort 区分）、get_drawings、get_image_info。
「可缓存耗时」= 各键耗时 × (1 − 1/该键调用次数) 之和，即假设同键调用耗时相近时，
只解析一次能省下的时间；未计入缓存本身的构造成本与内存占用。

用法（在仓库根目录运行）：
  python3 tools/render-probe/probe_dict_call_reuse.py            # 8 份，默认模式（图开、表关）
  python3 tools/render-probe/probe_dict_call_reuse.py --tables   # 追加 --tables screenshot
  python3 tools/render-probe/probe_dict_call_reuse.py --reuse     # 不重跑，用已有 calls.json 重新汇总
  python3 tools/render-probe/probe_dict_call_reuse.py --out-dir 某目录

产物：dict_call_reuse.json，以及 runs/dict-call-reuse/<stem>/calls.json（逐次调用明细）。
默认写入 experiments/arch-convergence-probe-20261124/（已被 gitignore）；tools/ 是受跟踪
目录，不往里写运行产物。要留档的结果另外拷一份带日期后缀的快照到 design/4-analysis/
（2026-11-24 的快照是 架构收敛WP-1.1按页解析调用重复程度-20261124.json）。
"""
from __future__ import annotations

import argparse
import fitz
import functools
import json
import platform
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "skills" / "pdf-markdown-summary" / "scripts"
BENCH_DIR = ROOT / "tests" / "basic-benchmark"
# 运行产物默认写入被忽略的 experiments/；可用 --out-dir 改到别处
DEFAULT_OUT_DIR = ROOT / "experiments" / "arch-convergence-probe-20261124"
OUT_PATH = DEFAULT_OUT_DIR / "dict_call_reuse.json"
RUNS_DIR = DEFAULT_OUT_DIR / "runs" / "dict-call-reuse"

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


def _clip_key(clip: Any) -> Tuple[float, ...]:
    if clip is None:
        return ()
    try:
        return tuple(round(float(v), 2) for v in clip)
    except TypeError:
        return tuple(round(float(v), 2) for v in (clip.x0, clip.y0, clip.x1, clip.y1))


def text_key(args, kwargs):
    option = args[0] if args else kwargs.get("option", "text")
    clip = args[1] if len(args) > 1 else kwargs.get("clip")
    flags = args[2] if len(args) > 2 else kwargs.get("flags")
    sort = args[3] if len(args) > 3 else kwargs.get("sort", False)
    return (str(option), _clip_key(clip), repr(flags), bool(sort))


def drawings_key(args, kwargs):
    extended = args[0] if args else kwargs.get("extended", False)
    return ("get_drawings", bool(extended))


def image_info_key(args, kwargs):
    hashes = args[0] if args else kwargs.get("hashes", False)
    xrefs = args[1] if len(args) > 1 else kwargs.get("xrefs", False)
    return ("get_image_info", bool(hashes), bool(xrefs))


def run_child(extra: List[str], out_json: Path) -> int:
    sys.path.insert(0, str(SCRIPTS_DIR))
    from core import pdf_to_markdown as p2m

    stats: Dict[Tuple, Dict[str, Any]] = defaultdict(lambda: {"calls": 0, "sec": 0.0})

    def wrap(attr: str, key_of):
        original = getattr(fitz.Page, attr)

        @functools.wraps(original)
        def wrapper(self, *args, **kwargs):
            key = (self.number,) + key_of(args, kwargs)
            entry = stats[key]
            started = perf_counter()
            try:
                return original(self, *args, **kwargs)
            finally:
                entry["sec"] += perf_counter() - started
                entry["calls"] += 1

        setattr(fitz.Page, attr, wrapper)

    wrap("get_text", text_key)
    wrap("get_drawings", drawings_key)
    wrap("get_image_info", image_info_key)

    started = perf_counter()
    rc = int(p2m.main(list(extra)) or 0)
    payload = {
        "return_code": rc,
        "total_sec": round(perf_counter() - started, 4),
        "calls": [
            {"page": key[0], "method": key[1], "detail": list(key[2:]), "calls": v["calls"], "sec": round(v["sec"], 4)}
            for key, v in stats.items()
        ],
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8", newline="\n")
    return rc


# 子进程对 get_text 行的 method 字段记的是 mode（dict/text/…），汇总时还原成方法名
TEXT_MODES = {"text", "dict", "words", "blocks", "html", "rawdict", "json", "xhtml"}


def summarize(run: Dict[str, Any]) -> Dict[str, Any]:
    groups: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"calls": 0, "sec": 0.0, "keys": 0, "cacheable": 0.0})
    for row in run["calls"]:
        kind = f"get_text({row['method']})" if row["method"] in TEXT_MODES else row["method"]
        g = groups[kind]
        g["calls"] += row["calls"]
        g["sec"] += row["sec"]
        g["keys"] += 1
        g["cacheable"] += row["sec"] * (1 - 1 / row["calls"])
    out = {}
    for label, g in groups.items():
        out[label] = {
            "calls": g["calls"], "distinct_keys": g["keys"],
            "sec": round(g["sec"], 3),
            "pct_of_total": round(100 * g["sec"] / run["total_sec"], 1) if run["total_sec"] else None,
            "cacheable_sec": round(g["cacheable"], 3),
            "cacheable_pct_of_total": round(100 * g["cacheable"] / run["total_sec"], 1) if run["total_sec"] else None,
        }
    hot = sorted(run["calls"], key=lambda r: -r["sec"] * (1 - 1 / r["calls"]))[:3]
    out["_hottest_repeated"] = [
        {"page": r["page"] + 1, "method": r["method"], "detail": r["detail"][:2], "calls": r["calls"], "sec": r["sec"]}
        for r in hot
    ]
    return out


def main(argv: Optional[List[str]] = None) -> int:
    global OUT_PATH, RUNS_DIR
    parser = argparse.ArgumentParser(description="按页解析类调用的重复程度探测")
    parser.add_argument("--child", action="store_true", help="内部使用：子进程入口")
    parser.add_argument("--out-json", help="内部使用：子进程结果输出路径")
    parser.add_argument("--tables", action="store_true", help="追加 --tables screenshot")
    parser.add_argument("--only", nargs="*", help="只跑指定 PDF 的 stem")
    parser.add_argument("--reuse", action="store_true",
                        help="不重跑，直接用 runs/dict-call-reuse/<stem>/calls.json 重新汇总")
    parser.add_argument("--out-dir", help="产物目录（默认 experiments/arch-convergence-probe-20261124）")
    args, rest = parser.parse_known_args(argv)
    if args.child:
        return run_child([a for a in rest if a != "--"], Path(args.out_json))

    out_dir = Path(args.out_dir).resolve() if args.out_dir else DEFAULT_OUT_DIR
    OUT_PATH = out_dir / "dict_call_reuse.json"
    RUNS_DIR = out_dir / "runs" / "dict-call-reuse"
    out_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(BENCH_DIR.glob("*.pdf"))
    if args.only:
        pdfs = [p for p in pdfs if p.stem in args.only]
    if not args.reuse and RUNS_DIR.exists():
        shutil.rmtree(RUNS_DIR)
    result: Dict[str, Any] = {
        "environment": {"platform": sys.platform, "machine": platform.machine(), "python": platform.python_version()},
        "mode": "tables" if args.tables else "default",
        "per_pdf": {},
    }
    for pdf in pdfs:
        run_dir = RUNS_DIR / pdf.stem
        run_dir.mkdir(parents=True, exist_ok=True)
        out_json = run_dir / "calls.json"
        extra = [
            "--pdf", str(pdf), "--out", str(run_dir / "paper.md"), "--asset-dir", str(run_dir / "assets"),
            "--report-json", str(run_dir / "text" / "conversion_report.json"),
            "--blocks-json", str(run_dir / "text" / "markdown_blocks.json"),
        ]
        if args.tables:
            extra += ["--tables", "screenshot"]
        if not args.reuse:
            proc = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--child", "--out-json", str(out_json), "--", *extra],
                cwd=str(ROOT), capture_output=True, text=True,
            )
        if not out_json.exists():
            print(f"  {LABELS.get(pdf.stem, pdf.stem)}: 失败 {(proc.stderr or proc.stdout)[-300:] if not args.reuse else '（没有 calls.json）'}", flush=True)
            continue
        run = json.loads(out_json.read_text(encoding="utf-8"))
        summary = summarize(run)
        with fitz.open(pdf) as pdf_doc:
            page_count = len(pdf_doc)
        result["per_pdf"][pdf.stem] = {"pages": page_count,
                                       "total_sec": run["total_sec"], "return_code": run["return_code"], "summary": summary}
        dict_row = summary.get("get_text(dict)", {})
        print(f"  {LABELS.get(pdf.stem, pdf.stem):12s} 总 {run['total_sec']:6.2f}s | dict 调用 {dict_row.get('calls', 0):4d} 次"
              f"（{dict_row.get('distinct_keys', 0)} 个不同键）{dict_row.get('sec', 0):6.2f}s，可缓存约 {dict_row.get('cacheable_sec', 0):6.2f}s",
              flush=True)
        for name in ("paper.md", "assets", "text"):
            target = run_dir / name
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(f"已写出 {OUT_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
