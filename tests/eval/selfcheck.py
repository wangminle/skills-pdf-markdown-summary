#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py — 评测器自检（非 pytest 套件，手动或由 run_eval --selfcheck 调用）。

覆盖 A0-3 三处口径修正、六项指标的基本行为，以及两处防回退用例：
  1. 资产键含页码/occurrence/group_id；
  2. 跨页预测不可配对（缺陷②），计入 cross_page_mismatch；
  3. 一对一约束：一个预测框最多配一次，且输出重复占用统计（缺陷③）；
  4. 截断判定：≤1pt 容差、元素必须被单框完整包含；
  5. coverage/purity 的多框并集计算；
  6. 混正文行计数（>1 行判过量）；
  7. 正式 index.json 兼容：items 键、id→ident、final_bbox 回退、
     find_pred_files 双布局与目录名空格归一化（Critical #1 防回退）；
  8. LabelMe 跨页拆分：多记录、occurrence 递增、同 group_id、本页坐标，
     同页多 panel 仍合并（Critical #2 防回退）。

运行：python tests/eval/selfcheck.py   或   python tests/eval/run_eval.py --selfcheck
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from keys import (  # noqa: E402
    BBox,
    asset_key,
    intersection_area,
    match_one_to_one,
    normalize_prediction,
    union_area,
)
from metrics import _count_body_lines, _is_truncated, evaluate_document  # noqa: E402

_FAILURES = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        _FAILURES.append(name)


def main() -> int:
    # 1) 资产键
    k = asset_key("doc1", "table", "11", 12, 1, "t11")
    check("asset_key 含全部组分", k == "doc1|table|11|p12|o1|gt11", k)
    check(
        "页码不同则键不同（Gemini Table 11 p12≠p63）",
        asset_key("d", "table", "11", 12) != asset_key("d", "table", "11", 63),
    )

    # 2) 一对一配对 + 页码校验
    gt = [
        {"key": asset_key("d", "figure", "1", 3), "document_id": "d", "kind": "figure",
         "ident": "1", "caption_page": 3, "occurrence": 1, "group_id": "",
         "content_bboxes": [BBox(100, 100, 200, 200)], "elements": []},
        {"key": asset_key("d", "figure", "2", 3), "document_id": "d", "kind": "figure",
         "ident": "2", "caption_page": 3, "occurrence": 1, "group_id": "",
         "content_bboxes": [BBox(110, 110, 210, 210)], "elements": []},
    ]
    preds = [
        # 一个框同时接近两条 GT —— 无约束时会被重复认领
        {"key": asset_key("d", "figure", "1", 3), "document_id": "d", "kind": "figure",
         "ident": "1", "caption_page": 3, "occurrence": 1, "group_id": "",
         "content_bboxes": [BBox(105, 105, 205, 205)], "has_bbox": True},
        # 跨页预测：ident 相同但页码不同，不允许配对
        {"key": asset_key("d", "figure", "2", 5), "document_id": "d", "kind": "figure",
         "ident": "2", "caption_page": 5, "occurrence": 1, "group_id": "",
         "content_bboxes": [BBox(110, 110, 210, 210)], "has_bbox": True},
    ]
    m = match_one_to_one(gt, preds)
    check("一对一：两条 GT 不能配同一框", len(m["matches"]) == 1, str(m["matches"]))
    check(
        "重复占用统计检出 1 组 / 2 条资产",
        m["duplicate_occupancy"]["n_groups"] == 1
        and m["duplicate_occupancy"]["n_assets_involved"] == 2,
        str(m["duplicate_occupancy"]),
    )
    check("跨页预测不可配对", preds[1]["key"] not in m["matches"].values() and
          all(v != 1 for v in m["matches"].values()))
    check("跨页错配诊断有记录", len(m["cross_page_mismatch"]) == 1,
          str(m["cross_page_mismatch"]))

    # 3) 截断判定
    pred_box = [BBox(0, 0, 100, 100)]
    inside = {"content_bboxes": pred_box,
              "elements": [{"name": "body", "bbox": BBox(10, 10, 90, 90)}]}
    check("元素完整包含 → 不截断", _is_truncated(inside, pred_box) is False)
    tol_case = {"content_bboxes": pred_box,
                "elements": [{"name": "body", "bbox": BBox(-0.5, 0, 100.5, 100)}]}
    check("超出 ≤1pt 容差内 → 不截断", _is_truncated(tol_case, pred_box) is False)
    cut = {"content_bboxes": pred_box,
           "elements": [{"name": "footnote", "bbox": BBox(10, 95, 90, 105)}]}
    check("footnote 被切 5pt → 截断", _is_truncated(cut, pred_box) is True)
    no_el = {"content_bboxes": pred_box, "elements": []}
    check("无 elements → 不参与判定 (None)", _is_truncated(no_el, pred_box) is None)

    # 4) 多框并集 coverage/purity
    a = [BBox(0, 0, 10, 10), BBox(5, 5, 15, 15)]  # 并集 175
    check("union_area 重叠去重", abs(union_area(a) - 175.0) < 1e-6, str(union_area(a)))
    b = [BBox(5, 5, 20, 20)]
    # a2 完全含于 b（100），a1∩b=(5,5,10,10)=25 含于 a2∩b，故并集为 100
    check("intersection_area = 100", abs(intersection_area(a, b) - 100.0) < 1e-6)

    # 5) 混正文行计数
    pred = [BBox(0, 0, 200, 200)]
    asset = [BBox(50, 50, 150, 150)]
    lines = [
        BBox(60, 60, 140, 70),    # 资产内
        BBox(10, 10, 190, 20),    # 非资产 1
        BBox(10, 180, 190, 190),  # 非资产 2
        BBox(10, 300, 190, 310),  # 框外
    ]
    check("非资产正文行计数 = 2", _count_body_lines(pred, asset, lines) == 2)

    # 6) evaluate_document 端到端（合成）
    gt_assets = [{
        "key": asset_key("d", "table", "1", 6), "document_id": "d", "kind": "table",
        "ident": "1", "caption_page": 6, "occurrence": 1, "group_id": "",
        "caption_bbox": BBox(100, 70, 500, 80),
        "content_bboxes": [BBox(120, 100, 480, 200)],
        "elements": [{"name": "body", "bbox": BBox(120, 100, 480, 200)}],
        "ambiguous": False,
    }]
    preds_ok = [{
        "key": asset_key("d", "table", "1", 6), "document_id": "d", "kind": "table",
        "ident": "1", "caption_page": 6, "occurrence": 1, "group_id": "",
        "content_bboxes": [BBox(100, 90, 500, 210)], "has_bbox": True,
    }]
    res = evaluate_document(gt_assets, preds_ok, lines_provider=lambda d, p: [])
    mt = res["metrics"]
    check("端到端：数量对齐率 1.0", mt["count_alignment"]["alignment_rate"] == 1.0)
    check("端到端：截断率 0", mt["truncation"]["truncation_rate"] == 0.0)
    check("端到端：配对正确率 1.0", mt["pairing"]["pairing_accuracy"] == 1.0)
    check("端到端：coverage 1.0", mt["content_coverage"]["mean"] == 1.0)
    check("端到端：purity < 1（框偏大）",
          0 < mt["crop_purity"]["mean"] < 1.0, str(mt["crop_purity"]))
    check("端到端：重复占用 0 组", mt["duplicate_occupancy"]["n_groups"] == 0)

    # 7) 正式 index.json 兼容（Critical #1 防回退）
    import json
    import tempfile

    from convert_labelme_to_gt import convert
    from run_eval import find_pred_files, load_preds

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # 正式产物布局：<doc>/images/index.json，{"items": [...]}，id 字段
        formal_dir = root / "DeepSeek_V3_2" / "images"
        formal_dir.mkdir(parents=True)
        (formal_dir / "index.json").write_text(
            json.dumps(
                {
                    "version": 2,
                    "items": [
                        {"id": "1", "type": "figure", "page": 2,
                         "final_bbox": [26.0, 0.0, 569.3, 313.7],
                         "content_bboxes": [[26.0, 0.0, 569.3, 313.7]],
                         "status": "accepted"},
                        {"id": "1", "type": "table", "page": 4,
                         "final_bbox": [71.6, 84.5, 523.8, 326.9]},
                    ],
                }
            ),
            encoding="utf-8",
        )
        # 实验 legacy 布局：<doc>/predictions.json
        legacy_dir = root / "1706.03762v7-attention_is_all_you_need"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "predictions.json").write_text(
            json.dumps({"predictions": [{"type": "figure", "ident": "1", "page": 3,
                                         "final_bbox": [26, 0, 586, 398.7]}]}),
            encoding="utf-8",
        )
        # 带空格的目录名应归一化为下划线 document_id
        space_dir = root / "Qwen3-Omni Technical Report" / "images"
        space_dir.mkdir(parents=True)
        (space_dir / "index.json").write_text(json.dumps({"items": []}), encoding="utf-8")

        found = find_pred_files(root)
        check("find_pred_files 同时发现两种布局", len(found) == 3, str(sorted(found)))
        check("带空格目录名归一化为下划线",
              "Qwen3-Omni_Technical_Report" in found, str(sorted(found)))

        preds = load_preds(found["DeepSeek_V3_2"], "DeepSeek_V3_2")
        check("load_preds 识别 items 键", len(preds) == 2, str(len(preds)))
        check("id 字段映射为 ident（不再是 'None'）",
              preds[0]["ident"] == "1" and preds[1]["ident"] == "1",
              str([p["ident"] for p in preds]))
        check("type 字段映射为 kind",
              preds[0]["kind"] == "figure" and preds[1]["kind"] == "table")
        check("content_bboxes 缺失时回退 [final_bbox]",
              preds[1]["has_bbox"]
              and preds[1]["content_bboxes"][0].as_list() == [71.6, 84.5, 523.8, 326.9],
              str(preds[1]["content_bboxes"]))
        # normalize_prediction 直接验证：只有 final_bbox 的正式 item
        p = normalize_prediction("d", {"id": "3", "type": "figure", "page": 5,
                                       "final_bbox": [1, 2, 3, 4]})
        check("normalize_prediction: 仅 final_bbox 也可出框",
              p["has_bbox"] and p["content_bboxes"][0].as_list() == [1.0, 2.0, 3.0, 4.0])

        # 8) LabelMe 跨页拆分为多条记录（Critical #2 防回退）
        lm1 = root / "page_0012.json"
        lm2 = root / "page_0013.json"
        lm1.write_text(json.dumps({"shapes": [
            {"label": "content:table:5", "points": [[150, 150], [750, 600]],
             "shape_type": "rectangle"},
            {"label": "caption:table:5", "points": [[150, 105], [750, 135]],
             "shape_type": "rectangle"},
        ]}), encoding="utf-8")
        lm2.write_text(json.dumps({"shapes": [
            {"label": "content:table:5", "points": [[150, 120], [750, 900]],
             "shape_type": "rectangle"},
        ]}), encoding="utf-8")
        gt = convert([lm1, lm2], "cross-page-doc")
        recs = gt["assets"]
        check("跨页：拆成两条记录", len(recs) == 2, str(len(recs)))
        if len(recs) == 2:
            check("跨页：occurrence 按页序 1/2",
                  recs[0]["occurrence"] == 1 and recs[1]["occurrence"] == 2,
                  str([r["occurrence"] for r in recs]))
            check("跨页：group_id 相同且为 g-table-5",
                  recs[0]["group_id"] == recs[1]["group_id"] == "g-table-5",
                  str([r["group_id"] for r in recs]))
            check("跨页：caption_page 各自页码",
                  recs[0]["caption_page"] == 12 and recs[1]["caption_page"] == 13)
            check("跨页：坐标只含本页框",
                  recs[0]["content_bboxes"] == [[100.0, 100.0, 500.0, 400.0]]
                  and recs[1]["content_bboxes"] == [[100.0, 80.0, 500.0, 600.0]],
                  str([r["content_bboxes"] for r in recs]))
            check("跨页：第二页复用首个 caption_bbox 并记 warning",
                  recs[1]["caption_bbox"] == [100.0, 70.0, 500.0, 90.0]
                  and any("caption" in w for w in gt["conversion_warnings"]),
                  str(gt["conversion_warnings"]))
        # 同页多 panel 仍合并为一条记录（规范③不回退）
        lm3 = root / "page_0004.json"
        lm3.write_text(json.dumps({"shapes": [
            {"label": "content:figure:2", "points": [[100, 100], [400, 300]],
             "shape_type": "rectangle"},
            {"label": "content:figure:2", "points": [[450, 100], [750, 300]],
             "shape_type": "rectangle"},
        ]}), encoding="utf-8")
        gt2 = convert([lm3], "multi-panel-doc")
        check("同页多 panel：合并为一条记录、两个 content_bboxes",
              len(gt2["assets"]) == 1
              and len(gt2["assets"][0]["content_bboxes"]) == 2
              and gt2["assets"][0]["group_id"] == "",
              json.dumps(gt2["assets"], ensure_ascii=False)[:200])

    print()
    if _FAILURES:
        print(f"自检失败 {len(_FAILURES)} 项: {_FAILURES}")
        return 1
    print("自检全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
