# 任务跟踪列表

记录本项目所有任务：代码 bug、需求调整、功能开发、代码审查、测试数据、文档维护、配置运维等。

> 说明：本文件是当前项目的任务清单。所有新增事项、状态变更和完成记录都应同步写入本文件。
> 字段说明：动作字段只允许以下 8 个固定枚举：修复、开发、优化、调整、规划、检查、文档、运维。
> 时间说明：发现时间和完成时间分开记录，格式为 YYYY-MM-DD HH:MM，使用机器本地时区的 24 小时制时间；未完成事项的完成时间填 -。
> 归并规则：审计、复核、核查、审查、验证、评估统一记为“检查”；重构、清理统一记为“优化”；方案、梳理统一记为“规划”；记录类文档事项统一记为“文档”。

## 代码 Bug

| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| BUG-001 | 修复 | 图表 caption 索引候选未评分，导致最佳 caption 过滤失效并把正文引用当作截图锚点 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已修复 | `build_caption_index()` 现在会为候选项计算 score；`get_best_for_page()` 对跨页兜底也执行最低分限制 |
| BUG-002 | 修复 | 截图正文污染检测失败后回退到 baseline 继续保存错误图片 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已修复 | 新增 `detect_text_pollution()`；Figure/Table 主循环遇到污染结果直接拒绝当前候选 |
| BUG-003 | 修复 | 双栏右栏 X 方向裁剪把 `margin_right` 当作边距数值使用，导致右栏边界计算错误 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已修复 | `refine_clip_x_range()` 改为把 `layout_model.margin_right` 作为页面右边界坐标使用 |
| BUG-004 | 修复 | 同页相邻 Figure/Table caption 未限制 baseline 窗口，导致连续图表场景混截上一张或下一张图 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已修复 | 新增 `limit_clip_by_neighbor_captions()`；Figure/Table baseline 使用同页高分 caption 收紧 y 边界，DeepSeek Figure 3 已验证不再混入 Figure 2 |
| BUG-005 | 修复 | Figure 精裁结果低于高度/面积比例阈值时被误回退到 baseline，导致正文重新混入截图 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已修复 | Figure 路径将比例阈值调整为软告警：未污染且不过窄的精裁结果会保留；Table 路径保持严格回退，避免正文段落误保留为表格 |
| BUG-006 | 修复 | PDF-to-Markdown 自定义 `blocks-json/report-json` 父目录未创建，且相对 `asset-dir` 与资产提取文本输出错误落到 PDF 源目录 | 2026-06-06 00:00 | 2026-06-06 00:00 | 已修复 | `pdf_to_markdown.py` 现在以 Markdown 输出目录为相对资源根，自动创建 JSON 父目录，并向资产提取显式传入 `--out-text` |
| BUG-007 | 修复 | `--debug-visual` 因阶段对象字段和 PDF 后端调用不兼容而静默失败，且输出未写入附件记录 | 2026-06-06 00:00 | 2026-06-06 00:00 | 已修复 | 统一通过 `create_debug_stage()` 创建阶段信息，改用后端兼容的 `dpi` 渲染，并将画线图与图例写入 `debug_artifacts` |
| BUG-008 | 修复 | Table caption 位于表格下方时仍默认向下截图，且无矢量线表格缺少方向证据 | 2026-06-06 00:00 | 2026-06-06 00:00 | 已修复 | Table 局部方向判定加入短单元格行、宽正文行和 caption 距离等文本结构证据 |
| BUG-009 | 修复 | 短图表的固定最小高度和标题宽度门槛导致章节标题混入截图 | 2026-06-06 00:00 | 2026-06-06 00:00 | 已修复 | 版式裁剪允许标题作为远端边界，并降低短内容最小高度限制 |
| BUG-010 | 修复 | Table 精裁被通用比例回退和正文污染检测误拒绝，导致 FunAudio 多个表格缺失或混入正文 | 2026-06-06 00:00 | 2026-06-06 00:00 | 已修复 | 新增表格文本结构识别和连续表格行带裁剪；已确认的表格行带可绕过通用高度回退与远端宽文本清理 |
| BUG-011 | 修复 | 两单元格小节标题被误识别为表头，导致 FunAudio Table 4 混入章节标题 | 2026-06-06 00:00 | 2026-06-06 00:00 | 已修复 | 两单元格行只有横跨大部分候选宽度时才视为表格行 |
| BUG-012 | 修复 | GPT-5 System Card 的短表、单文本块表格被拒绝，部分表格被对象裁切缩成局部列 | 2026-06-06 00:00 | 2026-06-06 00:00 | 已修复 | 表格行带增加弱结构模式；短表支持三行结构验收；可靠行带成立且最终 X 范围异常窄时恢复 baseline 宽度 |
| BUG-013 | 修复 | 表格方向评分把短数字单元格误当页脚，并被相邻 Figure、下一张表和章节标题干扰 | 2026-06-06 00:00 | 2026-06-06 00:00 | 已修复 | 页脚过滤限定到页面底部；方向评分改用最近结构化多单元格行；编号式章节标题不再作为稀疏表格尾行 |
| BUG-014 | 修复 | Gemini 正文句子 `Table 4, we compare...` 被当作图注，真实 Table 4 未提取 | 2026-06-06 00:00 | 2026-06-06 00:00 | 已修复 | 新增该类正文引用模式，并在 Table 扫描入口实际调用 `is_caption_reference()` 跳过引用候选 |
| BUG-015 | 修复 | Qwen 显式 `Table N:` caption 位于长文本块时被正文引用逻辑误拒绝，导致 Table 9 缺失 | 2026-06-11 00:00 | 2026-06-11 00:00 | 已修复 | 显式冒号 caption 不再仅因文本块较长被拒绝，同时保留普通正文引用过滤 |
| BUG-016 | 修复 | Qwen 多个表格的分组标题和紧凑数字行未进入连续表格行带，导致 Tables 10 至 13 截断 | 2026-06-11 00:00 | 2026-06-11 00:00 | 已修复 | 连续行带支持具有后续表格证据的桥接行和紧凑数字弱表格行，并限制弱行宽度以避免正文污染 |
| BUG-017 | 修复 | 通用正文边界阻断把图内短标签和紧凑数字块误判为正文，放宽后又造成 DeepSeek 回归 | 2026-06-11 00:00 | 2026-06-11 00:00 | 已修复 | 改为方向感知的短标题判定，保护邻近短标签聚类和非全宽紧凑数字块，同时继续阻断孤立标题、正文和全宽数字段落 |
| BUG-018 | 修复 | 双栏跨栏标题误终止裁剪 + 强结构表格分组行带被行距上限截断 | 2026-06-13 00:00 | 2026-06-13 00:00 | 已修复 | 窄栏 caption 的正文 blocker 候选按 `TextBlock.column` 或水平重叠过滤；强结构行仅在非句子型且仍处于桥接距离内时允许跨越较大分组间距，避免表格截断和正文误并入 |
| BUG-019 | 修复 | 复核并修复图表提取资源泄漏、完整流程重复提取、无对象 caption 反向加分、Figure 正文引用漏过滤及低优先级一致性问题 | 2026-06-13 00:00 | 2026-06-13 00:00 | 已修复 | 共 12 项：M1 PDF 句柄泄漏→统一 `@managed_pdf_document` 上下文管理并在异常路径关闭、`PDFDocument.close` 幂等、`pre_validate_pdf` 改 try/finally；M2 `process_pdf` 复用首次提取产物（`--reuse-existing`）；M3 无对象位置分改为 0；M4 Figure 扫描补 `is_caption_reference` 过滤正文引用；L1 Figure/Table 共用 idents 主正则；L2 删除死变量 `_SKIP_PATTERN`；L3 `get_unique_path` 改 `logger.warning`；L4 `stable_debug_number`(sha256) 取代 `hash`；L5 裸 except 改 `except Exception`+finally；L6 `fitz.open` 改回 `open_pdf`；L7 drawing 回退按 item 几何类型(Rect/Quad/Point)处理；L8 Supplementary 上下文命名组匹配并补 S 前缀 |
| BUG-020 | 修复 | Figure 顶部短图内标签被 far-side 正文检测误判，导致 autocrop 后红色最终边界漏掉说明文字 | 2026-06-18 00:00 | 2026-06-18 00:00 | 已修复 | `detect_far_side_text_evidence()` 与 `trim_far_side_text_post_autocrop()` 跳过短、无句末标点、非编号章节标题的图内标签；Attention Figure 2 重跑后 final y0=64.6，已覆盖 y=71.2 的图内标题 |
| BUG-021 | 修复 | Attention visualization / dense label figure 的大量小对象被 Phase B 单对象面积阈值过滤，导致黄线和红线切掉下半部分 | 2026-06-18 00:00 | 2026-06-18 00:00 | 已修复 | 新增 `_has_small_object_band_near_trimmed_edge()`；当 near-edge 收缩会丢掉横向覆盖广、纵向跨度足且延伸到原 near edge 的小对象带时，保留 phase_a 的 y 范围并继续允许后续 x 收窄；Attention Figure 3 重跑后 phase_b y1=306.3、final y1=306.5 |
| BUG-022 | 修复 | Attention Figure 5 的下方竖排文字由 text lines 表示，未进入 Phase B 对象证据，导致黄线和红线切掉文字下半部分 | 2026-06-18 00:00 | 2026-06-18 00:00 | 已修复 | 新增 `_has_text_label_band_near_trimmed_edge()`，`refine_clip_by_objects()` 支持可选 `text_lines`；Figure 路径传入当前页文本行，当 near-edge 收缩会切掉一整排窄文本标签时保留 phase_a 的 y 范围；Figure 5 重跑后 phase_b y1=596.3、final y1=596.4 |
| BUG-023 | 修复 | Attention Table 2 的顶部横向分界线未被 PyMuPDF drawing 暴露，baseline 从 caption 固定 gap 后开始导致红黄框压到表头 | 2026-06-19 00:00 | 2026-06-19 00:00 | 已修复 | 新增 `expand_clip_to_rendered_horizontal_rule()`，Table baseline 在 caption 与 near edge 的窄搜索带内用渲染像素补回横向分界线；兼容项目 `PDFPage.raw` 包装；Table 2 重跑后 baseline/phase_b/final y0 从 98.1 上移到 93.3 |
| BUG-024 | 修复 | Qwen3-Omni Figure 1 的图内短标签被 layout blocker 误判为远端标题，baseline/黄线只覆盖图下半部分；修复后 autocrop 又把页眉横线纳入红框 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已修复 | 短标题聚类支持阈值改为 `max(60pt, min_near_distance)`；新增 `trim_far_side_noise_before_content()` 清理 Figure far-side 页眉噪声；重跑 Qwen3-Omni 后 Figure 1 final 为 `63.6,62.9 -> 531.6,302.9` |
| BUG-025 | 修复 | Qwen3-Omni Table 9 的 layout far-strip 把表格内部数字行当作远端正文，导致 final 红框截断下半部分 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已修复 | 新增 `restore_table_tail_after_layout_trim()`，Table 路径在 layout 裁剪后检测被裁尾部是否仍像表格文本；重跑 Qwen3-Omni 后 Table 9 final 从 `66.1,248.8 -> 527.1,429.5` 恢复为 `66.1,248.8 -> 527.1,498.4` |
| BUG-026 | 修复 | FunAudio-ASR Table 5 的 final 红框底边贴近并切进表格最后一行文字 bbox，最终截图底部安全边距不足 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已修复 | 新增 `expand_table_clip_to_text_bounds()`，只在 Table final 阶段按 text line bbox 小幅补边并限制在 caption 前；重跑 FunAudio-ASR 后 Table 5 final 从 `159.4,69.8 -> 452.7,126.7` 调整为 `159.4,69.8 -> 452.7,131.4` |
| BUG-027 | 修复 | Gemini Figure 3 的 Phase A+ 精确两行检测把 y 轴底部两个窄刻度误判为 near-caption 正文，导致绿线、黄线、红线只截取图上半部分 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已修复 | `detect_exact_n_lines_of_text()` 新增 `min_line_width_ratio`，Figure Phase A+ 要求两行候选具备最小横向宽度；重跑 Gemini 后 Figure 3 final 从 `84.3,82.6 -> 506.0,188.9` 恢复为 `84.3,82.6 -> 512.0,233.3` |
| BUG-028 | 修复 | Gemini Figure 5 和 Figure 12 的图内 chart title 被 layout blocker 与 final autocrop 当作外部标题排除，导致最终截图漏掉图内题目 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已修复 | 新增 `expand_clip_to_nearby_figure_title()`；Figure 路径在 baseline text block limit 后和 final autocrop 后各恢复一次紧贴图主体的标题，跳过页眉和编号章节标题；重跑 Gemini 后 Figure 5 final 为 `128.5,141.0 -> 467.1,423.2`，Figure 12 final 为 `105.3,82.6 -> 490.2,403.6` |
| BUG-029 | 修复 | Qwen3-Omni Figure 3 因章节编号 `2.2` 与标题文本被拆成同基线两条文本，图内标题回收误把 `Audio Transformer (AuT)` 当作 chart title，导致红线混入章节标题 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已修复 | `expand_clip_to_nearby_figure_title()` 新增纯章节编号行及右侧同基线标题组合识别；重跑 Qwen3-Omni 后 Figure 3 final 从 `159.4,224.4 -> 440.9,506.0` 调整为 `159.4,249.2 -> 440.9,506.0`；Gemini Figure 5/12 回归仍保留图内标题 |
| BUG-030 | 修复 | Gemini Figure 14/15 的 Phase B 对象对齐把 near-caption 侧图内标注裁掉，导致红线漏掉子图说明和 Prompt 输入文字 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已修复 | 新增 `_near_caption_annotation_text_edge()`，由全边回退改为局部补边，只在 Phase B 即将裁掉 near-caption 图内标注时保护面板前缀或窄列多行文本；重跑 Gemini 后 Figure 14 final 从 `55.3,82.0 -> 541.1,291.7` 恢复为 `55.3,82.0 -> 541.1,311.3`，Figure 15 final 从 `61.1,521.4 -> 523.1,663.5` 恢复为 `61.1,542.3 -> 523.1,714.4` |
| BUG-031 | 修复 | Attention Figure 3 的图内标题回收误把 12pt 小节标题纳入红线，同时 Kearns Figure 4/6/7 的图内短标题和轴标题被 Phase A/B 裁切压住 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已修复 | `expand_clip_to_nearby_figure_title()` 增加字号上限；新增 `_restore_far_side_short_labels_after_text_trim()` 和 `_nearby_short_label_rects()`，只局部补回低字号短图题/轴标题；重跑 `20260620-017` 后 Attention Figure 3 final 为 `114.5,93.4 -> 509.8,306.5`，Kearns Figure 4/6/7 分别为 `134.6,271.7 -> 470.8,601.0`、`120.4,262.6 -> 499.6,576.0`、`120.9,81.4 -> 486.9,267.1` |
| BUG-032 | 修复 | GPT-5 System Card 单栏文档被误判成伪双栏，`refine_clip_x_range()` 按伪左栏裁剪导致 30 张 Figure 横向塌缩成窄条 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已修复 | `detect_columns()` 增加 column gap 与双峰间距几何校验；`refine_clip_x_range()` 增加 `_has_trustworthy_column_geometry()`，拒绝异常大 gap、整页边距和过窄列宽；重跑 `20260620-019/gpt-5-system-card/` 后 31 张 Figure final 最小宽度为 `452.2pt`，无 `width < 200pt` |
| BUG-033 | 修复 | Gemini 2.5 Report Table 1/3 的多行表头被 `limit_clip_by_text_blocks()` 当成外部 blocker，导致最终截图从表头下方开始 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已修复 | 新增 Table-only 的 `expand_clip_to_nearby_table_header()`，只在 layout text block limit 后、且下方存在表格行证据时恢复紧邻多行表头；重跑 `20260620-019/gemini_v2_5_report/` 后 Table 1 final 为 `57.4,113.1 -> 537.9,254.9`，Table 3 final 为 `62.2,210.3 -> 533.1,595.3` |
| BUG-034 | 修复 | Gemini 2.5 Report 多张 Table 在 final autocrop 后丢表头，且 Table 5 方向误判为下方 Table 6 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已修复 | `score_local_direction()` 增加下方后续 caption 负证据，解决上下表格夹 caption 的方向歧义；`expand_table_clip_to_text_bounds()` 增加 final-only 连通行带回补，`extract_tables.py` 传入 layout blocker 前 reference；重跑 `20260620-021/gemini_v2_5_report/` 后 Table 1/2/10/11 表头恢复，Table 5 切回上方小表 |
| BUG-035 | 修复 | Gemini 2.5 Report Table 4/6/12 的 Table final 连通行带误吃正文或残留正文尾句，导致红线从正文开始而不是表头开始 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已修复 | `expand_table_clip_to_text_bounds()` 增加正文行 blocker 和正文前缀/后缀裁除；正文后的安全起点只接受多片段结构化表格行，避免 `1/3 cases...` 这类短数字正文误触发；重跑 `20260620-027/gemini_v2_5_report/` 后 Table 4/6/12 final 分别为 `57.4,427.7 -> 537.9,703.2`、`57.4,211.8 -> 537.9,425.9`、`57.7,515.3 -> 526.4,734.3` |
| BUG-036 | 修复 | Qwen3-Omni Table 5/8/12/14/15/18 的 final 红框底部误吞表格正下方紧邻的章节标题（编号被拆到正文后只剩无编号短标题，绕过所有“编号章节标题”过滤） | 2026-06-20 00:00 | 2026-06-20 00:00 | 已修复 | 新增 Table-only 的 `trim_table_far_side_section_heading()`，在 `expand_table_clip_to_text_bounds()` 后按方向剔除远端紧跟表格、且外侧紧邻满宽正文段落的 layout `title_` 块；守卫 `_has_same_row_data_cell()` 用“标题右侧并排数字数据列”保留被误判为标题的表格末行（如 Table 2 `Generation RTF(...) 0.47 0.56 0.66`）；重跑 `20260620-031/2509.17765v1-Qwen3-Omni_Technical_Report/` 后 6 张表全部修复，Table 16(`7 Conclusion`) 连带修复，Table 2 与其余表无回退，Gemini/GPT-5 未误触发 |
| BUG-037 | 修复 | BUG-036 的 Table 远端章节标题裁除误伤 Gemini/Kearns 表头和 Attention Table 2 最右侧数据单元格，同时 FunAudio Table 4 的上方章节标题仍未裁净 | 2026-06-21 00:00 | 2026-06-21 00:00 | 已修复 | 将 `_has_same_row_data_cell()` 升级为同一行带左右两侧均检查的 `_has_same_row_table_context()`，新增附近表头结构保护、正文段落语义判断和拆分章节编号识别；重跑 `20260621-001/` 后 Attention Table 2 底部恢复，Gemini Table 2/4/6/10/12 与 Kearns Table 1 表头恢复，FunAudio Table 4 顶部章节标题剔除，FunAudio Table 2 无回退 |
| BUG-038 | 修复 | GPT-5 System Card Figure 22 的独立裸 `Figure 22` caption 被下方 Figure 23 大图吸走，导致公式/化学式图片漏截 | 2026-06-21 00:00 | 2026-06-21 00:00 | 已修复 | 新增 Figure-only 的 `correct_bare_figure_caption_direction()`：仅当当前方向为 below、caption 是裸 `Figure N`、下方存在下一张 Figure caption、且上方近处有对象证据时反转为 above；重跑 `20260621-001/gpt-5-system-card/` 后 Figure 22 final 从下方柱状图纠正为 `44.9,139.7 -> 550.4,233.4` |
| BUG-039 | 修复 | 20260621 剩余表格瑕疵：Qwen Table 16 误吞 `7 Conclusion`、Qwen Table 2 漏最后一行、FunAudio Table 2 与 Kearns Table 1 保留远端空白/正文尾巴 | 2026-06-21 00:00 | 2026-06-21 00:00 | 已修复 | `expand_table_clip_to_text_bounds()` 增加 Table-only 远端结构行收紧、弱 final 的连通行/布局同行末行回补；`trim_table_far_side_section_heading()` 增加 layout 同排 peer block 保护；重跑 Qwen 到 `tests/results/20260621-004/` 后 Table 2 final 为 `99.0,529.8 -> 496.4,677.9`、Table 16 final 为 `66.1,374.4 -> 527.1,701.4`，重跑 FunAudio/Kearns/GPT-5 到 `tests/results/20260621-002/` 后用户点名图表目视通过，GPT-5 Figure 29 未受影响 |
| BUG-040 | 修复 | 20260621-006 剩余小瑕疵：Gemini Table 12 数字正文尾句回归、GPT-5 Figure 29 顶部正文尾句残留、GPT-5 Table 16 底部换行尾行被裁 | 2026-06-21 00:00 | 2026-06-21 00:00 | 已修复 | Table 远端收紧安全起点恢复为仅接受多片段强结构行，避免 `1/3 cases...` 数字正文误触发；Table below 方向保留紧贴主行的短换行尾行；Figure autocrop 后处理和图内标题回收均排除小写正文尾句；重跑 Gemini 到 `tests/results/20260621-007/` 后 Table 12 final 为 `57.7,515.3 -> 526.4,734.3`，重跑 GPT-5 到 `tests/results/20260621-009/` 后 Figure 29 final 为 `44.9,342.8 -> 550.4,400.4`、Table 16 final 为 `76.4,169.7 -> 519.0,277.7` |
| BUG-041 | 修复 | `lib/debug_visual.py::save_debug_visualization` 的 `temp_doc` 在 `try` 块内首次赋值，`finally` 块引用时若早期抛异常会触发 `NameError`，掩盖原始异常 | 2026-06-22 00:00 | 2026-06-22 00:00 | 已修复 | 在 `try:` 之前提前初始化 `temp_doc = None`，确保 `finally` 块引用安全 |
| BUG-042 | 修复 | `core/extract_pdf_assets.py` 调用 `extract_tables` 时未传 `no_refine_tables`，导致 CLI `--no-refine` 对 Table 路径完全不生效，违反流程文档 2.1 节约定 | 2026-06-22 00:00 | 2026-06-22 00:00 | 已修复 | 调用 `extract_tables` 时补传 `no_refine_tables=no_refine_figs`，`--no-refine` 现在对 Figure 和 Table 同时生效 |
| BUG-043 | 修复 | `lib/direction.py::determine_direction` 页面位置启发式为硬 `return`，无条件覆盖 `global_anchor`，导致全文统计的强全局锚点对顶部/底部 caption 失效 | 2026-06-22 00:00 | 2026-06-22 00:00 | 已修复 | 将页面位置启发式改为候选方向 `heuristic_dir` 暂存；`global_anchor` 在局部证据弱或缺失时优先返回；仅当 `global_anchor` 为 `None` 时才回退到 `heuristic_dir` |
| BUG-044 | 修复 | `estimate_ink_ratio` 在 `lib/refine.py` 和 `lib/extract_helpers.py` 各有一份相同实现，存在行为分裂风险 | 2026-06-22 00:00 | 2026-06-22 00:00 | 已修复 | 统一为单一来源：`extract_helpers.py` 为唯一实现，`refine.py` 保留同名包装函数委托到 `extract_helpers.estimate_ink_ratio` |
| BUG-045 | 修复 | `lib/markdown_render.py::render_blocks` 生成器表达式中 `if render_block(block)` 对每个 block 调用两次 `render_block`，效率减半 | 2026-06-22 00:00 | 2026-06-22 00:00 | 已修复 | 改为先列表推导预计算，再过滤非空结果 |
| BUG-046 | 修复 | `lib/debug_visual.py::dump_page_candidates` 函数内 `temp_doc = None` 为从未使用的死代码 | 2026-06-22 00:00 | 2026-06-22 00:00 | 已修复 | 删除该行 |
| BUG-047 | 修复 | Debug 批量分析只能靠 legend 几何推断 fallback，且 Figure/Table 精裁拒绝后可能回退到含正文的 baseline；debug legend 缺少 Phase D 可观测阶段 | 2026-06-23 08:51 | 2026-06-23 08:51 | 已修复 | `extract_figures.py` 与 `extract_tables.py` 在验收拒绝、低比例保留、fallback 选择和污染拒绝时写入 `run.log.jsonl` 结构化事件；fallback 改为优先选择未污染的 `phase_a`、`phase_b`、`phase_d`，最后才用 baseline；debug 阶段增加 `phase_d`；`analyze_debug_batch.py` 支持解析 `phase_d` 和结构化 fallback/reject 日志 |
| BUG-048 | 修复 | 精裁回退选片高度门槛过低，导致短 `phase_a` clip 绕过正文污染检测并把伪表格/伪图导出 | 2026-06-23 13:16 | 2026-06-23 13:16 | 已修复 | `extract_tables.py` 与 `extract_figures.py` 的多阶段 fallback 选片门槛从硬编码 `base_clip.height * 0.25` 恢复为 `base_clip.height * thresholds.height_ratio`；保留 Table 路径 `looks_like_table_text()` 对短真实表格的特例；同步更新 Figure fallback 测试，明确过短 `phase_a` 应跳到 `baseline` |
| BUG-049 | 修复 | `apply_preset_robust()` 按外层 `sys.argv` 判断显式传参，程序化调用（非命令行）场景下调用方显式设置的参数会被 preset 覆盖 | 2026-07-31 08:48 | 2026-07-31 08:48 | 已修复 | `apply_preset_robust(args, argv=None)` 新增 `argv` 参数，为 None 时退回 `sys.argv`；`test_p0_env_priority.py` 新增 argv 透传回归测试；`pytest tests/scripts -q` 为 126 通过、0 失败 |
| BUG-050 | 修复 | `extract_tables` 存在 NameError；`lib/output.py` 计算 sha256 时一次性读入整个文件，且部分 docstring 与实际行为不符 | 2026-07-31 08:48 | 2026-07-31 08:48 | 已修复 | 修复 `extract_tables` 的 NameError；sha256 改为分块读取；同步修正 docstring；`pytest tests/scripts -q` 为 126 通过、0 失败 |
| BUG-051 | 修复 | 审查复现：`tests/eval` 无法消费正式 `index.json`（只认 `ident`/`predictions`/`attachments`/`*/predictions.json`，正式输出是 `id`/`items`/`**/images/index.json`）；`convert_labelme_to_gt.py` 跨页合并违背 SCHEMA 规范④（跨页框堆进同一 content_bboxes） | 2026-07-31 16:10 | 2026-07-31 16:30 | 已修复 | `normalize_prediction` 兼容 `id`→ident、`final_bbox` 优先回退链；`load_preds` 支持 `items` 键；`find_pred_files` 双格式发现 + 目录名空格归一化；LabelMe 转换按 `(kind,ident,occ,page)` 分组：同页合并、跨页拆分多条记录（occurrence 递增、同 group_id、坐标只含本页），SCHEMA 补跨页 caption 约定；用 `tests/results/20260731-002` 正式产物复现验证通过（DeepSeek_V3_2 正确读出 5 条），selfcheck 27 项全 PASS |
| BUG-052 | 修复 | 审查复现：golden 默认复用旧批次导致改代码后假绿；`-m "not golden"`/`--skip-golden` 可做出「看起来全绿」，AGENTS 规则未落地 | 2026-07-31 16:10 | 2026-07-31 16:30 | 已修复 | 新增 `_code_fingerprint.json`（skills 全量 .py 内容 sha256），批次复用前校验指纹、不符或缺失一律重提，`PDF_GOLDEN_REEXTRACT=1` 强制重提；conftest 拦截被 `-m`/`-k` 排除的 golden 用例并置 exit=1（豁免变量 `PDF_SKILL_ALLOW_GOLDEN_SKIP=1` 放行但醒目 WARNING）；`run_all.py --skip-golden` verdict 明确「不算全绿」且退出码非 0；验证：正常复用 0.68s 全绿、指纹不符触发重提、not-golden exit=1、豁免 exit=0；规范批次为 `tests/results/20260731-002/` |
| BUG-053 | 修复 | 未提交代码审查：`test_regex_patterns.py` 经 pytest/`run_all` 假绿（8 个 `test_*` 只 return 不 assert）；`pair_page` 未写入 `AssetCandidate.kind` 导致 A3 表格匹配失败；A1 报告读错 `caption_text` 字段；A3 重渲染失败时元数据回滚不完整；流程说明归档副本未入暂存 | 2026-08-07 14:35 | 2026-08-07 14:41 | 已修复 | 正则套件加 `_assert_all_passed`；`pair_page(..., kind=)` 写入 kind；A1 改读 `caption`；pipeline 失败时完整回滚元数据；归档流程说明已暂存；cli-options 补 `--layout-backend`；README 七份→八份；再补 `_MIN_MATCH_IOU=0.25` + 跨 kind 过滤 |
| BUG-054 | 修复 | 残留：A2 用 final_bbox 冒充 caption；A3 重复配对；pytest regex ReturnNotNoneWarning | 2026-08-07 15:00 | 2026-08-07 15:05 | 已修复 | `AttachmentRecord.caption_bbox` 落盘（figures/tables/output）；A1/A2 优先真实 caption_bbox，不再用 final_bbox；A3 复用 A2 `pairing_results`；pipeline 精修优先真实 caption；regex 拆 `_collect_*` + `test_* -> None` |
| BUG-055 | 修复 | Critical：Figure/Table 精修器将 truncation 硬编码为 False，text_pollution 仅搜步骤 notes 字符串，截断与正文污染验收实际未生效 | 2026-08-10 14:00 | 2026-08-10 15:00 | 已修复 | 新增 quality.detect_truncation（候选内对象覆盖/候选覆盖率二值判据）；figure.py/table.py 接入 detect_text_pollution + detect_truncation 真实信号，禁止硬编码；单测 test_a2_a3_fixes 覆盖截断/污染与 refiner 信号捕获 |
| BUG-056 | 修复 | Critical：四态输出契约未落地——review_required/rejected 时保留 legacy 几何却仍写 accepted 元数据，告警与人工复核状态丢失 | 2026-08-10 14:00 | 2026-08-10 15:00 | 已修复 | pipeline.run_refinement_pipeline：非 acceptable 状态仍写回 status/warnings/review_required/boundary_confidence；legacy_iou/legacy_cov 过低时几何保留 legacy 但状态升为 review_required；acceptable 应用时多 panel 保留 content_bboxes |
| BUG-057 | 修复 | Important：A3 _match_records_to_candidates 丢弃 caption 身份且不标记候选已用，两 record 可绑同一候选；content_bboxes 被压成 union 单框 | 2026-08-10 14:00 | 2026-08-10 15:00 | 已修复 | 改为返回 dict{bbox,content_bboxes,caption_bbox}；贪心一对一按 IoU 分配，used_cands+(page,kind,rounded_bbox) 防重复占用；多 panel frames 原样保留 |
| BUG-058 | 修复 | Important：多框分组 30pt 内相邻框无条件并入 multi-frame，可吞掉下一张独立图表（两图两 caption 变成 1 pair+1 orphan） | 2026-08-10 14:00 | 2026-08-10 15:00 | 已修复 | pairing._find_multi_frames 增加 captions/primary_caption：若相邻 content 有更近其他 caption 则不并入；回归 test_multi_frame_does_not_swallow_neighbor_with_own_caption |
| BUG-059 | 修复 | Important：外部 caption 只要文档级非空则全页禁用 Layout caption，部分页无外部 caption 时 0 配对+孤立 content | 2026-08-10 14:00 | 2026-08-10 15:00 | 已修复 | pair_layout_regions：按页过滤外部 caption，本页为空时回退 page_region.caption_regions；回归 test_external_caption_per_page_fallback_to_layout |
| BUG-060 | 修复 | Important：Golden 回归断链——benchmark PDF 已扁平化且 DeepSeek_V3_2 换为 k3_tech_report，测试仍扫 回测组* 子目录且无 golden_index.json | 2026-08-10 14:00 | 2026-08-10 15:05 | 已修复 | test_extraction_golden：CORE 改扁平路径，DeepSeek_V3_2→k3_tech_report(16F+5T)；coverage 扫 *.pdf；_resolve_golden_paths 写 tests/basic-benchmark/<stem>/images/golden_index.json；--update-golden 重建 8 份基准 |
| BUG-061 | 修复 | Critical: AssetCandidate.kind 丢失导致 Table 永远匹配不上 A3 候选 | 2026-08-07 10:00 | 2026-08-07 10:30 | 已修复 | `pairing.py` 的 `pair_page()` 创建 `AssetCandidate` 时未设置 `kind`（默认 "figure"）；`pair_layout_regions()` 按 figure/table 分别调用但未传入 `kind`；`_match_records_to_candidates()` 用 `content_list[0].kind` 建索引导致 table record 查 `(page,"table")` 得空映射。修复：`pair_page()` 新增 `kind` 参数并写入 `AssetCandidate.kind`；`pair_layout_regions()` 传入当前 kind；`_region_to_candidate()` 同步接收 kind。验证：Attention PDF 4 个 Table 全部 matched+applied（修复前 0 matched） |
| BUG-062 | 修复 | Critical: test_regex_patterns.py 在 pytest 下假绿 | 2026-08-07 10:00 | 2026-08-07 10:30 | 已修复 | 7 个 test_* 函数只 `return results` 不 assert，失败只写在返回列表里，pytest 仍算通过。修复：所有函数末尾调用 `_assert_all_passed(results)`（已有的辅助函数，执行 `assert not failed`）。验证：故意改期望后 pytest 报 FAILED |
| BUG-063 | 修复 | Important: A1 正文引用过滤字段名写错 | 2026-08-07 10:30 | 2026-08-07 10:30 | 已修复 | `extract_pdf_assets.py` A1 段用 `caption_text`/`caption_bbox`（不存在），`AttachmentRecord` 字段为 `caption`/`final_bbox`。修复：改为 `getattr(r, "caption", "")` + `getattr(r, "final_bbox", None)`。验证：Attention PDF `captions_filtered` 从 0 变为 1（之前恒为 0 因候选列表恒空） |
| BUG-064 | 修复 | Important: A3 重渲染失败时元数据回滚不完整 | 2026-08-07 10:30 | 2026-08-07 10:30 | 已修复 | `pipeline.py` 渲染失败只恢复 `final_bbox`/`content_bboxes`，不恢复 `source_signals`/`status`/`warnings`/`boundary_confidence`/`review_required`。修复：在修改前保存全部 7 个字段到 `_saved` dict，失败时完整恢复 |
| BUG-065 | 修复 | Important: detect_conflicts content_missing 过粗 | 2026-08-07 10:30 | 2026-08-07 10:30 | 已修复 | 原实现只看"该页有没有 legacy 资产"，不看"该 Layout 区域是否被任一 legacy 框覆盖"。修复：改为逐个 Layout 区域检查是否有任意 legacy bbox 与之 IoU>0，精确到区域级 |
| BUG-066 | 修复 | Important: Layout 缓存命中时忽略 pages 过滤 | 2026-08-07 10:30 | 2026-08-07 10:30 | 已修复 | `pymupdf_layout.py` 缓存命中直接 return，不应用 `pages` 参数（仅新提取路径过滤）。修复：缓存命中后同样执行 `pages` 过滤 |
| BUG-067 | 修复 | Minor: RegionBBox.vertical_gap 文档与实现不符 | 2026-08-07 10:30 | 2026-08-07 10:30 | 已修复 | 文档写"上方为负"，实现两侧都返回正值。修复文档为"other 在 self 上方或下方时均返回正值" |
| BUG-068 | 修复 | Minor: filter_text_reference_captions 注释与实现矛盾 | 2026-08-07 10:30 | 2026-08-07 10:30 | 已修复 | 注释写"不删除"，实现会从返回列表去掉。修复注释为"从结果中移除可疑引用" |
| BUG-069 | 修复 | Minor: --layout-backend 未写入 SKILL.md | 2026-08-07 10:30 | 2026-08-07 10:30 | 已修复 | SKILL.md 新增 `--layout-backend` 命令示例和说明；README.md 补充引用 |
| BUG-070 | 修复 | Critical: `--preset robust` 静默覆盖显式 `--no-*` 关闭参数 | 2026-08-29 00:00 | 2026-08-29 00:00 | 已修复 | 全项目深度审查确认。`collect_explicit_args` 把 `--no-table-autocrop` 归一化为 `no_table_autocrop`，而 `robust_defaults` 键为 `table_autocrop`，匹配失败致 `apply_preset_robust` 把用户显式关闭的开关 `setattr` 翻回 True（端到端复现：`--no-table-autocrop` 解析后 False→preset 后 True）。修复 `env_priority.py` 匹配时同时检查 `no_<key>`；实测 6 个 `--no-*` 旗标全部尊重显式值，未显式传参时 preset 仍正常生效。新增回归 `test_apply_preset_robust_respects_no_flag_explicit` |
| BUG-071 | 修复 | Important: `pdf_to_markdown.py` 资产提取失败仍返回 0（静默失败） | 2026-08-29 00:00 | 2026-08-29 00:00 | 已修复 | 深度审查确认。`_run_asset_extraction` 的 `exit_code` 只写进 report，`main()` 无条件 `return 0`，下游 `process_pdf.py` 依赖该退出码，导致提取失败时输出无图 md 且无失败信号。修复：资产启用且提取失败时向 stderr 报错并返回提取退出码；`report.assets` 增记 `exit_code`。新增回归 `test_asset_extraction_failure_propagates_exit_code`、`test_assets_disabled_returns_zero` |
| BUG-072 | 修复 | Important: `run_all.py` 套件清单遗漏 `test_a2_a3_fixes.py` | 2026-08-29 00:00 | 2026-08-29 00:00 | 已修复 | 深度审查确认。`run_all.py` 自称「单命令跑全套」，但 8 套件清单未含 A2/A3 核心回归（一对一配对/多框/四态落盘，9 用例），仅裸 `pytest tests/` 才覆盖，无机制保证持续回归。修复：套件清单补入该文件并同步 docstring（8→9 套件） |
| BUG-073 | 修复 | Important: `--preset robust` 覆盖显式 CLI 别名 | 2026-08-30 12:59 | 2026-08-30 13:06 | 已修复 | `--autocrop-white-threshold 123` 解析 dest 为 `autocrop_white_th=123`，但 `collect_explicit_args` 只收集旗标名，preset 改回 250。修复：`collect_explicit_args`/`apply_preset_robust` 接受 parser，按 dest 识别别名；`extract_pdf_assets.main_modular` 传入 parser。新增 `test_collect_explicit_args_maps_option_alias_to_dest`、`test_apply_preset_robust_respects_option_alias_dest`；修复为 parser action.dest 映射，build_parser_modular 与 apply_preset_robust 共用 parser；别名回归已通过。 |
| BUG-074 | 修复 | Important: `--images off --tables screenshot` 仍导出并插入 Figure | 2026-08-30 12:59 | 2026-08-30 13:06 | 已修复 | 编排层仅支持 `--no-tables`，提取器无禁用 Figure 旗标且不过滤 figure items。修复：提取层新增 `--include-figures`/`--no-figures`；编排层 images=off 时传 `--no-figures` 并按 mode 过滤 items。新增 `test_extract_parser_accepts_no_figures`、`test_images_off_tables_on_does_not_insert_figures`；提取层新增 --include-figures/--no-figures，高层编排传递 --no-figures 并二次过滤 items；混合模式回归已通过。 |
| BUG-075 | 修复 | Important: 资产提取失败时报告顶层 `status` 仍为 ready | 2026-08-30 12:59 | 2026-08-30 13:06 | 已修复 | CLI 已传播非零退出码且 `assets.exit_code` 可用，但顶层 status 无条件写 ready。修复：提取启用且 exit_code 非 0 时 `status=failed`；`test_asset_extraction_failure_propagates_exit_code` 补断言；报告顶层 status 现根据 assets.exit_code 写 ready/failed，非零退出码仍向上游传播；回归已通过。 |
| BUG-076 | 修复 | Important: `run_all.py` 将测试文件缺失或 pytest 零收集当作 skip 并可返回 0 | 2026-08-30 12:59 | 2026-08-30 13:06 | 已修复 | 清单内套件路径错误或零收集时统一入口可假绿。修复：除用户显式授权的排除模式外，缺失/零收集一律失败；新增 `test_run_all.py` 并纳入套件清单（9→10）；清单内脚本缺失与 pytest exit 5 现均判失败；新增 test_run_all.py 4 项防假绿回归并纳入统一入口。 |
| BUG-077 | 修复 | visual-review：题注筛选误收正文引用、误拒真实长题注 | 2026-09-07 16:17 | 2026-09-07 17:30 | 已修复 | DeepSeek `Table 6. Also, we evaluate…` 被当题注；Gemini Figure 9 因 `based on` 被 -20 参考扣分（19<25）未导出。新增 `is_explicit_caption_format()`：`Table N \|` / `Figure N:` 为真题注；`based on` 收窄为 `based on (figure\|table)`；句号后 Also/We/This 视为正文引用。真实 PDF：Gemini Figure 9 评分 68≥25，DeepSeek p37 引用被拒、p38 真表 64 分。 |
| BUG-078 | 修复 | visual-review：堆叠表把题注上方前一张表当成当前表 | 2026-09-07 16:17 | 2026-09-07 17:30 | 已修复 | DeepSeek Table 3/10/11 题注在真实表上方，局部方向却判 above。`score_local_direction()` 识别「上一题注向下附着」后，两题注之间的内容全部归上一张表；章节标题不再干扰附着；一侧无结构化行时不再落入 object-ratio。真实页：p29 Table 3、p55 Table 10/11 均判 below。 |
| BUG-079 | 修复 | visual-review：精裁因 height_ratio 回退 baseline，题注上方残留摘要/小节/列表 | 2026-09-07 16:17 | 2026-09-07 17:45 | 已修复 | FunAudio Figure 1 phase_d 因 0.364<0.450 被拒回含摘要的 baseline。Figure 路径恢复 `allow_low_ratio_keep`，fallback 高度门槛改为 `max(80, base*min(0.20, height_ratio))`。新增 `_trim_lingering_body_before_objects()`：在绘图对象带之外继续裁掉摘要尾句、拆分的 `4.1` 小节标题和项目列表；Phase D 对象扩边后再次调用，避免摘要小矢量把 y0 扩回去。004：FunAudio F1 `y0=436.5`，F3 `y0=191.5`，gpt-5 F22/F29 `y0=139.7/343.5`，K3 F1 `y0=405.5`。 |
| BUG-080 | 修复 | visual-review：左右独立图合并、多子图文本裁切丢掉上排 | 2026-09-07 16:17 | 2026-09-07 17:30 | 已修复 | DeepSeek Figure 11/12 同页左右独立编号却导出同一全宽框。`limit_clip_by_neighbor_captions()` 对 y 重叠的左右 caption 在中点拆 X。K3 Figure 13 的 phase_a 把上边界从 260 收到 447，丢掉上排绘图区；`trim_clip_head_by_text_v2` 增加 `object_rects` 保护远侧绘图带。004：Fig11 `[67.2,240.5,292.5,381.7]`，Fig12 `[302.9,240.5,528.9,382.5]`；K3 F13 `y0=318.8`。 |
| BUG-081 | 修复 | visual-review：长表搜索窗不足、表头被脚注重叠裁切 | 2026-09-07 16:17 | 2026-09-07 17:45 | 已修复 | K3 Table 2 / DeepSeek Table 12 初始窗口过短导致行带截断。Table 路径在方向判定前收集邻接 caption，并用 caption 到页边（再按邻接限制）的 `table_search_clip` 做行带搜索。K3 Table 3 合并题注 y1=120 与 Proprietary 表头 y0=118.2 重叠，窗口从 126 起切字；`expand_clip_to_nearby_table_header()` 在 below 方向即使 original 未被收紧也对 clip 上方短表头做 peek，允许轻擦题注的短标签，并在 final 再恢复一次。004：K3 T2 `y1=689.2`，T3 `y0=114.2`（含 Proprietary/Open Weight）；DeepSeek T12 `y1=753.4`。 |
| BUG-082 | 修复 | visual-review：Figure 摘要小矢量回扩、Table 远端调查正文被扩边吞入 | 2026-09-07 16:17 | 2026-09-07 17:40 | 已修复 | DeepSeek Figure 1 的 phase_d 已到 466，但 `expand_clip_to_nearby_figure_objects` 把摘要文字小矢量当绘图对象把 y0 扩回 433。过滤过小矢量（w<20 或 h<14 或面积<120）并在对象扩边后再裁残留正文。DeepSeek Table 8 被 `expand_table_clip_to_text_bounds` 吃进表后调查段落；新增 `trim_table_clip_far_side_body()`。004：Figure 1 `y0=466.0`，Table 8 `y1=304.8`。 |

## 调整事项

| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| ADJ-001 | 调整 | 项目定位从“PDF 论文图表提取与摘要脚本”调整为正式 Skill 项目 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | Skill 目标明确为 PDF 转 Markdown、PDF 带图摘要、完整处理流程三类能力 |
| ADJ-002 | 调整 | 正式 Skill 工作目录确定为 `skills/pdf-markdown-summary/` | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | `SKILL.md`、`references/`、`examples/`、`scripts/` 均以该目录为最新版事实来源 |
| ADJ-003 | 调整 | 旧版脚本和旧资料统一归档到 `old-version/` | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | `old-version/` 仅供参考，不再修改和维护 |
| ADJ-004 | 调整 | `docs/` 目录重新分层 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | `docs/1-archive/` 存旧文档，`docs/2-plans/` 存当前计划，`docs/3-ref/` 只读不写 |
| ADJ-005 | 调整 | `AGENTS.md` 从长说明书压缩为执行约束清单 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 保留目录职责、只读规则、Skill 目录规则、task-list 记录规则和基础验证规则 |
| ADJ-006 | 调整 | 根目录启用 `task-list.md` 作为后续任务记录文件 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 参考 `examples/task-list.md` 的分类和字段创建，本次未修改样例文件 |
| ADJ-007 | 调整 | 统一正式 Skill 命名为 `pdf-markdown-summary` | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 目录已改为 `skills/pdf-markdown-summary/`，`SKILL.md` frontmatter `name` 已改为 `pdf-markdown-summary`，当前文档引用已同步 |
| ADJ-008 | 调整 | 修复 `skill-creator` 审查发现的 Skill 规范缺口 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 新增 `agents/openai.yaml`；删除 Skill 内 `examples/README.md`；清理 `.DS_Store`、`__pycache__` 和 `.pyc` 发布垃圾文件 |
| ADJ-009 | 优化 | 拆分超载的 `lib/refine.py` 并清理 Markdown/DrawItem/像素检测模块边界 | 2026-06-22 00:00 | 2026-06-22 00:00 | 已完成 | 将精裁实现拆入 `pixel_detect.py`、`text_trim.py`、`object_refine.py`、`figure_post.py`、`table_refine.py`、`far_side.py`、`acceptance.py`、`clip_limit.py`；`refine.py` 保留兼容导出；新增 `markdown.py`，旧 Markdown 模块改为兼容导出；`DrawItem` 统一使用 `models.py` 定义，`estimate_ink_ratio` 迁入像素检测模块 |
| ADJ-010 | 调整 | 删除 `--engine legacy` 与 `PDF_SUMMARY_AGENT_ENGINE` 环境变量，引擎固定为 modular；CLI 删除从未生效的死参数 `--protect-far-edge-px`（原默认 18）与 `--near-edge-pad-px`（原默认 6），新增 `--no-refine-near-edge-only` 反向开关 | 2026-07-31 08:48 | 2026-07-31 08:48 | 已完成 | `--refine-near-edge-only` 默认 True；四个入口脚本 `--help` 验证正常 |
| ADJ-011 | 调整 | 核对 preset robust 实际取值并同步 `scripts/__init__.py` 版本号 | 2026-07-31 08:48 | 2026-07-31 08:48 | 已完成 | robust 实际生效：clip-height 520（argparse 裸默认 650）、margin-x 26（裸默认 20）、caption-gap 6（裸默认 5），并默认开启 text-trim、autocrop、autocrop-mask-text；版本号从 0.3.1 同步为 0.5.10，与 git tag V0.5.10 一致 |
| ADJ-012 | 调整 | （补录）`lib/debug_visual.py` 存在未提交的 STAGE_COLORS 配色调整改动 | 2026-07-31 08:48 | - | 进行中 | 用户进行中的工作，本次仅登记状态，不代表已完成 |
| ADJ-013 | 调整 | ID 去重：功能开发区 BUG-025~033 与代码 Bug 区重复，移入代码 Bug 区并改号为 BUG-061~069（BUG-025->BUG-061; BUG-026->BUG-062; BUG-027->BUG-063; BUG-028->BUG-064; BUG-029->BUG-065; BUG-030->BUG-066; BUG-031->BUG-067; BUG-032->BUG-068; BUG-033->BUG-069）；DOC-051 重复条目改号为 DOC-054 | 2026-08-10 15:20 | 2026-08-10 15:20 | 已完成 | 保留原始记录内容，仅改号和迁移分区 |

## 检查事项

| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| CHK-001 | 检查 | 确认现有 PDF skill 能支撑 PDF 转 Markdown，但不是一键专用转换器 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 明确普通 PDF 可提取文本/表格/图片后组织为 Markdown，扫描版 PDF 需要 OCR fallback |
| CHK-002 | 检查 | 对照 `wangminle/docs-to-markdown` 思路，梳理当前项目实现 PDF-to-Markdown 所需改造 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 结论为需要独立 `pdf_to_markdown` 能力、OCR fallback、表格 Markdown 化、图片抽取和结构清洗 |
| CHK-003 | 检查 | 检查根目录 `scripts/` 与 Skill 内 `scripts/` 的同步关系 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 之前已按 `diff -qr` 排除缓存文件核对，确认 Skill 脚本与根目录脚本保持一致 |
| CHK-004 | 检查 | 读取 `examples/task-list.md` 的分类和字段 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 仅参考样例结构，未修改 `examples/` 中的内容 |
| CHK-005 | 检查 | 核对新建 `task-list.md` 和样例文件状态 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 已读取根目录清单结构，并通过 `git diff -- examples/task-list.md` 确认样例文件无改动 |
| CHK-006 | 检查 | 使用 `skill-creator` 规范完整检查 `skills/pdf-markdown-summary/` | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | `quick_validate.py` 通过；三个入口脚本 `--help` 通过；`compileall` 通过；发现目录名含 `&`、frontmatter 名称与目录不一致、缺少推荐 `agents/openai.yaml`、存在 `examples/README.md` 和缓存/系统文件等规范问题 |
| CHK-007 | 检查 | 复核 Skill 命名规范第 1、2 点修复结果 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | `quick_validate.py skills/pdf-markdown-summary` 通过；三个入口脚本 `--help` 通过；当前文件中已无 `pdf-markdown-&-summary` 残留引用 |
| CHK-008 | 检查 | 复核 Skill 规范缺口修复结果 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | `quick_validate.py skills/pdf-markdown-summary` 通过；三个入口脚本 `--help` 通过；确认 Skill 内无 README 类辅助文档，发布目录无 `.DS_Store`、`__pycache__`、`.pyc` |
| CHK-009 | 检查 | 提交前检查 GitHub 与本地 Git 状态 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | `main` 与 `origin/main` 同步；确认远端仓库为 `wangminle/skills-pdf-markdown-summary`；`old-version/` 既有文件修改为换行符变化，不纳入本次 stage |
| CHK-010 | 检查 | 提交前重新运行基础验证 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | `python3 -m compileall skills/pdf-markdown-summary/scripts` 通过；三个入口脚本 `--help` 通过；排除 `old-version/` 后 `git diff --check` 通过 |
| CHK-011 | 检查 | 清理 `main` 历史中的重复提交与空 merge | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 已保留备份分支 `codex-main-before-rebase-20260605`；删除重复 patch `760a1d1`、`a02a33c` 和空 merge `dc38520`；保留非空 merge 内容为普通提交；新旧树内容一致 |
| CHK-012 | 检查 | 将 `V0.2.1` 的三次提交压缩为单个提交 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 已保留备份分支 `codex-main-before-v021-squash-20260605`；将 `c9b8737`、`8a353c2`、`5031fe7` 重写为单个 `aef4f25`；新旧 `main` 顶端树内容一致 |
| CHK-013 | 检查 | 逐张检查 `tests/results/20250605` 下 140 张图表截图效果 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 结论为代码有修复入口但实际输出未达标，主要问题是 caption 索引未评分和污染结果仍被保存 |
| CHK-014 | 检查 | 按 skill-creator 规范复检 skill 包合规性 | 2026-06-13 00:00 | 2026-06-13 00:00 | 已完成 | 9 项全部通过：name 与目录一致（kebab-case）、description 598 字符含触发条件、frontmatter 仅标准字段、顶层仅标准目录、references 3 个全被引用无孤立、无运行产物入库、无 README 辅助文档、agents/openai.yaml 齐全、渐进式披露合理；git 层面完全符合；唯一提示 scripts/ 下 __pycache__ 物理存在（运行产物，已 gitignore 隔离） |
| CHK-015 | 检查 | 核对 `tests/results/20260622-001/` debug-visual 分析结论是否正确 | 2026-06-23 08:51 | 2026-06-23 08:51 | 已完成 | 复跑 `python tests/scripts/analyze_debug_batch.py`，确认附件中的 8 篇 PDF legend/flagged 数量与全局统计一致；同时确认当前批次 `run.log.jsonl` 文件为空，因此“stderr 日志比脚本多 fallback”在现有产物中不可直接复现，但代码确有普通 logger fallback 信息未进入结构化日志的问题 |
| CHK-016 | 检查 | 从根因重新审查 PDF 图表定位架构、完整仓库与外部最佳实践 | 2026-07-21 00:00 | 2026-07-21 00:00 | 已完成 | 通读正式 Skill、当前脚本与测试、关键历史调优/竞品文档和 Basic Benchmark 复盘；核对 PDF 语义结构、PDFFigures2、GROBID、PyMuPDF4LLM Layout、Docling、DocLayout-YOLO、PP-StructureV3、PaddleOCR-VL、MinerU、OmniDocBench 官方资料；结论为开放世界下仅靠 caption/排版启发式不能保证 99%，应改为多证据候选融合、可插拔布局后端、bbox benchmark 与低置信复核 |
| CHK-017 | 检查 | 核对 `PDF图表提取架构根因复盘与技术路线分析报告-20260721.md` 事实与结论是否成立 | 2026-07-27 23:41 | 2026-07-27 23:41 | 已完成 | 逐条复核：38 模块/14,101 行、tests/scripts 5,444 行、`run_all.py --skip-golden` 222 通过 0 失败（8+3+3+1+56+3+19+129）、`tests/results/` 为空、benchmark 7+1 PDF、tables 三档同路径、pdfplumber 未接线、OCR `not_implemented`、资产追加文末、`AttachmentRecord`/`index.json` 无 bbox/置信度、单页单矩形、Golden 产物写入 `tests/basic-benchmark/` 旁均成立；`find_tables` 与 Tagged PDF 确未接线，故 Phase 1 建议有增量；外部数据 PDFFigures2（CS-150 0.980/0.961/0.970、CS-Large 0.936/0.897/0.916）、DocLayout-YOLO DocLayNet mAP 79.7、PaddleOCR-VL 0.9B/109 语言、PyMuPDF4LLM Layout 为 CPU-only GNN、Docling 为 RT-DETR 系+TableFormer、299 样本统计口径均核实正确；发现 4 处需修正：仓库许可证为 Apache-2.0 而非 MIT、策略冲突清单实为 25 条而非 27 条、OmniDocBench 1651 页/10 类/5 版式/5 语言属 v1.6 而所引 CVPR 2025 论文为 981/9/4/3、Golden 断言中 caption 非空与 page/continued 差异实际不置 `passed=False`；另有 13 步主链描述简化（无 Phase C、`layout blocker` 实为 `adjust_clip_with_layout`、标题回补在 baseline 亦发生）与三处逻辑需收紧（99% 定义两次切换、图匹配未消除调参空间、Phase 0 的 50–100 标注量不足以支撑 Phase 1 判定）；核心结论"开放世界下纯结构启发式不能保证 99%"成立 |
| CHK-018 | 检查 | 按架构报告方案用独立实验验证 PyMuPDF4LLM Layout 粗定位可行性 | 2026-07-28 15:13 | 2026-07-28 15:30 | 已完成 | 在 `docs/3-experiments/20260728-pymupdf4llm-layout-bbox/` 对 basic-benchmark 8 PDF 跑 Layout+legacy；建立 provisional bbox GT（180 caption）；Layout 配对率 95.6%，与 legacy final mean IoU 0.72；结论：报告 Phase 2 方向可行，须保留精修，未合入主链 |
| CHK-019 | 检查 | 二次独立复核 Layout 实验指标口径、代表案例与正式 Skill 架构边界 | 2026-07-28 16:30 | 2026-07-28 17:00 | 已完成 | 阅读 GT、metrics、compare、实验脚本和正式 `AttachmentRecord`/Figure/Table 主链；确认 Layout 0.68 秒/页、legacy 0.57 秒/页，Figure/Table mean IoU 分别为 0.664/0.780；发现 provisional GT 由 Layout 自身构造、8 组候选框被重复分给 16 条资产、legacy 对比仅按 type+ident 且忽略页码，故 95.6% 配对率和硬失败比例不能作为真实准确率；架构结论收紧为 Layout 作可插拔候选/证据后端、全页一对一配对独立成层、现有规则降级为专用小幅精修和 legacy fallback |

## 测试数据

| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| TST-001 | 开发 | 新增 caption 锚点与正文污染回归测试 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 新增 `tests/scripts/test_caption_anchor_quality.py`，覆盖候选评分、最低分过滤、正文污染检测和同页相邻 caption 边界限制；`run_all.py --skip-golden` 当前 146 通过、0 失败 |
| TST-002 | 检查 | 使用 Basic Benchmark 7 个 PDF 重新实测最终图表抽取效果 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 输出位于 `tests/results/20260605/*_after_final_accept/`；7 个 PDF 共写入 113 张有效图表截图，其中 figures=69、tables=44 |
| TST-003 | 检查 | 实测 PDF-to-Markdown 导出功能并补充 CLI 输出路径回归测试 | 2026-06-06 00:00 | 2026-06-06 00:00 | 已完成 | 新增 `tests/scripts/test_pdf_to_markdown_cli.py` 并接入 `run_all.py`；`run_all.py --skip-golden` 当前 149 通过、0 失败；DeepSeek Markdown 导出产物位于 `tests/results/20260606/DeepSeek_V3_2_markdown_export_fixed2/` |
| TST-004 | 检查 | 反复对照画线输出验证 DeepSeek_V3_2 与 FunAudio-ASR 截图区域 | 2026-06-06 00:00 | 2026-06-06 00:00 | 已完成 | 最终输出位于 `tests/results/20260606-012/`；逐图核对 DeepSeek 4 图 + 1 表、FunAudio 4 图 + 8 表均完整且未混入正文/章节标题；`run_all.py --skip-golden` 为 158 通过、0 失败 |
| TST-005 | 检查 | 使用 GPT-5 System Card、Gemini 2.5 Report 扩展验证截图算法，并确保 DeepSeek/FunAudio 不退化 | 2026-06-06 00:00 | 2026-06-06 00:00 | 已完成 | 最终输出位于 `tests/results/20260606-022/`；GPT-5 为 31 图 + 26 表，Gemini 为 14 图 + 12 表；画线与总览目视确认 GPT Table 7/8、Gemini Table 3/4/11 等关键边界正确；DeepSeek 4 图 + 1 表、FunAudio 4 图 + 8 表与 `20260606-012` 逐图 SHA-256 完全一致；`run_all.py --skip-golden` 为 166 通过、0 失败 |
| TST-006 | 检查 | 使用 Attention、Qwen3-Omni、HFT Risk Books 扩展画线调试，并回归既有四份 PDF | 2026-06-11 00:00 | 2026-06-11 00:00 | 已完成 | 最终输出位于 `tests/results/20260611-007/`；新增三份分别为 5 图 + 4 表、3 图 + 18 表、8 图 + 1 表；既有四份无图表缺失或已知视觉退化；FunAudio 逐图哈希完全一致；完整测试 178 通过、0 失败 |
| TST-007 | 检查 | 使用 Attention 真实双栏 PDF 画线验证 BUG-018 修复并补充回归测试 | 2026-06-13 00:00 | 2026-06-13 00:00 | 已完成 | 最终输出位于 `tests/results/20260613-004/1706.03762v7-attention_is_all_you_need/`；5 图 + 4 表均完整，Table 2/3 最终边界停在正文前，9 张最终截图与 `20260611-007` 逐图 SHA-256 完全一致；新增 3 条回归测试；`run_all.py --skip-golden` 为 181 通过、0 失败，`compileall` 与三个入口 `--help` 通过 |
| TST-008 | 检查 | 验证 BUG-019 健壮性与一致性修复 | 2026-06-13 00:00 | 2026-06-13 00:00 | 已完成 | 新增 `test_maintenance_fixes.py` 覆盖异常关闭、无对象评分、Figure 引用过滤、完整流程复用、共享正则、drawing 回退、确定性编号和 Supplementary 上下文；`run_all.py --skip-golden` 为 190 通过、0 失败，`compileall`、三个入口 `--help` 与 `git diff --check` 通过；完整 `run_all.py` 的 3 项 Golden 因 Basic Benchmark 目录缺少 `images/index.json` 失败，与本次代码无关 |
| TST-009 | 检查 | 对 Basic Benchmark 7 个 PDF 执行完整 Markdown 转换与 `--debug-visual` 图表提取 | 2026-06-18 00:00 | 2026-06-18 00:00 | 已完成 | 输出位于 `tests/results/20260618-001/`；每个 PDF 按 `markdown/`、`assets/`、`images/`、`txt/` 分层保存；最终共提取 68 图 + 70 表，生成 138 张 debug 画线图；已按最终 `index.json` 重写 Markdown 资产段落，验证 138 个 Markdown 图片链接均存在 |
| TST-010 | 检查 | 验证 BUG-020 的 Attention Figure 2 图内标题裁剪修复 | 2026-06-18 00:00 | 2026-06-18 00:00 | 已完成 | 新增 far-side 检测回归测试，先复现 9 通过、1 失败，再修复为 10 通过、0 失败；重跑 Attention 的 `--debug-visual`，`Figure_2_p4_debug_stages.png` 红框已包含顶部说明；`compileall`、三个入口 `--help`、`run_all.py --skip-golden`（191 通过、0 失败）均通过 |
| TST-011 | 检查 | 验证 BUG-021 的 Attention Figure 3 dense label 裁剪修复 | 2026-06-18 00:00 | 2026-06-18 00:00 | 已完成 | 新增小对象带回归测试，先复现 10 通过、1 失败，再修复为 11 通过、0 失败；重跑 Attention `--debug-visual` 后 Figure 3 的 phase_b 从原 y1=253.8 恢复到 y1=306.3，final 为 `114.5,93.4 -> 509.8,306.5`；已目视检查 debug 图并验证该 PDF Markdown 9 个图片链接均存在 |
| TST-012 | 检查 | 验证 BUG-022 的 Attention Figure 5 竖排文字裁剪修复 | 2026-06-18 00:00 | 2026-06-18 00:00 | 已完成 | 新增竖排文本标签回归测试，先复现 11 通过、1 失败，再修复为 12 通过、0 失败；重跑 Attention `--debug-visual` 后 Figure 5 的 phase_b 从原 y1=557.4 恢复到 y1=596.3，final 为 `116.4,178.6 -> 504.0,596.4`；已目视检查 debug 图和最终截图，并验证该 PDF Markdown 9 个图片链接均存在 |
| TST-013 | 检查 | 验证 BUG-023 的 Attention Table 2 顶部横线补偿修复 | 2026-06-19 00:00 | 2026-06-19 00:00 | 已完成 | 新增渲染横线回归测试，先复现 12 通过、1 失败，再修复为 13 通过、0 失败；重跑 Attention `--debug-visual` 后 Table 2 的 baseline/phase_b 从原 y0=98.1 上移到 y0=93.3，final 为 `125.8,93.3 -> 486.3,246.9`；已目视检查 debug 图和最终截图，并验证该 PDF Markdown 9 个图片链接均存在 |
| TST-014 | 检查 | 验证 BUG-024 的 Qwen3-Omni Figure 1 baseline 与页眉噪声修复 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 新增 `test_baseline_clip_preserves_spread_diagram_labels_above_caption` 和 `test_autocrop_trims_far_side_header_rule_before_figure_content`；`test_caption_anchor_quality.py` 36 通过、0 失败，`test_maintenance_fixes.py` 13 通过、0 失败，`compileall` 通过；输出位于 `tests/results/20260620-005/2509.17765v1-Qwen3-Omni_Technical_Report/` |
| TST-015 | 检查 | 验证 BUG-025 的 Qwen3-Omni Table 9 表格尾部恢复修复 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 新增 `test_layout_trim_preserves_structured_table_tail`；`test_caption_anchor_quality.py` 37 通过、0 失败，`test_maintenance_fixes.py` 13 通过、0 失败，`compileall` 与三个入口脚本 `--help` 通过；输出位于 `tests/results/20260620-006/2509.17765v1-Qwen3-Omni_Technical_Report/` |
| TST-016 | 检查 | 验证 BUG-026 的 FunAudio-ASR Table 5 final 文本 bbox 安全补边 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 新增 `test_table_final_padding_keeps_text_bbox_before_caption`；`test_caption_anchor_quality.py` 38 通过、0 失败，`test_maintenance_fixes.py` 13 通过、0 失败，`compileall` 与三个入口脚本 `--help` 通过；输出位于 `tests/results/20260620-009/FunAudio-ASR/` |
| TST-017 | 检查 | 验证 BUG-027 的 Gemini Figure 3 窄轴刻度误触发 exact-two-lines 裁切修复 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 新增 `test_text_trim_ignores_narrow_axis_ticks_near_caption`；`test_caption_anchor_quality.py` 39 通过、0 失败，`test_maintenance_fixes.py` 13 通过、0 失败，`compileall` 与三个入口脚本 `--help` 通过；输出位于 `tests/results/20260620-010/gemini_v2_5_report/` |
| TST-018 | 检查 | 验证 BUG-028 的 Gemini Figure 5 / Figure 12 图内标题恢复修复 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 新增 `test_baseline_expands_to_nearby_chart_title_above_figure` 与 `test_baseline_title_recovery_ignores_page_header_and_section_title`；`test_caption_anchor_quality.py` 41 通过、0 失败，`test_maintenance_fixes.py` 13 通过、0 失败，`compileall`、三个入口脚本 `--help` 与 `git diff --check` 通过；输出位于 `tests/results/20260620-012/gemini_v2_5_report/` |
| TST-019 | 检查 | 验证 BUG-029 的 Qwen3-Omni Figure 3 拆分章节标题负例修复 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 新增 `test_baseline_title_recovery_ignores_split_numbered_section_heading`；`test_caption_anchor_quality.py` 42 通过、0 失败，`test_maintenance_fixes.py` 13 通过、0 失败，`compileall`、三个入口脚本 `--help` 与 `git diff --check` 通过；Qwen 输出位于 `tests/results/20260620-013/2509.17765v1-Qwen3-Omni_Technical_Report/`，Gemini 回归输出位于 `tests/results/20260620-014/gemini_v2_5_report/` |
| TST-020 | 检查 | 验证 BUG-030 的 Gemini Figure 14/15 near-caption 图内标注保护 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 新增 `test_phase_b_preserves_near_caption_panel_subcaptions` 与 `test_phase_b_preserves_near_caption_prompt_text_column`；局部补边重构后 `test_caption_anchor_quality.py` 47 通过、0 失败，`test_maintenance_fixes.py` 13 通过、0 失败，`compileall` 与入口脚本 `--help` 通过；输出更新至 `tests/results/20260620-018/gemini_v2_5_report/` |
| TST-021 | 检查 | 验证 BUG-031 的 Attention/Kearns 标题与轴标题冲突修复 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 新增 `test_final_title_recovery_ignores_large_section_title`、`test_phase_a_restores_far_side_short_chart_title`、`test_phase_b_expands_to_nearby_axis_titles_without_full_edge_fallback`；重跑 Attention/Kearns 到 `tests/results/20260620-017/`，重跑 Gemini 到 `tests/results/20260620-018/` 并目视核对关键 debug 图；`test_caption_anchor_quality.py` 47 通过、`test_maintenance_fixes.py` 13 通过 |
| TST-022 | 检查 | 验证 BUG-032 GPT-5 伪双栏防护与 BUG-033 Gemini 多行表头回收 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 新增 `test_column_detection_rejects_unrealistic_large_gap_candidate`、`test_x_refine_ignores_untrusted_wide_gap_layout_columns`、`test_table_header_recovery_restores_multiline_header_above_table_body`；`test_caption_anchor_quality.py` 50 通过、`test_maintenance_fixes.py` 13 通过，`compileall`、四个入口脚本 `--help` 与 `git diff --check` 通过；真实输出位于 `tests/results/20260620-019/` |
| TST-023 | 检查 | 验证 BUG-034 的 Gemini 表格 final 表头回补与 Table 5 方向修复 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 新增 `test_table_final_text_bounds_recovers_connected_header_band` 与 `test_table_direction_tie_break_prefers_nearest_structured_table`；`test_caption_anchor_quality.py` 52 通过、`test_maintenance_fixes.py` 13 通过，`compileall` 与四个入口脚本 `--help` 通过；重跑 Gemini 到 `tests/results/20260620-021/` 并目视核对 Table 1/2/5/10/11 |
| TST-024 | 检查 | 验证 BUG-035 的 Gemini Table 4/6/12 final 正文 blocker 与正文前缀裁除 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 新增 `test_table_final_text_bounds_stops_before_body_paragraph` 与 `test_table_final_text_bounds_recovers_header_but_not_leading_body_line`；`test_caption_anchor_quality.py` 54 通过、`test_maintenance_fixes.py` 13 通过，`compileall` 与四个入口脚本 `--help` 通过；重跑 Gemini 到 `tests/results/20260620-027/` 并目视核对 Table 4/6/12，同时确认 Table 5/10 无回退 |
| TST-025 | 检查 | 验证 BUG-037/038 的多 PDF 表格回归与 GPT-5 Figure 22 方向纠偏 | 2026-06-21 00:00 | 2026-06-21 00:00 | 已完成 | 新增 `test_table_far_side_keeps_header_followed_by_table_rows`、`test_table_far_side_trims_numbered_section_heading_above_table`、`test_table_far_side_keeps_same_row_data_cell_at_far_edge`、`test_bare_figure_caption_prefers_above_when_next_caption_below`、`test_bare_figure_caption_keeps_below_without_above_object`；`test_caption_anchor_quality.py` 61 通过，`test_maintenance_fixes.py` 13 通过，`compileall` 通过；重跑 Attention/FunAudio/Gemini/Kearns/GPT-5/Qwen 到 `tests/results/20260621-001/` 并目视核对用户点名图表与 Qwen BUG-036 回归 |
| TST-026 | 检查 | 验证 BUG-039 的 Table final 远端收紧与 layout 同排末行回补 | 2026-06-21 00:00 | 2026-06-21 00:00 | 已完成 | 新增 `test_table_final_text_bounds_recovers_qwen_table2_tail_row`、`test_table_final_text_bounds_recovers_tail_row_from_layout_blocks`、`test_table_final_text_bounds_trims_far_side_blank_before_table`、`test_table_final_text_bounds_trims_body_tail_before_header`、`test_table_far_side_trims_single_number_section_heading`、`test_table_far_side_keeps_layout_only_same_row_data_cell`；局部测试 `test_caption_anchor_quality.py` 为 67 通过、`test_maintenance_fixes.py` 为 13 通过，`compileall` 通过；真实输出位于 `tests/results/20260621-002/` 与 `tests/results/20260621-004/`，已目视核对用户点名图表 |
| TST-027 | 检查 | 验证 BUG-040 的 Gemini/GPT-5 三个剩余小瑕疵修复 | 2026-06-21 00:00 | 2026-06-21 00:00 | 已完成 | 新增 `test_table_final_text_bounds_trims_numeric_body_tail_before_header`、`test_table_final_text_bounds_keeps_wrapped_tail_cell_line`、`test_figure_noise_trim_ignores_sentence_tail_as_content_evidence`、`test_figure_post_autocrop_trims_narrow_lowercase_sentence_tail`、`test_figure_title_recovery_ignores_lowercase_sentence_tail`；局部测试 `test_caption_anchor_quality.py` 为 72 通过；重跑 Gemini 到 `tests/results/20260621-007/`、GPT-5 到 `tests/results/20260621-009/` 并目视核对点名图表；完整 `python -m pytest tests/scripts -q` 为 111 通过、10 个既有 warning，`compileall`、四个入口脚本 `--help` 与 `git diff --check` 通过 |
| TST-028 | 检查 | 使用最新代码转换 `DeepSeek_V4.pdf` 并生成 debug visual 与阅读摘要 | 2026-06-21 00:00 | 2026-06-21 00:00 | 已完成 | 输出位于 `tests/results/20260621-013/DeepSeek_V4/`；运行 `process_pdf.py --preset robust` 生成 `markdown/DeepSeek_V4.md`，运行 `extract_pdf_assets.py --debug-visual --debug-captions --no-prune-images` 生成 debug 画线图；最终 `images/index.json` 为 13 张 Figure、13 张 Table，`Table 6` 因 fallback 文本污染过高被拒绝；验证主 Markdown 26 个图片链接、摘要 23 个图片链接、index 26 个图表文件均存在；摘要位于 `markdown/DeepSeek_V4_阅读摘要-20260621.md` |
| TST-029 | 检查 | 逐张审查 `DeepSeek_V4` debug visual 并对照当前流程文档定位问题 | 2026-06-21 00:00 | 2026-06-21 00:00 | 已完成 | 审查 `tests/results/20260621-013/DeepSeek_V4/images/debug/` 全部 27 张 debug 图及最终图表 contact sheet；Figure 组整体可用，问题集中在 Table 路径：`Table_3` 与 `Table_11` 方向被上一张表吸走，`Table_6` 正文引用误识别导致真实 Table 6 被漏掉，`Table_8` 带入表后正文，`Table_12` 大表尾部截断；已对照 `docs/PDF图表提取流程逻辑说明-20260621.md` 将问题映射到 caption 引用过滤、Table 方向判定、baseline/text-block 限制、table-band/final text-bbox 回补和污染验收分支 |
| TST-030 | 检查 | 验证 DeepSeek_V4 Figure 2/4/8/13 裁剪修复 | 2026-06-22 00:00 | 2026-06-22 00:00 | 已完成 | 新增 pipe caption 非引用、figure 远端对象回收、final near-caption padding、长 pipe caption 邻近方向纠偏、链式图内标题回收等回归测试；`test_caption_anchor_quality.py` 为 80 通过，`compileall` 与四个入口脚本 `--help` 通过；重跑 `DeepSeek_V4.pdf` 至 `tests/results/20260622-004/DeepSeek_V4/`，`images/index.json` 为 15 张 Figure、13 张 Table；已目视核对 `Figure_2_p6`、`Figure_4_p11`、`Figure_8_p40`、`Figure_13_p43` debug 图，顶部/底部截断和 Figure 8 漏检/误框问题已修复 |
| TST-031 | 检查 | 验证 BUG-041~046 六个 bug 修复批次 | 2026-06-22 00:00 | 2026-06-22 00:00 | 已完成 | `python3 -m compileall scripts/` 通过；四个入口脚本 `--help` 均正常；使用 `tests/basic-benchmark/` 中 Attention is all you need（5 figures/4 tables）、Qwen3-Omni（3 figures/18 tables）、Kearns（8 figures/1 table）三个 PDF 以及 `tests/some-verification/DeepSeek_V4.pdf`（15 figures/13 tables）进行实际提取验证，均成功生成 `index.json`、图片和文本，未出现异常；`--no-refine 1,2` 同时作用于 Figure 和 Table 路径，验证 BUG-042 修复生效；`process_pdf.py` 端到端流程通过，Markdown 输出正常；输出位于 `tests/results/20260622-001/` |
| TST-032 | 检查 | 验证 `refine.py` 模块拆分、Markdown 合并与 `DrawItem`/像素检测边界清理 | 2026-06-22 00:00 | 2026-06-22 00:00 | 已完成 | `python3 -m compileall skills/pdf-markdown-summary/scripts` 通过；四个入口脚本 `extract_pdf_assets.py`、`pdf_to_markdown.py`、`summarize_pdf.py`、`process_pdf.py` 的 `--help` 均正常；`PYTHONPATH=skills/pdf-markdown-summary/scripts` 导入检查确认 `lib.refine`、Figure/Table 主循环、Markdown 新旧路径和 `DrawItem` 单一来源均可加载；`python3 -m pytest tests/scripts -q` 为 119 通过、15 个既有 warning；`git diff --check -- skills/pdf-markdown-summary/scripts task-list.md` 通过，全量 `git diff --check` 仍受既有 `docs/2-ref/pdf_image_extractor.py` 与 `package-lock.json` 行尾空白影响，按只读规则未处理 `docs/2-ref/` |
| TST-033 | 检查 | 验证 BUG-047 fallback/Phase D/结构化日志修复 | 2026-06-23 08:51 | 2026-06-23 08:51 | 已完成 | `python -m compileall skills\pdf-markdown-summary\scripts tests\scripts` 通过；`python tests\scripts\test_maintenance_fixes.py` 为 19 通过、0 失败；`python tests\scripts\test_qa04_structured_log.py` 为 1 通过、0 失败；三个入口脚本 `extract_pdf_assets.py`、`pdf_to_markdown.py`、`summarize_pdf.py` 的 `--help` 均通过；复跑 `python tests\scripts\analyze_debug_batch.py` 正常输出当前批次统计 |
| TST-034 | 检查 | 验证 BUG-048 精裁回退高度门槛修复 | 2026-06-23 13:16 | 2026-06-23 13:16 | 已完成 | 先运行 `pytest tests/scripts/test_qa03_debug_artifacts.py::test_rejected_table_still_creates_debug_visuals -q` 复现 1 失败；修复后同用例为 1 通过，完整 `test_qa03_debug_artifacts.py` 为 3 通过；`test_caption_anchor_quality.py test_maintenance_fixes.py` 为 99 通过；`python3 tests/scripts/test_maintenance_fixes.py` 为 19 通过、0 失败；`python3 -m compileall skills/pdf-markdown-summary/scripts tests/scripts` 通过；四个入口脚本 `extract_pdf_assets.py`、`pdf_to_markdown.py`、`process_pdf.py`、`summarize_pdf.py` 的 `--help` 均通过；`pytest tests/scripts -q` 为 125 通过、15 个既有 warning；本机 `python` 命令不存在，已改用 `python3` |
| TST-035 | 检查 | 验证架构复盘期间当前非 Golden 测试基线 | 2026-07-21 00:00 | 2026-07-21 00:00 | 已完成 | 运行 `python3 tests/scripts/run_all.py --skip-golden`，P0/P1、debug artifacts、结构化日志、caption 锚点、PDF-to-Markdown CLI、维护修复和正则共 222 通过、0 失败；未运行 Golden，因为当前 `tests/results/` 无既有结果且该入口会向 `tests/basic-benchmark/<stem>/` 写产物，与现行输出目录规则不一致 |
| TST-036 | 检查 | basic-benchmark 上 PyMuPDF4LLM Layout vs legacy robust 独立实验 | 2026-07-28 15:20 | 2026-07-28 15:30 | 已完成 | 8 PDF Layout 全通过；legacy robust+debug-visual 全通过并解析 final bbox；provisional GT 180 资产、配对率 95.6%；Layout↔legacy mean IoU 0.72；产物在 `docs/3-experiments/20260728-pymupdf4llm-layout-bbox/` |
| TST-037 | 检查 | Layout vs legacy 逐资产深度对比与失败模式分类 | 2026-07-28 15:45 | 2026-07-28 16:20 | 已完成 | 新增实验脚本 04~11（对比图、分歧统计、单页排查、语义质量、碎片化、自动裁决、caption 证据、性能）；渲染 180 组同页双框对比图并目视复核 30 例低 IoU 案例；自动裁决：打平 98（54.4%）、Layout 更好 63（35.0%）、legacy 更好 14（7.8%）、冲突 5（2.8%）；硬失败 legacy 10（5.6%）vs Layout 14（7.8%）且模式互补；legacy 空白率均值 22.8%、35 例 >40%、6 例正文污染 >10%；多框资产 4.1%，并集 7/7 改善 0 例变差；Layout 性能 0.68 s/页、270 页 182.7s、依赖新增 onnxruntime 42.5MB；结论见 `docs/3-experiments/20260728-pymupdf4llm-layout-bbox/架构设计评估与建议-20260728.md` |
| TST-038 | 检查 | 测试套件整改与全量回归验证 | 2026-07-31 08:48 | 2026-07-31 08:48 | 已完成 | `test_extraction_golden.py` 对比差异改为判失败、产物输出到 `tests/results/<yyyymmdd-xxx>/` 并新增 pytest 入口（golden marker）；`run_all.py` 重写为统一走 pytest 调用，修复 `--skip-p1` 误嵌套 5 个套件的问题，golden 默认跳过（`--with-golden` 启用）；`test_p0_env_priority.py` monkeypatch 化并新增 argv 透传回归测试；`test_qa04_structured_log.py` 增加日志全局状态还原；`test_regex_patterns.py` 的 TestCase/TestResult 改名 RegexCase/RegexResult；`analyze_debug_batch.py` 批次路径改为命令行参数；新增 `tests/scripts/conftest.py` 注册 golden marker；验证：`pytest tests/scripts -q` 为 126 通过、0 失败，`run_all.py` 8 个套件全部 OK，四个入口脚本 `--help` 正常 |
| TST-039 | 检查 | A0-2：golden 纳入 bbox/文件指纹并生成 8 份基准 + 反向验证 | 2026-07-31 15:30 | 2026-07-31 15:30 | 已完成 | `ItemSignature` 增加 `final_bbox`（≤0.5pt 容差）+ PNG 尺寸/sha256 严格比对；meta 断言禁止空跑（基准缺失即红）；golden 默认纳入 pytest 普通运行；8 份基准生成（产物 `tests/results/20260731-001/`），各 PDF 资产数：Attention 5F4T、Qwen3-Omni 3F18T、DeepSeek_V3_2 4F1T、FunAudio 4F8T、Gemini 15F12T、GPT-5 31F26T、Kearns 8F1T、DeepSeek_V4 15F14T；基准为初始冻结（变更检测器），已知缺陷 gemini 缺 Figure 9、DeepSeek_V4 Table 6 类问题按方案预期一并冻结；反向验证：篡改 bbox +5pt 与篡改 sha256 均报红、恢复后转绿；`pytest tests/scripts -q` 为 135 passed、0 skipped，`run_all.py` 9 套件全 OK |
| TST-040 | 检查 | Basic Benchmark 8 PDF `--debug-visual` 全量跑批与效果评估 | 2026-07-31 19:37 | 2026-07-31 19:45 | 已完成 | 产物 `tests/results/20260731-003/`；8/8 exit=0，约 2m17s；提取 85F+84T=169，与 CORE/golden 数量与 `final_bbox` 完全一致（bbox_diff=0）；debug 画线 169 张；`refine_fallback` 49 次（约 29%），主因 object_coverage/area_ratio；`analyze_debug_batch` 有大量 shrink/fallback flag（信号偏多，不全等于缺陷）；目视：Attention Fig1/Table2、Qwen Table3、FunAudio Table1、DeepSeek_V4 Fig4 可用；DeepSeek_V4 Table6 仍为正文引用假 caption（与 TST-029/039 已知冻结一致）；Attention 冒烟 GT eval：alignment/pairing/truncation=1.0/1.0/0，purity mean=0.43（框偏松）、excess_body 1/3；`pytest -m 'not golden'` 126 通过，`tests/eval/selfcheck` 通过 |
| TST-041 | 检查 | A2/A3 缺陷修复全量回归：新增 test_a2_a3_fixes + 重建 8 份 golden 并验证全绿 | 2026-08-10 14:30 | 2026-08-10 15:08 | 已完成 | test_a2_a3_fixes.py 9 passed；pytest tests/scripts -q → 144 passed 0 skipped（含 8 golden+coverage）；compileall 与四入口 --help 通过；tests/eval/selfcheck 全 PASS；提取批次 tests/results/20260810-001/；golden 位于 tests/basic-benchmark/*/images/golden_index.json（变更检测器，随本轮修复单独冻结） |
| TST-042 | 检查 | 全项目深度审查（4 并行审查 agent）+ BUG-070~072 修复验证 | 2026-08-29 00:00 | 2026-08-29 00:00 | 已完成 | 审查 agent 报告 ~60 条发现，逐条对抗性验证：确认 4 条真实缺陷（BUG-070/071/072 + 过期 docstring），推翻 13+ 条高危误报（含 off-by-one、prune 误删、双写覆盖、指纹位置/覆盖、方向反转、monkeypatch 错位等，均有代码/执行证据）；修复后验证：compileall OK、`pytest tests/ -q` → 147 passed 0 skipped（144 基线 + 3 新回归；skills/ 改动触发指纹变化，golden 按设计自动重提取新批次并与 20260810-001 基准比对通过，确认提取行为零变化）；四入口 `--help` 全过；`--no-*` 六旗标端到端复验全部尊重显式值且无显式传参时 preset 正常生效 |
| TST-043 | 检查 | 验证 BUG-073~076 与 Golden 顶层说明修复 | 2026-08-30 13:20 | 2026-08-30 13:20 | 已完成 | TDD 先红后绿：针对性 10 通过；`pytest tests/ -q` → 155 passed 0 skipped（147 基线 + 8 新回归）；compileall 通过；四入口 `--help` 通过；`git diff --check` 通过；skills 改动触发 golden 指纹变化并自动重提取，比对通过 |
| TST-044 | 检查 | 0.6.2 版本与文档审计全量验证 | 2026-08-30 13:00 | 2026-08-30 13:06 | 已完成 | pytest tests/ -q 为 155 passed、0 skipped（含 8 PDF Golden 重提取比较）；run_all.py 为 10 常规套件 + Golden 全 OK，155 通过、0 失败、0 跳过；compileall、四入口 --help、eval selfcheck、23 项针对性回归、CLI 87 旗标文档对照、10 份当前 Markdown 本地链接检查与 git diff --check 均通过。 |
| TST-045 | 检查 | 验证 visual-review 17+1 项修复（BUG-077~082） | 2026-09-07 16:17 | 2026-09-07 17:45 | 已完成 | 新增 `tests/scripts/test_visual_review_20260907.py`；`pytest tests/scripts/test_visual_review_20260907.py tests/scripts/test_caption_anchor_quality.py` 95 passed；`pytest tests/scripts/ -k "not golden"` 161 passed（golden 排除按规则不算全绿）；compileall 与四入口 `--help` 通过。问题 PDF 重提至 `tests/results/20260907-004/`（benchmark 只读）。002 `run_benchmark.sh` 统计改为 `type` 回退 `kind`。未跑 `--update-golden`。 |
| TST-046 | 检查 | 验证主链三态验收与题注对账（DEV-016） | 2026-09-07 22:47 | 2026-09-07 23:10 | 已完成 | `test_extraction_status_inventory.py` 13 passed；`compileall` 与四入口 `--help` 通过；`PDF_SKILL_ALLOW_GOLDEN_SKIP=1 pytest tests/scripts -k "not golden"` 175 passed、9 deselected（不算全绿）；Attention/Gemini 冒烟写入 `tests/results/20260907-005/`：Attention 9/9 accepted、inventory expected=exported=9；Gemini Figure 9 p31 accepted，Table 12 `review_required`（object_truncation），inventory 28/28。未更新 Golden。 |

## 文档维护

| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| DOC-001 | 文档 | 写入 PDF-to-Markdown 重构出发点与五步实施路径 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 文档位于 `docs/PDF-to-Markdown重构出发点与实施路径-20260605.md` |
| DOC-002 | 文档 | 新增 PDF Markdown Summary Skill 设计文档 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 原位于 `docs/2-plans/`，重构完成后于 DOC-019 归档至 `docs/1-archive/skill-refactor-plans-20260605/2026-06-05-pdf-summary-agent-skill-design.md` |
| DOC-003 | 文档 | 新增 PDF Markdown Summary Skill 实施计划 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 原位于 `docs/2-plans/`，重构完成后于 DOC-019 归档至 `docs/1-archive/skill-refactor-plans-20260605/2026-06-05-pdf-summary-agent-skill-implementation-plan.md` |
| DOC-004 | 文档 | 重写根目录 `README.md` | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 中文在前、英文在后，简要说明 Skill 作用、效果、安装和使用方法 |
| DOC-005 | 文档 | 更新根目录 `AGENTS.md` | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 记录目录职责、`old-version/` 规则、`docs/3-ref/` 只读规则和 `task-list.md` 规则 |
| DOC-006 | 文档 | 整理 `docs/` 下历史文档 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 与当前重构无关的旧文档已移动到 `docs/1-archive/legacy-docs-before-skill-refactor-20260605/` |
| DOC-007 | 文档 | 创建根目录 `task-list.md` | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 参考 `examples/task-list.md` 的分类和字段，并整理今天对话形成的任务记录 |
| DOC-008 | 文档 | 在 `AGENTS.md` 中新增 Markdown 文档命名规则 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 所有新建 Markdown 文档文件名必须增加 `-yyyyMMDD` 时间后缀 |
| DOC-009 | 文档 | 从 `AGENTS.md` 顶层目录职责中删除根目录 `scripts/` 说明 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 按用户要求移除“当前开发源码与兼容入口；有效更新需要同步到正式 Skill”这一条 |
| DOC-010 | 文档 | 提交前修正 `README.md` 的过期结构说明和空白问题 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 将根目录 `scripts/` 表述改为 Skill 包内脚本源码，移除不存在的 Skill `examples/README.md` 说明，并修复 `git diff --check` 报告的 README 空白问题 |
| DOC-011 | 文档 | 提交前规范化正式 Skill 脚本和当前文档的换行与行尾空白 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 仅处理正式 Skill、当前 docs、README、AGENTS、task-list 和 examples 样例；未处理 `docs/3-ref/` 参考文件和既有 `old-version/` 文件 |
| DOC-012 | 文档 | 在 `AGENTS.md` 中新增 Basic Benchmark 实测输出目录规则 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 实际 PDF 文档测试优先使用 `tests/basic-benchmark/`，输出写入 `tests/results/<YYYYMMDD>/<pdf-name>/`，并按 `markdown/`、`assets/`、`images/`、`txt/` 分层保存 |
| DOC-013 | 文档 | 记录 DeepSeek_V3_2 与 FunAudio-ASR 截图区域调优和修复完整过程 | 2026-06-06 00:00 | 2026-06-06 00:00 | 已完成 | 新增 `docs/PDF图表截图区域调优与修复完整记录-20260606.md`，记录初始问题、逐轮调优、根因、最终流程、代码改动、验证结果和后续建议；已核对文档关键记录并通过 `git diff --check` |
| DOC-014 | 文档 | 补充 GPT-5 System Card 与 Gemini 2.5 Report 扩展调优全过程 | 2026-06-06 00:00 | 2026-06-06 00:00 | 已完成 | 在 `docs/PDF图表截图区域调优与修复完整记录-20260606.md` 增补批次 `20260606-013` 至 `20260606-022`、新增根因、最终结果和回归结论 |
| DOC-015 | 文档 | 记录新增三份 PDF 调优与既有四份 PDF 回归验证全过程 | 2026-06-11 00:00 | 2026-06-11 00:00 | 已完成 | 新增 `docs/PDF图表截图区域调优与修复完整记录-20260611.md`，记录问题分类、算法调整、测试覆盖、七份 PDF 最终结果和不回退判定方法 |
| DOC-016 | 文档 | 记录 BUG-018 双栏 blocker 与强结构表格分组行带修复过程 | 2026-06-13 00:00 | 2026-06-13 00:00 | 已完成 | 新增 `docs/PDF双栏与强结构表格裁剪调优记录-20260613.md`，记录 review 结论、真实 Attention 画线验证、中间回归、最终规则和测试结果 |
| DOC-017 | 文档 | 按 skill-creator 规范补全 CLI 参数参考文档 | 2026-06-13 00:00 | 2026-06-13 00:00 | 已完成 | 新增 `skills/pdf-markdown-summary/references/cli-options.md`，覆盖 4 个入口全部参数（pdf_to_markdown/summarize_pdf/process_pdf 高层入口 + extract_pdf_assets 调参引擎按功能分组、常用调参场景、roadmap 预留参数）；SKILL.md References 段新增引用；两个现有 reference 各加 `cli-options.md` 交叉引用，确认 references 无孤立文件，`git diff --check` 通过 |
| DOC-018 | 文档 | 文档审查并更新过期内容 | 2026-06-13 00:00 | 2026-06-13 00:00 | 已完成 | 核实 README 输出文件清单与 roadmap 项均准确（gathered_text/figure_contexts/layout_model.json 仍产出；图片按 caption 位置插入仍为 roadmap）。更新 README：目录树补 `cli-options.md`、使用方法加调参提示、已完成列表补智能 caption 检测/四阶段精裁/双栏感知/复用机制/CLI 参考文档（中英两处对齐）。更新 `docs/skill-execution-flow-20260605.md`：修正日期笔误 2025→2026，Step B 反映 BUG-019/M2 的 `--reuse-existing` 复用机制；`git diff --check` 通过 |
| DOC-019 | 文档 | 归档已完成的 skill 重构计划文档 | 2026-06-13 00:00 | 2026-06-13 00:00 | 已完成 | 将 `docs/2-plans/` 下两个重构期文档（设计 + 实施计划）`git mv` 至 `docs/1-archive/skill-refactor-plans-20260605/`（保留 rename 历史），删除空的 `docs/2-plans/` 目录；同步更新 AGENTS.md 第 4 节 `docs/2-plans/` 描述与 task-list DOC-002/003 路径 |
| DOC-020 | 文档 | 新增 task-list 结构说明文档 | 2026-06-17 00:00 | 2026-06-17 00:00 | 已完成 | 文档位于 `docs/task-list结构说明-20260617.md`；已独立分析当前 `task-list.md` 的分区、字段、ID 前缀、动作枚举、状态用法和维护建议；`git diff --check -- task-list.md` 通过，`rg -n "[ \t]+$" docs/task-list结构说明-20260617.md task-list.md` 无行尾空白输出 |
| DOC-021 | 文档 | 新增 Basic Benchmark 图表细致排查记录 | 2026-06-18 00:00 | 2026-06-18 00:00 | 已完成 | 文档位于 `docs/Basic-Benchmark图表细致排查记录-20260618-0621.md`；记录 7 个 PDF 本轮排查目标、Attention Figure 2/3/5、Table 2 根因、调整、验证结果和后续策略冲突清单 |
| DOC-023 | 文档 | 补充 Qwen3-Omni Figure 1 图表裁剪排查记录 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 在 `docs/Basic-Benchmark图表细致排查记录-20260618-0621.md` 追加 Qwen3-Omni Figure 1 的现象、关键边界、根因、调整、验证与策略冲突项 |
| DOC-022 | 文档 | 同步 AGENTS.md 只读参考目录重编号（docs/3-ref→docs/2-ref） | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 用户将只读参考目录由 `docs/3-ref/` 重编号为 `docs/2-ref/`；更新 AGENTS.md §4（标注原 `docs/3-ref/`、已重编号、只读约束不变；禁止修改/删除/移动/重命名、禁止写入运行产物三条约束迁移到 `docs/2-ref/`）与 §8（验证规则“不要写入”同步改为 `docs/2-ref/`）；历史日志条目 ADJ-004/DOC-005/DOC-011 中 `docs/3-ref/` 为当时事实，保持不动 |
| DOC-024 | 文档 | 补充 Qwen3-Omni Table 9 表格下半部分截断排查记录 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 在 `docs/Basic-Benchmark图表细致排查记录-20260618-0621.md` 追加 Table 9 的现象、关键边界、layout far-strip 根因、尾部恢复策略、验证结果与策略冲突项 |
| DOC-025 | 文档 | 补充 FunAudio-ASR Table 5 final 红框贴字排查记录 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 在 `docs/Basic-Benchmark图表细致排查记录-20260618-0621.md` 追加 Table 5 的现象、关键边界、text bbox 安全补边策略、验证结果与策略冲突项 |
| DOC-026 | 文档 | 补充 Gemini Figure 3 只截取图上半部分排查记录 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 在 `docs/Basic-Benchmark图表细致排查记录-20260618-0621.md` 追加 Figure 3 的现象、关键边界、Phase A+ exact-two-lines 根因、窄轴刻度保护策略、验证结果与策略冲突项 |
| DOC-027 | 文档 | 补充 Gemini Figure 5 / Figure 12 图内标题被裁掉排查记录 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 在 `docs/Basic-Benchmark图表细致排查记录-20260618-0621.md` 追加两张图的现象、关键边界、layout blocker + final autocrop 根因、图内标题回收策略、验证结果与策略冲突项 |
| DOC-028 | 文档 | 补充 Qwen3-Omni Figure 3 图内标题回收冲突排查记录 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 在 `docs/Basic-Benchmark图表细致排查记录-20260618-0621.md` 追加 Figure 3 的冲突现象、关键边界、拆分章节编号根因、负例识别策略、Gemini 回归验证和策略冲突项 |
| DOC-029 | 文档 | 补充 Gemini Figure 14/15 near-caption 图内标注被 Phase B 裁掉排查记录 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 在 `docs/Basic-Benchmark图表细致排查记录-20260618-0621.md` 追加两张图的现象、关键边界、Phase B 对象裁剪根因、图内标注保护策略、验证结果与策略冲突项 |
| DOC-030 | 文档 | 补充 Attention Figure 3 与 Kearns Figure 4/6/7 标题和轴标题冲突复核记录 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 在 `docs/Basic-Benchmark图表细致排查记录-20260618-0621.md` 追加四张图的现象、真实干涉判断、关键边界、局部补边策略、验证结果与策略冲突项，并同步修正 BUG-030 的局部补边实现记录 |
| DOC-031 | 文档 | 补充 GPT-5 伪双栏横向塌缩与 Gemini Table 多行表头截断排查记录 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 在 `docs/Basic-Benchmark图表细致排查记录-20260618-0621.md` 追加 GPT-5 System Card 31 张 Figure 宽度复测、Gemini Table 1/3 表头恢复、风险权衡和策略冲突项 |
| DOC-032 | 文档 | 补充 Gemini 2.5 Report 表格二次复核记录 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 在 `docs/Basic-Benchmark图表细致排查记录-20260618-0621.md` 追加 Table 1/2/5/10/11 的现象、根因、final 连通行带回补、方向近邻 caption 负证据、验证结果和策略冲突项 |
| DOC-033 | 文档 | 补充 Gemini 2.5 Report 表格第三轮复核记录 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 在 `docs/Basic-Benchmark图表细致排查记录-20260618-0621.md` 追加 Table 4/6/12 的正文误纳入根因、正文 blocker、正文前缀裁除、验证结果和策略冲突项 |
| DOC-034 | 文档 | 补充 Qwen3-Omni 表格远端误吞章节标题排查记录 | 2026-06-20 00:00 | 2026-06-20 00:00 | 已完成 | 在 `docs/Basic-Benchmark图表细致排查记录-20260618-0621.md` 追加 Table 5/8/12/14/15/18 的现象、关键边界、拆分编号导致标题绕过过滤的根因、`trim_table_far_side_section_heading()` 与 `_has_same_row_data_cell()` 守卫、验证结果（含 Table 2/16 边界）和策略冲突项 |
| DOC-035 | 文档 | 补充多 PDF 表格回归与 GPT-5 Figure 22 裸 caption 方向纠偏记录 | 2026-06-21 00:00 | 2026-06-21 00:00 | 已完成 | 在 `docs/Basic-Benchmark图表细致排查记录-20260618-0621.md` 追加 Attention/FunAudio/Gemini/Kearns 表格回归样本、BUG-036 守卫升级、GPT-5 Figure 22 裸 caption 方向纠偏、`20260621-001` 验证坐标和策略冲突项 |
| DOC-036 | 文档 | 补充 20260621 剩余表格瑕疵收口记录 | 2026-06-21 00:00 | 2026-06-21 00:00 | 已完成 | 在 `docs/Basic-Benchmark图表细致排查记录-20260618-0621.md` 追加 Qwen Table 2/16、FunAudio Table 2、Kearns Table 1 与 GPT-5 Figure 29 的现象、根因、Table-only 修复、验证坐标、风险权衡，并更新当前策略冲突清单 |
| DOC-037 | 文档 | 补充 20260621 Gemini/GPT-5 三个小瑕疵二次收口记录 | 2026-06-21 00:00 | 2026-06-21 00:00 | 已完成 | 在 `docs/Basic-Benchmark图表细致排查记录-20260618-0621.md` 追加 Gemini Table 12、GPT-5 Figure 29、GPT-5 Table 16 的现象、根因、最小修复、验证坐标和风险权衡，并更新策略冲突清单 |
| DOC-038 | 文档 | 补充 Basic Benchmark 图表排查阶段性总复盘并重命名文档 | 2026-06-21 00:00 | 2026-06-21 00:00 | 已完成 | 在 `docs/Basic-Benchmark图表细致排查记录-20260618-0621.md` 追加“为什么这轮最终能收口”的总结，归纳阶段化 debug、局部化修复、冲突负例记录、结构化版式判断和真实 PDF + 单元测试验证闭环；同时将原文档从 `20260618` 后缀重命名为 `20260618-0621` 后缀，并同步更新 task-list 中的当前文档路径 |
| DOC-039 | 文档 | 新增当前 PDF 图表提取流程 Mermaid 说明文档 | 2026-06-21 00:00 | 2026-06-21 00:00 | 已完成 | 新增 `docs/PDF图表提取流程逻辑说明-20260621.md`，按当前代码梳理 Figure/Table 提取主流程、caption 评分过滤、方向判定、baseline 限制、Phase A/B/X/layout/autocrop、Table 专用 final 后处理、refine_safe 验收与 debug 保存分支，并用 Mermaid 流程图说明关键判断 |
| DOC-040 | 文档 | 按 skill-creator 规范复核并更新正式 Skill 文档与 README | 2026-06-21 00:00 | 2026-06-21 00:00 | 已完成 | 读取 `$skill-creator` 规范后，精简 `skills/pdf-markdown-summary/SKILL.md`，将触发语义集中到 description，正文改为核心工作流、命令、输出规则、提取能力和 references 导航；更新 `agents/openai.yaml`、`references/pdf-to-markdown.md`、`references/pdf-summary.md` 与 `README.md`，补充当前 Figure/Table 稳定提取、debug visual、Basic Benchmark 记录和 Mermaid 流程文档入口，并修正 OCR 仍为 roadmap/保留参数的表述 |
| DOC-041 | 文档 | 同步 BUG-041~046 修复到流程逻辑说明文档 | 2026-06-22 00:00 | 2026-06-22 00:00 | 已完成 | 更新 `docs/PDF图表提取流程逻辑说明-20260621.md`：2.1 节补充 `no_refine_tables` 已接线说明；2.4 节补充 `estimate_ink_ratio` 单一来源说明；第 4 节 `determine_direction` 流程图改为 `global_anchor` 优先于页面位置启发式；新增第 17 节"变更记录"列出六个 bug 的文件、问题与修复 |
| DOC-042 | 文档 | 新增 PDF 图表提取架构根因复盘与技术路线分析报告 | 2026-07-21 00:00 | 2026-07-21 00:00 | 已完成 | 文档位于根目录 `PDF图表提取架构根因复盘与技术路线分析报告-20260721.md`；分析结构启发式的可达性边界、当前代码与 benchmark 缺口、轻量/CPU Layout/重模型分层、是否必须 YOLO/VLM、候选融合架构、bbox 指标与分阶段实施路线 |
| DOC-043 | 文档 | 按 CHK-017 核查结论修正架构根因复盘报告 | 2026-07-27 23:41 | 2026-07-27 23:41 | 已完成 | 修正 `PDF图表提取架构根因复盘与技术路线分析报告-20260721.md`：§5.4 许可证由 MIT 改为 Apache-2.0 并补充"PyMuPDF 隔离为可替换后端应在 Phase 0 决定"；§4 策略冲突由 27 条改为 25 条并补文档路径；§5.2 OmniDocBench 标明 1,651 页属 v1.6、CVPR 2025 论文对应 v1.0（981/9/4/3）并补数据集链接；§4 根因六改为区分"硬失败三类（数量/缺失 ID/缺失文件）"与"仅记 message 不失败两类（caption 非空、`(type,id,page,continued)` 差集）"；§3.1 13 步主链补充简化说明（无 Phase C、`adjust_clip_with_layout`、标题回补亦在 baseline、遗漏 `refine_clip_to_table_band` 等）；§1.1 增加两种 99% 口径不可混用的说明；§6.3 补充配对图边权同为手调参数、不消除根因四；§8 Phase 0 标注量标注为仅打通指标管道、Phase 1 标注依赖 Phase 0 结果可能被否决；§7.4 补充 1 次失败需约 470 样本与 i.i.d. 假设冲突；§5.3 补充 PyMuPDF4LLM 已内置 Layout 并自带插件式 OCR、Phase 2/3 可合并前移。已核实文档内 PDFFigures2、DocLayout-YOLO、PaddleOCR-VL、Docling、PyMuPDF 许可等其余引用无误，`git diff --check` 通过 |
| DOC-044 | 文档 | 新建 docs/3-experiments 并写入 PyMuPDF4LLM Layout 可行性实验说明与评测报告 | 2026-07-28 15:13 | 2026-07-28 15:30 | 已完成 | 目录 `docs/3-experiments/20260728-pymupdf4llm-layout-bbox/`；含 README、独立脚本、raw_layout/overlays/legacy/gt/metrics 与 `可行性报告-20260728.md`；未合入 Skill 主链 |
| DOC-045 | 文档 | 输出 Layout 实验与 legacy 输出的对比结论及后续架构建议 | 2026-07-28 15:45 | 2026-07-28 16:25 | 已完成 | `docs/3-experiments/20260728-pymupdf4llm-layout-bbox/架构设计评估与建议-20260728.md`；核心结论为「Layout 供证据 + legacy 做精修 + 冲突进复核」的融合架构，而非替换；修正原报告两处定位（Layout 应升级为独立证据源、精修应降级为小幅校正）；给出 L0~L4 分层与 P0~P4 实施顺序；未改动 Skill 主链 |
| DOC-046 | 文档 | 在 Layout 架构评估文档中补充二次独立复核过程与指标口径修正 | 2026-07-28 17:00 | 2026-07-28 17:00 | 已完成 | 更新 `docs/3-experiments/20260728-pymupdf4llm-layout-bbox/架构设计评估与建议-20260728.md`，新增第 8 节，记录本次分析步骤、性能与分类统计、代表案例、GT 自证、候选框重复分配、legacy 跨页误匹配风险、L0~L4 目标架构、建议代码边界与 P0~P4 实施顺序；明确当前 95.6% 配对率和硬失败比例仅作探索，不能作为真实准确率 |
| DOC-047 | 文档 | 写入 Layout vs legacy 对比结论与完整分析过程独立文档 | 2026-07-28 22:54 | 2026-07-28 22:55 | 已完成 | 新建 `docs/3-experiments/20260728-pymupdf4llm-layout-bbox/对比结论与分析过程-20260728.md`；汇总分析步骤、三把尺子、自动裁决与硬失败、关键案例、成本、对报告两处修正、融合架构建议与 P0~P4；同步更新实验 README |
| DOC-048 | 文档 | 按最新代码事实对齐 README、AGENTS、架构报告与 Skill 文档 | 2026-07-31 08:48 | 2026-07-31 08:48 | 已完成 | `README.md` 许可证 MIT 改为 Apache-2.0（与 LICENSE 文件一致）、两处归档文档链接更新到 `docs/1-archive/`；`docs/PDF图表提取架构根因复盘与技术路线分析报告-20260721.md` 引用路径同步更新；`references/cli-options.md` 补充 preset robust 实际生效取值说明（Default 列为 argparse 裸默认）、删除 `--protect-far-edge-px`/`--near-edge-pad-px` 死参数条目、`--refine-near-edge-only` 补充 `--no-refine-near-edge-only` 反向开关与默认 True、`--tables` 说明 auto/screenshot/structure 当前同为截图（structure 为 roadmap 占位）、`--ocr` 更正为纯 no-op（仅 report 记录 not_implemented）、`--no-refine` 补充同时作用于 Figure 和 Table；`references/pdf-to-markdown.md` 补全 Expected Outputs（`images/index.json`、`images/*.png`、`text/<stem>.txt`、`text/gathered_text.json`、`images/layout_model.json`、`images/figure_contexts.json`、`images/run.log.jsonl`）并说明 `--tables auto` 名不副实；`SKILL.md` debug overlay 阶段补 `phase_d`；`references/pdf-summary.md` 补充 overlay 实际位置 `images/debug/<run_id>/`；`AGENTS.md` 删除 `examples/` 提法与根目录 `scripts/` 同步条目、补充 `docs/3-experiments/` 规则；grep 验证无 MIT 残留、无 docs/ 根目录旧死链 |
| DOC-049 | 文档 | （补录）两个文档移入 `docs/1-archive/` 当时未记录 | 2026-07-31 08:48 | 2026-07-31 08:48 | 已完成 | `Basic-Benchmark图表细致排查记录-20260618-0621.md` 与 `PDF图表提取流程逻辑说明-20260621.md` 由 `docs/` 根目录移入 `docs/1-archive/`；本次已同步更新 README 与架构报告中的引用路径（见 DOC-048） |
| DOC-050 | 规划 | 对比四份架构报告并输出技术迭代实施方案 | 2026-07-31 15:05 | 2026-07-31 15:05 | 已完成 | 新增 `docs/PDF图表提取技术迭代实施方案-20260731.md`；以二次复核（架构评估 §8）为最严口径，固化用户验收标准（留白/≤1 行混正文可接受，漏检/错配/截断零容忍，数量对齐 + 信息完整为核心 KPI），按 P0~P4 给出实施计划、退出条件与模块边界；当前处于 P0，建议起点 P0-3（数据模型升级）与 P0-1（评测口径修正） |
| DOC-051 | 文档 | 更新实施方案 A0 完成状态并同步 AGENTS.md 验证规则 | 2026-07-31 15:30 | 2026-07-31 15:30 | 已完成 | `docs/PDF图表提取技术迭代实施方案-20260731.md` 头部状态与 §9 更新为 A0 开发任务完成（A0-1/2/3/5/6 ✅，A0-4 工具链就绪、人工标注待人工）；`AGENTS.md` §8 新增四条：golden 默认纳入 pytest 且 0 跳过才算全绿、golden 基准更新须单独提交并在 task-list 逐条说明、`tests/eval/` 版本化评测器定位、`tests/annotations/` 人工真值存放规则 |
| DOC-054 | 检查 | 评审技术迭代实施方案并按评审结论重写为 v2 | 2026-07-31 10:05 | 2026-07-31 10:20 | 已完成 | 核对结果：方案对四份依据文档的数字引用（8 份 PDF/270 页/180 资产、0.68 与 1.25 s/页、22.8% 空白率、56 例 legacy_loose、7.8%/5.6%、95.6% 仅为候选覆盖率、42.5MB、并集 7/7、299 样本量）逐条无误，技术方向成立。发现三类问题并已修订 `docs/PDF图表提取技术迭代实施方案-20260731.md`：①**回归网空跑**——仓库 `golden_index.json` 数量为 0，`_golden_available_specs()` 返回空列表致 golden 用例被 pytest 跳过（实测为 126 通过 **1 跳过**，非 v1 所述「126 通过 0 失败」），且 `ItemSignature` 仅比较 `(type,id,page,continued)`、`index.json` 无 bbox 字段，框位移动检测不到 → 新增 A0-2「让 golden 真正可比较」（先落 bbox 字段、再扩比较器、再生成基准、并对空跑判失败）；②**评测器不可版本化**——v1 将评测口径修正限定在已 gitignore 的 `docs/3-experiments/`，丢失了源文档「固化成 tests/ 评测入口」的要求 → A0-3 迁入 `tests/eval/`；③**验收口径自相矛盾**——「>1 行混正文」定级不一致、coverage≥0.99 与截断零容忍互斥、`review_required` 是否导出未定义 → §2 重写为四类硬失败（新增「过量混正文」作防退化护栏）、截断改二值判据、coverage 回到 0.995 且降级为筛查器、四态结果一律导出图片。另：阶段编号 P0~P4 改 A0~A4（避开仓库既有 `test_p0_env_priority.py`/`test_p1_ident_parsing.py` 命名）并补 §8.6 映射表；补 A0-4 标注可执行细节（LabelMe + `tests/annotations/` + schema + 双人复核）、A1 flag 打开时的退出条件、`requirements-layout.txt` 依赖 extras 形态、工作量粗估与 KPI 未达标降级路径、golden 为「变更检测器非正确性基准」的说明；`pytest` 全绿标准收紧为「golden 不得 0 收集或跳过」。验证命令：`python3 -m pytest tests/scripts -q` → 126 passed, 1 skipped；`find tests -name golden_index.json` → 0 个 |
| DOC-052 | 文档 | （方案 A0-6）`AGENTS.md` 事实对齐 | 2026-07-31 10:20 | 2026-07-31 10:20 | 已完成 | §8 验证规则：「三个入口脚本」更正为四个并点名（`extract_pdf_assets.py`/`pdf_to_markdown.py`/`process_pdf.py`/`summarize_pdf.py`）；「7 个 PDF 测试文件夹」更正为 8 份（回测组1 七份 + 回测组2 `DeepSeek_V4.pdf`） |
| DOC-053 | 文档 | task-list 同步本轮 A2/A3 验收缺陷修复与 golden 重建记录 | 2026-08-10 15:08 | 2026-08-10 15:10 | 已完成 | 补记 BUG-055~060 与 TST-041；对应审查结论：截断/污染未实现、四态未落盘、一对一/多框/逐页回退、Golden 断链 |
| DOC-055 | 文档 | AGENTS.md §8 遗留 stale 引用：benchmark PDF 已扁平化为 tests/basic-benchmark/*.pdf，仍写「回测组1 七份 + 回测组2 的 DeepSeek_V4.pdf」（BUG-060 修复时漏同步） | 2026-08-10 16:01 | 2026-08-10 16:22 | 已完成 | AGENTS.md:71 改为 8 份 PDF 扁平路径并点名全部文件；其余引用（实施方案 A0-6、task-list 历史记录）为历史快照保留；时间校正证据：git log -S DOC-055 与 git blame 均指向提交 978473b（2026-08-10 16:22），以该提交时间作为完成时间。 |
| DOC-056 | 文档 | 深度审查发现 `test_extraction_golden.py` 两处过期 docstring 与「tests/results/ 整体 gitignore」决议矛盾 | 2026-08-29 00:00 | 2026-08-29 00:00 | 已完成 | `_find_golden_index` 与 `_resolve_golden_paths` docstring 原称 golden 为「版本化 fixture，通过 .gitignore 例外跟踪」；改为「本地基准，不纳入版本控制（tests/results/ 已整体 gitignore）」，并补充新 clone 需先运行 `--update-golden` 生成基准的说明 |
| DOC-057 | 文档 | Golden 模块顶层说明仍要求「基准更新必须单独提交」，与 tests/results 整体 gitignore 冲突 | 2026-08-30 12:53 | 2026-08-30 13:20 | 已完成 | 顶层说明与命令示例改为：基准更新后在 task-list.md 记录差异原因；基准由本地 `--update-golden` 生成，不纳入版本控制 |
| DOC-058 | 文档 | 版本升级到 0.6.2 并审计所有当前可维护文档 | 2026-08-30 12:59 | 2026-08-30 13:06 | 已完成 | 更新 scripts/__init__.py、README、SKILL、CLI/workflow reference、技术迭代方案、架构历史快照声明、eval README 与 Golden 说明；归档、docs/2-ref 和 old-version 未改。 |

## 功能开发

| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| DEV-001 | 开发 | 创建正式 Skill 包 `skills/pdf-markdown-summary/` | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 包含 `SKILL.md`、`references/`、`examples/`、`scripts/` |
| DEV-002 | 开发 | 新增 PDF 转 Markdown 入口能力 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 入口脚本为 `skills/pdf-markdown-summary/scripts/pdf_to_markdown.py`，核心实现位于 `scripts/core/pdf_to_markdown.py` |
| DEV-003 | 开发 | 新增 PDF 带图摘要素材准备入口能力 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 入口脚本为 `skills/pdf-markdown-summary/scripts/summarize_pdf.py`，复用现有图表提取与摘要业务逻辑 |
| DEV-004 | 开发 | 新增完整处理流程入口能力 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 入口脚本为 `skills/pdf-markdown-summary/scripts/process_pdf.py`，用于串联 Markdown 转换和摘要素材准备 |
| DEV-005 | 开发 | 补充 Skill 参考文档与示例说明 | 2026-06-05 00:00 | 2026-06-05 00:00 | 已完成 | 包含 `references/pdf-to-markdown.md`、`references/pdf-summary.md`、`examples/README.md` |
| DEV-006 | 开发 | A0-1：升级正式数据模型（实施方案 v2） | 2026-07-31 15:30 | 2026-07-31 15:30 | 已完成 | `AttachmentRecord`/`index.json` 新增 `final_bbox`、`content_bboxes`、`source_signals`、`pairing_confidence`、`boundary_confidence`、`warnings`、`review_required`、`status` 八个字段，全部可选带默认值（置信度 None、source_signals=["caption"]、status="accepted"），旧 index.json 读路径兼容；`extract_figures.py:785`、`extract_tables.py:863` 构造点填入 final clip 坐标（round 1 位小数）；只加字段落盘，截图行为零变化；验证：四个入口 `--help`、pytest 126 passed、Attention 全量提取 9/9 条 final_bbox 与 PNG 实测像素一致（误差 ≤1px） |
| DEV-007 | 开发 | A0-3/A0-4：版本化评测器 `tests/eval/` 与标注工具链 `tests/annotations/` | 2026-07-31 15:30 | 2026-07-31 15:30 | 已完成 | `tests/eval/`：资产键 `document_id+kind+ident+caption_page+occurrence+group_id`、预测匹配校验页码、全页一对一贪心配对 + 候选重复占用统计（修正二次复核三缺陷）；六项指标（数量对齐率/截断率二值判定层/配对正确率/过量混正文率/coverage/purity）+ `run_eval.py` CLI + 19 项自检全 PASS；`tests/annotations/`：SCHEMA-20260731.md（14 字段、五条规范正反例、reviewer≠annotator、样本量警示）、`convert_labelme_to_gt.py`（LabelMe 像素→PDF 点，DPI=108=72×1.5，往返转换验证精确还原）、冒烟种子 gt.json（3 资产，annotator=agent-bootstrap，注明待人工复核替换）；真实人工标注待人工执行 |
| DEV-008 | 开发 | A1-1/A1-2/A1-3：Layout 模块边界 + PyMuPDF4LLM adapter + 依赖可选化 | 2026-08-06 10:00 | 2026-08-06 12:00 | 已完成 | 新增 `lib/regions.py`（RegionBBox/PageRegion/LayoutResult + classify_region）、`lib/assets.py`（AssetCandidate/PairingResult/CropResult/ConflictRecord/LayoutIntegrationReport）、`lib/backends/base.py`（LayoutBackend Protocol + get_backend 工厂）、`lib/backends/pymupdf_layout.py`（PyMuPDFLayoutBackend：pymupdf4llm.to_markdown(page_chunks=True) -> PageRegion，L0 缓存 key=PDF hash+后端版本+参数版本，缓存命中正确）、`lib/page_scene.py`（PageScene/SceneCache）、`requirements-layout.txt`（pymupdf4llm>=1.28.0），主 requirements.txt 注释指向；缺失依赖时 get_backend() 返回 None 降级为 off |
| DEV-009 | 开发 | A1-4：Layout 三件事 + feature flag 集成 | 2026-08-06 10:00 | 2026-08-06 12:00 | 已完成 | `lib/layout_integration.py`：filter_text_reference_captions（正文引用过滤）、seed_content_candidates（候选种子）、detect_conflicts（冲突检测 IoU<0.3）、build_integration_report；feature flag `--layout-backend`（CLI choices=off/pymupdf4llm 默认 off）+ `PDF_SUMMARY_LAYOUT_BACKEND`（ENV）；core/extract_pdf_assets.py 集成：flag on 时提取 Layout -> 影子模式产出 layout_integration.json 报告；DeepSeek_V4 实测：58页/525区域/8冲突（Table 6 IoU=0.0 检出）；flag off 时零影响（Attention golden PASSED，126 tests passed） |
| DEV-010 | 开发 | A2-1/A2-2：全页配对与多框 | 2026-08-06 13:00 | 2026-08-06 15:00 | 已完成 | `lib/pairing.py`：pair_page（贪心一对一匹配，edge_distance 代替 center distance 适合高瘦图框）、_find_multi_frames（gap≤30pt+水平/垂直对齐 -> 多框并集）、pair_layout_regions（全 PDF 配对）、pairing_report（JSON 报告含 duplicate_occupancy 统计）；RegionBBox 新增 edge_distance 方法；core/extract_pdf_assets.py 集成：flag on 时产出 layout_pairing.json；8 份 benchmark PDF 实测：86 pairs / 0 duplicate groups（A0 基线 8组/16条 -> 0）/ 1 multi-frame asset（Qwen3-Omni）；Attention golden PASSED |
| DEV-011 | 开发 | A3-1/A3-2/A3-3/A3-4/A3-5：精修改造+截断修复 | 2026-08-06 16:00 | 2026-08-06 23:30 | 已完成 | `lib/quality.py`（置信度四态评估：accepted/accepted_with_margin/review_required/rejected）、`lib/refiners/base.py`（RefinementStep Protocol + _clamp_movement max_move=30pt/max_tighten=15pt + LegacyBoundaryGuardStep threshold=20pt/expand_ratio=0.5）、`lib/refiners/figure.py`（LegacyBoundaryGuard->ObjectSnap->ConservativeTextTrim->ConservativeAutocrop 四步管道）、`lib/refiners/table.py`（同结构+水平联合+表头保护）、`lib/pipeline.py`（后端编排：匹配->精修->质量评估->应用/回退->layout_refinement.json 报告 + _bbox_coverage safety net _MIN_LEGACY_COVERAGE=0.55）；A3 初版评估发现截断率从基线 5.95%升至 13.10%，新增 LegacyBoundaryGuardStep 仅扩展显著内缩于 legacy 的边界（>20pt gap 按 0.5 比例扩展）+ coverage 安全网，最终 8 份 benchmark 截断率降至 7.19%（排除 4 个预存截断后有效 4.91%低于基线）、purity mean 0.7769（基线 0.7346）、coverage mean 0.9774；16 个模块级常量（A1/A2 的 6+A3 的 10）；Attention golden PASSED、127 tests passed |
| DEV-012 | 开发 | A4-2：阈值校准 | 2026-08-06 23:30 | 2026-08-06 23:30 | 已完成 | A3 参数调优完成：LegacyBoundaryGuardStep threshold=20pt/expand_ratio=0.5（经 A3v2/v3/v4 三轮对比选定 v3）；pipeline.py _MIN_LEGACY_COVERAGE=0.55（精修结果覆盖 legacy 不足 55% 时回退）；legacy IoU diff 阈值≥0.3 保持；quality.py 置信度阈值 HIGH=0.85/MEDIUM=0.65/LOW=0.40 保持不变。A3v3 最终指标：截断率 7.19%（有效 4.91%）、purity 0.7769、coverage 0.9774 |
| DEV-013 | 开发 | A4-1：holdout 集搭建 | 2026-08-06 23:30 | - | 进行中 | `tests/holdout/` 目录结构已创建 + README.md（holdout 要求：cross-publisher、扫描件/旋转/跨页/同页多图/无边框表、≥5 份 PDF ≥50 标注、退出条件 alignment≥90%/truncation≤5%/pairing≥85%/excess≤10%）；需人工提供 holdout PDF 并完成 GT 标注后方可执行 A4-3 正式评估 |
| DEV-014 | 开发 | A4-3：holdout 正式 KPI 评估 | - | - | 待开发 | 依赖 A4-1 holdout 集就绪；在独立 holdout 上按 §2 口径运行 run_eval.py 并与退出条件对比，达标后方可对外宣称数字 |
| DEV-015 | 调整 | golden 基准目录迁移：8 份 golden_index.json 从 tests/basic-benchmark/<stem>/images/ 移至 tests/results/20260810-001/<stem>/images/（与提取产物同批次）；basic-benchmark 恢复为纯 PDF 只读输入 | 2026-08-10 16:16 | 2026-08-10 16:30 | 已完成 | test_extraction_golden 新增 _find_golden_index（从 results 各批次找最新 golden，不校验指纹）；_resolve_golden_paths 去掉 basic-benchmark golden 逻辑和 benchmark_group 兼容；--update-golden 改写当前批次；.gitignore 加 tests/results/**/golden_index.json 例外；AGENTS.md §3/§8 同步 |
| DEV-016 | 开发 | 主链三态验收 + 题注对账：留白不降级，污染/漏检落盘 | 2026-09-07 22:47 | 2026-09-07 23:10 | 已完成 | `lib/assess.py` 按布尔信号定级：标题/正文入框或正文引用 → rejected；截断/表带未收束/弱锚点/重复 PNG/对账补裁 → review_required；额外留白仍 accepted。四态字段保留，`accepted_with_margin` 仅 Layout 链使用。显式题注与裸 `Figure N`/`Table N` 纳入 expected；漏检补裁 PNG 进 index，Markdown 只插入 accepted / accepted_with_margin。污染候选不再静默跳过。 |

## 配置运维

| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| OPS-001 | 运维 | 检查并维护 .gitignore，符合 Windows 开发现状 | 2026-06-13 00:00 | 2026-06-13 00:00 | 已完成 | 删除无效规则 `tests-basic-benchmark/`（笔误，实际输入目录 `tests/basic-benchmark/` 需跟踪）与 `ref/`（无对应目录）；新增 Windows 系统缓存（Thumbs.db/ehthumbs.db/desktop.ini）、编辑器临时文件（\*.swp/\*.swo/\*~）、环境密钥（.env/.env.*）；保留 `__pycache__/`、`tests/results/` 等现有规则；经 `git check-ignore` 验证 tests/results 仍忽略、tests/basic-benchmark 未被误伤，`git diff --check` 通过 |
| OPS-002 | 运维 | 将 docs/3-experiments/ 加入 .gitignore | 2026-07-29 23:30 | 2026-07-29 23:30 | 已完成 | 新增规则 `docs/3-experiments/`；该目录此前未被 git 跟踪（仅有未跟踪文件），无需 `git rm --cached`；`git check-ignore` 确认生效 |

## 统计摘要

| 分类 | 总数 | 已完成 | 待开发/待修复 | 完成率 |
| --- | --- | --- | --- | --- |
| 代码 Bug | 76 | 76 | 0 | 100% |
| 调整事项 | 13 | 12 | 1 | 92.3% |
| 检查事项 | 20 | 20 | 0 | 100% |
| 测试数据 | 44 | 44 | 0 | 100% |
| 文档维护 | 58 | 58 | 0 | 100% |
| 功能开发 | 16 | 14 | 2 | 87.5% |
| 配置运维 | 2 | 2 | 0 | 100% |
| **总计** | 229 | 226 | 3 | 98.7% |

## 项目阅读与诊断记录（2026-09-07）

本节为用户要求的项目熟悉、评估与诊断记录，未修复下述问题。上方统计保留原历史口径，不表示本轮发现的问题已解决。正式 Skill 源码未修改；新增隔离复现脚本、合成 PDF、日志和真实论文提取结果均位于 `tests/results/20260907-001/`，未更新 Golden 基准，未修改 benchmark、只读参考目录或历史归档。

### 阅读与检查范围

- 使用 `git status --short`、`git log -5 --oneline`、`rg --files`、`rg -n`、`cat`、`sed`、`wc -l` 阅读仓库规则、README、正式 SKILL/references、四个入口及 core、正文提取、Figure/Table 裁剪、Layout adapter/pairing/refiners/pipeline、质量与输出模型、pytest/Golden、版本化评测器、两份现行架构文档和历史策略冲突记录。
- 检查实际 Python 依赖：Python 3.13.13、pytest 9.0.3、PyMuPDF 1.28.0、pymupdf4llm 1.28.0、numpy 2.4.4、scipy 1.17.1。AST 统计正式脚本为 52 个 Python 文件、17,759 行；`extract_tables`、`extract_figures` 函数分别为 803、726 行（含注释与空行）。
- 检查数据现状：benchmark 8 份 PDF；本地 Golden 8 份；holdout 仅 README；8 份 annotations 均声明为自动 bootstrap/provisional GT，尚非正式人工真值，且仍含 DeepSeek_V3_2、未含当前 benchmark 的 k3_tech_report。

### 验证命令与结果

| 命令或操作 | 结果与边界 |
| --- | --- |
| `python3 -m pytest tests/scripts/ -q -p no:cacheprovider --basetemp=tests/results/20260907-001/pytest-temp` | 首次由于本轮指定的临时目录父目录未创建，151 passed、4 个 tmp_path setup errors；属于本轮调用准备问题。执行 `mkdir -p tests/results/20260907-001` 后重跑：155 passed、0 skipped、5 条 SWIG 弃用警告，退出码 0。Golden 实际执行比较，但复用了当前代码指纹匹配的既有产物，并非八份 PDF 全部重新提取。 |
| `python3 tests/results/20260907-001/diagnose.py` | 退出码 0；脚本内通过 subprocess 运行四入口 `--help`，均返回 0；以 `ast.parse` 检查正式脚本、测试与评测器共 72 个 Python 文件，全部通过；运行 `python3 tests/eval/selfcheck.py`，33 项自检通过。全部明细见本批次日志与 `diagnosis.json`。 |
| `diagnose.py` 的合成 PDF 复现 | 跨栏标题顺序错误、纯图片 OCR force 空输出仍 ready、同目录两 PDF 默认提取删除前一份图片均复现。删除仅发生在本轮专门生成的 Alpha/Beta 合成样本目录内，未涉及既有用户产物。 |
| `normalize_prediction` + `evaluate_document` 隔离复现 | 候选框完整、实际 final_bbox 仅半幅且图片路径不存在时，仍报告 exported=1、alignment=1、coverage=1、truncation=0；证明实际渲染框与候选证据被混用，且文件存在性未验证。 |
| `detect_truncation` / `assess_quality` / `detect_text_pollution` 隔离探针（随后补入 diagnose.py） | 100×100pt 候选/对象被裁掉 5pt，返回未截断且 accepted、confidence=0.9；两行宽长正文返回无污染。说明在线检测阈值不等同于方案的元素完整包含、正文超过一行即失败。补入脚本后 `ast.parse` 通过。 |
| `PDF_SUMMARY_LAYOUT_CACHE_DIR=tests/results/20260907-001/layout-cache python3 skills/pdf-markdown-summary/scripts/extract_pdf_assets.py --pdf tests/basic-benchmark/1706.03762v7-attention_is_all_you_need.pdf --out-dir tests/results/20260907-001/attention-off/images --out-text tests/results/20260907-001/attention-off/txt/attention.txt --preset robust --layout-backend off` | 全新提取，退出码 0；5 Figure + 4 Table，9 张 PNG 均存在，全部默认 accepted，pairing_confidence 均为空。stdout/stderr 写入 `attention-off.log`。 |
| 同上命令将 `attention-off` 替换为 `attention-pymupdf4llm`、`--layout-backend off` 替换为 `--layout-backend pymupdf4llm` | 全新提取与独立缓存，退出码 0；5 Figure + 4 Table；Layout 提取 15 页/167 区域，9 配对、2 孤立内容框；A3 匹配 7、应用 6、保留旧框 1；输出状态 accepted=6、accepted_with_margin=2、review_required=1。9 张 PNG 均存在。日志为 `attention-pymupdf4llm.log`。 |
| 两种路径 Figure 1 图片目视核对 | Transformer 主体和可见标签均保留；该项仅为局部目视抽查，不代表九张图表或整个 benchmark 正确率验收。 |

### 诊断发现（均未修复）

| 优先级 | 发现 | 证据与影响 |
| --- | --- | --- |
| P1 | 同目录默认输出缺少文档隔离 | `core/extract_pdf_assets.py` 默认共享 images/index.json，`lib/output.py:112` 清理全部未被当前索引引用的 Figure_/Table_ PNG。Beta 提取后 Alpha 图片消失，已有 Markdown 链接可能失效。 |
| P1 | 正式评测混用候选框和截图框，未验证图片文件 | `tests/eval/keys.py:152` 优先 content_bboxes；多 panel 模式中该字段保存原候选，而实际 PNG 由 final_bbox 渲染。has_bbox 仅检查列表非空，不能代表图片已导出。 |
| P1 | 四态输出尚未成为全流程统一验收 | `AttachmentRecord.status` 默认 accepted；Layout 默认 off；无匹配和异常路径仍保留默认状态，未导出资产不生成失败记录。Layout 候选补全与过滤主要停留在报告，精修仍以旧 records 为集合。 |
| P1 | 文档退出结论与指标及检测能力不一致 | 实施方案 A3 表列截断率 7.19%、过量混正文率 10.71%，随后却勾选两项为 0。在线截断/污染阈值并非 §2 的人工元素级判据；检测未报错不能作为真实零缺陷证据。 |
| P2 | 双栏正文排序破坏跨栏标题顺序 | `text_extract.py:343` 先按栏再按 y 排序，全篇共享双栏判断及首页宽度。最小样本输出左栏四段后才出现页顶跨栏标题。 |
| P2 | OCR 未实现时顶层仍可能成功 | `core/pdf_to_markdown.py:212` 只按资产提取退出码决定 ready；纯图片 PDF + `--ocr force` 返回 0、ready，正文 Markdown 只有文件名标题，OCR 子状态虽明确 not_implemented，但顶层契约易误导下游。 |
| P2 | 可复现性与独立验证仍有缺口 | Golden 缓存指纹仅覆盖正式 Python 代码，不覆盖输入 PDF、依赖版本或有效参数；核心依赖无版本约束；人工 GT/holdout 未就绪，暂不能对外据此宣称准确率。 |

建议处理顺序：先修输出隔离与评测对象契约，再补齐统一验收/复核和文档事实对齐，然后用独立人工 GT 约束 Layout 融合；Markdown 阅读顺序和能力声明应独立验收。保留现有 caption、图表精修、debug 和回归积累，避免在未建立可信评测之前扩大调参或全面重写范围。

## Basic Benchmark 全量提取（--debug-visual，2026-09-07）

应用户要求，使用正式 Skill（v0.6.2）最新能力对 Basic Benchmark 8 份 PDF 全量运行资产提取，并启用 visual 诊断标记（`--debug-visual --debug-captions`），结果单独保存于 `tests/results/20260907-002/`。运行脚本为该批次目录内 `run_benchmark.sh`，逐份调用四入口之一 `extract_pdf_assets.py`；`--layout-backend` 保持默认 `off`。

### 命令模板（每份 PDF）

```bash
python3 skills/pdf-markdown-summary/scripts/extract_pdf_assets.py \
  --pdf "tests/basic-benchmark/<stem>.pdf" --preset robust \
  --debug-visual --debug-captions \
  --out-dir "tests/results/20260907-002/<stem>/images" \
  --out-text "tests/results/20260907-002/<stem>/txt/<stem>.txt" \
  --manifest "tests/results/20260907-002/<stem>/assets/manifest.csv" \
  --index-json "tests/results/20260907-002/<stem>/images/index.json" \
  --log-file "tests/results/20260907-002/<stem>/assets/extract.log"
```

### 结果汇总（明细见 `tests/results/20260907-002/run-status.tsv`）

| PDF | 退出码 | Figure | Table | 正式 PNG | Debug 叠加图 | 文本 (字节) |
| --- | --- | --- | --- | --- | --- | --- |
| 1706.03762v7-attention_is_all_you_need | 0 | 5 | 4 | 9 | 9 | 39,681 |
| 2509.17765v1-Qwen3-Omni Technical Report | 0 | 3 | 18 | 21 | 21 | 92,561 |
| DeepSeek_V4 | 0 | 15 | 14 | 29 | 29 | 177,602 |
| FunAudio-ASR | 0 | 4 | 8 | 12 | 12 | 49,538 |
| KearnsNevmyvakaHFTRiskBooks | 0 | 8 | 1 | 9 | 9 | 69,017 |
| gemini_v2_5_report | 0 | 15 | 12 | 27 | 27 | 219,693 |
| gpt-5-system-card | 0 | 31 | 26 | 57 | 57 | 132,374 |
| k3_tech_report | 0 | 16 | 5 | 21 | 21 | 190,165 |
| 合计 | 全部 0 | 97 | 88 | 185 | 185 | 约 1.07 MB |

### 验证与边界

- 8 份 PDF 全部退出码 0；每个资产各生成一张 debug 叠加图（`<stem>/images/debug/`，含 baseline/phase_a/phase_b/phase_d/final 多阶段边界框），批次总量约 89 MB。
- 图表检出数量与 `tests/results/20260830-001/` 批次完全一致（5/4、3/18、15/14、4/8、8/1、15/12、31/26、16/5），无回归。
- stderr 逐一检查：无错误与堆栈；gpt-5-system-card、FunAudio-ASR 中 "error" 命中仅为资产文件名本身（Health_error_rates、Word_Error_Rate）。
- 抽查 `gemini_v2_5_report/images/debug/Figure_6_p22_debug_stages.png`：多阶段多色裁剪框与图注高亮清晰可用。
- `tests/basic-benchmark/` 保持只读，未写入任何结果或临时文件；批次目录按 `<stem>/{images,txt,assets}` 分层。
- 本轮未运行 `--update-golden`，Golden 基准未变更；`--debug-captions` 的评分明细在各自 `assets/` 日志中。

## Basic Benchmark visual 产物独立复核（2026-09-07）

用户要求检查 `tests/results/20260907-002/` 的 debug-visual 结果是否正确。本轮只做产物与代码路径复核，未修改正式 Skill、原始 PDF、002 批次和 Golden；独立复核产物放在 `tests/results/20260907-003/`。既有 `task-list.md` 内容与未跟踪 `tests/tests/` 保留。

### 操作、验证命令与结果

| 操作或命令 | 结果与边界 |
| --- | --- |
| 读取项目规则、PDF 视觉核对技能、002 的 run-status.tsv/run_benchmark.sh、8 份 index.json、重点日志与 debug legend | 确认本批次默认 layout-backend=off；185 项全部标记 accepted。读操作未改动参考目录。 |
| `python3 tests/results/20260907-003/audit.py` | 生成 185 项 inventory.json、8 份 integrity.json 记录及 24 张联系表；正式 PNG 全部可解码，索引 PDF 哈希前缀全部匹配，300 DPI 图片尺寸与 final_bbox 误差均不超过 2 像素。 |
| 查看全部 24 张联系表，按疑点放大 PNG、对照原页、查看重点 debug 图及 legend | 185 张导出完成缩略图初筛；重点原页复核确认 17 张导出有实质问题，另外 Gemini Figure 9 未导出。不是全页人工 GT 验收，未逐一目视全部 debug 图。 |
| `python3 tests/results/20260907-003/render_pages.py` | 使用 `pdftoppm -f <页> -l <页> -scale-to 1250 -singlefile -png` 独立渲染 21 张候选 PDF 原页至 003/pages，退出码 0。benchmark 保持只读。 |
| 内联 Python：Pillow 对全部 debug PNG 执行 verify；比较 DeepSeek Figure 11/12 SHA-256 | 185 张 debug PNG 均可解码；Figure 11 与 12 导出文件字节完全相同，原页实际是两个独立编号图。 |
| `rg` 读取 caption_detection.py、extract_figures.py、debug_visual.py 和相关运行日志 | 确认 Figure 候选筛选使用 25 分门槛；Gemini Figure 9 日志为 19 分、reference 扣 20 分。FunAudio Figure 1 日志明确高度比例过小后回退；K3 Figure 13 的 legend 显示 phase_a 已丢上排子图。首次尝试读取 caption_scoring.py/captions.py 时文件不存在，随后通过 rg --files 找到真实模块 caption_detection.py；未据错误路径形成结论。 |
| `python3 tests/results/20260907-003/write_review.py` | 生成 visual-review-20260907.md、findings.json、reviewed-inventory.json；问题导出按文档计数：DeepSeek 9、FunAudio 2、GPT-5 2、K3 4。 |
| 内联 Python：对 003 中 3 个脚本 ast.parse、JSON 解码、报告链接存在性、清单计数检查 | 3 个复核脚本语法通过；JSON 可解析；83 个报告链接均存在；17 条确认缺陷与 185 项清单一致。通过 fitz 核实 8 份 PDF 共 311 页。未运行正式 pytest 或全量重提取，因为本轮没有修改正式脚本。 |

### 结论及未修复问题

- 文件生成与 debug 叠加正常，但截图内容不能判为全对。确认 17 张问题导出：6 张题注错配/正文误识别/相邻图合并，4 张内容截断，7 张混入多行正文；另确认 Gemini Figure 9 这一编号未导出。该数是当前发现下限，不是完整错误率。
- DeepSeek Table 3/10/11 选中上方相邻表；Table 6 把第 37 页正文当表，真实表在第 38 页；Figure 11/12 重复合并；Table 12 长表截断。
- K3 Figure 13 丢失上排两幅绘图区，Table 2 缺少后续 Agentic 行和全部 Vision 分组，Table 3 顶部切过表头字形。
- FunAudio Figure 1 的较好精修框被拒绝并回退，重新包含整段摘要；同文 Figure 3、GPT-5 Figure 22/29 等也混入多行正文。
- Qwen Table 6/17、DeepSeek Table 14 放大后排除了疑似左缘截断；不计入缺陷。单行页眉及少量邻图题注残留另列为清理项。
- 附带发现：002/run_benchmark.sh 第 31–32 行按 kind 统计，实际索引字段为 type；直接重跑该脚本会写出 Figure/Table 为 0 的计数。独立统计现有产物仍确认为 97/88。本轮未修改原批次脚本。
- 报告及逐项证据：`tests/results/20260907-003/visual-review-20260907.md`。检查的是实际产物；后续应先建立这些失败样例的人工验收，再分别修题注配对、内容完整性和回退策略。
- 收尾执行 `git diff --check` 通过；`git status --short` 仍只显示原有 `task-list.md` 修改和未跟踪 `tests/tests/`，复核结果位于已忽略的 tests/results/。

## visual 缺陷成因与修复保证范围讨论（2026-09-07）

- 用户询问问题属于架构还是参数，以及修复后是否能保证全部正确。本轮只分析，不实施修复。
- 使用 `sed`/`rg` 核查正式 `extract_figures.py` 的题注过滤与回退链、`extract_tables.py` 的题注过滤、`caption_detection.py` 评分、`text_trim.py` 文本裁切和 `models.py` 默认状态；确认存在参数与决策机制交互，不能归因于单个阈值。
- 判定边界：当前默认路径的局部启发式决策、以原窗口比例代理完整性、导出默认 accepted 等机制需要加强；不据此否定现有模块划分或断言必须整体重写。17 个已知缺陷修复后仍须验证同批次其他资产、补查漏检并使用独立样本，不能预先保证全部正确。
- 本轮未修改正式代码、测试数据或结果；未运行测试，代码和日志读取用于解释现有证据。

## visual-review 报告逐项修复（2026-09-07）

按 `tests/results/20260907-003/visual-review-20260907.md` 的 17 张问题图 + Gemini Figure 9 漏检修复正式 Skill，验证产物写入 `tests/results/20260907-004/`。

### 操作、验证命令与结果

| 操作或命令 | 结果与边界 |
| --- | --- |
| 修改 `caption_detection.py`、`direction.py`、`clip_limit.py`、`extract_figures.py`、`extract_tables.py`、`text_trim.py`、`table_refine.py`、`figure_post.py` | 对应 BUG-077~082：题注筛选、堆叠表方向、精裁回退、左右拆 X / 多子图保护、长表窗口、表头 peek、远端调查正文、摘要小矢量。 |
| `python3 -m pytest tests/scripts/test_visual_review_20260907.py tests/scripts/test_caption_anchor_quality.py -q` | 95 passed。 |
| `python3 -m compileall -q skills/pdf-markdown-summary/scripts`；四入口 `--help` | 语法检查通过；`extract_pdf_assets.py`、`pdf_to_markdown.py`、`process_pdf.py`、`summarize_pdf.py` 均 exit 0。 |
| `python3 -m pytest tests/scripts/ -q -k "not golden"` | 161 passed、9 deselected；因未设 `PDF_SKILL_ALLOW_GOLDEN_SKIP` 退出码 1，按规则不算全绿。 |
| 5 份问题 PDF 提取到 `tests/results/20260907-004/`（`--preset robust --debug-visual --debug-captions`） | 全部 exit 0。Gemini Figure 9 已导出 p31；DeepSeek Table 6 改为 p38 真表；Fig 11/12 左右分离且 bbox 不同；Table 3/10/11 方向 below。 |
| 核对 004 索引 bbox 与 K3 Table 3 PNG | DeepSeek F1 `y0=466.0`、T8 `y1=304.8`、T12 `y1=753.4`；FunAudio F1 `y0=436.5`；K3 T2 `y1=689.2`、T3 `y0=114.2`（Proprietary/Open Weight 完整）、F13 `y0=318.8`。 |

### 结论

报告中 17 张实质错误与 Gemini Figure 9 漏检均已对因修复，并在 004 批次问题 PDF 上复核 bbox。单行页眉、邻图题注残留等报告未计入 17 项的清理项本轮未改。未更新 Golden。

## 主链三态验收与题注对账（2026-09-07）

按用户口径：截图留白略多可接受，框进标题或正文段落不可接受。schema 仍保留四态字段，主链实际使用三态。

### 操作、验证命令与结果

| 操作或命令 | 结果与边界 |
| --- | --- |
| 新增 `lib/assess.py`，接入 `extract_figures` / `extract_tables` / `extract_pdf_assets` / `pdf_to_markdown` | 评估只读几何布尔信号；污染与弱锚点落盘；提取后 `finalize_caption_inventory` 写入 `index.json.inventory`；Markdown 过滤非 insertable 状态。 |
| `python3 -m compileall -q skills/pdf-markdown-summary/scripts`；四入口 `--help` | 语法检查通过，四个入口均 exit 0。 |
| `python3 -m pytest tests/scripts/test_extraction_status_inventory.py tests/scripts/test_pdf_to_markdown_cli.py -q` | 通过（含留白仍 accepted、裸 Figure 22 进 expected、正文引用 unexpected 才 reject、Markdown 只插 accepted / accepted_with_margin）。 |
| `PDF_SKILL_ALLOW_GOLDEN_SKIP=1 python3 -m pytest tests/scripts/ -q -k "not golden"` | 175 passed、9 deselected；golden 排除不算全绿。 |
| Attention / Gemini 提取到 `tests/results/20260907-005/` | Attention 9 项全部 accepted，inventory 9/9。Gemini 28 项：Figure 9 p31 accepted；Table 12 `review_required`（object_truncation）；inventory expected=exported=28、missing=0。未更新 Golden。 |

### 结论

主链不再用 `height_ratio` 把留白判失败。能确定身份且框内无标题/正文的资产为 accepted；完整性不确定进 review_required 并仍出 PNG；正文引用或框内段落为 rejected 并仍出 PNG。Markdown 只插入前两态中的 accepted / accepted_with_margin。未跑 8 份 Golden 更新。

## 当前 Basic Benchmark 结构定位审查（2026-09-22）

用户要求仔细检查当前代码是否已通过 PDF 结构定位良好处理 basic 测试集全部 PDF。本轮仅审查与验证，保留所有既有未提交修改，未修改正式 Skill、版本化测试脚本、benchmark PDF、只读参考目录或 Golden。

### 操作、验证命令与结果

| 操作或命令 | 结果与边界 |
| --- | --- |
| `git status --short`；读取 AGENTS.md、正式 SKILL.md、task-list.md、提取/验收/Golden/评测器代码及 annotations 来源 | 确认工作区已有修改；当前 benchmark 8份共304页。现有GT为自动bootstrap，未当作人工真值使用。 |
| 内联Python通过 `git show HEAD:tests/basic-benchmark/<旧文件>` 与当前文件比较 SHA-256/页数/首页文本 | Kimi同为47页但字节不同；DeepSeek从58页V4换成51页V4.1；旧Golden清单未同步新文件名。只读，不恢复/改名输入。 |
| `python3 tests/results/20260922-001/run_audit.py` | 当前8份PDF全量以 `--preset robust --debug-visual --debug-captions` 重提取，8/8 exit0。输出全部放001批次各PDF的 images/txt/assets/markdown 分层。实际命令及哈希见run-status.json。 |
| `python3 -m pytest tests/scripts/ -q > tests/results/20260922-001/pytest.log 2>&1` | exit1：175 passed、9 failed、0 skipped。6项旧Golden差异、2项旧PDF路径不存在、1项新输入未纳入覆盖。不是全绿。pytest自动提取产物位于20260922-002，未更新Golden。 |
| `python3 tests/results/20260922-001/inspect_outputs.py`（分阶段及最终汇总） | 174项：167 accepted、7 review_required；生成summary.json与17张联系表；全部174项完成缩略图初筛。 |
| 内联Python使用fitz渲染疑点PDF原页，在内存页副本绘制最终bbox后仅保存PNG至001/assets；查看原页与截图 | 至少确认5项实质内容缺陷：Kimi F1右侧图截断、F12图内标题遗漏、F14轴标题/图例截断；Kearns F7图内标题/倍率遗漏；Gemini T11跨p60–63只输出p63。全部仍accepted。非304页全页人工GT验收。 |
| 独立只读代码审查；`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=skills/pdf-markdown-summary/scripts python3` 调用assess纯函数 | `objects_truncated_on_far_side([0,0,100,60],[0,0,100,100],[[0,0,100,100]],'below')` 返回False；默认AssessmentInput返回accepted/0.85；同key的rejected空路径记录仍使inventory missing为空。明确自评盲点，未修改代码。 |
| 内联Python校验输入哈希、代码指纹、PNG解码与300DPI/bbox尺寸 | 8份PDF哈希和正式脚本指纹前后不变；174项PNG均可解码、尺寸误差≤3像素；保存integrity.json。仅证明文件一致性，不证明内容正确。 |
| 生成 `tests/results/20260922-001/structure-review-20260922.md`；追加本台账 | 完整报告包含8份结果、5项原页证据、代码行号、Golden失败分类、验收范围与修复优先级。所有新Markdown带日期后缀。 |
| 收尾：审查报告本地链接、审查临时Python的AST语法、`git diff --check`、`git status --short` | 结果见本轮收尾验证输出。正式代码未改，未重复执行四入口help/compileall。 |

### 结论

默认 `layout-driven=on` 的文本/几何版式辅助确实存在，独立语义版面后端默认off。当前可确认8份都跑通，但不能判定所有图表准确完整；inventory与提取共用题注识别、续表需要本页题注、完整性自评忽略图内文字/横向截断等盲点均有证据。确认5项为发现下限，不是完整错误率；7项review_required也不等于7项错误。先修内容完整性和人工验收，再逐项审核Golden差异。

## Basic 结构定位缺陷修复（2026-09-22）

用户明确授权按审查问题立即逐项修复。本轮保留既有未提交修改，只对正式实现增量修正；未写入、改名或删除 benchmark 输入，未动 old-version 或 docs/2-ref。计划见 `docs/2-plans/basic结构定位修复计划-20260922.md`。

### 实现与失败复现

- 图形横向收缩纳入图中文字边界，排除页边竖排水印，恢复 Kimi F1 右侧柱图、F14 轴标题及图例。
- 图内标题恢复允许部分相交文字，使用原始搜索范围，并在正文清理后恢复，修复 Kimi F12、Kearns F7。补上异栏、完整正文句、长正文和 Kimi F13 负例，避免恢复图前段落。
- 新增 `table_continuation.py`，根据相邻页续页标记、重复表头及横线一致性恢复 Gemini T11 p60–63；支持无题注 debug 图。续表经过文字截断验收，默认保留全部结构匹配片段；四入口帮助与 Skill/CLI 文档说明 `--allow-continued` 仅控制重复题注续项。
- 完整性验收识别大比例部分对象、横向文字截断；inventory 排除空路径、严格检查文件存在，先过滤正文引用再选择真实题注，单列推断续页及待复核计数。
- Golden 输入清单同步当前 Kimi/DeepSeek V4.1 文件名、图表数量和 Gemini T11 新增三页；未修改输入 PDF。新增 `test_structure_review_20260922.py` 22 项用例，真实 PDF 断言来自原页人工确认的文字、边界和页码。

### 验证命令与中间结果

测试日志统一在 `tests/results/20260922-003/`；实际图片批次为 004–011，均写 tests/results。调试中显式放行 Golden 排除，不计为全绿。

| 命令或操作 | 结果 |
| --- | --- |
| `PDF_SKILL_ALLOW_GOLDEN_SKIP=1 python3 -m pytest tests/scripts/test_structure_review_20260922.py -q`（逐阶段、先失败后修复） | 初始10项失败验证缺陷；随后水印、题注竞争、异栏标题、续页自评、正文恢复均先复现失败。最终22 passed，日志 final-structure.log。 |
| `PDF_SKILL_ALLOW_GOLDEN_SKIP=1 python3 -m pytest tests/scripts/ -q -k 'not golden and not structure_review_20260922'` | 175 passed，31 deselected；final-unit.log，不算全绿。 |
| `python3 -m compileall -q skills/pdf-markdown-summary/scripts tests/scripts` | exit0，compileall.log。 |
| 四入口 `python3 skills/pdf-markdown-summary/scripts/{extract_pdf_assets,pdf_to_markdown,process_pdf,summarize_pdf}.py --help`（逐个执行） | 4/4 exit0，help.log。 |
| 独立只读复核 | 发现并修正异栏正文恢复、续页绕过自评；再次复核四个复现均通过，无新增阻断问题。 |
| `python3 tests/results/20260922-011/run_audit.py` | 最终8份全量robust、debug-visual、debug-captions；具体每份命令/输入哈希/退出码见该批次run-status.json，汇总在最终结果段。 |
| `python3 tests/results/20260922-003/compare_final.py` | 逐项比较本轮审查输出001与最终输出011、旧本地Golden；生成 assets/changes.json、golden-differences.json、changed-*.jpg，目视核对修改图片。 |

## 全量代码 bug 审查与 benchmark 印证（2026-09-22，第二轮）

用户要求仔细检查当前项目所有代码、以 basic-benchmark 印证是否还有 bug。本轮为只读审查：未修改正式 Skill、测试脚本、benchmark PDF、Golden；工作区另有并行会话正在修复今晨报告的 5 项缺陷，本轮结论以其修改中的工作树为准。

### 操作、验证命令与结果

| 操作或命令 | 结果与边界 |
| --- | --- |
| `python3 -m compileall -q skills/pdf-markdown-summary/scripts` | 通过。 |
| `Python 3.13 -m pytest tests/scripts/ -q`（系统 python3 无 pytest，须用 `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3`） | exit1：13 failed / 182 passed。9 项 golden（含已删除的 k3_tech_report、DeepSeek_V4 旧规格）+ 4 项 structure-review 红测。注意运行期间工作树被并行会话改动，golden 收集用的是旧文件名规格。 |
| 复跑 `pytest tests/scripts/test_structure_review_20260922.py -q` | 5 failed / 17 passed：原 4 项红测中 3 项已随并行修复转绿，新增 5 项红测指向未修缺陷（题注引用高分抢占、标题回收跨栏跟随、续表碎片带切字仍 accepted、标题回收吞正文、Kimi F13 正文残留）。 |
| 6 个并行只读子代理分组精读 scripts/ 全部 40+ 文件、tests/scripts、tests/eval | 产出按严重度分级的 bug 清单；主代理对 P1/P2 逐条读原文核实，纠正了子代理两处错误归因（clip_limit `_is_supported_short_title` 符号方向、quality `detect_truncation` 判据 2 影响面）。 |
| 读 `tests/results/20260922-009/gemini_v2_5_report/images/index.json` | Gemini Table 11 已导出 p60–p63 四页（p61/62 continued=True），今晨缺陷 1 已被并行修复，端到端印证通过。 |
| 目视核对 010 批次 Kimi F1/F12/F14、Kearns F7 PNG | F1 右柱图、F12 图内标题、F14 轴标题与图例、Kearns F7 标题与 ×10^4 倍率均已补齐，今晨缺陷 2–5 修复生效；Kimi F14 仍夹带页眉（清理项，未修）。 |
| 读 tests/annotations 各 gt.json 的 document_id | 均为下划线命名，run_eval 的 GT 键空格归一化缺陷在当前数据下不触发（潜伏）；annotations 仍含 DeepSeek_V3_2/V4、缺 Kimi-K3/DeepSeek_V41，GT 覆盖与 benchmark 改名不同步。 |

### 结论

今晨 5 项内容缺陷均已被并行会话修复并有 benchmark 产物印证；仍确认存在的新 bug 以 text_trim 近端距离公式写反（v1 与 v2 Phase B，Phase B 整段失效）、extract_tables 截断检查仍不含文字对象、markdown_insertable(None) 默认放行、layout_model 'fig' 子串误分类、get_best_for_page 跨页回退违约为代表，另有约 20 项 P3 级潜伏/死代码问题，明细见当轮会话报告。Golden 基准仍是改名前旧基准，6 项差异需人工逐条裁决后再决定是否 --update-golden。

011批次最终目视发现 GPT F9/F13/F18/F22 的标题恢复误带无句号正文尾行，未更新Golden。新增四个真实PDF失败用例，修正为基于前行宽度、字体、行距和左对齐识别连续正文；26项回归与新批次重新验收。

## Basic 结构定位缺陷修复收尾与 Golden 更新（2026-09-22）

继续处理结构审查报告中的 5 项内容缺陷，并收口并行审查发现的正文残留与 Kimi Figure 14 运行页眉问题。benchmark 输入保持只读；测试产物与本地 Golden 均写入 `tests/results/`。

### 最终修复

- Gemini Table 11 已恢复 p60、p61、p62、p63 四个片段，续页均经过文字和对象截断验收。
- Kimi Figure 1 右侧柱图与分数、Figure 12 图内标题、Figure 14 纵轴标题与右侧图例均已恢复。
- Kearns Figure 7 图内标题及 `×10^4` 倍率标记已恢复。
- Kimi Figure 14 的运行页眉文字和 Logo 已移除。根因是 Logo 在真实 PDF 中属于小型 `image_rect`，此前只过滤了微小矢量路径；现改为仅忽略紧邻运行页眉文字的小型图片，正常位图子图不受影响。
- `tests/scripts/test_structure_review_20260922.py` 增加真实 PDF 的 Kimi Figure 14 页眉边界断言，并将纯函数样例改为真实的图片 Logo 类型。

### Golden 差异审查

先用最终代码重新提取并运行旧 Golden 对比，完整日志为 `tests/results/20260922-037/golden-review.log`；再目视检查 17 个自动标记为 `review_required` 的资产，汇总图为 `tests/results/20260922-037/visual-review-flagged.png`。这些项目的标题、坐标轴、图例、表头与末行均完整，告警来自线条或对象贴近裁框的保守判据。

| PDF | 审查到的 Golden 差异 | 更新理由 |
| --- | --- | --- |
| Attention | 6 个 bbox/PNG 变化，身份集合不变 | 5 幅 Figure 去除整页留白、页眉或正文区域并收紧到图形；Table 2 顶边微调 2.1pt。 |
| Qwen3-Omni | 10 个 bbox/PNG 变化，身份集合不变 | Figure 1/3 去除页边与正文；Table 1 恢复完整横向表宽；Table 4/5/6/8/10/13/17 为表带边界微调。 |
| Kimi K3 | 新文件身份，旧基准不存在；当前 16 Figure + 5 Table | 输入由 `k3_tech_report.pdf` 更换为 `2607.24653v2-Kimi-K3.pdf`；新基准包含本轮 F1/F12/F14 完整性修复及 F14 页眉清理。 |
| FunAudio-ASR | 3 个 bbox/PNG 变化，身份集合不变 | Figure 1/3/4 去除摘要、章节标题或页宽空白，保留实际绘图区。 |
| Gemini 2.5 | 14 个 bbox/PNG 变化；新增 Figure 9；Table 11 改为 p60–63 四片段 | Figure 横向收紧、Table 顶边微调；补回 Figure 9；修复 Table 11 仅导出末页的问题，并正确标记 p61–63 为续页。 |
| GPT-5 System Card | 10 个 bbox/PNG 变化，身份集合不变 | Figure 1/2/3/6/7/22/29 去除页眉或正文，Figure 9/18/28 为小于 1pt 的边界微调。 |
| Kearns | 7 个 bbox/PNG 变化，身份集合不变 | 多幅 Figure 去除页边空白并收紧；Figure 7 同时恢复图内标题和倍率标记；Figure 5 为小幅横向补边。 |
| DeepSeek V4.1 | 新文件身份，旧基准不存在；当前 12 Figure + 5 Table | 输入由 58 页 V4 更换为 51 页 `DeepSeek_V41_Tech_Report.pdf`，不能沿用旧 V4 Golden，按新文档独立建立基准。 |

确认上述差异与修复目标一致后执行 `python3 tests/scripts/test_extraction_golden.py --update-golden -v`，8/8 更新成功；随后不带更新参数反向对比，8/8 通过。更新和复核日志分别为 `tests/results/20260922-037/golden-update.log`、`tests/results/20260922-037/golden-verify.log`。

### 最终验证

| 命令或操作 | 结果 |
| --- | --- |
| `python3 -m pytest tests/scripts/test_structure_review_20260922.py -q` | 28 passed；5 项原报告缺陷、Gemini 四页续表及 Kimi F14 页眉边界均通过真实 PDF 验收。 |
| `python3 -m pytest tests/scripts/test_caption_anchor_quality.py -q` | 80 passed。 |
| 目视查看最新 Kimi Figure 14 PNG | 页眉与 Logo 已移除；纵轴标题、横轴标题、曲线区域及右侧四项图例完整。 |
| `python3 tests/scripts/test_extraction_golden.py -v` | 更新后 8/8 PDF 通过。 |
| `python3 -m pytest tests/scripts/test_extraction_golden.py -q` | 9 passed，包含 8 份 PDF 对比及 1 项基准覆盖检查，Golden 未跳过。 |
| `python3 -m pytest tests/scripts/ -q` | 233 passed、0 failed、0 skipped；5 条为 PyMuPDF SWIG 弃用警告。日志为 `tests/results/20260922-037/pytest-full-final.log`。 |
| `python3 -m compileall -q skills/pdf-markdown-summary/scripts tests/scripts` | exit 0。 |
| 四入口 `python3 skills/pdf-markdown-summary/scripts/{extract_pdf_assets,pdf_to_markdown,process_pdf,summarize_pdf}.py --help`（逐个执行） | 4/4 exit 0。 |

### 结论

审查报告确认的 5 项内容缺陷、后续发现的标题恢复正文残留和 Kimi Figure 14 页眉残留均已修复。当前 Basic Benchmark 为 8 份 PDF、95 个 Figure、82 个 Table/续表片段，共 177 项；Golden 实际执行且完整测试全绿。Golden 仍是本地变更检测器，不替代独立人工 GT。

## 只读审查 P1/P2/P3 缺陷修复（2026-09-22 晚）

承接当轮只读审查报告，逐条修复报告中点名的 P1/P2/P3 问题。执行期间工作树仍被并行会话实时编辑（`figure_post.py` 于 20:04 被改动），本节结论以各步骤当时的工作树为准。

### 代码修复

| 级别 | 位置 | 修复内容 |
| --- | --- | --- |
| P1-1 | `lib/text_trim.py` v1 `trim_clip_head_by_text`、v2 Phase B | 近端距离公式两个方向写反已改正为 `near_is_top` 时取 `lb.y0 - caption_rect.y1`、否则取 `caption_rect.y0 - lb.y1`，与 Phase C 镜像一致。 |
| P1-1 附带 | 同文件 v2 | 公式修正后 Phase B 会把表格行当远端正文裁掉。Phase B 的候选行改由 `skip_adjacent_sweep` 控制（表格路径直接跳过），docstring 同步说明该开关同时作用于 Phase B 与 Phase C。 |
| P1-1 附带 | 同文件 v2 最小高度兜底 | 原兜底以「题注 ±600pt」重入递归，会返回整页横幅。改为回退到 Phase A 结果，Phase A 亦塌缩时回退原始 clip。 |
| P1-2 | `lib/extract_tables.py` | 表侧 `object_truncation` 补入 `text_crosses_clip_boundary`，与图侧对齐；传 `min_inside_height_ratio=0.5`，避免仅擦到裁框上下边的邻行误报。 |
| P1-2 配套 | `lib/assess.py` | `text_crosses_clip_boundary` 新增 `min_inside_height_ratio` 参数，默认 0.0 保持图侧行为不变。 |
| P2-3 | `lib/assess.py`、`core/pdf_to_markdown.py` | `markdown_insertable` 在缺 status 时不再无条件放行，改为回退判断 `review_required` 与 `warnings`；调用方补传这两个字段。 |
| P2-4 | `lib/models.py` | `get_best_for_page` 新增 `allow_cross_page`（默认 False），跨页回退改为显式选择加入，默认严格限本页。 |
| P2-5 | `lib/layout_model.py` | 题注图/表分类改用正则捕获的行首 label token，不再用 `'fig' in text.lower()` 子串匹配。 |
| P2-6 | `lib/extract_tables.py` | `header_clipped`、`far_side_body` 接入 `AssessmentInput`，分别复用 `expand_clip_to_nearby_table_header` 与 `trim_table_clip_far_side_body` 作为事后探测，不新增探测逻辑。 |
| P2-7 | `lib/table_refine.py` | `expand_table_clip_to_text_bounds` 改用 `_is_caption_like`，同时排除 Figure 与 Table 题注。 |
| P2-8 | `lib/pairing.py` | orphan 候选不再硬编码 `page=0`，改为传入真实页码。 |
| P3 | `lib/direction.py` | 合并行为相同的 `>=0.6` / `>=0.5` 两分支为单一 `>=0.5`，docstring 同步。 |
| P3 | `lib/clip_limit.py` | `limit_clip_by_neighbor_captions` 新增 `min_width`（默认 40，与原 `min_height` 默认一致），横向拆分验收不再误用高度下限。 |
| P3 | `lib/acceptance.py` | 删除返回值中不存在的死值 `base_text` 及其三层调整，连同仅供其使用的 `desc`。 |
| P3 | `lib/extract_figures.py`、`lib/extract_tables.py` | 去掉 `x_dist` 的 falsy 短路（`x0==0.0` 不再被当作缺失）；`seen_counts` 在渲染异常分支回滚，避免该编号被永久跳过。 |
| P3 | `lib/debug_visual.py` | `draw_rects_on_pix` 改为直接写 `pix.samples_mv`。原实现调用 PyMuPDF 1.28 已移除的 `pix.set_samples`，配合 `dump_page_candidates` 的宽 except 一直在静默失败，同时修掉 alpha 位图只重绑定局部变量的问题。 |
| P3 | `lib/output.py` | `get_run_id` 增加毫秒精度，避免同秒两跑覆盖 debug 目录。 |
| P3 | `tests/eval/run_eval.py` | `find_gt_files` 的目录键套用 `_doc_key`，与预测侧归一化一致。 |
| P3 | `tests/eval/keys.py` | GT 缺 `ident` 或 `caption_page` 时抛显式 `ValueError`，替代 `"None"` 键与 `int(None)` 崩溃。 |
| P3 | `tests/eval/metrics.py` | `n_extra` 改用 `n_pred_exported`，无框预测不再同时计入漏检与多检。 |
| P3 | `tests/scripts/test_extraction_golden.py` | `ItemSignature` 身份元组加入按文件序计算的 `occurrence`，重复 `(type,id,page,continued)` 不再静默覆盖；同时修正把 `index_path.parent.parent` 说成批次目录的注释（实为单 PDF 目录）。 |
| P3 | `tests/scripts/conftest.py` | 新增 `pytest_runtest_logreport`，运行期 `pytest.skip()` 的 golden 用例与收集期排除同等对待，补上「0 跳过」规则的缺口。 |

未修：`pipeline.py:375-388` 无 caption 时的 direction 回退、`pipeline.py:360` 只传 `orient=='O'` 矢量、`clip_limit.py:157-160` above/below 取样不镜像、`quality.py` 判据 2 文档与实现不一致、`output.py` rejected 记录写 `"file": ""`。这五条经复核属存疑或仅文档问题，改动会影响现有语义，保留待定。

### 回归测试

新增 `tests/scripts/test_review_fixes_20260922.py`，21 项用例覆盖上述每一条修复，含 Phase B 对 Figure 生效/对表格跳过的对照、最小高度兜底不返回整页、`min_inside_height_ratio` 的贴边行与真实侧切两种情形、`markdown_insertable` 的三种回退、`get_best_for_page` 跨页开关、题注 label token 分类、orphan 页码、`min_width`、eval 三项、golden 签名去重、alpha 位图画框。

### 验证记录

| 命令或操作 | 结果 |
| --- | --- |
| `python3 -m compileall -q skills/pdf-markdown-summary/scripts` | exit 0。 |
| 四入口 `--help`（`extract_pdf_assets`/`pdf_to_markdown`/`process_pdf`/`summarize_pdf`） | 4/4 exit 0。 |
| `pytest tests/scripts/test_review_fixes_20260922.py -q` | 21 passed。 |
| 修复前基线 `tests/results/20260922-020` vs 修复后 `20260922-026`（8 份 benchmark 全量重跑） | bbox 变动 0、新增 0、删除 0、状态变动 0。全部修复对 benchmark 产物零影响。 |
| P1-1 中途定位（`--debug-visual` 追 Gemini Table 12 分阶段 clip） | 仅修公式会让 Phase A 输出整页横幅 `(x,141.4)~(x,1341.4)`，命中「题注 ±600pt」兜底；据此补上 Phase B 表格保护与兜底重写，之后差异归零。 |
| `pytest tests/scripts/ -q`（含 golden，当前工作树） | 233 passed、0 failed、0 skipped，golden 实际执行。 |

### 期间发现，未处理

- **工作树被并行会话实时编辑**：`figure_post.py` 于 20:04 改动，修复了 Kimi 运行页眉残留。以该改动为界重跑 benchmark（`20260922-026` vs `20260922-040`）：Kimi 11 幅 Figure 的 `y0` 上移 2.4~44.0pt，其余 7 份 PDF 零差异，状态无变化。本节此前所有「零差异」结论均在该改动之前取得，不受其影响（两侧基线同源）。
- **`object_truncation` 存在系统性误报**：当前 177 项资产中 17 项（9.6%）被判 `review_required`，告警全部为 `object_truncation`。目视核对 FunAudio F1、Attention F2、GPT-5 F1 三例，裁剪框完整无缺。根因是 `objects_truncated_on_far_side` 用 `get_drawings()` / 图像块的**路径外框**判断，而该外框包含被 clip path 裁掉的部分与位图白边，系统性大于可见墨迹范围；`lost_fraction > 0.02` 且外溢 `> 2.0pt` 的判据过紧。实测触发对象：Attention F2 是位图白边外溢 18.3pt，FunAudio F1 是位图白边外溢 38.8pt，GPT-5 F1 是 10 个被 clip path 裁过的柱形路径。后果是这 17 项按四态契约不进 Markdown。修复方向是在判定前把对象框收敛到可见墨迹范围（`pixel_detect` 已有 `estimate_ink_ratio` / `detect_content_bbox_pixels` 可复用），属并行会话 `assess.py` 截断判定重写的范围，本轮未改。

## 清理冗余备份分支（2026-09-22）

| 操作或命令 | 结果与边界 |
| --- | --- |
| `git merge-base --is-ancestor`、`git log main..<branch>`、`git diff` 检查两备份分支 | `codex-main-before-rebase-20260605` 与 `codex-main-before-v021-squash-20260605` 内容完全一致；两者tip与 main 的 `e608fee`（V0.5.1-Build0243-20260605）内容逐字节相同，仅保留 rebase 前的旧提交图谱。 |
| `git branch -D codex-main-before-rebase-20260605 codex-main-before-v021-squash-20260605` | 已删除。现仅剩本地 `main` 与远端 `origin/main`。内容零丢失；仅 rebase 前旧哈希不可达，将由 git GC 最终回收。 |

## 第二轮复查：修复验证与新代码审查（2026-09-22）

并行会话完成墨迹探测修复与诊断代码撤除后，用户要求再查 bug。本轮只读：compileall 通过；两个只读子代理分别复审墨迹探测新代码（pixel_detect/assess/两 extract/refiners/入口）与上一轮 17 项修复点+评测器改动。

### 操作、验证命令与结果

| 操作或命令 | 结果与边界 |
| --- | --- |
| `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pytest tests/scripts/ -q` | **237 passed、0 failed、0 skipped**（196.8s，含 golden），本轮全绿。 |
| 复查上一轮 P1/P2 修复（grep+子代理精读） | 17 项修复点全部落实：text_trim 距离公式两方向已纠正、表侧截断检查已并入 text_crosses_clip_boundary、markdown_insertable 改 review_required/warnings 兜底、get_best_for_page 加 allow_cross_page=False、layout_model 改行首 token 判断、direction 死阈值删除、table_refine 题注排除正则补齐、clip_limit 新增 min_width、pairing orphan 页码修正、acceptance 死值移除、debug_visual alpha 原地写、output 空路径/run_id 毫秒、eval 三件套（GT 键归一化/int(None)/双重计数）修复且 selfcheck 33 项 PASS、conftest 补运行期 skip 拦截、golden 新文件名+同键 occurrence 编号。 |
| 子代理合成输入边界验证（空/单元素/NaN/双向 direction/框内外）+ benchmark 实测 ink probe 坐标 | 坐标换算（dpi scale、pix.irect 原点归一）正确，未发现崩溃级问题。 |

### 结论

上一轮确认 bug 已全部修复，测试全绿。新改动仍有 3 项 P2 级遗留：table_continuation.py:117 续表截断判定缺主链同款保护参数（易系统性误报 review_required）；extract_tables.py:405-415+923-932 的 table_search_clip 扩到整页放大 table_band_open 触发面；assess.py:371-379 的 lost_fraction 分支无视 direction 与远侧设计不一致。另有 table_refine.py:961-976 的 max_expand 绕过上轮未修，及 seen_counts 回退残留、estimate_ink_ratio 未用导入、per-record 重建 ink probe 等 P3 项。杂散目录 tests/tests/results/ 与 test_extraction_golden.py:17 陈旧注释待清理。

## 剩余审查问题修复（2026-09-23）

用户授权修复剩余P2/P3及inventory_gap根除保护。保留工作区全部既有修改，未修改benchmark输入、old-version或只读参考目录。

### 修改与取舍

- 续表 `text_crosses_clip_boundary` 对齐主表 `min_inside_height_ratio=0.5`，保留真实横向截断告警，排除擦边邻行误报。
- 表格恢复仍可搜索整页，`table_band_open` 独立限定为原始高度且受邻题注约束的baseline，避免将整页剩余短行当未闭合表格。
- `objects_truncated_on_far_side` 保留相交对象任意侧截断告警，明确其与完全分离题注侧对象豁免的区别；文档说明400平方点小对象检测盲区，补正反测试。
- 文本安全补边钳回max_expand探测范围，整条文字bbox不再绕过上限。
- 两提取器渲染失败后归零删除seen_counts键，保证同编号后页可重试。合成两页PDF注入首个PNG保存失败，验证Figure/Table均在第二页成功。
- 标题支持在上下方向均搜索两侧近邻、采用非负几何间距，远侧紧跟正文时保留章节阻断，兼容现有数字表头保护测试。
- 删除未用estimate_ink_ratio导入，墨迹探测闭包按页创建并复用缓存。
- prune仅清理运行前已存在且inode/大小/mtime/ctime未变化、未被当前有效索引引用的文件；无快照或坏索引时不删除。本轮新增与运行中改写图片保留。入口在开始提取前采集快照。
- run_id测试替换恒真断言为毫秒格式和同一运行稳定性检查，不虚称时间戳在同毫秒必定唯一；删除Golden陈旧版本示例注释。
- 已确认杂散目录仅3个错误cwd运行日志，将 `tests/tests/results/20260907-002/` 归档至 `tests/results/20260923-001/archived-misplaced/20260907-002/`，仅移除空父目录。
- 已确认 `tests/annotations/DeepSeek_V4/` 仅有旧V4 bootstrap标注，将其完整保留至 `tests/annotations/archive/DeepSeek_V4/gt.json`，避免默认单层GT发现误用。没有将旧坐标改名伪装V4.1标注；当前V4.1仍缺人工GT。全部4个移动文件前后SHA256相同，见archival-moves.json。

### 验证过程

日志统一在 `tests/results/20260923-001/`；pytest实际提取自动创建后续日期批次。

| 命令/操作 | 结果 |
| --- | --- |
| `PDF_SKILL_ALLOW_GOLDEN_SKIP=1 python3 -m pytest tests/scripts/test_remaining_review_20260923.py -q` | 首轮5失败/1通过，分别复现prune、max_expand、镜像标题、续表擦边；修复后6通过。新增失败重试及余量判定后8通过/2缺新函数，完成后定向全套通过。 |
| `PDF_SKILL_ALLOW_GOLDEN_SKIP=1 python3 -m pytest tests/scripts/ -q -k 'not golden and not structure_review_20260922'` | 最终209 passed，38 deselected；中间发现并修复Rect构造NameError及表头/章节标题兼容回归。此结果排除Golden，不算全绿。 |
| `python3 -m compileall -q skills/pdf-markdown-summary/scripts tests/scripts tests/eval` | exit0。 |
| 四入口 `python3 skills/pdf-markdown-summary/scripts/{extract_pdf_assets,pdf_to_markdown,process_pdf,summarize_pdf}.py --help`（逐一执行） | 4/4 exit0，help.log。 |
| `python3 tests/eval/run_eval.py --selfcheck` | 结果见eval.log。 |
| `git diff --check`；检查归档文件清单与哈希 | 无空白错误；移动范围严格为上述4文件。 |

### 全量结果与 Golden 差异验收

- `python3 -m pytest tests/scripts/ -q --basetemp=tests/results/20260923-001/pytest-final`：246 passed、1 failed、0 skipped，唯一失败为 FunAudio-ASR Table 4 的预期Golden几何/PNG变化。实际重提取全部8份，当前产物位于20260923-003（中途被终止的调试批次002未用于最终结论）。
- `python3 tests/results/20260923-001/review_diffs.py`：逐项比较最新代码指纹匹配产物与原Golden，8份中仅1个PNG变化。FunAudio-ASR Table 4 p10 bbox从 `[135.4,299.5,421.0,478.7]` 改为 `[180.7,299.5,421.0,478.7]`；原因是安全补边不再被整行bbox绕过max_expand。已目视比较新旧PNG，去除左侧空白，表头、Environment首列、11行环境及Average行均完整。其余PNG身份、bbox及哈希不变，因此准许更新本地Golden；这仅是变更检测，不宣称全量人工真值验收。
- `PDF_SKILL_ALLOW_GOLDEN_SKIP=1 python3 -m pytest tests/scripts/test_remaining_review_20260923.py -q --basetemp=tests/results/20260923-001/remaining-tmp`：12 passed，新增坏索引和被引用旧文件保护检查也通过。最终完整套件将纳入新增的这2项。
- 评测器selfcheck全部通过；AST验证73个Python文件通过，git diff --check通过。CLI文档已同步prune的新语义。

### 最终完成验证

- `python3 tests/scripts/test_extraction_golden.py --update-golden`：8通过、0失败；差异原因已逐项记录（仅FunAudio T4）。日志golden-update.log。
- `python3 -m pytest tests/scripts/ -q --basetemp=tests/results/20260923-001/pytest-confirmed`：**249 passed、0 failed、0 skipped，含Golden**。最终确认复用刚刚全量重提取且代码指纹一致的8份产物；日志full-final.log。5条PyMuPDF/SWIG弃用警告不影响通过。
- 内联Python校验：8份输入PDF的SHA256与20260922-001审查时一致，全部177个PNG可解码、inventory missing为0；仍有4项review_required，保留待复核状态，未以改Golden隐藏。详情integrity.json。
- 本轮全部列出的P2/P3代码问题已处理；旧V4标注作为历史数据保留，当前V4.1人工GT缺失未伪造补齐。未提交或回滚用户的其他修改。

## 版本升级 0.6.3 与文档同步（2026-09-23）

将 2026-09-22/23 两轮审查修复（墨迹探测四态评估、续表恢复、prune 安全化等）以版本号 0.6.3 固化，并把对外文档刷新到当前代码状态。未改动任何脚本逻辑，仅版本字符串与文档内容。

### 修改清单

| 文件 | 修改内容 |
| --- | --- |
| `skills/pdf-markdown-summary/scripts/__init__.py` | `__version__` 0.6.2 → 0.6.3。 |
| `skills/pdf-markdown-summary/SKILL.md` | Current package version 0.6.2 → 0.6.3（能力清单在上一轮已含续表恢复条目，本轮核对无需再改）。 |
| `README.md` | 版本号 0.6.2 → 0.6.3；「当前状态/Status」新增四态质量评估（assess）、跨页续表自动恢复、题注对账、`--prune-images` 安全化四项能力；回归基线由「155 passed、0 skipped（2026-08-30 复验）」更新为「249 passed、0 failed、0 skipped（2026-09-23 复验）」，并注明 benchmark 输入集 2026-09 更新（Kimi K3、DeepSeek V4.1 替换旧版，仍 8 份）。中英文两节同步。 |
| `AGENTS.md` | 第 8 节 benchmark 清单同步实际目录：`k3_tech_report` → `2607.24653v2-Kimi-K3`，`DeepSeek_V4` → `DeepSeek_V41_Tech_Report`（与 `tests/basic-benchmark/` 现存 8 份 PDF 一致）。 |
| `task-list.md` | 本节记录。 |

references/ 三个文档核对结论：`cli-options.md` 与四入口 `--help` 逐项一致（`--prune-images`、`--allow-continued` 新语义上一轮已写入）；`pdf-to-markdown.md`、`pdf-summary.md` 工作流描述仍准确，无需改动。`docs/` 根目录两份 2026-07 历史分析文档与 `docs/1-archive/`、`docs/2-ref/` 均未触碰。

### 验证记录

| 命令或操作 | 结果 |
| --- | --- |
| `python3 -m compileall -q skills/pdf-markdown-summary/scripts` | exit 0。 |
| 四入口 `--help`（`extract_pdf_assets` / `pdf_to_markdown` / `process_pdf` / `summarize_pdf`） | 4/4 exit 0。 |
| 版本一致性 grep（`__init__.py` / `SKILL.md` / `README.md`） | 三处均为 0.6.3。 |

