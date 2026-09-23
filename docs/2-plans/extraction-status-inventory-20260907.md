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
