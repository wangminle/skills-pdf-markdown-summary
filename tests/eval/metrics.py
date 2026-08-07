# -*- coding: utf-8 -*-
"""metrics.py — 方案 §2.6 六项指标的计算。

口径以 docs/PDF图表提取技术迭代实施方案-20260731.md §2 为准：

1. 数量对齐率：导出资产数与真实 Figure/Table 数的对齐（漏检/多检分别统计）。
   「有条目但无框」按 §2.2 计入漏检。
2. 截断率：§2.5 判定层——GT 标注的每个构成元素是否被预测框（多框并集）
   完整包含，≤1pt 浮点容差，二值。GT 未提供 elements 的条目不参与判定。
3. 配对正确率：全页一对一约束下，GT 配对到正确预测（kind+ident+页码
   一致）的比例。
4. 过量混正文率：框内非资产正文行 >1 行的资产占比（§2.3 第 4 类硬失败）。
   需要页面文本行，由调用方注入 lines_provider(document_id, page)。
   「非资产正文行」= 行中心落在预测框内、且与所有 GT 构成元素框
   （无 elements 时退化为 content_bboxes）均无交叠的文本行；
   行需有一半以上高度落入框内才算「框内」。
5. content coverage：GT 与预测交集 / GT 面积（多 bbox 取并集）。
   阈值 0.995 仅作筛查（§2.5 筛查层），不作合格判据。
6. crop purity：GT 与预测交集 / 预测面积。不设阈值，仅观察趋势。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

try:  # 支持包导入与 `python tests/eval/run_eval.py` 直接运行
    from .keys import (
        CONTAIN_TOL_PT,
        BBox,
        intersection_area,
        match_one_to_one,
        union_area,
    )
except ImportError:  # pragma: no cover
    from keys import (  # type: ignore
        CONTAIN_TOL_PT,
        BBox,
        intersection_area,
        match_one_to_one,
        union_area,
    )

COVERAGE_SCREEN_THRESHOLD = 0.995  # §2.5 筛查层阈值

LinesProvider = Callable[[str, int], List[BBox]]


def _is_truncated(gt: Dict[str, Any], pred_boxes: List[BBox]) -> Optional[bool]:
    """§2.5 判定层：任一构成元素不被预测并集完整包含（≤1pt 容差）即截断。

    GT 未标注 elements 时返回 None（不参与截断率统计）。
    「被并集包含」= 存在某个预测框单独包含该元素（元素不可分割到多框）。
    """
    elements = gt.get("elements") or []
    if not elements:
        return None
    for el in elements:
        eb = el["bbox"]
        if not any(pb.contains(eb, tol=CONTAIN_TOL_PT) for pb in pred_boxes):
            return True
    return False


def _count_body_lines(
    pred_boxes: List[BBox],
    asset_region: List[BBox],
    lines: List[BBox],
) -> int:
    """框内非资产正文行计数（见模块 docstring 第 4 条）。"""
    n = 0
    for ln in lines:
        h = ln.y1 - ln.y0
        if h <= 0:
            continue
        inside = False
        for pb in pred_boxes:
            inter = pb.intersect(ln)
            if inter is not None and (inter.y1 - inter.y0) >= 0.5 * h:
                inside = True
                break
        if not inside:
            continue
        if any(ar.intersect(ln) is not None for ar in asset_region):
            continue
        n += 1
    return n


def evaluate_document(
    gt_assets: List[Dict[str, Any]],
    preds: List[Dict[str, Any]],
    lines_provider: Optional[LinesProvider] = None,
) -> Dict[str, Any]:
    """对单个文档计算六项指标与逐条明细。"""
    m = match_one_to_one(gt_assets, preds)
    matches: Dict[str, int] = m["matches"]

    rows: List[Dict[str, Any]] = []
    for gt in gt_assets:
        pi = matches.get(gt["key"])
        pred = preds[pi] if pi is not None else None
        row: Dict[str, Any] = {
            "gt_key": gt["key"],
            "kind": gt["kind"],
            "ident": gt["ident"],
            "caption_page": gt["caption_page"],
            "ambiguous": gt.get("ambiguous", False),
            "matched": pred is not None,
        }
        if pred is None:
            row["truncated"] = None
            row["coverage"] = None
            row["purity"] = None
            row["body_lines_in_box"] = None
            row["excess_body"] = None
        else:
            row["pred_key"] = pred["key"]
            pb = pred["content_bboxes"]
            gb = gt["content_bboxes"]
            gt_area = union_area(gb)
            pred_area = union_area(pb)
            inter = intersection_area(gb, pb)
            row["coverage"] = round(inter / gt_area, 4) if gt_area > 0 else None
            row["purity"] = round(inter / pred_area, 4) if pred_area > 0 else None
            row["truncated"] = _is_truncated(gt, pb)
            # 同 kind+ident+页码才算配对正确（tier 0）
            row["pair_correct"] = (
                pred["ident"] == gt["ident"] and pred["occurrence"] == gt["occurrence"]
            )
            if lines_provider is not None:
                lines = lines_provider(gt["document_id"], gt["caption_page"])
                asset_region = [el["bbox"] for el in gt.get("elements") or []] or gb
                n_lines = _count_body_lines(pb, asset_region, lines)
                row["body_lines_in_box"] = n_lines
                row["excess_body"] = n_lines > 1
            else:
                row["body_lines_in_box"] = None
                row["excess_body"] = None
        rows.append(row)

    # —— 汇总 ——
    n_gt = len(gt_assets)
    n_pred = len(preds)
    n_pred_exported = sum(1 for p in preds if p["has_bbox"])
    matched_rows = [r for r in rows if r["matched"]]
    n_matched = len(matched_rows)
    # 漏检：GT 无配对 + 配对到「有条目无框」之外的缺失；
    # 「有条目但无框」的预测按 §2.2 计入漏检风险（它们不可能被一对一配对，
    # 因为无框不可配对，其对应 GT 落入 unmatched）。
    n_missing = n_gt - n_matched
    n_extra = n_pred - n_matched  # 多检：未配对到任何 GT 的预测

    judged_trunc = [r for r in matched_rows if r["truncated"] is not None]
    n_truncated = sum(1 for r in judged_trunc if r["truncated"])
    pair_correct = sum(1 for r in matched_rows if r.get("pair_correct"))
    judged_body = [r for r in matched_rows if r["excess_body"] is not None]
    n_excess_body = sum(1 for r in judged_body if r["excess_body"])
    coverages = [r["coverage"] for r in matched_rows if r["coverage"] is not None]
    purities = [r["purity"] for r in matched_rows if r["purity"] is not None]

    metrics = {
        "count_alignment": {
            "n_gt": n_gt,
            "n_pred": n_pred,
            "n_pred_exported": n_pred_exported,
            "n_matched": n_matched,
            "n_missing": n_missing,
            "n_extra": n_extra,
            "alignment_rate": round(n_matched / n_gt, 4) if n_gt else None,
        },
        "truncation": {
            "n_judged": len(judged_trunc),
            "n_truncated": n_truncated,
            "truncation_rate": (
                round(n_truncated / len(judged_trunc), 4) if judged_trunc else None
            ),
        },
        "pairing": {
            "n_gt": n_gt,
            "n_pair_correct": pair_correct,
            "pairing_accuracy": round(pair_correct / n_gt, 4) if n_gt else None,
            "one_to_one": True,
        },
        "excess_body_text": {
            "n_judged": len(judged_body),
            "n_excess": n_excess_body,
            "excess_body_rate": (
                round(n_excess_body / len(judged_body), 4) if judged_body else None
            ),
            "note": None
            if lines_provider is not None
            else "未提供页面文本行（--pdf-root），本指标未计算",
        },
        "content_coverage": {
            "n": len(coverages),
            "mean": round(sum(coverages) / len(coverages), 4) if coverages else None,
            "pct_ge_0.995": (
                round(
                    sum(1 for c in coverages if c >= COVERAGE_SCREEN_THRESHOLD)
                    / len(coverages),
                    4,
                )
                if coverages
                else None
            ),
            "role": "screening_only",
        },
        "crop_purity": {
            "n": len(purities),
            "mean": round(sum(purities) / len(purities), 4) if purities else None,
            "role": "observe_only_no_threshold",
        },
        "duplicate_occupancy": m["duplicate_occupancy"],
        "cross_page_mismatch": m["cross_page_mismatch"],
    }
    return {"metrics": metrics, "rows": rows}


def aggregate(per_doc: List[Dict[str, Any]]) -> Dict[str, Any]:
    """跨文档汇总（对各计数简单求和后重算比例）。"""
    docs = [d["metrics"] for d in per_doc]
    rows = [r for d in per_doc for r in d["rows"]]

    def s(path: str) -> int:
        return sum(_dig(m, path) or 0 for m in docs)

    n_gt = s("count_alignment.n_gt")
    n_matched = s("count_alignment.n_matched")
    n_jt = s("truncation.n_judged")
    n_tr = s("truncation.n_truncated")
    n_pc = s("pairing.n_pair_correct")
    n_jb = s("excess_body_text.n_judged")
    n_eb = s("excess_body_text.n_excess")
    coverages = [r["coverage"] for r in rows if r.get("coverage") is not None]
    purities = [r["purity"] for r in rows if r.get("purity") is not None]
    return {
        "count_alignment": {
            "n_gt": n_gt,
            "n_pred": s("count_alignment.n_pred"),
            "n_pred_exported": s("count_alignment.n_pred_exported"),
            "n_matched": n_matched,
            "n_missing": s("count_alignment.n_missing"),
            "n_extra": s("count_alignment.n_extra"),
            "alignment_rate": round(n_matched / n_gt, 4) if n_gt else None,
        },
        "truncation": {
            "n_judged": n_jt,
            "n_truncated": n_tr,
            "truncation_rate": round(n_tr / n_jt, 4) if n_jt else None,
        },
        "pairing": {
            "n_gt": n_gt,
            "n_pair_correct": n_pc,
            "pairing_accuracy": round(n_pc / n_gt, 4) if n_gt else None,
            "one_to_one": True,
        },
        "excess_body_text": {
            "n_judged": n_jb,
            "n_excess": n_eb,
            "excess_body_rate": round(n_eb / n_jb, 4) if n_jb else None,
        },
        "content_coverage": {
            "n": len(coverages),
            "mean": round(sum(coverages) / len(coverages), 4) if coverages else None,
            "pct_ge_0.995": (
                round(
                    sum(1 for c in coverages if c >= COVERAGE_SCREEN_THRESHOLD)
                    / len(coverages),
                    4,
                )
                if coverages
                else None
            ),
            "role": "screening_only",
        },
        "crop_purity": {
            "n": len(purities),
            "mean": round(sum(purities) / len(purities), 4) if purities else None,
            "role": "observe_only_no_threshold",
        },
        "duplicate_occupancy": {
            "n_groups": s("duplicate_occupancy.n_groups"),
            "n_assets_involved": s("duplicate_occupancy.n_assets_involved"),
            "details": [
                d
                for m in docs
                for d in (m["duplicate_occupancy"]["details"] or [])
            ],
        },
        "cross_page_mismatch": [
            x for m in docs for x in (m["cross_page_mismatch"] or [])
        ],
    }


def _dig(d: Dict[str, Any], path: str) -> Any:
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur
