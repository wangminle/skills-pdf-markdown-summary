#!/usr/bin/env python3
"""Analyze debug-visual batch output for tuning signals.

用法:
    python3 tests/scripts/analyze_debug_batch.py tests/results/20260622-001

参数:
    batch   tests/results/ 下的批次目录（如 20260622-001）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]


@dataclass
class StageDelta:
    name: str
    baseline_h: float
    stage_h: float
    baseline_area: float
    stage_area: float

    @property
    def height_ratio(self) -> float:
        return self.stage_h / max(1.0, self.baseline_h)

    @property
    def area_ratio(self) -> float:
        return self.stage_area / max(1.0, self.baseline_area)


@dataclass
class LegendAnalysis:
    pdf: str
    item: str
    page: int
    caption: str = ""
    stages: dict[str, StageDelta] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _parse_rect_block(block: str) -> tuple[float, float, float, float] | None:
    m = re.search(
        r"Position:\s*([\d.]+),([\d.]+)\s*->\s*([\d.]+),([\d.]+)\s*\n\s*Size:\s*([\d.]+)×([\d.]+)pt",
        block,
    )
    if not m:
        return None
    x0, y0, x1, y1 = map(float, m.groups()[:4])
    return x0, y0, x1, y1


def parse_legend(path: Path) -> LegendAnalysis | None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    m = re.match(r"===\s*(Figure|Table)\s+(\S+)\s+Debug Legend\s+\(Page\s+(\d+)\)", text)
    if not m:
        return None
    kind, ident, page = m.group(1), m.group(2), int(m.group(3))
    cap = re.search(r"Caption:\s*(.+)", text)
    analysis = LegendAnalysis(
        pdf=path.parts[-4],
        item=f"{kind} {ident}",
        page=page,
        caption=cap.group(1).strip() if cap else "",
    )

    stage_names = ("baseline", "phase_a", "phase_b", "phase_d", "final", "fallback", "rejected")
    stage_blocks = re.split(r"\n(?=baseline:|phase_a:|phase_b:|phase_d:|final:|fallback:|rejected:)", text)
    rects: dict[str, tuple[float, float, float, float]] = {}
    for block in stage_blocks:
        for stage in stage_names:
            if block.startswith(stage + ":"):
                rect = _parse_rect_block(block)
                if rect:
                    rects[stage] = rect
    if "baseline" not in rects:
        return analysis

    bx0, by0, bx1, by1 = rects["baseline"]
    b_area = max(1.0, (bx1 - bx0) * (by1 - by0))
    b_h = max(1.0, by1 - by0)
    for stage, (x0, y0, x1, y1) in rects.items():
        if stage == "baseline":
            continue
        analysis.stages[stage] = StageDelta(
            stage,
            b_h,
            max(1.0, y1 - y0),
            b_area,
            max(1.0, (x1 - x0) * (y1 - y0)),
        )

    if "phase_a" in analysis.stages and analysis.stages["phase_a"].height_ratio < 0.85:
        analysis.notes.append("phase_a_shrink>15%")
    if "phase_b" in analysis.stages and analysis.stages["phase_b"].height_ratio < 0.75:
        analysis.notes.append("phase_b_shrink>25%")
    if "phase_d" in analysis.stages and analysis.stages["phase_d"].height_ratio < 0.75:
        analysis.notes.append("phase_d_shrink>25%")
    if "final" in analysis.stages:
        fr = analysis.stages["final"].height_ratio
        if fr < 0.55:
            analysis.notes.append(f"final_small_h={fr:.2f}")
        shrink_refs = [
            analysis.stages[s].height_ratio
            for s in ("phase_b", "phase_d")
            if s in analysis.stages
        ]
        if abs(fr - 1.0) < 0.02:
            if any(r < 0.95 for r in shrink_refs):
                analysis.notes.append("fallback_to_baseline")
    if "rejected" in rects:
        analysis.notes.append("rejected_stage_present")
    return analysis


def scan_logs(pdf_dir: Path) -> list[str]:
    out: list[str] = []
    log_paths = [
        pdf_dir / "assets" / "run.log.jsonl",
        pdf_dir / "images" / "run.log.jsonl",
    ]
    for log_path in log_paths:
        if not log_path.exists():
            continue
        for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            event = str(ev.get("event") or "")
            details = ev.get("details") or {}
            msg = str(ev.get("message") or details.get("reason") or "")
            haystack = " ".join([event, msg]).lower()
            if any(k in haystack for k in ("reject", "fallback", "pollution")):
                out.append(
                    f"{ev.get('kind')} {ev.get('id')} p{ev.get('page')}: "
                    f"{event} {msg}".strip()
                )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="分析 debug-visual 批次输出，统计调参信号。",
    )
    parser.add_argument(
        "batch",
        type=Path,
        help="批次目录路径（如 tests/results/20260622-001）",
    )
    args = parser.parse_args()

    batch: Path = args.batch
    if not batch.is_dir():
        # 友好报错，不抛 traceback
        print(f"错误: 批次目录不存在: {batch}", file=sys.stderr)
        print(f"用法: python3 {Path(__file__).name} <批次目录>", file=sys.stderr)
        return 1

    all_items: list[LegendAnalysis] = []
    for pdf_dir in sorted(batch.iterdir()):
        if not pdf_dir.is_dir():
            continue
        dbg = pdf_dir / "images" / "debug"
        if not dbg.exists():
            continue
        logs = scan_logs(pdf_dir)
        flagged = []
        for legend in sorted(dbg.glob("*_stages_legend.txt")):
            parsed = parse_legend(legend)
            if parsed:
                all_items.append(parsed)
                if parsed.notes:
                    flagged.append(parsed)
        print("=" * 72)
        print(pdf_dir.name)
        print(f"  legends={len(list(dbg.glob('*_stages_legend.txt')))} flagged={len(flagged)}")
        for note in logs[:10]:
            print(f"  LOG {note}")
        for item in flagged[:12]:
            print(f"  FLAG {item.item} p{item.page}: {', '.join(item.notes)}")

    # Global stats
    note_counts: dict[str, int] = {}
    for item in all_items:
        for n in item.notes:
            note_counts[n] = note_counts.get(n, 0) + 1
    print("\n" + "=" * 72)
    print("GLOBAL NOTE COUNTS")
    for k, v in sorted(note_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
