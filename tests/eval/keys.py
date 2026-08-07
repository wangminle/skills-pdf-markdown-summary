# -*- coding: utf-8 -*-
"""keys.py — 资产键、BBox 几何、一对一配对（A0-3 口径修正核心）。

相对实验脚本（docs/3-experiments/.../scripts/03_build_gt_and_eval.py）
的三处修正：

1. 资产键 = document_id + kind + ident + caption_page + occurrence + group_id。
   原实验 asset_key 只用 (type, ident, page)，pairwise_agreement 甚至只用
   (pdf, type, ident) 忽略页码，造成虚假跨页分歧（如 Gemini Table 11 p12
   被映射到 p63）。
2. 预测匹配强制校验页码：caption_page 不一致的预测不允许配对，
   只记入 cross_page_mismatch 诊断。
3. 配对为全页一对一：一个预测框最多分配给一条 GT；同时输出
   「候选重复占用统计」——若取消一对一约束，同一预测框会被多少条 GT
   同时认领（A2 归零目标的对照基线：8 组 / 16 条资产）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# 截断判定的浮点容差（方案 §2.5：≤1pt）
CONTAIN_TOL_PT = 1.0


@dataclass
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    @classmethod
    def from_any(cls, values: Any) -> "BBox":
        x0, y0, x1, y1 = values
        return cls(float(x0), float(y0), float(x1), float(y1))

    def as_list(self) -> List[float]:
        return [round(self.x0, 2), round(self.y0, 2), round(self.x1, 2), round(self.y1, 2)]

    @property
    def area(self) -> float:
        return max(0.0, self.x1 - self.x0) * max(0.0, self.y1 - self.y0)

    def center(self) -> Tuple[float, float]:
        return ((self.x0 + self.x1) / 2.0, (self.y0 + self.y1) / 2.0)

    def intersect(self, other: "BBox") -> Optional["BBox"]:
        ix0, iy0 = max(self.x0, other.x0), max(self.y0, other.y0)
        ix1, iy1 = min(self.x1, other.x1), min(self.y1, other.y1)
        if ix1 <= ix0 or iy1 <= iy0:
            return None
        return BBox(ix0, iy0, ix1, iy1)

    def contains(self, other: "BBox", tol: float = CONTAIN_TOL_PT) -> bool:
        """other 是否被本框完整包含（容差 tol，默认 1pt，方案 §2.5）。"""
        return (
            other.x0 >= self.x0 - tol
            and other.y0 >= self.y0 - tol
            and other.x1 <= self.x1 + tol
            and other.y1 <= self.y1 + tol
        )


def union_area(boxes: List[BBox]) -> float:
    """矩形列表的并集面积（x 轴扫描线，精确）。"""
    if not boxes:
        return 0.0
    xs = sorted({c for b in boxes for c in (b.x0, b.x1)})
    total = 0.0
    for i in range(len(xs) - 1):
        x0, x1 = xs[i], xs[i + 1]
        if x1 <= x0:
            continue
        ys = sorted(
            (b.y0, b.y1) for b in boxes if b.x0 < x1 and b.x1 > x0
        )
        y_cur, y_end = None, None
        for y0, y1 in ys:
            if y_cur is None:
                y_cur, y_end = y0, y1
            elif y0 <= y_end:
                y_end = max(y_end, y1)
            else:
                total += (x1 - x0) * (y_end - y_cur)
                y_cur, y_end = y0, y1
        if y_cur is not None:
            total += (x1 - x0) * (y_end - y_cur)
    return total


def intersection_area(a_boxes: List[BBox], b_boxes: List[BBox]) -> float:
    """union(A) ∩ union(B) 的面积 = 两两交集矩形的并集面积。"""
    inters = []
    for a in a_boxes:
        for b in b_boxes:
            r = a.intersect(b)
            if r is not None:
                inters.append(r)
    return union_area(inters)


def asset_key(
    document_id: str,
    kind: str,
    ident: str,
    caption_page: int,
    occurrence: int = 1,
    group_id: str = "",
) -> str:
    """A0-3 修正后的资产键（缺陷①修复）。"""
    return (
        f"{document_id}|{kind}|{ident}|p{int(caption_page)}"
        f"|o{int(occurrence)}|g{group_id or '-'}"
    )


def normalize_gt_asset(document_id: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    """把 tests/annotations/<doc>/gt.json 的单条记录规范化。"""
    kind = raw.get("kind") or raw.get("type")
    ident = str(raw.get("ident"))
    page = int(raw.get("caption_page") or raw.get("page"))
    occurrence = int(raw.get("occurrence") or 1)
    group_id = str(raw.get("group_id") or "")
    content = [BBox.from_any(b) for b in (raw.get("content_bboxes") or [])]
    elements = []
    for el in raw.get("elements") or []:
        bb = el.get("bbox") if isinstance(el, dict) else el
        if bb:
            elements.append(
                {
                    "name": el.get("name", "element") if isinstance(el, dict) else "element",
                    "bbox": BBox.from_any(bb),
                }
            )
    return {
        "key": asset_key(document_id, kind, ident, page, occurrence, group_id),
        "document_id": document_id,
        "kind": kind,
        "ident": ident,
        "caption_page": page,
        "occurrence": occurrence,
        "group_id": group_id,
        "caption_bbox": BBox.from_any(raw["caption_bbox"]) if raw.get("caption_bbox") else None,
        "content_bboxes": content,
        "elements": elements,
        "ambiguous": bool(raw.get("ambiguous")),
        "raw": raw,
    }


def normalize_prediction(document_id: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    """把预测（legacy predictions.json 或正式 index.json）的单条规范化。

    字段映射（兼容两种格式）：
      kind  = kind 或 type
      ident = ident 或 id（正式 index.json 用 id；缺失时为 ""，不会是 "None"）
      page  = caption_page 或 page
      bbox  = content_bboxes；缺失时回退 [final_bbox]，再回退 [content_bbox]
    has_bbox=False 表示「有条目但无图片/无框」，按方案 §2.2 计入漏检。
    """
    kind = raw.get("kind") or raw.get("type")
    ident = str(raw.get("ident") or raw.get("id") or "")
    page = int(raw.get("caption_page") or raw.get("page") or 0)
    occurrence = int(raw.get("occurrence") or 1)
    group_id = str(raw.get("group_id") or "")
    boxes_raw = raw.get("content_bboxes") or []
    if not boxes_raw:
        single = raw.get("final_bbox") or raw.get("content_bbox")
        boxes_raw = [single] if single else []
    content = [BBox.from_any(b) for b in boxes_raw if b]
    return {
        "key": asset_key(document_id, kind, ident, page, occurrence, group_id),
        "document_id": document_id,
        "kind": kind,
        "ident": ident,
        "caption_page": page,
        "occurrence": occurrence,
        "group_id": group_id,
        "content_bboxes": content,
        "has_bbox": bool(content),
        "raw": raw,
    }


def _candidate_score(gt: Dict[str, Any], pred: Dict[str, Any]) -> Optional[Tuple[int, float]]:
    """候选配对打分；不允许的配对返回 None。

    tier 0：kind+ident+occurrence 相同且页码一致（缺陷②：页码强制校验）。
    tier 1：同 kind 同页、ident 不同的兜底（按 IoU 排序，供配对器选择）。
    页码不同的预测一律不可配对（跨页 continued 由 group_id 机制处理，
    不允许单条 GT 配到异页预测）。
    """
    if gt["kind"] != pred["kind"]:
        return None
    if not pred["has_bbox"]:
        return None
    if gt["caption_page"] != pred["caption_page"]:
        return None
    gt_boxes = gt["content_bboxes"]
    pred_boxes = pred["content_bboxes"]
    inter = intersection_area(gt_boxes, pred_boxes)
    union = union_area(gt_boxes) + union_area(pred_boxes) - inter
    iou = inter / union if union > 0 else 0.0
    same_id = gt["ident"] == pred["ident"] and gt["occurrence"] == pred["occurrence"]
    tier = 0 if same_id else 1
    return (tier, -iou)


def match_one_to_one(
    gt_assets: List[Dict[str, Any]],
    preds: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """全页一对一贪心配对（缺陷③修复）+ 候选重复占用统计。

    返回：
      matches: {gt_key: pred_index}
      unmatched_gt / unmatched_pred: 索引列表
      duplicate_occupancy: 取消一对一约束时会被多条 GT 同时认领的
        预测框统计（n_groups / n_assets_involved / details）。
      cross_page_mismatch: kind+ident 相同但页码不同的 (gt, pred) 诊断。
    """
    pairs = []
    for gi, gt in enumerate(gt_assets):
        for pi, pred in enumerate(preds):
            s = _candidate_score(gt, pred)
            if s is not None:
                pairs.append((s, gi, pi))
    pairs.sort(key=lambda x: (x[0][0], x[0][1]))

    used_gt, used_pred = set(), set()
    matches: Dict[str, int] = {}
    for s, gi, pi in pairs:
        if gi in used_gt or pi in used_pred:
            continue
        used_gt.add(gi)
        used_pred.add(pi)
        matches[gt_assets[gi]["key"]] = pi

    # —— 候选重复占用统计（一对一约束取消时的反事实） ——
    # 对每条 GT 求「若无约束它会认领的最佳 pred」，统计被 ≥2 条 GT 认领的框。
    best_claim: Dict[str, Optional[int]] = {}
    for gi, gt in enumerate(gt_assets):
        best_pi, best_s = None, None
        for pi, pred in enumerate(preds):
            s = _candidate_score(gt, pred)
            if s is None:
                continue
            if best_s is None or s < best_s:
                best_s, best_pi = s, pi
        best_claim[gt["key"]] = best_pi
    claims: Dict[int, List[str]] = {}
    for gt_key, pi in best_claim.items():
        if pi is not None:
            claims.setdefault(pi, []).append(gt_key)
    dup_details = [
        {
            "pred_key": preds[pi]["key"],
            "n_gt_claims": len(gt_keys),
            "gt_keys": sorted(gt_keys),
        }
        for pi, gt_keys in sorted(claims.items())
        if len(gt_keys) > 1
    ]
    duplicate_occupancy = {
        "n_groups": len(dup_details),
        "n_assets_involved": sum(d["n_gt_claims"] for d in dup_details),
        "details": dup_details,
    }

    # —— 跨页错配诊断（kind+ident 相同、页码不同） ——
    cross_page = []
    for gt in gt_assets:
        for pred in preds:
            if (
                gt["kind"] == pred["kind"]
                and gt["ident"] == pred["ident"]
                and gt["caption_page"] != pred["caption_page"]
            ):
                cross_page.append(
                    {
                        "gt_key": gt["key"],
                        "pred_key": pred["key"],
                        "gt_page": gt["caption_page"],
                        "pred_page": pred["caption_page"],
                    }
                )

    return {
        "matches": matches,
        "unmatched_gt": [i for i in range(len(gt_assets)) if i not in used_gt],
        "unmatched_pred": [i for i in range(len(preds)) if i not in used_pred],
        "duplicate_occupancy": duplicate_occupancy,
        "cross_page_mismatch": cross_page,
    }
