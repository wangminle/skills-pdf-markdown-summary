#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_eval.py — 版本化评测器 CLI 入口（A0-3）。

输入：
  --gt-dir     GT 目录（tests/annotations/），结构为 <document_id>/gt.json
  --pred-root  预测根目录。支持两种布局（predictions.json 优先）：
               实验 legacy 的 <document_id>/predictions.json，
               正式提取产物的 <document_id>/images/index.json（{"items": [...]}）。
  --pdf-root   可选。PDF 根目录（如 tests/basic-benchmark），用于计算
               「过量混正文率」（需要页面文本行）。不提供则该指标跳过。
  --out        可选。完整结果（含逐条明细）写出路径。
  --selfcheck  运行 selfcheck.py 自检后退出。

输出：stdout 打印六项指标 JSON + 候选重复占用统计。
GT 为空是正常状态（标注尚未开始）：打印友好提示并以 0 退出。

用法示例：
  python tests/eval/run_eval.py \
      --gt-dir tests/annotations \
      --pred-root docs/3-experiments/20260728-pymupdf4llm-layout-bbox/legacy \
      --pdf-root tests/basic-benchmark
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from keys import BBox, normalize_gt_asset, normalize_prediction  # noqa: E402
from metrics import aggregate, evaluate_document  # noqa: E402


def find_gt_files(gt_dir: Path) -> Dict[str, Path]:
    """{document_id: gt.json 路径}。"""
    out = {}
    if not gt_dir.exists():
        return out
    for p in sorted(gt_dir.glob("*/gt.json")):
        out[p.parent.name] = p
    return out


def _doc_key(dirname: str) -> str:
    """目录名 → document_id（空格转下划线，与 GT/pdf_stem 约定一致）。"""
    return dirname.replace(" ", "_")


def find_pred_files(pred_root: Path) -> Dict[str, Path]:
    """{document_id: 预测文件路径}。

    支持两种产物布局（predictions.json 优先）：
      - 实验 legacy：`<document_id>/predictions.json`
      - 正式提取产物：`<document_id>/images/index.json`（递归匹配）
    根目录本身是一个 JSON 文件时也直接接受。
    """
    out: Dict[str, Path] = {}
    if pred_root.is_file():
        out[_doc_key(pred_root.parent.name)] = pred_root
        return out
    for p in sorted(pred_root.glob("*/predictions.json")):
        out[_doc_key(p.parent.name)] = p
    for p in sorted(pred_root.glob("**/images/index.json")):
        out.setdefault(_doc_key(p.parent.parent.name), p)
    return out


def load_gt(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    doc_id = data.get("document_id") or path.parent.name
    return [normalize_gt_asset(doc_id, a) for a in data.get("assets") or []]


def load_preds(path: Path, doc_id: str) -> List[Dict[str, Any]]:
    """加载预测文件。兼容三种顶层键：正式 index.json 的 `items`、
    实验 legacy 的 `predictions`、以及 `attachments`；顶层为数组也接受。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        items = data.get("items") or data.get("predictions") or data.get("attachments") or []
    else:
        items = data
    return [normalize_prediction(doc_id, p) for p in items]


def make_lines_provider(pdf_root: Path) -> "callable":
    """打开 PDF 取文本行（PyMuPDF line 粒度）。按文档缓存。"""
    import fitz  # PyMuPDF，仅在使用 --pdf-root 时需要

    pdf_map = {p.stem.replace(" ", "_"): p for p in pdf_root.rglob("*.pdf")}
    cache: Dict[str, Any] = {}

    def provider(document_id: str, page: int) -> List[BBox]:
        if document_id not in cache:
            pdf_path = pdf_map.get(document_id)
            cache[document_id] = fitz.open(pdf_path) if pdf_path else None
        doc = cache[document_id]
        if doc is None or page < 1 or page > len(doc):
            return []
        d = doc[page - 1].get_text("dict")
        lines = []
        for block in d.get("blocks") or []:
            if block.get("type") != 0:
                continue
            for line in block.get("lines") or []:
                text = "".join(s.get("text", "") for s in line.get("spans") or []).strip()
                if text and line.get("bbox"):
                    lines.append(BBox.from_any(line["bbox"]))
        return lines

    return provider


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="版本化评测器：六项指标（方案 §2.6）+ 候选重复占用统计"
    )
    ap.add_argument("--gt-dir", type=Path, help="GT 根目录（<document_id>/gt.json）")
    ap.add_argument(
        "--pred-root",
        type=Path,
        help="预测根目录（<doc>/predictions.json 或 <doc>/images/index.json），或单个预测文件",
    )
    ap.add_argument("--pdf-root", type=Path, default=None, help="PDF 根目录（可选，用于混正文指标）")
    ap.add_argument("--out", type=Path, default=None, help="完整结果 JSON 写出路径（可选）")
    ap.add_argument("--selfcheck", action="store_true", help="运行自检后退出")
    args = ap.parse_args(argv)

    if args.selfcheck:
        import selfcheck

        return selfcheck.main()

    if not args.gt_dir or not args.pred_root:
        ap.error("--gt-dir 与 --pred-root 均为必填（--selfcheck 除外）")

    gt_files = find_gt_files(args.gt_dir)
    if not gt_files:
        print(
            json.dumps(
                {
                    "status": "no_gt",
                    "message": (
                        f"在 {args.gt_dir} 下未找到任何 <document_id>/gt.json。"
                        "人工标注尚未开始是正常状态；请先完成 A0-4 标注，"
                        "或参考 tests/annotations/SCHEMA-20260731.md。"
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    pred_files = find_pred_files(args.pred_root)
    lines_provider = make_lines_provider(args.pdf_root) if args.pdf_root else None

    per_doc = []
    missing_pred = []
    for doc_id, gt_path in sorted(gt_files.items()):
        gt_assets = load_gt(gt_path)
        pred_path = pred_files.get(doc_id)
        if pred_path is None:
            missing_pred.append(doc_id)
            preds: List[Dict[str, Any]] = []
        else:
            preds = load_preds(pred_path, doc_id)
        result = evaluate_document(gt_assets, preds, lines_provider)
        result["document_id"] = doc_id
        result["gt_path"] = str(gt_path)
        result["pred_path"] = str(pred_path) if pred_path else None
        per_doc.append(result)

    overall = aggregate(per_doc)
    preds_without_gt = sorted(set(pred_files) - set(gt_files))
    summary = {
        "status": "ok",
        "n_documents": len(per_doc),
        "documents_without_predictions": missing_pred,
        "predictions_without_gt": preds_without_gt,
        "metrics": overall,
    }
    if preds_without_gt:
        print(
            f"提示：{len(preds_without_gt)} 份预测无对应 GT（{', '.join(preds_without_gt[:5])}"
            f"{'…' if len(preds_without_gt) > 5 else ''}），已跳过——标注未完成是正常状态。",
            file=sys.stderr,
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps({"summary": summary, "per_document": per_doc}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"完整结果已写出: {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
