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

### Qwen3-Omni Figure 1：黄线从图下半部分开始，红线进一步截断

文件：

`tests/results/20260620-003/2509.17765v1-Qwen3-Omni_Technical_Report/images/debug/Figure_1_p2_debug_stages.png`

现象：

- 修复前蓝线、绿线、黄线完全重合，均只覆盖整张图的下半部分。
- 红线继承错误窗口后继续收窄，只截取了图底部区域。
- 这不是 Phase B 单独裁坏，而是 baseline 在进入 Phase A/B 之前已经被裁短。

关键边界：

| 阶段 | 修复前边界 | 修复后边界 | 判断 |
| --- | --- | --- | --- |
| baseline | `26.0,223.6 -> 569.3,302.6` | `26.0,0.0 -> 569.3,302.6` | baseline 不再被图内标签误截断 |
| phase_a | `26.0,223.6 -> 569.3,302.6` | `26.0,0.0 -> 569.3,302.6` | 继承完整候选窗口 |
| phase_b | `26.0,223.6 -> 569.3,302.6` | `26.0,0.0 -> 569.3,302.6` | 不再从图下半部分开始 |
| final | `78.8,255.9 -> 519.9,302.9` | `63.6,62.9 -> 531.6,302.9` | 红线完整覆盖图主体且排除页眉横线 |
| caption | `70.9,308.6 -> 525.7,351.5` | 同左 | caption 位于图下方 |

根因：

- Figure 1 是 caption 在下方、图在上方的场景，原始固定高度 baseline 理论上足够覆盖整图。
- `limit_clip_by_text_blocks()` 用 layout text blocks 收紧远端边界时，把图内部 `Query` / `Response` 等 `title_h3` 短标签误判成远端章节标题。
- 其中一个图内短标签和其他短标签的垂直距离略超过旧的 60pt 支持阈值，导致短标签聚类保护未生效，baseline 被错误推到 `y0=223.6`。
- 修复 baseline 后，autocrop 又把页面上方的页眉横线当作 far-side 内容，红线顶部一度停在 `y0=38.6`，混入多余页眉线和空白。

实际调整：

- 将 `_is_supported_short_title()` 中“附近短标题聚类”的垂直支持阈值从固定 `60pt` 扩展为 `max(60pt, min_near_distance)`。
- 新增 `trim_far_side_noise_before_content()`。
- Figure autocrop 后处理阶段会根据真实图像块、非页眉类矢量对象和图内短文本标签，识别第一批真实内容；若 autocrop far edge 明显早于真实内容，则把 far edge 回收到内容前少量 padding。
- 该规则只处理 Figure far-side 噪声，不改变 Table 的渲染横线补偿，也不改变 Phase B near-edge 对齐。

验证：

- 新增回归测试：`test_baseline_clip_preserves_spread_diagram_labels_above_caption`。
- 新增回归测试：`test_autocrop_trims_far_side_header_rule_before_figure_content`。
- `python -m pytest tests/scripts/test_caption_anchor_quality.py -q`：36 通过、0 失败。
- `python -m pytest tests/scripts/test_maintenance_fixes.py -q`：13 通过、0 失败。
- `python -m compileall skills/pdf-markdown-summary/scripts`：通过。
- 重跑 Qwen3-Omni 到 `tests/results/20260620-005/` 后，Figure 1 红线为 `63.6,62.9 -> 531.6,302.9`，目视确认完整覆盖图主体，且不再包含页眉横线。

风险与权衡：

- 该修复放宽的是“短标题聚类互相支持”的距离，不是把所有短标题都当图内标签；孤立远端章节标题仍可作为 blocker。
- far-side 噪声裁切依赖真实内容证据，只有 autocrop 边界明显早于图像/矢量/图内短文本证据时才回收。
- 若某些图的真实顶部就是单独页眉式细横线且下方内容距离较远，仍需后续逐图观察；当前规则优先保护 Figure 中常见的页面分隔线误入。

### Qwen3-Omni Table 9：layout 远端裁剪误切表格下半部分

文件：

`tests/results/20260620-005/2509.17765v1-Qwen3-Omni_Technical_Report/images/debug/Table_9_p12_debug_stages.png`

现象：

- Table 9 的 baseline、phase_a、phase_b 都覆盖完整表格，到 Table 10 caption 前停止。
- final 红线只到 `Counting` 分组附近，漏掉 `CountBench`、`Video Understanding`、`LVBench`、`MLVU` 等下半部分。
- 因此问题不在 caption 锚点、Phase A 或 Phase B，而在 Phase B 之后到 final 之间。

关键边界：

| 阶段 | 修复前边界 | 修复后边界 | 判断 |
| --- | --- | --- | --- |
| baseline | `26.0,248.8 -> 569.3,498.1` | `26.0,248.8 -> 569.3,498.1` | 原始窗口完整 |
| phase_a | `26.0,248.8 -> 569.3,498.1` | `26.0,248.8 -> 569.3,498.1` | 文本裁切未误伤 |
| phase_b | `26.0,248.8 -> 569.3,498.1` | `26.0,248.8 -> 569.3,498.1` | 对象对齐未误伤 |
| final | `66.1,248.8 -> 527.1,429.5` | `66.1,248.8 -> 527.1,498.4` | 红线恢复到表格底部 |
| caption | `70.6,224.4 -> 524.4,246.3` | 同左 | caption 位于表格上方 |

根因：

- `refine_clip_to_table_band()` 对 Table 9 没有收短，实测返回完整 baseline。
- 真正收短发生在 `adjust_clip_with_layout()` 的 far-strip 逻辑。
- layout model 将表格内的数字行聚成 `paragraph_group`，这些块位于候选框远端边缘附近。
- far-strip 原本用于排除候选框远端的正文段落，但在 Table 9 中把仍属于表格尾部的 `paragraph_group` 当作外部正文，提前把 y1 裁到约 `429.1`。
- 后续 pixel autocrop 只在已截短窗口内工作，因此无法再恢复 `CountBench` 和 `Video Understanding` 下方行。

实际调整：

- 新增 `restore_table_tail_after_layout_trim()`。
- Table 路径在 `adjust_clip_with_layout()` 后比较 layout 前后的窗口；如果 layout 裁掉的远端尾部本身仍满足 `looks_like_table_text()` 的短单元格/数字型表格特征，则恢复远端 y 边界。
- 该保护只接入 Table 提取链路，不改变 Figure 的 layout 裁剪逻辑。

验证：

- 新增回归测试：`test_layout_trim_preserves_structured_table_tail`。
- `python -m pytest tests/scripts/test_caption_anchor_quality.py -q`：37 通过、0 失败。
- `python -m pytest tests/scripts/test_maintenance_fixes.py -q`：13 通过、0 失败。
- `python -m compileall skills/pdf-markdown-summary/scripts`：通过。
- 三个入口脚本 `--help` 通过：`extract_pdf_assets.py`、`pdf_to_markdown.py`、`process_pdf.py`。
- 重跑 Qwen3-Omni 到 `tests/results/20260620-006/` 后，Table 9 final 为 `66.1,248.8 -> 527.1,498.4`，目视确认完整覆盖表格下半部分。

风险与权衡：

- 该规则只在“被 layout 裁掉的尾部区域本身像表格”时恢复，不会简单取消 layout 对表格的正文保护。
- 如果某些真实正文尾部由大量短数字组成，可能被误判为表格尾部；当前由 `looks_like_table_text()` 的短文本比例和宽正文比例约束。

### FunAudio-ASR Table 5：final 红线与底部文字过近

文件：

`tests/results/20260620-008/FunAudio-ASR/images/debug/Table_5_p11_debug_stages.png`

现象：

- Table 5 的黄线覆盖完整候选窗口，阶段边界本身不需要调整。
- final 红线底边贴近 B 行文字，最终截图底部几乎没有安全边距。
- legend 显示表格文字块底部到 `y=128.9`，修复前 final 只到 `y=126.7`，已经低于文字 bbox 底部约 `2.2pt`。

关键边界：

| 阶段 | 修复前边界 | 修复后边界 | 判断 |
| --- | --- | --- | --- |
| baseline | `26.0,0.0 -> 586.0,126.4` | 同左 | 候选窗口完整，保持不动 |
| phase_a | `26.0,0.0 -> 586.0,126.4` | 同左 | 文本裁切未误伤 |
| phase_b | `26.0,0.0 -> 586.0,126.4` | 同左 | 黄线合理，不调整 |
| final | `159.4,69.8 -> 452.7,126.7` | `159.4,69.8 -> 452.7,131.4` | 红线补到文字 bbox 外，并停在 caption 前 |
| caption | `142.8,132.4 -> 468.9,142.4` | 同左 | final 与 caption 保留约 `1pt` 间隔 |

根因：

- 该表格没有清晰闭合底线，pixel autocrop 更容易贴着最后一行墨迹收边。
- `table_autocrop_pad=20px` 对多数表格足够，但在这张小表上换算到页面坐标后，底部仍贴近文字 bbox。
- 如果全局增大 `table_autocrop_pad`，会让所有表格变松，可能重新混入 caption 或正文。

实际调整：

- 新增 `expand_table_clip_to_text_bounds()`。
- 只在 Table final 阶段执行，且只在候选 final 已经像表格文本时生效。
- 用当前 final 附近的 text line bbox 做安全补边；对 caption 在下方的表格，允许向 caption 方向最多扩到 `caption.y0 - 1pt`，避免把 caption 纳入截图。
- 不改变 baseline、Phase A、Phase B、layout、autocrop 全局参数。

验证：

- 新增回归测试：`test_table_final_padding_keeps_text_bbox_before_caption`。
- `python -m pytest tests/scripts/test_caption_anchor_quality.py -q`：38 通过、0 失败。
- `python -m pytest tests/scripts/test_maintenance_fixes.py -q`：13 通过、0 失败。
- `python -m compileall skills/pdf-markdown-summary/scripts`：通过。
- 三个入口脚本 `--help` 通过：`extract_pdf_assets.py`、`pdf_to_markdown.py`、`process_pdf.py`。
- 重跑 FunAudio-ASR 到 `tests/results/20260620-009/` 后，Table 5 final 为 `159.4,69.8 -> 452.7,131.4`，最终截图底部 B 行不再贴边，且没有混入 caption。

风险与权衡：

- 该规则不应替代 Table 9 的 layout 尾部恢复；它只解决 final autocrop 贴字的问题。
- 因为补边只允许在 final 附近小范围查找 text bbox，并且跳过 caption 文本，所以比调大全局 `table_autocrop_pad` 风险低。
- 如果某些正文段落被错误裁成 table-like final，理论上也可能被小幅补边；现有污染检测仍会在后续验收阶段过滤明显正文。

### Gemini 2.5 Report Figure 3：Phase A 把图底部误裁掉

文件：

`tests/results/20260620-008/gemini_v2_5_report/images/debug/Figure_3_p5_debug_stages.png`

现象：

- baseline 蓝线覆盖完整图表主体和 caption 上方区域。
- phase_a 绿线从 `y1=236.1` 被裁到 `y1=188.8`，把三组柱状图的 x 轴、底部刻度和柱子底部直接截掉。
- phase_b 黄线和 final 红线继承了 phase_a 的错误，因此最终截图只剩图上半部分。

关键边界：

| 阶段 | 修复前边界 | 修复后边界 | 判断 |
| --- | --- | --- | --- |
| baseline | `26.0,0.0 -> 569.3,236.1` | 同左 | 原始窗口完整 |
| phase_a | `26.0,70.8 -> 569.3,188.8` | `26.0,70.8 -> 569.3,236.1` | 修复后不再裁掉轴刻度 |
| phase_b | `26.0,70.8 -> 569.3,188.8` | `26.0,70.8 -> 569.3,236.1` | 继承完整 phase_a |
| final | `84.3,82.6 -> 506.0,188.9` | `84.3,82.6 -> 512.0,233.3` | 红线完整覆盖图主体 |
| caption | `62.4,242.1 -> 365.3,253.6` | 同左 | caption 位于图下方 |

根因：

- Phase A+ 的 `detect_exact_n_lines_of_text()` 用于识别 near-caption 侧“恰好两行正文”并做更激进裁切。
- Gemini Figure 3 的 near-caption 搜索带中只有 y 轴底部两个窄刻度文本：`20` 和 `0`。
- 旧逻辑只检查文本行数量和高度，不检查文本行宽度，因此把两个窄刻度当成“精确两行正文”。
- 对 `direction='above'`，该逻辑把 near edge 裁到第一条匹配行上方约 `y=189`，导致图底部被截断。

实际调整：

- `detect_exact_n_lines_of_text()` 新增 `min_line_width_ratio` 参数。
- Figure Phase A+ 调用时要求 exact-two-lines 候选行具备最小横向宽度：`max(0.18, width_ratio * 0.35)`。
- 纯数字刻度、窄轴标签等图内短文本不再触发“精确两行正文”裁切；真正宽正文行仍可触发该保护。

验证：

- 新增回归测试：`test_text_trim_ignores_narrow_axis_ticks_near_caption`。
- `python -m pytest tests/scripts/test_caption_anchor_quality.py -q`：39 通过、0 失败。
- `python -m pytest tests/scripts/test_maintenance_fixes.py -q`：13 通过、0 失败。
- `python -m compileall skills/pdf-markdown-summary/scripts`：通过。
- 三个入口脚本 `--help` 通过：`extract_pdf_assets.py`、`pdf_to_markdown.py`、`process_pdf.py`。
- 重跑 Gemini 到 `tests/results/20260620-010/` 后，Figure 3 final 为 `84.3,82.6 -> 512.0,233.3`，目视确认完整覆盖三组柱状图、x 轴和底部刻度。

风险与权衡：

- 该修复只收紧 exact-two-lines 的触发条件，不关闭 Phase A+。
- 如果某些真实需要裁掉的 near-caption 正文是非常窄的两行文字，可能不再被 exact-two-lines 识别；但这类窄文本更接近图内标签/轴刻度，保守不裁更安全。
- 该规则不影响 Table final 文本 bbox 补边、Qwen Table 9 layout 尾部恢复或 Attention dense label 保护。

### Gemini 2.5 Report Figure 5 / Figure 12：图内标题被当作外部标题裁掉

文件：

`tests/results/20260620-009/gemini_v2_5_report/images/debug/Figure_5_p15_debug_stages.png`

`tests/results/20260620-009/gemini_v2_5_report/images/debug/Figure_12_p64_debug_stages.png`

现象：

- Figure 5 的图内标题 `Gemini 2.5 Pro Plays Pokemon Progress Timeline` 位于图主体上方 `y=145.0 -> 152.5`，但修复前 baseline/phase/final 均从 `y=158.5` 附近开始，标题被排除在截图外。
- Figure 12 的图内标题 `Gemini Plays Pokemon Progress Timeline` 位于 `y=86.6 -> 95.2`，修复前 baseline/phase/final 从 `y=101.2` 附近开始，同样漏掉标题。
- 用户判断“把属于图的标注或者图的题目当成外围文字”基本准确；更精确地说，是 layout blocker 与 final autocrop 都把紧贴图主体的图内标题排除掉了。

关键边界：

| 图表 | 阶段 | 修复前边界 | 修复后边界 | 判断 |
| --- | --- | --- | --- | --- |
| Figure 5 | baseline | `26.0,158.5 -> 569.3,423.1` | `26.0,141.0 -> 569.3,423.1` | 蓝线恢复图内标题 |
| Figure 5 | final | `128.5,158.5 -> 467.1,423.2` | `128.5,141.0 -> 467.1,423.2` | 红线恢复图内标题 |
| Figure 12 | baseline | `26.0,101.2 -> 569.3,403.8` | `26.0,82.6 -> 569.3,403.8` | 蓝线恢复图内标题 |
| Figure 12 | final | `105.3,101.2 -> 490.2,403.6` | `105.3,82.6 -> 490.2,403.6` | 红线恢复图内标题 |

根因：

- `limit_clip_by_text_blocks()` 会把 `title_h3` 作为可能的外部标题 blocker，用于避免章节标题混入截图。
- Gemini Figure 5/12 的图内 chart title 也被 layout model 标为 `title_h3`，且紧贴图主体上方，因此 baseline 被裁到标题下方。
- 第一次只在 baseline 后恢复图内标题后，蓝/绿/黄线正确，但 final 红线仍错误；原因是后续 layout/autocrop 仍会以已经排除标题的窗口做最终像素裁切。

实际调整：

- 新增 `expand_clip_to_nearby_figure_title()`，只恢复紧贴图主体的候选标题行。
- 该函数跳过页眉宽文本和编号章节标题，例如 `4.1. Gemini Plays Pokemon`，避免把正文标题放回截图。
- Figure 路径在 baseline text block limit 后调用一次，保证蓝/绿/黄线拥有正确候选范围。
- Figure 路径在 final autocrop 后再调用一次，并以 `clip_after_B` 作为可恢复边界，保证红线不会被 layout/autocrop 再次收窄到标题下方。
- 该修复只作用于 Figure，不修改 Table，不调整全局 autocrop 参数。

验证：

- 新增回归测试：`test_baseline_expands_to_nearby_chart_title_above_figure`。
- 新增负例测试：`test_baseline_title_recovery_ignores_page_header_and_section_title`。
- `python -m pytest tests/scripts/test_caption_anchor_quality.py -q`：41 通过、0 失败。
- `python -m pytest tests/scripts/test_maintenance_fixes.py -q`：13 通过、0 失败。
- `python -m compileall skills/pdf-markdown-summary/scripts`：通过。
- 三个入口脚本 `--help` 通过：`extract_pdf_assets.py`、`pdf_to_markdown.py`、`process_pdf.py`。
- 重跑 Gemini 到 `tests/results/20260620-012/` 后，Figure 5 和 Figure 12 的 debug 图与最终截图均确认红线包含图内标题，且未纳入页眉、章节标题或下方正文。

风险与权衡：

- 该规则要求标题与图主体 near edge 的间距很小，适合 chart title / 图内标注，不适合恢复距离较远的段落标题。
- 如果某些图内标题被拆成多行且第一行距离图主体较远，当前规则可能只恢复贴近图主体的一行；这是有意保守，避免把章节标题误并入。
- 与 Qwen3-Omni Figure 1 的短标签聚类保护不同，本规则处理的是单行或少量宽标题；二者互补，不共用阈值。

### Qwen3-Omni Figure 3：图内标题回收误纳入章节标题

文件：

`tests/results/20260620-010/2509.17765v1-Qwen3-Omni_Technical_Report/images/debug/Figure_3_p4_debug_stages.png`

现象：

- 修复 Gemini Figure 5/12 后，Qwen3-Omni Figure 3 的红线把章节标题 `Audio Transformer (AuT)` 左侧残片纳入了最终截图。
- 该标题属于正文结构 `2.2 Audio Transformer (AuT)`，不是 Figure 3 的图内题目。
- 旧 debug 中 baseline、phase_a、phase_b 均从 `y=224.4` 开始，final 从 `y=224.4` 开始，导致章节标题混入。

关键边界：

| 阶段 | 冲突时边界 | 修复后边界 | 判断 |
| --- | --- | --- | --- |
| baseline | `26.0,224.4 -> 569.3,508.0` | `26.0,244.4 -> 569.3,508.0` | 修复后不再覆盖章节标题 |
| phase_a | `26.0,224.4 -> 569.3,508.0` | `26.0,244.4 -> 569.3,508.0` | 继承正确 baseline |
| phase_b | `26.0,224.4 -> 569.3,508.0` | `26.0,244.4 -> 569.3,508.0` | 黄线只保留图主体候选区 |
| final | `159.4,224.4 -> 440.9,506.0` | `159.4,249.2 -> 440.9,506.0` | 红线不再含章节标题 |
| caption | `70.9,514.0 -> 524.6,545.8` | 同左 | caption 位于图下方 |

根因：

- PDF 文本抽取把章节标题拆成两条同基线文本行：
  - `70.9,228.4 -> 83.3,238.4 | 2.2`
  - `93.3,228.4 -> 210.1,238.4 | Audio Transformer (AuT)`
- `expand_clip_to_nearby_figure_title()` 原本只跳过“文本自身以编号开头”的标题。
- 对于这种编号和标题被拆开的情况，`2.2` 被跳过了，但右侧 `Audio Transformer (AuT)` 没有编号前缀，且距离图主体很近，于是被误当作图内 chart title 回收。

实际调整：

- `expand_clip_to_nearby_figure_title()` 新增纯章节编号行识别：如 `2.2`、`4.`。
- 当候选标题行与纯章节编号行垂直重叠，并且位于编号右侧小间距内时，整行视为章节标题组合，跳过回收。
- 保留 Gemini Figure 5/12 所需的无编号 chart title 回收；该类标题没有左侧同基线章节编号，因此不受影响。

验证：

- 新增回归测试：`test_baseline_title_recovery_ignores_split_numbered_section_heading`。
- `python -m pytest tests/scripts/test_caption_anchor_quality.py -q`：42 通过、0 失败。
- `python -m pytest tests/scripts/test_maintenance_fixes.py -q`：13 通过、0 失败。
- `python -m compileall skills/pdf-markdown-summary/scripts`：通过。
- 三个入口脚本 `--help` 通过：`extract_pdf_assets.py`、`pdf_to_markdown.py`、`process_pdf.py`。
- 重跑 Qwen3-Omni 到 `tests/results/20260620-013/` 后，Figure 3 final 为 `159.4,249.2 -> 440.9,506.0`，最终截图不再包含章节标题。
- 同次抽查 Qwen3-Omni Figure 1，final 仍为 `63.6,62.9 -> 531.6,302.9`，之前的短标签/页眉噪声修复未回退。
- 重跑 Gemini 到 `tests/results/20260620-014/` 后，Figure 5 final 仍为 `128.5,141.0 -> 467.1,423.2`，Figure 12 final 仍为 `105.3,82.6 -> 490.2,403.6`，图内 chart title 回收未被破坏。

风险与权衡：

- 该负例保护只在“纯章节编号”和“右侧标题”同基线且水平距离很近时触发，不会屏蔽普通无编号 chart title。
- 如果某个图内标题本身左侧带类似 `2.2` 的编号标签，可能被保守跳过；但这类形态更接近正文小节标题，宁可不扩红线，也不能把章节标题截进最终图。
- 这个修复说明 Figure 图内标题回收必须持续维护负例，不适合简单放宽 max_gap 或改大全局 padding。

### Gemini 2.5 Report Figure 14 / Figure 15：Phase B 裁掉 near-caption 图内标注

文件：

`tests/results/20260620-010/gemini_v2_5_report/images/debug/Figure_14_p69_debug_stages.png`

`tests/results/20260620-010/gemini_v2_5_report/images/debug/Figure_15_p69_debug_stages.png`

现象：

- Figure 14 的 baseline/phase_a 已覆盖两张子图下方的 `(a)/(b)` 面板说明，但 phase_b 把底边从 `311.9` 收到 `291.6`，导致红线漏掉第二行说明文字。
- Figure 15 的 baseline/phase_a 已覆盖 Prompt 列下方四行输入说明，但 phase_b 把底边从 `714.1` 收到 `663.2`，导致红线只截到第一行上半部分。
- 这类 case 下用户判断“绿线更合理”是准确的；问题发生在 Phase B 对象边界对齐，而不是 baseline、Phase A 或 final autocrop。

关键边界：

| 图表 | 阶段 | 修复前边界 | 修复后边界 | 判断 |
| --- | --- | --- | --- | --- |
| Figure 14 | baseline | `26.0,82.0 -> 569.3,311.9` | 同左 | 原始候选正确 |
| Figure 14 | phase_a | `26.0,82.0 -> 569.3,311.9` | 同左 | 绿线正确 |
| Figure 14 | phase_b | `26.0,82.0 -> 569.3,291.6` | `26.0,82.0 -> 569.3,311.9` | 修复后保留面板说明 |
| Figure 14 | final | `55.3,82.0 -> 541.1,291.7` | `55.3,82.0 -> 541.1,311.3` | 红线包含 `(a)/(b)` 说明 |
| Figure 15 | baseline | `26.0,521.4 -> 569.3,714.1` | 同左 | 原始候选正确 |
| Figure 15 | phase_a | `26.0,521.4 -> 569.3,714.1` | 同左 | 绿线正确 |
| Figure 15 | phase_b | `26.0,521.4 -> 569.3,663.2` | `26.0,521.4 -> 569.3,714.1` | 修复后保留 Prompt 文字 |
| Figure 15 | final | `61.1,521.4 -> 523.1,663.5` | `61.1,521.4 -> 523.1,714.4` | 红线包含完整四行输入说明 |

根因：

- Phase B 的 `refine_clip_by_objects()` 根据图像/矢量对象边界收紧 near-caption 侧边界。
- 旧逻辑已经保护了小对象带和窄文本标签带，但 Figure 14 的 `(a)/(b)` 面板说明是宽文本，Figure 15 的 Prompt 输入说明是窄列多行正文形态，都不满足旧的“窄标签带”条件。
- 这些文字虽然看起来像 paragraph text，但位置在图主体与 Figure caption 之间，应视为图内内容，而不是正文污染。

实际调整：

- 新增 `_near_caption_annotation_text_edge()`，从“布尔触发后恢复整条 near edge”改为“返回需要补到的局部边界”。
- 仅当 Phase B 即将裁掉 near-caption 侧文字时触发，且排除 Figure/Table caption、编号章节标题等外部文本。
- 当前接受两类保守形态：
  - 子图面板说明：候选文字中存在 `(a)`、`(b)` 这类面板前缀，且至少两行。
  - 窄列多行图内说明：至少三行，整体宽度不超过 `min(180pt, 35% clip width)`，整体高度足够且不过高。
- near-caption 检测使用纯对象边界作为探针，避免后续短标签补边先吃掉部分文本后反而让检测失效。
- 该逻辑只影响 Phase B 的 near-edge 收缩，不修改 baseline、Phase A、final autocrop 或图内标题回收规则。

验证：

- 新增回归测试：`test_phase_b_preserves_near_caption_panel_subcaptions`。
- 新增回归测试：`test_phase_b_preserves_near_caption_prompt_text_column`。
- `python -m pytest tests/scripts/test_caption_anchor_quality.py -q`：47 通过、0 失败。
- `python -m pytest tests/scripts/test_maintenance_fixes.py -q`：13 通过、0 失败。
- `python -m compileall skills/pdf-markdown-summary/scripts`：通过。
- 三个入口脚本 `--help` 通过：`extract_pdf_assets.py`、`pdf_to_markdown.py`、`process_pdf.py`。
- 重跑 Gemini 到 `tests/results/20260620-018/gemini_v2_5_report/` 后，Figure 14/15 的最终截图均完整保留下方图内标注。
- 同次抽查 Gemini Figure 3/5/12：Figure 3 仍为 `84.3,82.6 -> 512.0,233.3`，Figure 5 仍为 `128.5,141.0 -> 467.1,423.2`，Figure 12 仍为 `105.3,82.6 -> 490.2,403.6`。

风险与权衡：

- 这个保护不能简单扩展为“保留所有 near-caption 文字”，否则会把真正的正文污染保留下来。
- 当前规则依赖面板前缀或窄列多行形态，能覆盖这两个 Gemini case，但仍保守地拒绝大段全宽正文。
- 如果后续遇到没有 `(a)/(b)` 前缀、但横跨全宽的图内说明，仍可能被 Phase B 裁掉；届时需要新增更强证据，例如对象下缘间距、左右列对齐或 caption 前空白结构，而不是扩大当前阈值。

### Attention Figure 3 与 Kearns Figures 4/6/7：图内标题恢复和对象裁切规则的冲突复核

文件：

`tests/results/20260620-016/1706.03762v7-attention_is_all_you_need/images/debug/Figure_3_p13_debug_stages.png`

`tests/results/20260620-016/KearnsNevmyvakaHFTRiskBooks/images/debug/Figure_4_p11_debug_stages.png`

`tests/results/20260620-016/KearnsNevmyvakaHFTRiskBooks/images/debug/Figure_6_p13_debug_stages.png`

`tests/results/20260620-016/KearnsNevmyvakaHFTRiskBooks/images/debug/Figure_7_p18_debug_stages.png`

现象：

- Attention Figure 3 的红线重新包含 `Attention Visualizations` 小节标题，顶部多出不属于图主体的文字。
- Kearns Figure 4 的红线漏掉图内上方标题 `absolute trainer` 和右下 `feature index`。
- Kearns Figure 6 / Figure 7 的红线靠近底部轴标题，`state value` / `volume submitted` 安全边距不足，且 20260620-016 的黄线仍可见较大空白。
- 这些问题一开始看起来像 Gemini Figure 14/15 的 near-caption 修复造成的干涉，但代码探针确认 `_near_caption_annotation_text_edge()` 对 Attention/Kearns 这四张并未触发；真实冲突来自图内标题恢复和 Phase A/B 对短轴标题的处理边界。

关键边界：

| 图表 | 20260620-016 final | 20260620-017 final | 判断 |
| --- | --- | --- | --- |
| Attention Figure 3 | `114.5,68.8 -> 509.8,306.5` | `114.5,93.4 -> 509.8,306.5` | 修复后不再吃入小节标题，恢复此前准确边界 |
| Kearns Figure 4 | `134.6,296.1 -> 427.9,580.7` | `134.6,271.7 -> 470.8,601.0` | 修复后包含 `absolute trainer`、`policy index`、`feature index` |
| Kearns Figure 6 | `120.4,285.2 -> 499.6,564.6` | `120.4,262.6 -> 499.6,576.0` | 修复后包含四个子图标题和底部 `state value` |
| Kearns Figure 7 | `120.9,81.4 -> 486.9,257.0` | `120.9,81.4 -> 486.9,267.1` | 修复后包含底部 `volume submitted` |

根因：

- Attention Figure 3 的 final autocrop 后，`expand_clip_to_nearby_figure_title()` 看到 `Attention Visualizations` 与图主体上边界距离很近，且此前只排除了页眉、编号章节标题和拆分章节编号，没有字号上限，因此把 12pt 小节标题当作图内 chart title 补回。
- Kearns Figure 4 的 `absolute trainer` 是图内标题，但 Phase A 远端正文裁切先把上方正文清掉时，也把该低字号短标题切掉；后续 final 阶段已经无法恢复。
- Kearns Figure 4/6/7 的轴标题不是 image/vector 对象，而是 PDF text line；旧 Phase B 只用图像/矢量对象决定 near edge，导致对象边界对齐会贴近坐标轴并裁掉或压住轴标题。
- 这三类问题不能用扩大 autocrop padding 解决，否则会让正文污染和空白一起回流。

实际调整：

- `expand_clip_to_nearby_figure_title()` 增加 `max_title_font_size=11.0`，保留 Gemini Figure 15 的 10.9pt 表头和低字号图内 chart title，同时拒绝 Attention 的 12pt 文档小节标题。
- 新增 `_restore_far_side_short_labels_after_text_trim()`，在 Phase A 全部远端正文裁切之后，只把贴近新边界、低字号、短文本、非 caption 的图内标签局部补回。
- 新增 `_nearby_short_label_rects()`，Phase B 对象对齐时把靠近图像/矢量对象的低字号短轴标题纳入对象证据，避免 near edge 压到 `feature index`、`state value`、`volume submitted`。
- Gemini Figure 14/15 的 near-caption 修复同步改为 `_near_caption_annotation_text_edge()` 局部补边，并用纯对象边界作为探针，避免和短标签证据互相遮挡。

验证：

- 新增回归测试：`test_final_title_recovery_ignores_large_section_title`。
- 新增回归测试：`test_phase_a_restores_far_side_short_chart_title`。
- 新增回归测试：`test_phase_b_expands_to_nearby_axis_titles_without_full_edge_fallback`。
- `python -m pytest tests/scripts/test_caption_anchor_quality.py -q`：47 通过、0 失败。
- `python -m pytest tests/scripts/test_maintenance_fixes.py -q`：13 通过、0 失败。
- `python -m compileall skills/pdf-markdown-summary/scripts`：通过。
- 入口脚本 `--help` 通过：`extract_pdf_assets.py`、`pdf_to_markdown.py`、`process_pdf.py`、`summarize_pdf.py`。
- 重跑 Attention、Kearns 到 `tests/results/20260620-017/`，重跑 Gemini 到 `tests/results/20260620-018/`，上述四张图与 Gemini Figure 14/15 均目视通过。

风险与权衡：

- 字号上限会让少数 11pt 以上的真实图内标题不再通过标题恢复；但这类标题更容易和文档小节标题混淆，当前选择保守拒绝。
- 短标签恢复要求“贴近新边界”，不会扫描整页；如果图内标题与正文之间间隔很大，仍可能被当成外部文字切掉。
- Phase B 只把低字号短标签作为对象证据，不会把全宽段落或 caption 文本纳入对象范围，避免和正文清理规则互相干涉。

### GPT-5 System Card Figures：伪双栏导致 X 方向横向塌缩

文件：

`tests/results/20260620-019/gpt-5-system-card/images/debug/Figure_1_p13_debug_stages.png`

现象：

- GPT-5 System Card 的 31 张 Figure 中，修复前 30 张被横向裁成左侧极窄一条；典型 final 宽度只有约 `112-119pt`，右边界集中停在 `x1=182.6` 附近。
- baseline 原本为整页宽 `543.3pt`，实际图像对象也横跨 `x=70.9 -> 524.4`，因此不是对象证据不足，而是 X 收窄策略错误信任了伪双栏版式。
- Table 不明显受影响，因为 Table 路径后续有 `restore_table_clip_width()` 兜底恢复宽度。

关键边界：

| 项目 | 边界/数值 | 判断 |
| --- | --- | --- |
| 误判 layout | `num_columns=2`，`column_gap=327pt` | gap 超过页面宽度 50%，不是可信双栏 |
| caption 中心 | 约 `297.6pt`，略小于页面中心 | 被策略 1 判为左栏 |
| 修复前 final | 宽度约 `112-119pt` | 图右侧 2/3 被裁掉 |
| 修复后 final | 31 张 Figure 最小宽度 `452.2pt`、最大宽度 `505.5pt` | 无 `width < 200pt` 的横向塌缩 |

根因：

- `detect_columns()` 只看直方图双峰，GPT-5 单栏文档中图表内文字和居中标题形成了假双峰。
- 旧逻辑没有校验 `column_gap` 和双峰间距是否符合真实双栏几何，导致产生 `column_gap=327pt` 这种明显不合理的版式模型。
- `refine_clip_x_range()` 策略 1 直接信任 `num_columns>=2`，把图按伪左栏裁剪，后续 autocrop 只能在已经被截断的局部内收缩，无法恢复右侧内容。

实际调整：

- `detect_columns()` 接受双栏前新增几何校验：`column_gap` 必须大于 0 且不超过页面宽度 30%，双峰间距必须落在页面宽度 18%-60% 之间。
- `refine_clip_x_range()` 新增 `_has_trustworthy_column_geometry()`，对异常大 gap、页边距等于整页、列宽过窄等情况拒绝使用双栏列边界。
- 这两个保护只影响 X 方向双栏裁列，不修改 y 方向裁剪、Phase A/B、autocrop 或 Table 宽度恢复规则。

验证：

- 新增回归测试：`test_column_detection_rejects_unrealistic_large_gap_candidate`。
- 新增回归测试：`test_x_refine_ignores_untrusted_wide_gap_layout_columns`。
- 重跑 GPT-5 到 `tests/results/20260620-019/gpt-5-system-card/`，提取 31 图 + 26 表。
- 批量读取 31 个 Figure legend：final 最小宽度 `452.2pt`、最大宽度 `505.5pt`，`width < 200pt` 数量为 0。
- 目视检查 Figure 1 debug 图，红线已覆盖完整柱状图、标题和图例，不再只剩左侧 y 轴和第一组柱。

风险与权衡：

- 真实双栏 PDF 若列间距异常大，可能被当成单栏，X 方向会偏宽；但这比把单栏图裁成窄条更安全，后续对象证据和 autocrop 仍会做收窄。
- 该规则不放宽正文清理，不会让 Figure 的 y 方向重新混入正文。

### Gemini 2.5 Report Tables：多行表头被 layout blocker 裁掉

文件：

`tests/results/20260620-019/gemini_v2_5_report/images/debug/Table_1_p2_debug_stages.png`

`tests/results/20260620-019/gemini_v2_5_report/images/debug/Table_3_p12_debug_stages.png`

现象：

- Gemini Table 1 / Table 3 的多行模型表头被当作外部 `title_h3` / `paragraph_group` blocker，final 从表头下方开始，读者只能看到数据行。
- Table 3 的旧 baseline y0 位于 `233.8pt` 附近，正好压在第二行表头下方，后续 `refine_clip_to_table_band()` 只能在被裁短的窗口内工作，无法主动恢复表头。
- Table 5 这种大表已经保住表头，本轮修复需要避免把相邻正文或下一张表混进来。

关键边界：

| 图表 | 修复后 final | 判断 |
| --- | --- | --- |
| Gemini Table 1 | `57.4,113.1 -> 537.9,254.9` | 包含两行表头和全部数据行 |
| Gemini Table 3 | `62.2,210.3 -> 533.1,595.3` | 包含 `Capability/Benchmark` 与 Gemini 系列表头 |
| Gemini Table 5 | `57.4,209.5 -> 537.9,423.9` | 表头保留，未把下方说明正文纳入 final |

根因：

- Table 路径复用了 Figure 的 `limit_clip_by_text_blocks()`，而 Gemini 的表头行是满宽、多词、低字号文本块，命中了 `_looks_like_blocker()` 的宽文本 blocker 分支。
- 表头本身没有被当作结构化表格行保护；旧的图内标题回收只服务 Figure，不服务 Table。
- 一旦 baseline 在 layout blocker 阶段被压到表头下方，后续表格行带裁剪不会向外扩张到原始 baseline 之外。

实际调整：

- 新增 `expand_clip_to_nearby_table_header()`，只在 Table 路径、且仅在 `limit_clip_by_text_blocks()` 之后运行。
- 该函数必须同时满足：原始 baseline 比 limited clip 更大、limited clip 内部仍像表格文本、被裁掉的相邻区域有至少两行短表头候选、候选紧贴表格主体且不与 caption 重叠。
- Figure 路径不调用该逻辑；Table 的 final autocrop padding、Table tail 恢复和 X 宽度恢复规则也未改变。

验证：

- 新增回归测试：`test_table_header_recovery_restores_multiline_header_above_table_body`。
- 重跑 Gemini 到 `tests/results/20260620-019/gemini_v2_5_report/`，提取 13 图 + 12 表。
- 目视检查 Table 1 / Table 3 debug 图，红线已包含多行表头；Table 5 表头仍保留，未出现下方正文并入。
- `test_caption_anchor_quality.py` 从 47 条增加到 50 条，全部通过。

风险与权衡：

- 当前只恢复紧贴表格主体的多行短表头，不尝试恢复远距离说明文字。
- 若某些正文恰好像多列表头并紧贴表格主体，存在小幅误恢复风险；因此函数要求 limited clip 内已有连续表格行证据，并排除 caption、长句和句末标点文本。

### Gemini 2.5 Report Tables 二次复核：final 表头截断与 Table 5 方向误判

文件：

`tests/results/20260620-020/gemini_v2_5_report/images/debug/Table_1_p2_debug_stages.png`

`tests/results/20260620-020/gemini_v2_5_report/images/debug/Table_2_p6_debug_stages.png`

`tests/results/20260620-020/gemini_v2_5_report/images/debug/Table_5_p14_debug_stages.png`

`tests/results/20260620-020/gemini_v2_5_report/images/debug/Table_10_p27_debug_stages.png`

`tests/results/20260620-020/gemini_v2_5_report/images/debug/Table_11_p63_debug_stages.png`

现象：

- Table 1 / Table 2 / Table 11 的 baseline 已经覆盖表头，但 final autocrop 把顶部表头裁掉；这不是上一轮 BUG-033 的 layout blocker 问题。
- Table 10 的 baseline 从表格中部开始，`Key Results for Gemini 2.5 Pro` 表头和 CBRN 首组上半部分在 layout text block limit 阶段已经丢失。
- Table 5 的 caption 属于上方小表，但局部方向证据在上下两张表之间打平后回到默认 `below`，最终截到了下方 Table 6；这是方向级错误，不能接受。

关键边界：

| 图表 | 20260620-020 final | 20260620-021 final | 判断 |
| --- | --- | --- | --- |
| Table 1 | `57.4,113.1 -> 537.9,254.9` | `57.4,86.8 -> 537.9,254.9` | 修复后包含顶部模型分组表头 |
| Table 2 | `174.1,105.6 -> 421.5,185.7` | `174.1,87.1 -> 421.5,185.7` | 修复后包含 `Model / AI Studio model ID` |
| Table 5 | `57.4,209.5 -> 537.9,423.9` | `57.4,82.6 -> 537.9,156.0` | 修复后从下方 Table 6 切回上方 Table 5 |
| Table 10 | `57.4,230.9 -> 537.9,420.0` | `57.4,86.2 -> 537.9,420.0` | 修复后包含表头和 CBRN 首组完整内容 |
| Table 11 | `63.2,107.6 -> 532.4,363.8` | `63.2,87.1 -> 532.4,363.8` | 修复后包含三列表头 |

根因：

- `expand_clip_to_nearby_table_header()` 只放在 layout blocker 之后，能修 Table 3 这类 baseline 已被压低的表头，但不能处理 final autocrop 对表头的二次裁切。
- `expand_table_clip_to_text_bounds()` 旧逻辑只做 `max_expand=8pt` 的贴字补边，无法恢复距离 final 边界 15-140pt 的表头或上半段表格内容。
- Table 10 的上半段被 layout blocker 当作 `paragraph_group` 外部正文裁掉，但这些文字实际上是表格内部长单元格，不符合“短表头”假设。
- Table 5 上下两侧都有表格文本证据，旧 `score_local_direction()` 在分数接近时没有利用“下方很快出现下一张 Table caption”这个负证据，最终落回 Table 默认 `below`。

实际调整：

- `score_local_direction()` 的 Table 路径在上下表格证据接近时，新增下一张 caption 负证据：如果下方搜索带内出现后续 Table/Figure caption，且上方结构化表格行也紧贴当前 caption，则优先选择 `above`。
- `expand_table_clip_to_text_bounds()` 从小幅贴字补边扩展为 final-only 的连通文本行带回补：只有当前 final 已经像表格时，才沿远离 caption 的一侧按行距连通性向 reference clip 回补表头或上半段表格。
- `extract_tables.py` 将 final 回补的 reference 改为 layout text block limit 之前的窗口，而不是已经被裁短的 `clip`，使 Table 10 这类早期丢失内容仍有恢复上下文。
- 这三处均为 Table-only；Figure 路径、全局 autocrop 参数、Table caption 识别和 Table X 宽度恢复规则不变。

验证：

- 新增回归测试：`test_table_final_text_bounds_recovers_connected_header_band`。
- 新增回归测试：`test_table_direction_tie_break_prefers_nearest_structured_table`。
- `python -m pytest tests/scripts/test_caption_anchor_quality.py -q`：52 通过、0 失败。
- `python -m pytest tests/scripts/test_maintenance_fixes.py -q`：13 通过、0 失败。
- `python -m compileall skills/pdf-markdown-summary/scripts`：通过。
- 入口脚本 `--help` 通过：`extract_pdf_assets.py`、`pdf_to_markdown.py`、`process_pdf.py`、`summarize_pdf.py`。
- 重跑 Gemini 到 `tests/results/20260620-021/gemini_v2_5_report/`，Table 1/2/5/10/11 目视通过。

风险与权衡：

- final 连通行带回补可能让红线比纯像素 autocrop 更高，但它只在当前 final 已像表格时触发，并且只沿行距连续的表格文本回补；遇到明显段落间隔会停止。
- 方向 tie-break 依赖“下方出现下一张 caption”的负证据，不改变有高置信局部方向证据的 case；如果上下都是相邻短表且缺少后续 caption，仍会保持原有评分逻辑。
- Table 10 这类长文本单元格本质上不像传统短数字表，不能用“短表头”规则解决；因此单独引入 final/reference 连通行带，而不是继续放宽 layout blocker。

### Gemini 2.5 Report Tables 第三轮复核：final 连通行带误吃正文与正文前缀残留

文件：

`tests/results/20260620-021/gemini_v2_5_report/images/debug/Table_4_p13_debug_stages.png`

`tests/results/20260620-021/gemini_v2_5_report/images/debug/Table_6_p14_debug_stages.png`

`tests/results/20260620-021/gemini_v2_5_report/images/debug/Table_12_p70_debug_stages.png`

现象：

- Table 4 的红线从 `y0=347.1pt` 开始，吃入 `Video Understanding` 小节标题和说明正文；真实表格表头在 `y≈433.7pt`。
- Table 6 的红线从 `y0=179.5pt` 开始，吃入上一张 Table 5 的 caption 延续说明；真实表格表头在 `y≈217.8pt`。
- Table 12 的红线从 `y0=484.5pt` 开始，包含 `1/3 cases...` 这一段正文尾句；真实表格表头是 `Model / Trial / Model response`，在 `y≈517.8pt`。

关键边界：

| 图表 | 20260620-021 final | 20260620-027 final | 判断 |
| --- | --- | --- | --- |
| Table 4 | `57.4,347.1 -> 537.9,703.2` | `57.4,427.7 -> 537.9,703.2` | 修复后不再吃入小节标题和说明正文，保留表头 |
| Table 6 | `57.4,179.5 -> 537.9,425.9` | `57.4,211.8 -> 537.9,425.9` | 修复后不再吃入上一表 caption/说明，保留表头 |
| Table 12 | `57.7,484.5 -> 526.4,734.3` | `57.7,515.3 -> 526.4,734.3` | 修复后排除正文尾句，从表头开始 |
| Table 5 | `57.4,82.6 -> 537.9,156.0` | `57.4,82.6 -> 537.9,156.0` | 方向修复无回退 |
| Table 10 | `57.4,86.2 -> 537.9,420.0` | `57.4,86.2 -> 537.9,420.0` | 上半段表格回补无回退 |

根因：

- BUG-034 的 final 连通行带回补只按行距连续性向远离 caption 的一侧扩张，没有区分“表格行”与“正文段落行”；Table 4/6 的上方正文正好与表头距离很近，于是被当作连通行带一起纳入 final。
- Table 12 不是扩张过头，而是 final 输入本身已经包含正文尾句；旧逻辑只会扩张和贴字补边，不会主动裁掉已进入 final 的正文前缀。
- Table 12 的正文尾句含 `1/3`、`2/3`、`3 seconds` 等数字，不能简单用“短文本 + 多数字”识别为表格行，否则会把正文尾句当成结构化表格起点。

实际调整：

- `expand_table_clip_to_text_bounds()` 的行分组增加 `part_count + text` 元信息，区分多片段结构化表格行、宽长正文行、普通短行。
- final 连通行带回补遇到宽长正文行或非表格行即停止，不再跨过正文段落继续向上扩。
- 新增 final-only 正文前缀/后缀裁除：当 Table final 远离 caption 一侧先出现正文行、后面才出现结构化表格行时，将红线收回到第一条结构化表格行前。
- 正文前缀裁除里的结构化表格行只接受 `part_count >= 2`，不再接受单行多数字文本，避免 Table 12 的 `1/3 cases...` 误触发。
- `looks_like_table_text()` 的早退从裁除前移到裁除后；如果没有成功裁除且当前区域仍不像表格，仍然保持早退，不放宽非表格候选。

验证：

- 新增回归测试：`test_table_final_text_bounds_stops_before_body_paragraph`。
- 新增回归测试：`test_table_final_text_bounds_recovers_header_but_not_leading_body_line`。
- `python -m pytest tests/scripts/test_caption_anchor_quality.py -q`：54 通过、0 失败。
- `python -m pytest tests/scripts/test_maintenance_fixes.py -q`：13 通过、0 失败。
- `python -m compileall skills/pdf-markdown-summary/scripts`：通过。
- 入口脚本 `--help` 通过：`extract_pdf_assets.py`、`pdf_to_markdown.py`、`process_pdf.py`、`summarize_pdf.py`。
- 重跑 Gemini 到 `tests/results/20260620-027/gemini_v2_5_report/`，Table 4/6/12 目视通过，并核对 Table 5/10 无回退。

风险与权衡：

- 该修复只在 Table final 文本 bbox 安全补边函数内生效，不影响 Figure 路径和全局 autocrop。
- 对单列、单片段的表格表头，正文前缀裁除会更保守，可能不主动裁除；这是有意取舍，因为单片段短文本与正文尾句不可稳定区分。
- 连通行带回补仍保留 BUG-034 的能力，但新增正文 blocker 后，不再跨正文段落恢复远处表格内容。

### Qwen3-Omni Tables：表格远端误吞紧邻的章节标题

文件：

`tests/results/20260620-028/2509.17765v1-Qwen3-Omni_Technical_Report/images/debug/Table_5_p10_debug_stages.png`

`tests/results/20260620-028/2509.17765v1-Qwen3-Omni_Technical_Report/images/debug/Table_8_p11_debug_stages.png`

`tests/results/20260620-028/2509.17765v1-Qwen3-Omni_Technical_Report/images/debug/Table_12_p13_debug_stages.png`

`tests/results/20260620-028/2509.17765v1-Qwen3-Omni_Technical_Report/images/debug/Table_14_p14_debug_stages.png`

`tests/results/20260620-028/2509.17765v1-Qwen3-Omni_Technical_Report/images/debug/Table_15_p14_debug_stages.png`

`tests/results/20260620-028/2509.17765v1-Qwen3-Omni_Technical_Report/images/debug/Table_18_p17_debug_stages.png`

现象：

- 这 6 张表都是 caption 在上、表格在下（`direction=below`），final 红框底部统一多吞了表格正下方紧邻的“章节标题”。
- Table 5 吞入 `Performance of Audio→Text`，Table 8 吞入 `Performance of Vision →Text`，Table 12 吞入 `Evaluation of X→Speech`，Table 14 吞入 `Evaluation of Cross-Lingual Speech Generation`，Table 15 吞入 `6 Evaluating Non-Degradation Across Modalities`，Table 18 吞入 `Qualitative Results from Qwen3-Omni-30B-A3B-Captioner`。
- 表格主体本身完整，问题只在远端（底部）多了一条不属于表格的标题。

关键边界：

| 图表 | 20260620-028 final | 20260620-031 final | 被排除的章节标题(块顶) |
| --- | --- | --- | --- |
| Table 5 | `66.1,267.4 -> 529.5,433.9` | `66.1,267.4 -> 529.5,414.4` | Performance of Audio→Text (420.4) |
| Table 8 | `65.8,555.7 -> 529.5,746.0` | `65.8,555.7 -> 529.5,726.5` | Performance of Vision →Text (732.5) |
| Table 12 | `68.4,299.9 -> 526.9,388.5` | `68.4,299.9 -> 526.9,369.0` | Evaluation of X→Speech (375.0) |
| Table 14 | `68.4,197.5 -> 519.9,394.1` | `68.4,197.5 -> 519.9,375.6` | Evaluation of Cross-Lingual... (381.6) |
| Table 15 | `86.3,524.9 -> 449.6,720.2` | `86.3,524.9 -> 449.6,699.7` | 6 Evaluating Non-Degradation (705.7) |
| Table 18 | `65.8,521.2 -> 529.3,711.7` | `65.8,521.2 -> 529.3,693.3` | Qualitative Results from... (699.3) |
| Table 2 | `99.0,529.8 -> 496.4,677.9` | `99.0,529.8 -> 496.4,677.9` | 误判表格行，未裁（见“风险与权衡”） |

根因：

- 这些章节标题的编号（`5.1.2` / `5.2` / `9.2`）被 PDF 抽取拆到了后面的正文段落里（如 layout 块文本是 `5.1.2 We compare...`），导致标题块只剩下 `Performance of Audio→Text` 这种**无编号短标题**。
- 该形态绕过了 `refine_clip_to_table_band()`、far-side 文本检测里所有“编号章节标题”过滤（`^\d+(\.\d+)+\s+\S` 等），因此既不会被识别为外部标题，也不会被当作正文裁掉。
- Phase A 的远端裁切只清理“宽正文段落”，不清理这种单行短标题；autocrop 在 `table_band_changed` 时还会跳过 far-side 文本裁切。最终这条 layout `title_` 块残留在表格远端被纳入红框。
- 其稳定共性：它们都是远端的 layout `title_` 块，且紧跟其后就是一整段满宽正文段落（章节标题后必有正文），而表格列表头永远在近端、其后是表格数据行而非正文段落——这给了可靠判别信号。

实际调整：

- 新增 `trim_table_far_side_section_heading()`，仅在 Table 路径、`expand_table_clip_to_text_bounds()` 之后运行，按方向从 final 远端剔除紧跟表格的章节标题。
- 判定一个远端 `title_` 块为章节标题需同时满足：位于 final 远端 60% 区域、远离 caption、其外侧紧邻一段满宽正文段落、且其外侧没有 ≥2 行窄表格单元格。
- 防误裁守卫 `_has_same_row_data_cell()`：只看标题**右侧**同一行带是否有并排的数字数据列。若有（如被误判为标题的表格末行 `Generation RTF(...) 0.47 0.56 0.66`），说明它其实是表格行而非标题，保留不裁；章节编号 `5.1.2` 位于标题左侧，被显式排除以免误伤真正的章节标题。
- 该逻辑只缩小 final 远端边界，不修改 baseline、Phase A/B、autocrop、Table 宽度/尾部恢复或 Figure 路径。

验证：

- 新增回归测试：`test_table_far_side_trims_trailing_section_heading`（复刻 Table 5：标题被裁，cut 到 `heading.y0-6`）。
- 新增回归测试：`test_table_far_side_keeps_misclassified_last_data_row`（复刻 Table 2：右侧带数据列的误判行被保留）。
- `python -m pytest tests/scripts -q`：95 通过、0 失败（原 93 + 新增 2）。
- `python -m compileall skills/pdf-markdown-summary/scripts/lib/refine.py`：通过。
- 入口脚本 `--help` 通过：`extract_pdf_assets.py`、`pdf_to_markdown.py`、`process_pdf.py`、`summarize_pdf.py`。
- 重跑 Qwen3-Omni 到 `tests/results/20260620-031/2509.17765v1-Qwen3-Omni_Technical_Report/`：用户列出的 6 张表全部修复，Table 16（`7 Conclusion`）同因连带修复，Table 2 正确保留，其余表 final 与 028 完全一致（无回退）。
- 同批重跑 Gemini / GPT-5（`tests/results/20260620-031/`）：所有 Table final 要么不变、要么是其它已合并修复带来的“变高”（本次只会缩小，不会增高），即新裁剪未在这两份 PDF 误触发。

风险与权衡：

- 守卫依赖“标题右侧有并排数字数据列”来识别被误判为标题的表格末行；若某真实章节标题右侧恰好有独立数字（罕见），会保守地不裁（保持旧行为），不会误删表格内容。
- 仅处理紧贴表格、外侧紧邻满宽正文段落的远端标题；若标题与表格之间间隔很大或外侧不是正文段落，则不裁。
- `above` 方向也对称实现，但 6 个失败样本均为 `below`；`above` 分支同样要求“外侧紧邻满宽正文段落 + 无右侧数据列”，避免把表格自身的列表头当成标题裁掉。

### 多 PDF Table 回归：远端章节标题裁除误伤表头 / 数据行

文件：

`tests/results/20260620-033/1706.03762v7-attention_is_all_you_need/images/debug/Table_2_p8_debug_stages.png`

`tests/results/20260620-033/FunAudio-ASR/images/debug/Table_2_p9_debug_stages.png`

`tests/results/20260620-033/FunAudio-ASR/images/debug/Table_4_p10_debug_stages.png`

`tests/results/20260620-033/gemini_v2_5_report/images/debug/Table_2_p6_debug_stages.png`

`tests/results/20260620-033/gemini_v2_5_report/images/debug/Table_4_p13_debug_stages.png`

`tests/results/20260620-033/gemini_v2_5_report/images/debug/Table_6_p14_debug_stages.png`

`tests/results/20260620-033/gemini_v2_5_report/images/debug/Table_10_p27_debug_stages.png`

`tests/results/20260620-033/gemini_v2_5_report/images/debug/Table_12_p70_debug_stages.png`

`tests/results/20260620-033/KearnsNevmyvakaHFTRiskBooks/images/debug/Table_1_p8_debug_stages.png`

现象：

- Attention Table 2 的 final 红框底部被裁到 `y1=211.7`，漏掉 `Transformer (base model)` / `Transformer (big)` 两行。
- Gemini Table 2/4/6/10/12 与 Kearns Table 1 的 final 红框顶部被裁到表头下方，漏掉多列表头或关键列名。
- FunAudio Table 4 则是相反问题：红框顶部仍包含 `6.2.3 Evaluation on Noise Robustness` 章节标题，需要继续剔除。
- FunAudio Table 2 本轮目视没有问题，作为“不应被本轮修复影响”的保留样本。

根因：

- BUG-036 的 `trim_table_far_side_section_heading()` 只针对 Qwen3-Omni 的 `below` 表格尾部样本设计，判定“远端 title 后面有正文段落”即可裁除。
- Gemini / Kearns 的表头中存在被 layout 模型标成 `title_h3` 的短列名，例如 `Key Results for Gemini 2.5 Pro`、`CCL reached?`、`Feature(s) Added`；这些标题块后面紧跟的不是正文，而是多列数据行，但旧守卫没有充分利用“同一行带存在其他表格单元格”和“后续行是结构化表格行”。
- Attention Table 2 的 `3.3 · 10^18` 是最右侧数据单元格，被误判为 `title_h3`。旧守卫偏向检查右侧并排数字列，对最右侧单元格失效。
- FunAudio Table 4 是 `above` 方向，章节编号 `6.2.3` 与标题文本在同一行但分裂为不同文本行；旧 `above` 分支对“标题外侧正文”的检查方向不够准确，导致没有裁掉章节标题。

实际调整：

- 将 `_has_same_row_data_cell()` 升级为 `_has_same_row_table_context()`：同一行带同时检查标题左右两侧的短单元格 / 数字单元格，排除纯章节编号，覆盖 Attention 这类最右侧数据单元格。
- 新增 `_has_near_table_header_context()`：当 `title_` 块附近存在多片段表头/数据行时，优先视为表格内部内容，不作为章节标题裁除。
- 新增 `_is_body_paragraph()`：章节标题后必须跟随“足够长、足够宽、带句子/章节语义”的正文段落；短数字行、短单元格行不再触发章节标题裁除。
- 新增 `_has_near_section_number()`：支持章节编号与标题拆成同基线两段文本的场景，用于保留 FunAudio Table 4 的章节标题裁除能力。
- `above` / `below` 共用同一套候选判定，只在最终 cut 方向上对称处理，避免针对单一方向的隐含偏差。

验证：

| 图表 | 20260620-033 final | 20260621-001 final | 结论 |
| --- | --- | --- | --- |
| Attention Table 2 | `125.8,93.3 -> 486.3,211.7` | `125.8,93.3 -> 486.3,246.9` | 底部两行恢复 |
| FunAudio Table 2 | `103.0,550.3 -> 509.1,689.9` | `103.0,550.3 -> 509.1,689.9` | 无回退 |
| FunAudio Table 4 | `135.4,281.1 -> 421.0,478.7` | `135.4,299.5 -> 421.0,478.7` | 顶部章节标题剔除 |
| Gemini Table 2 | `174.1,105.6 -> 421.5,185.7` | `174.1,87.1 -> 421.5,185.7` | 表头恢复 |
| Gemini Table 4 | `57.4,453.3 -> 537.9,703.2` | `57.4,427.7 -> 537.9,703.2` | 表头恢复 |
| Gemini Table 6 | `57.4,242.1 -> 537.9,425.9` | `57.4,211.8 -> 537.9,425.9` | 表头恢复 |
| Gemini Table 10 | `57.4,117.1 -> 537.9,420.0` | `57.4,86.2 -> 537.9,420.0` | 表头恢复 |
| Gemini Table 12 | `57.7,534.7 -> 526.4,734.3` | `57.7,515.3 -> 526.4,734.3` | 表头恢复 |
| Kearns Table 1 | `83.9,425.8 -> 478.9,494.5` | `83.9,384.5 -> 478.9,494.5` | 表头恢复，仅多留少量安全空白 |

新增回归测试：

- `test_table_far_side_keeps_header_followed_by_table_rows`
- `test_table_far_side_trims_numbered_section_heading_above_table`
- `test_table_far_side_keeps_same_row_data_cell_at_far_edge`

风险与权衡：

- 这次没有放宽 Table autocrop，也没有改全局 text blocker；只在 BUG-036 新增的 Table-only 远端章节标题裁除函数内增强判定。
- 遇到无法可靠区分的短单片段标题时，策略偏保守：宁可不裁章节标题，也不裁掉表头或表格末行。
- Kearns Table 1 的 final 顶部会保留一点空白，这是保护表头的代价；比误裁列名更可接受。

### GPT-5 System Card Figure 22：裸 Figure caption 被下方下一张图吸走

文件：

`tests/results/20260620-033/gpt-5-system-card/images/debug/Figure_22_p39_debug_stages.png`

现象：

- Caption 只有独立居中的 `Figure 22`，真实内容是 caption 上方的分子图与 InChI 公式。
- 旧方向判定被下方 Figure 23 的柱状图对象面积吸引，final 红框跑到下方 Figure 23，漏掉 Figure 22 的公式/化学式图片。

根因：

- `score_local_direction()` 对 Figure 主要依赖上下对象覆盖率；当 caption 是裸 `Figure N` 且下方下一张图对象更大时，会把下一张图当作当前图内容。
- 这类裸 caption 没有冒号说明文本，不能用一般 caption 文本长度或语义区分方向。

实际调整：

- 新增 `correct_bare_figure_caption_direction()`，只在 Figure 路径生效。
- 触发条件很窄：当前方向已判为 `below`、caption 文本必须是裸 `Figure N` / `Fig. N`、同页下方存在下一张 Figure caption、caption 上方近处有 image/vector 对象证据，且该对象与页面横向有足够重叠。
- Figure 提取时复用同页高分 Figure caption 列表，同时用于裸 caption 方向纠偏和相邻 caption 窗口限制。

验证：

| 图表 | 20260620-033 final | 20260621-001 final | 结论 |
| --- | --- | --- | --- |
| GPT-5 Figure 22 | `68.6,272.9 -> 528.0,504.5` | `44.9,139.7 -> 550.4,233.4` | 从下方 Figure 23 纠正到上方公式/化学式图 |

新增回归测试：

- `test_bare_figure_caption_prefers_above_when_next_caption_below`
- `test_bare_figure_caption_keeps_below_without_above_object`

风险与权衡：

- 该修复不会影响普通带标题说明的 Figure caption，也不会影响 Table。
- 如果裸 `Figure N` 上方没有对象证据，即使下方有后续 caption，也保持原方向，避免凭 caption 形态强行反转。

### 20260621 剩余瑕疵收口：Table final 远端空白、正文尾巴与末行回补

文件：

`tests/results/20260621-001/2509.17765v1-Qwen3-Omni_Technical_Report/images/debug/Table_16_p15_debug_stages.png`

`tests/results/20260621-001/2509.17765v1-Qwen3-Omni_Technical_Report/images/debug/Table_2_p6_debug_stages.png`

`tests/results/20260621-001/FunAudio-ASR/images/debug/Table_2_p9_debug_stages.png`

`tests/results/20260621-001/KearnsNevmyvakaHFTRiskBooks/images/debug/Table_1_p8_debug_stages.png`

`tests/results/20260621-001/gpt-5-system-card/images/debug/Figure_29_p45_debug_stages.png`

现象：

- Qwen3-Omni Table 16 的 final 红框继续把表格下方 `7 Conclusion` 纳入截图；这是 BUG-036 同类问题，但单级编号 `7` 与标题在同一文本块里，旧的“拆分章节编号”判断覆盖不到。
- Qwen3-Omni Table 2 的 final 红框漏掉最后一行 `Generation RTF(Real Time Factor)`；该行左侧被 layout 判成 `title_h3`，右侧数字块在部分文本行证据里缺失。
- FunAudio-ASR Table 2 与 Kearns Table 1 的 final 红框保留了远端大空白或上一段正文尾巴；表格主体完整，但截图不够干净。
- GPT-5 System Card Figure 29 目视复核后红框只覆盖图像本体，本轮未发现需要修改 Figure 路径的问题。

根因：

- `expand_table_clip_to_text_bounds()` 之前主要做文字 bbox 安全补边和连通行带回补；它能恢复被 final autocrop 裁掉的表头/末行，但对“已经进入 final 的远端空白或正文尾巴”缺少二次收紧。
- 弱表格 final 不满足 `looks_like_table_text()` 时，旧逻辑会直接返回，导致 Qwen Table 2 这种“真实末行在 final 外侧、且末行部分证据来自 layout block”的场景无法回补。
- `trim_table_far_side_section_heading()` 的同排数据保护依赖 `text_lines`；当同排数字块只可靠存在于 layout block 中时，保护证据不足，容易在章节标题裁除与真实末行保留之间摇摆。

实际调整：

- `expand_table_clip_to_text_bounds()` 新增 Table-only 的远端结构行收紧：只在 far side 存在大空白或正文尾句，且后续能找到强结构表格行时，把红框收回到首个/最后一个结构化表格行附近。
- 对弱表格 final 先尝试远端连通行回补，再尝试 layout 同排数据块回补，避免因为当前 final 太短就直接放弃真实末行。
- `trim_table_far_side_section_heading()` 的 `_has_same_row_table_context()` 增加 layout 同排 peer block 检查，纯章节编号仍排除，短数字/短单元格 peer 可保护真实表格末行。
- Figure 29 没有进入上述 Table-only 逻辑，保持原 Figure 裁剪链路。

验证：

| 图表 | 20260621-001 final | 修复后 final | 结论 |
| --- | --- | --- | --- |
| Qwen Table 2 | `99.0,529.8 -> 496.4,656.7` | `99.0,529.8 -> 496.4,677.9` (`20260621-004`) | 末行 `Generation RTF` 与右侧数字恢复 |
| Qwen Table 16 | `66.1,374.4 -> 527.1,739.3` | `66.1,374.4 -> 527.1,701.4` (`20260621-004`) | `7 Conclusion` 被剔除，表格底行保留 |
| FunAudio Table 2 | `103.0,550.3 -> 509.1,689.9` | `103.0,582.5 -> 509.1,689.9` (`20260621-002`) | 顶部大空白收紧，表格主体完整 |
| Kearns Table 1 | `83.9,384.5 -> 478.9,494.5` | `133.3,406.4 -> 478.9,494.5` (`20260621-002`) | 上方正文尾句剔除，表头与表格保留 |
| GPT-5 Figure 29 | `44.9,328.7 -> 550.4,400.4` | `44.9,328.7 -> 550.4,400.4` (`20260621-002`) | 未受本轮 Table 修复影响 |

新增回归测试：

- `test_table_final_text_bounds_recovers_qwen_table2_tail_row`
- `test_table_final_text_bounds_recovers_tail_row_from_layout_blocks`
- `test_table_final_text_bounds_trims_far_side_blank_before_table`
- `test_table_final_text_bounds_trims_body_tail_before_header`
- `test_table_far_side_trims_single_number_section_heading`
- `test_table_far_side_keeps_layout_only_same_row_data_cell`

风险与权衡：

- 这轮仍不改全局 autocrop、不改 Figure 路径、不改 layout blocker 阈值；所有新逻辑都在 Table final 或 Table 远端章节标题裁除内。
- 远端收紧要求“强结构表格行”作为安全边界，避免把正文里的短数字句误当表格；代价是极少数单列、无数字、无多片段的表格不会被主动收紧。
- layout 同排 peer block 只作为保护/回补证据，不会单独触发大范围扩张，避免重新引入 Gemini 表格正文污染问题。

### 20260621 二次收口：Gemini Table 12 数字正文回归、GPT-5 Figure 29 正文尾句与 Table 16 换行尾行

文件：

`tests/results/20260621-006/gemini_v2_5_report/images/debug/Table_12_p70_debug_stages.png`

`tests/results/20260621-006/gpt-5-system-card/images/debug/Figure_29_p45_debug_stages.png`

`tests/results/20260621-006/gpt-5-system-card/images/debug/Table_16_p29_debug_stages.png`

现象：

- Gemini Table 12 的红框再次把表格上方正文尾句 `1/3 cases...` 纳入截图。
- GPT-5 Figure 29 的最终导出图顶部带入上一段正文尾句 `of such behaviors.`；debug 红框看起来只是贴近图顶，但最终 PNG 能明显看到正文残留。
- GPT-5 Table 16 的红框底部切掉第二行 `Cyber Range` 描述单元格的最后一行 `network?` 和底部横线。

根因：

- BUG-039 为了恢复弱 final 的末行，把 `_trim_far_side_to_first_structured_row()` 的“强结构行”放宽成 `part_count >= 2 or numeric_count >= 2`。这重新打开了 BUG-035：Gemini Table 12 的正文尾句含 `1/3`、`2/3`、`3 seconds`，被误当成表格起点。
- GPT-5 Figure 29 的正文尾句较窄，未达到 `trim_far_side_text_post_autocrop()` 的正文宽度阈值；随后 `expand_clip_to_nearby_figure_title()` 又把它当作紧贴图主体的图内标题回收。
- GPT-5 Table 16 的 `network?` 是同一表格单元格的换行短尾行，因短且带问号，被 Table final 远端噪声收紧误当作 trailing noise。

实际调整：

- Table final 远端收紧的安全起点恢复为只接受 `part_count >= 2`，不再把单行多数字正文当成强结构表格行；真实末行回补继续交给连通行与 layout 同排 peer 逻辑。
- Table `below` 方向的远端收紧增加“短换行尾行”保护：当短单片段尾行紧贴多片段表格行、宽度较窄且不是编号章节标题时，不作为噪声裁掉。
- Figure autocrop 后的正文修剪增加小写正文尾句识别；图内标题回收也排除“小写开头 + 句末标点”的正文尾句，避免先裁掉又被回收。

验证：

| 图表 | 20260621-006 final | 修复后 final | 结论 |
| --- | --- | --- | --- |
| Gemini Table 12 | `57.7,488.0 -> 526.4,734.3` | `57.7,515.3 -> 526.4,734.3` (`20260621-007`) | 正文数字尾句剔除，从表头开始 |
| GPT-5 Table 16 | `76.4,169.7 -> 519.0,262.1` | `76.4,169.7 -> 519.0,277.7` (`20260621-009`) | `network?` 和底部横线恢复 |
| GPT-5 Figure 29 | `44.9,328.7 -> 550.4,400.4` | `44.9,342.8 -> 550.4,400.4` (`20260621-009`) | 顶部正文尾句剔除，图主体完整 |

新增回归测试：

- `test_table_final_text_bounds_trims_numeric_body_tail_before_header`
- `test_table_final_text_bounds_keeps_wrapped_tail_cell_line`
- `test_figure_noise_trim_ignores_sentence_tail_as_content_evidence`
- `test_figure_post_autocrop_trims_narrow_lowercase_sentence_tail`
- `test_figure_title_recovery_ignores_lowercase_sentence_tail`

风险与权衡：

- Table 的数字弱行回补没有删除，只是不再作为“远端收紧安全起点”；这避免正文数字句污染，同时仍保留 Qwen Table 2 这类真实末行回补。
- `network?` 保护只在 `below` 方向、紧贴多片段表格行、短窄单行时触发；后续章节标题仍由 `trim_table_far_side_section_heading()` 裁除。
- Figure 小写正文尾句规则只处理明显正文残片，不影响无句末标点的图内短标题、轴标题和面板标签。

## 当前策略冲突清单

| 策略 | 主要收益 | 已发现风险 | 关联图表 |
| --- | --- | --- | --- |
| far-side 正文检测 | 避免 autocrop 把远端正文纳入最终截图 | 会误伤短图内标签 | Attention Figure 2 |
| Phase B 对象对齐 | 去掉空白，贴近图形主体 | 单对象面积阈值会丢掉小对象密集图的真实内容 | Attention Figure 3 |
| Phase B 文本标签保护 | 保留 dense label figure 中的图内竖排文字 | 若阈值过松可能把正文标签化；当前用窄框、多数量、行带覆盖来约束 | Attention Figure 5 |
| Table 渲染横线补偿 | 在 `get_drawings()` 为空时补回肉眼可见的表格横线 | 依赖像素阈值；需限制在 caption 与 near edge 的窄搜索带内 | Attention Table 2 |
| Layout blocker 短标签聚类保护 | 防止图内 `Query`/`Response` 等短标签被当作远端正文标题截断 baseline | 阈值过松会放过真实远端短章节标题；当前仍要求多个短标签互相支持 | Qwen3-Omni Figure 1 |
| Figure far-side 页眉噪声清理 | 避免 autocrop 把页眉横线当作图内容纳入红框 | 真实图顶部若只有单独细横线，可能被视为噪声；需依赖真实内容证据约束 | Qwen3-Omni Figure 1 |
| Table layout 尾部恢复 | 避免 layout far-strip 把表格内部数字行当作远端正文裁掉 | 若真实正文尾部大量短数字化，可能误恢复；当前要求被裁尾部满足表格文本特征 | Qwen3-Omni Table 9 |
| Table final 文本 bbox 安全补边 | 避免 pixel autocrop 让红框贴住或切进表格文字 | 若错误 final 已像表格且附近有短文本，可能小幅扩张；当前限制在 caption 前和 final 近邻范围 | FunAudio-ASR Table 5 |
| Phase A+ 精确两行裁切 | 处理 near-caption 侧恰好两行正文残留 | 会把窄轴刻度误当正文行；当前要求候选行具备最小宽度 | Gemini Figure 3 |
| Figure 图内标题回收 | 保留紧贴图主体的 chart title / 图内题目 | 若标题与外部小标题距离过近可能混淆；当前跳过页眉、编号章节标题和拆开的同基线章节编号标题，并增加字号上限 | Gemini Figure 5/12；Qwen3-Omni Figure 3；Attention Figure 3 |
| Figure 小写正文尾句裁除 | 清理 final 顶部/底部带入的正文残片 | 若真实图内标题本身是小写句子且带句末标点，可能被裁；当前只作为正文尾句负例，不影响短标签与无标点图内标题 | GPT-5 Figure 29 |
| Phase A/B 短轴标题补边 | 保留低字号短图题、轴标题和子图标题 | 若放宽到长文本会重新吃入正文；当前要求低字号、短文本、贴近对象或贴近被裁边界 | Kearns Figure 4/6/7 |
| Phase B near-caption 图内标注保护 | 防止对象对齐把子图说明、Prompt 文本等图内标注裁掉 | 若过宽会保留正文污染；当前返回局部边界，要求面板前缀或窄列多行形态，并排除 caption/章节标题 | Gemini Figure 14/15 |
| 双栏版式几何校验 | 防止单栏文档被伪双栏 X 裁列截成窄条 | 真实异常宽列距双栏可能回退成单栏而偏宽；后续仍交给对象/autocrop 收窄 | GPT-5 System Card Figures |
| Table 多行表头回收 | 恢复被 layout blocker 裁掉的紧邻表头 | 若正文伪装成短多列表头且紧贴表格，可能小幅误恢复；当前要求下方已有表格行证据 | Gemini Table 1/3 |
| Table final 连通行带回补 | 恢复 final autocrop 或早期 layout blocker 裁掉的表头/上半段表格 | 可能比纯像素边界略宽；当前要求 final 已像表格且行距连续，遇到段落间隔停止 | Gemini Table 1/2/10/11 |
| Table final 正文 blocker 与前缀裁除 | 防止连通行带把近邻正文并入表格，并裁掉已进入 final 的正文尾句 | 对单片段表头更保守，可能不主动裁；当前只接受多片段结构化表格行作为正文后的安全起点 | Gemini Table 4/6/12 |
| Table final 远端空白/正文收紧 | 清理 final 已经纳入的远端空白或正文尾巴 | 只在有多片段强结构表格行时触发，单列弱结构表格可能保持偏宽；单行多数字正文不再作为安全起点 | FunAudio Table 2；Kearns Table 1；Gemini Table 12 |
| Table final 换行尾行保护 | 保留表格单元格中紧贴主行的短换行尾行 | 若真实章节标题极短且紧贴表格，可能暂时保留；后续章节标题裁除函数继续兜底 | GPT-5 Table 16 |
| Table final layout 同排末行回补 | 在 `text_lines` 缺失同排数字时，利用 layout block 保护/恢复真实表格末行 | 若 layout 把正文短块误排成同行，可能误扩；当前要求贴近 far edge、同排 peer 非长正文且非纯章节编号 | Qwen3-Omni Table 2 |
| Table 方向近邻 caption 负证据 | 解决上下两张表夹着当前 caption 时默认 below 抓错表 | 只处理下方出现后续 caption 且上方也紧贴表格的近似平分场景，不覆盖所有方向歧义 | Gemini Table 5 |
| Table 远端章节标题裁除 | 剔除被误吞到表格远端、编号被拆走或单级编号的章节标题 | 容易误伤被 layout 标成 `title_h3` 的表头或最右侧数据单元格；当前用同一行带表格上下文、附近表头结构、正文语义、章节编号和 layout 同排 peer 共同约束 | Qwen3-Omni Table 5/8/12/14/15/16/18；Attention Table 2；Gemini Table 2/4/6/10/12；Kearns Table 1；FunAudio Table 4 |
| Figure 裸 caption 方向纠偏 | 防止独立 `Figure N` caption 被下方下一张大图吸走 | 只在裸 `Figure N`、下方存在下一 Figure caption、上方近处有对象证据时反转；无法覆盖有长 caption 的复杂方向歧义 | GPT-5 System Card Figure 22 |
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
