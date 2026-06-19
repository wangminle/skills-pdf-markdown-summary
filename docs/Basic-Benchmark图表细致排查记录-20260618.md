# Basic Benchmark 图表细致排查记录

> 日期：2026-06-18
> 范围：`tests/basic-benchmark/` 中 7 个 PDF 的 Markdown 转换、图表提取与 `--debug-visual` 逐图排查。
> 输出批次：`tests/results/20260618-001/`

## 目标

本轮工作不是单纯追求某一个参数在所有 PDF 上立即通过，而是逐图检查 `debug-visual` 的阶段边界，记录每个策略的收益、风险和冲突点，便于后续在 7 个 PDF 之间权衡设计。

重点关注：

- `baseline` / 蓝线：caption 锚点生成的原始窗口是否安全。
- `phase_a` / 绿线：文本裁切后是否仍保留完整图表。
- `phase_b` / 黄线：对象边界对齐是否过度收缩。
- `final` / 红线：最终截图是否完整、是否混入正文、是否过窄或过宽。

## 当前批次概览

`tests/results/20260618-001/` 已对 7 个 PDF 完成完整 Markdown 转换和 `--debug-visual` 图表提取。

| PDF | 图 | 表 | debug 图 | 备注 |
| --- | ---: | ---: | ---: | --- |
| `1706.03762v7-attention_is_all_you_need` | 5 | 4 | 9 | 当前正在细致排查 |
| `2509.17765v1-Qwen3-Omni_Technical_Report` | 3 | 18 | 21 | 待复查 |
| `DeepSeek_V3_2` | 4 | 1 | 5 | 待复查 |
| `FunAudio-ASR` | 4 | 8 | 12 | 待复查 |
| `KearnsNevmyvakaHFTRiskBooks` | 8 | 1 | 9 | 待复查 |
| `gemini_v2_5_report` | 13 | 12 | 25 | 待复查 |
| `gpt-5-system-card` | 31 | 26 | 57 | 待复查 |

## 已检查项目

### Attention Figure 2：顶部图内标题被红线漏掉

文件：

`tests/results/20260618-001/1706.03762v7-attention_is_all_you_need/images/debug/Figure_2_p4_debug_stages.png`

现象：

- 原始红线没有包含图上方的 `Scaled Dot-Product Attention` 和 `Multi-Head Attention` 两个图内标题。
- caption 和 baseline 方向正确，问题发生在后处理阶段。

关键证据：

- 图内标题文本块：`y=71.2 -> 81.2`
- 修复前 final：`y0=87.2`，已在标题下方。
- 修复后 final：`y0=64.6`，覆盖标题。

根因：

`detect_far_side_text_evidence()` 与 `trim_far_side_text_post_autocrop()` 只按“远端、够宽、字号像正文、长度超过阈值”判断正文，把短图内标签误判成 far-side 正文，从而把 autocrop 后的红线向内推。

调整：

- 新增 `_looks_like_short_figure_label()`。
- far-side 正文检测跳过短、无句末标点、非编号章节标题的图内标签。

验证：

- 新增回归测试：`test_far_side_text_detection_ignores_short_figure_internal_title`。
- 先复现失败：维护测试 9 通过、1 失败。
- 修复后：维护测试 10 通过、0 失败。
- 重跑 Attention `--debug-visual` 后，Figure 2 红线已包含顶部图内标题。

风险与权衡：

- 保留编号章节标题过滤，避免把 `3.2.1 Scaled Dot-Product Attention` 这类正文结构误当图内标签。
- 这个修复只影响 far-side 正文证据，不改变 Phase B 对象对齐。

### Attention Figure 3：绿线完整，黄线和红线切掉下半部分

文件：

`tests/results/20260618-001/1706.03762v7-attention_is_all_you_need/images/debug/Figure_3_p13_debug_stages.png`

现象：

- 绿线 `phase_a` 基本完整，底部停在 caption 上方。
- 黄线 `phase_b` 把下半部分旋转文字、淡色 attention 标记和彩色块切掉。
- 红线继承黄线的 y 范围，只进一步收窄 x，因此同样切掉下半部分。

关键边界：

| 阶段 | 边界 | 判断 |
| --- | --- | --- |
| baseline | `26.0,90.7 -> 586.0,306.3` | 安全，接近完整图 |
| phase_a | `26.0,90.7 -> 586.0,306.3` | 安全，绿线合理 |
| phase_b | `26.0,90.7 -> 586.0,253.8` | y1 过早收缩 |
| final | `114.5,93.4 -> 509.8,253.9` | 继承 phase_b 截断 |
| caption | `108.0,312.3 -> 504.2,355.1` | phase_a 底边与 caption 之间仍有间隔 |

根因：

Phase B 的 `refine_clip_by_objects()` 使用单个对象面积阈值筛选候选对象：

- baseline/phase_a 内共有 620 个 vector 对象。
- 通过 `object_min_area_ratio=0.012` 的候选只有 17 个。
- 这 17 个候选合并成一个组件：`282.9,156.0 -> 434.9,245.8`。
- 加 `object_pad=8` 后得到黄线 y1：`245.8 + 8 = 253.8`。
- 被切掉的下半部分其实有 264 个小 vector 对象，最大 y 到 `302.06`，但单个面积比最大只有 `0.0060`，低于阈值，合并前就被过滤掉。

设计冲突：

- Phase B 对大图、图块和表格边框有帮助，可以去掉空白。
- 但 dense label / attention visualization 这类图由大量小对象、旋转文字和淡色标记组成，单对象面积阈值会把真实内容当噪声过滤。
- 如果直接全局降低 `object_min_area_ratio`，可能让普通图引入细碎噪声或正文残留。

修复方向：

当前采用更保守的局部规则，而不是全局改参数：

- 当 Phase B 对靠近 caption 的边界做大幅收缩时，检查被裁掉的 near-caption 区域是否存在大量小对象证据。
- 如果被裁掉区域里小对象数量多、横向覆盖宽、纵向跨度足够，并且延伸到接近原 phase_a 的 near edge，则判断为 dense label figure。
- 这种情况下不接受 Phase B 的 y 收缩，保留 phase_a 的 y 范围；后续仍允许 `refine_clip_x_range()` 收窄 x。

实际调整：

- 新增 `_has_small_object_band_near_trimmed_edge()`。
- 只在 `near_edge_only=True` 的 Phase B 收缩路径生效。
- 对 `direction='above'`，若 proposed y1 到 phase_a y1 之间存在大量小对象带，则回退 y1 到 phase_a y1。
- 对 `direction='below'` 做了对称保护，避免 caption 在上方时出现同类截断。
- 小对象带判定同时要求：裁掉高度足够、对象数量至少 8、横向覆盖至少 30% clip 宽度、纵向跨度足够，并且延伸到原 near edge 附近。
- 不降低 `object_min_area_ratio`，避免普通图表因全局阈值放宽而引入噪声。

验证：

- 新增回归测试：`test_object_refinement_preserves_near_edge_when_many_small_objects_would_be_cut`。
- 先复现失败：维护测试 10 通过、1 失败。
- 修复后：维护测试 11 通过、0 失败。
- 重跑 Attention `--debug-visual` 后，Figure 3 边界变为：
  - `phase_b`: `26.0,90.7 -> 586.0,306.3`
  - `final`: `114.5,93.4 -> 509.8,306.5`
- 目视确认红线完整包含底部旋转词、淡色 attention 标记和彩色块。
- 因在已有目录重跑产生 `_1.png` 文件名，已同步更新该 PDF Markdown 的 9 个图片链接，并验证 9 个链接均存在。
- 快速扫 Attention 5 图 + 4 表 debug 图例，未发现本次保护导致的明显异常扩张。

风险与权衡：

- 该规则故意只在 proposed near edge 会裁掉大量“小对象带”时触发，不改变普通大对象对齐逻辑。
- 阈值偏保守，可能漏掉对象数量少但仍属于 dense label 的图；后续排查其他 6 个 PDF 时需要继续记录。
- Figure 3 的红线现在保留完整 y 范围，但 x 方向仍由后续流程收窄，因此不会退回全页宽截图。
- 后续需要在其余 6 个 PDF 上继续看是否有相似 dense label 图，避免和短图、散点图、复杂表格策略冲突。

### Attention Figure 5：下方竖排文字被红线截断

文件：

`tests/results/20260618-001/1706.03762v7-attention_is_all_you_need/images/debug/Figure_5_p15_debug_stages.png`

现象：

- 绿线 `phase_a` 到 caption 上方，完整包含下方红色 attention visualization 的竖排文字。
- 黄线 `phase_b` 先把 y1 从 `596.3` 收到 `557.4`。
- 红线继承黄线的 y 范围，因此把下方竖排文字切到一半。

关键边界：

| 阶段 | 修复前边界 | 修复后边界 | 判断 |
| --- | --- | --- | --- |
| baseline | `26.0,76.3 -> 586.0,596.3` | `26.0,76.3 -> 586.0,596.3` | 安全 |
| phase_a | `26.0,76.3 -> 586.0,596.3` | `26.0,76.3 -> 586.0,596.3` | 安全 |
| phase_b | `26.0,76.3 -> 586.0,557.4` | `26.0,76.3 -> 586.0,596.3` | 修复前 y1 过早收缩 |
| final | `116.4,178.6 -> 504.0,557.5` | `116.4,178.6 -> 504.0,596.4` | 修复后包含下方竖排文字 |
| caption | `108.0,602.3 -> 504.0,634.2` | 同左 | phase_a 底边与 caption 之间仍有间隔 |

根因：

Figure 5 与 Figure 3 同属于 attention visualization / dense label figure，但证据形态不同：

- Figure 3 被切掉的下半部分主要是大量小 vector 对象。
- Figure 5 被切掉的下方竖排文字由 PyMuPDF 提取为 `text_lines`，不是 vector 对象。
- Phase B 之前只看 `image_rects + vector_rects`，完全没有把图内竖排文字作为内容证据。
- 该页 baseline/phase_a 内有 916 个 vector 对象，通过面积阈值后合并为两个大组件。
- 距 caption 最近的大组件为 `149.8,443.9 -> 470.3,549.4`，加 `object_pad=8` 后得到错误黄线 y1：`557.4`。
- 被切掉的 near-caption 区域中有一整排窄竖排文本标签，text union 约为 `120.7,545.3 -> 497.7,590.0`，横向覆盖宽且延伸到 phase_a 底边附近。

实际调整：

- 新增 `_has_text_label_band_near_trimmed_edge()`。
- `refine_clip_by_objects()` 增加可选 `text_lines` 参数。
- Figure 提取路径在 Phase B 调用中传入当前页 `text_lines`。
- 当 proposed near-edge 收缩会切掉一整排窄文本标签时，保留 phase_a 的 y 范围；后续仍允许 `refine_clip_x_range()` 收窄 x。
- 该规则要求：文本数量至少 8、单个文本框较窄、横向覆盖至少 30% clip 宽度、纵向跨度足够，并且标签行延伸到原 near edge 附近。

验证：

- 新增回归测试：`test_object_refinement_preserves_near_edge_when_vertical_text_labels_would_be_cut`。
- 先复现失败：维护测试 11 通过、1 失败。
- 修复后：维护测试 12 通过、0 失败。
- 重跑 Attention `--debug-visual` 后，Figure 5 红线完整包含下方竖排文字。
- 同步更新该 PDF Markdown 的 9 个图片链接，并验证 9 个链接均存在。
- 快速扫 Attention 5 图 + 4 表 debug 图例，未发现本次保护导致的明显异常扩张。

风险与权衡：

- 这是对 Figure 3 小对象证据的补充，不替代 vector 小对象带判断。
- 规则刻意要求“很多窄文本框形成一排”，避免把普通 caption 或正文段落误当图内标签。
- 目前只在 Figure 提取路径传入 `text_lines`，避免影响 Table Phase B 的既有裁剪行为。

### Attention Table 2：表格顶部分界线未被纳入，红黄框压表头

文件：

`tests/results/20260618-001/1706.03762v7-attention_is_all_you_need/images/debug/Table_2_p8_debug_stages.png`

现象：

- 修复前黄线和红线的顶部都在 `y0=98.1`。
- 表头第一行 `BLEU` / `Training Cost (FLOPs)` 的文本框从约 `y=97.9` 开始，红黄框几乎压到表头文字。
- 肉眼可见表格顶部有一条横向分界线，但原算法没有把它作为边界。

关键边界：

| 阶段 | 修复前边界 | 修复后边界 | 判断 |
| --- | --- | --- | --- |
| baseline | `26.0,98.1 -> 586.0,278.3` | `26.0,93.3 -> 586.0,278.3` | baseline 起点原本过低 |
| phase_a | `26.0,98.1 -> 586.0,188.2` | `26.0,93.3 -> 586.0,185.8` | 修复后保留顶部横线 |
| phase_b | `26.0,98.1 -> 586.0,188.2` | `26.0,93.3 -> 586.0,185.8` | 继承修复后的 near edge |
| final | `125.8,98.1 -> 486.3,246.9` | `125.8,93.3 -> 486.3,246.9` | 顶部不再压表头 |
| caption | `107.7,71.2 -> 504.0,92.1` | 同左 | 横线位于 caption 与原 baseline 之间 |

根因：

- 这页 `page.get_drawings()` 返回 0，PyMuPDF 没有把肉眼可见的表格横线暴露为 drawing/vector 对象。
- baseline 对 caption 在上、表格在下的场景直接使用 `caption_bbox.y1 + table_caption_gap`。
- Table 2 caption y1 约为 `92.1`，默认 `table_caption_gap=6`，所以 baseline y0 变成 `98.1`。
- 渲染像素探测显示，横向深色行实际位于约 `y=94.35`，正好落在 caption 与原 baseline 的间隙中。
- 由于 baseline 一开始就排除了这条线，后续 Phase A/B/final 都无法再恢复它。
- 第一次实现像素探测后仍未生效，是因为真实提取流程传入的是项目的 `PDFPage` 包装对象，其 `get_pixmap()` 不接受 `matrix` 参数；helper 捕获异常后返回原 clip。改为优先使用 `.raw.get_pixmap()` 后生效。

实际调整：

- 新增 `expand_clip_to_rendered_horizontal_rule()`。
- 对 Table baseline，在 caption 与当前 near edge 之间渲染一个很窄的搜索带。
- 当搜索带中出现横向覆盖足够宽的深色像素行时，将 near edge 扩到该横线之前。
- 同时支持原生 `fitz.Page` 和项目 `PDFPage` 包装对象。
- 只在 Table 提取路径调用，不改变 Figure 裁剪，也不全局调小 `table_caption_gap`。

验证：

- 新增回归测试：`test_table_clip_expands_to_rendered_horizontal_rule_between_caption_and_header`。
- 先复现失败：维护测试 12 通过、1 失败。
- 修复后：维护测试 13 通过、0 失败。
- 重跑 Attention `--debug-visual` 后，Table 2 红线和黄线顶部从 `98.1` 上移到 `93.3`。
- 目视确认最终 Table 2 截图顶部包含横向分界线，表头不再被红框压住。
- 验证该 PDF Markdown 的 9 个图片链接均存在。

风险与权衡：

- 这个规则依赖渲染像素，成本比直接读 drawing 略高，但搜索带很窄，只在 Table baseline 阶段执行。
- 规则要求横向深色覆盖比例足够高，避免普通 caption 字形或局部文字被误判为横线。
- 对没有顶部横线的表格，helper 返回原 clip，不改变既有行为。

## Attention 阶段性结论

截至 Table 2 顶部横线补偿修复后，`1706.03762v7-attention_is_all_you_need` 这份 PDF 的 5 个 Figure 和 4 个 Table 已完成逐图 debug 复查。

当前结论：

- 红色 `final` 线框已经达到非常准确的状态，能完整覆盖图表主体和必要图内标签。
- Figure 2 的顶部图内标题、Figure 3 的底部 dense label、小对象带和 Figure 5 的下方竖排文本标签均已被保住。
- Table 2 的顶部横向分界线已被纳入，红框不再压住表头。
- Attention 这份 PDF 中目前未再看到明显的正文混入、图表主体截断、红框过窄或红框过宽问题。
- 这份 PDF 可作为后续排查其余 6 个 Basic Benchmark PDF 时的当前高质量参照样例。

需要继续保持的边界：

- Figure 的 dense label 保护只应在 near-caption 收缩会切掉小对象带或窄文本标签带时触发。
- Table 的渲染横线补偿只应限制在 caption 与 near edge 之间的窄搜索带内。
- 不应因为 Attention 结果良好而全局放宽对象面积阈值或文本标签阈值。

## 当前策略冲突清单

| 策略 | 主要收益 | 已发现风险 | 关联图表 |
| --- | --- | --- | --- |
| far-side 正文检测 | 避免 autocrop 把远端正文纳入最终截图 | 会误伤短图内标签 | Attention Figure 2 |
| Phase B 对象对齐 | 去掉空白，贴近图形主体 | 单对象面积阈值会丢掉小对象密集图的真实内容 | Attention Figure 3 |
| Phase B 文本标签保护 | 保留 dense label figure 中的图内竖排文字 | 若阈值过松可能把正文标签化；当前用窄框、多数量、行带覆盖来约束 | Attention Figure 5 |
| Table 渲染横线补偿 | 在 `get_drawings()` 为空时补回肉眼可见的表格横线 | 依赖像素阈值；需限制在 caption 与 near edge 的窄搜索带内 | Attention Table 2 |
| X 方向收窄 | 避免全页宽截图和正文混入 | 依赖对象或文本证据保住 y 范围；若 y 已被 Phase B 截断，无法恢复 y | Attention Figure 3/5 |
| 低比例软接受 | 避免合理精裁因面积/高度比例略低被回退 | 若上游已经截断，软接受会保留错误精裁 | Attention Figure 3/5 |

## 后续记录模板

每新增一个图表排查项，按以下结构追加：

```markdown
### <PDF 名称> <Figure/Table 编号>：<问题摘要>

文件：

`tests/results/.../images/debug/...`

现象：

- ...

关键边界：

| 阶段 | 边界 | 判断 |
| --- | --- | --- |
| baseline | ... | ... |
| phase_a | ... | ... |
| phase_b | ... | ... |
| final | ... | ... |

根因：

...

调整：

...

验证：

...

风险与权衡：

...
```
