#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""convert_labelme_to_gt.py — LabelMe JSON → tests/annotations/<doc>/gt.json。

LabelMe 在整页渲染图上标注，渲染参数与实验脚本
docs/3-experiments/20260728-pymupdf4llm-layout-bbox/scripts/01_extract_layout.py
第 89 行保持一致：fitz.Matrix(1.5, 1.5)，即 zoom=1.5、DPI=108（72×1.5）。
本脚本据此把像素坐标换算回 PDF 点坐标：pt = px × 72 / DPI = px / 1.5。

LabelMe rectangle shape 的 points 为 [[x1,y1],[x2,y2]]（像素，任意角顺序）。

shape label 命名约定（冒号分隔，occurrence 用 # 后缀，默认 1）：
  content:<kind>:<ident>[#<occ>]            资产主体内容框（可多个 → content_bboxes[]）
  caption:<kind>:<ident>[#<occ>]            caption 框（每个资产最多一个）
  element:<kind>:<ident>[#<occ>]:<name>     构成元素框（截断判定用，可多个）
  false_caption                             正文引用（伪 caption），记入 false_captions[]

分组规则（SCHEMA 规范③/④）：同 (kind, ident) 同页多框合并为一条记录
（多 panel，进 content_bboxes[]）；跨页则拆成多条记录，每条 caption_page
各自页码、坐标只含本页框，occurrence 按页码顺序从 1 递增，group_id 统一为
g-{kind}-{ident}。某页记录缺 caption 时复用该资产首个 caption_bbox 并记 warning。

用法：
  python tests/eval/convert_labelme_to_gt.py \
      --document-id 1706.03762v7-attention_is_all_you_need \
      --out tests/annotations/1706.03762v7-attention_is_all_you_need/gt.json \
      page_0003.json page_0004.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 与 01_extract_layout.py 的 fitz.Matrix(1.5, 1.5) 一致：DPI = 72 × 1.5
RENDER_ZOOM = 1.5
DEFAULT_DPI = 72.0 * RENDER_ZOOM  # 108.0

LABEL_RE = re.compile(
    r"^(?P<role>content|caption|element):(?P<kind>[a-z]+):(?P<ident>[^:#]+)"
    r"(?:#(?P<occ>\d+))?(?::(?P<ename>.+))?$"
)


def px_rect_to_pt(points: List[List[float]], dpi: float) -> List[float]:
    """LabelMe 像素矩形 → PDF 点坐标 [x0,y0,x1,y1]（归一化角序）。"""
    (x1, y1), (x2, y2) = points[0], points[1]
    scale = 72.0 / dpi
    return [
        round(min(x1, x2) * scale, 2),
        round(min(y1, y2) * scale, 2),
        round(max(x1, x2) * scale, 2),
        round(max(y1, y2) * scale, 2),
    ]


def page_from_filename(path: Path) -> Optional[int]:
    m = re.search(r"(\d+)", path.stem)
    return int(m.group(1)) if m else None


def convert(
    labelme_files: List[Path],
    document_id: str,
    dpi: float = DEFAULT_DPI,
    annotator: str = "",
    annotated_at: str = "",
) -> Dict[str, Any]:
    """按 SCHEMA 规范③/④ 分组：

    - 同 (kind, ident, occ) 同页的多框合并为一条记录（多 panel，content_bboxes[]）；
    - 同 (kind, ident) 跨页则拆成多条记录，每条 caption_page 各自页码、
      坐标只含本页框，occurrence 按页码顺序从 1 递增，
      group_id 统一为 g-{kind}-{ident}；
    - caption 框归属本页记录；若某页记录没有本页 caption，复用该资产
      首个 caption_bbox 并在 conversion_warnings 注明。
    """
    # key = (kind, ident, occ_label, page)
    assets: Dict[Tuple[str, str, int, Optional[int]], Dict[str, Any]] = {}
    false_captions: List[Dict[str, Any]] = []
    skipped: List[str] = []

    for lm_path in labelme_files:
        data = json.loads(lm_path.read_text(encoding="utf-8"))
        page = page_from_filename(lm_path)
        for shape in data.get("shapes") or []:
            if shape.get("shape_type", "rectangle") != "rectangle":
                skipped.append(f"{lm_path.name}: 非 rectangle shape（{shape.get('shape_type')}）已跳过")
                continue
            label = str(shape.get("label") or "")
            points = shape.get("points") or []
            if len(points) != 2:
                skipped.append(f"{lm_path.name}: label={label!r} points 不是两点，已跳过")
                continue
            bbox = px_rect_to_pt(points, dpi)

            if label == "false_caption":
                false_captions.append({"page": page, "bbox": bbox, "source_file": lm_path.name})
                continue

            m = LABEL_RE.match(label)
            if not m:
                skipped.append(f"{lm_path.name}: 无法解析的 label {label!r}，已跳过")
                continue
            role = m.group("role")
            kind = m.group("kind")
            ident = m.group("ident")
            occ = int(m.group("occ") or 1)
            key = (kind, ident, occ, page)
            rec = assets.setdefault(
                key,
                {
                    "document_id": document_id,
                    "kind": kind,
                    "ident": ident,
                    "caption_page": page,
                    "occurrence": occ,
                    "group_id": "",
                    "caption_bbox": None,
                    "content_bboxes": [],
                    "elements": [],
                    "ambiguous": False,
                    "ambiguity_reason": "",
                    "annotator": annotator,
                    "reviewer": "",
                    "annotated_at": annotated_at,
                },
            )
            if role == "caption":
                rec["caption_bbox"] = bbox
            elif role == "content":
                rec["content_bboxes"].append(bbox)
            else:  # element
                rec["elements"].append({"name": m.group("ename") or "element", "bbox": bbox})

    # 跨页拆分处理：同 (kind, ident) 出现在多页 → occurrence 按页序递增、统一 group_id
    by_asset: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for (kind, ident, _occ, _page), rec in assets.items():
        by_asset.setdefault((kind, ident), []).append(rec)

    out_assets = []
    for (kind, ident), recs in by_asset.items():
        recs.sort(key=lambda r: (r["caption_page"] or 0, r["occurrence"]))
        multi_page = len({r["caption_page"] for r in recs}) > 1
        # 该资产的首个 caption（跨页时供缺 caption 的记录复用）
        first_caption = next((r["caption_bbox"] for r in recs if r["caption_bbox"]), None)
        for i, rec in enumerate(recs):
            if multi_page:
                # 规范④：跨页 continued，occurrence 按页码顺序从 1 递增
                rec["occurrence"] = i + 1
                rec["group_id"] = f"g-{kind}-{ident}"
            if rec["caption_bbox"] is None and first_caption is not None:
                rec["caption_bbox"] = first_caption
                skipped.append(
                    f"{kind} {ident} p{rec['caption_page']}: 本页未标 caption，"
                    "已复用该资产首个 caption_bbox（规范④约定）"
                )
            out_assets.append(rec)
    out_assets.sort(key=lambda r: (r["caption_page"] or 0, r["kind"], r["ident"], r["occurrence"]))

    return {
        "document_id": document_id,
        "coordinate_space": "pdf_points",
        "source": f"labelme@{dpi:g}dpi",
        "assets": out_assets,
        "false_captions": false_captions,
        "conversion_warnings": skipped,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="LabelMe JSON → gt.json 转换器（像素 → PDF 点，默认 DPI=108）"
    )
    ap.add_argument("labelme_json", nargs="+", type=Path, help="LabelMe 导出的 JSON（可多个，跨页）")
    ap.add_argument("--document-id", required=True, help="文档 ID（= tests/annotations/ 下的目录名）")
    ap.add_argument("--out", type=Path, help="输出 gt.json 路径（缺省打印到 stdout）")
    ap.add_argument("--dpi", type=float, default=DEFAULT_DPI,
                    help=f"渲染 DPI（默认 {DEFAULT_DPI:g}，与 01_extract_layout.py 的 Matrix(1.5,1.5) 一致）")
    ap.add_argument("--annotator", default="", help="标注人")
    ap.add_argument("--annotated-at", default="", help="标注时间（ISO 格式）")
    args = ap.parse_args(argv)

    for p in args.labelme_json:
        if not p.exists():
            print(f"错误：文件不存在 {p}", file=sys.stderr)
            return 2

    gt = convert(args.labelme_json, args.document_id, args.dpi, args.annotator, args.annotated_at)
    text = json.dumps(gt, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"已写出 {args.out}（{len(gt['assets'])} 条资产，"
              f"{len(gt['false_captions'])} 条 false_caption）", file=sys.stderr)
    else:
        print(text)
    if gt["conversion_warnings"]:
        for w in gt["conversion_warnings"]:
            print(f"警告：{w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
