# 提取状态与题注对账设计 - 20260907

留白偏多可以接受；标题或正文段落被框进截图不可以。主链实际使用三态，schema 仍保留四态字段。

## 状态

- `accepted`：身份正确，框内没有标题/正文段落。额外留白不降级。
- `accepted_with_margin`：仅 Layout 精修链沿用；主链不因留白赋值。Markdown 与 `accepted` 同等插入。
- `review_required`：身份大致正确，但完整性不确定（对象截断、表带未收束、表头被切、重复 PNG、题注分过低、对账补裁）。
- `rejected`：身份错误（正文引用）或框内含标题/正文。

## 评估

`lib/assess.py` 只根据布尔信号定级，不用 `height_ratio` 代表完整性。

## 对账

显式题注、裸 `Figure N` / `Table N` 标签，且非正文引用，构成 expected；与 exported `(kind, ident, page)` 求 missing/unexpected。缺口补裁后写入索引，Markdown 不插入。正文引用落入 unexpected 时标为 rejected；显式/裸题注即使不在 expected 也不自动 reject。

## 2026-09-28 更新

- `review_required` 触发源新增**跨类型重叠**：figure/table 最终框互相压盖（交叠占较小框 ≥5%）时双方打 `cross_kind_overlap_with_*` 告警并降级 review_required，只打标不改几何；payload 新增 `cross_kind_overlaps` 列表。
- 对账范围与用户显式开关同口径：`--no-figures`/`--no-tables` 禁用的类型、`--min`/`--max-figure` 范围外的编号不参与「缺失」判定；非数字编号（S1 / 罗马数字 / 3a）不受范围限制，与提取主循环的 `int(ident)` 口径一致。
- `missing_count` / `unexpected_count` 与补裁后的最终对账结果同源（此前计数取自补裁前，出现 missing=[] 而 missing_count>0 的自相矛盾）。
- 补裁 PNG 文件名带页码（`<Kind>_<ident>_p<page>_inventory_gap_*.png`），跨页同编号同题注不再互相覆盖。
- Layout 精修链（A3）状态只降不升：legacy rejected 的记录即使几何精修可接受，也保持不可插入（`legacy_rejected_preserved`），不会被晋升回 Markdown 可插入状态。
