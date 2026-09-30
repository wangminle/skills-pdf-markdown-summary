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
| BUG-083 | 修复 | 复数标签 "Figures 3 and 4 …" 起句的正文被解析成附录编号 S3 并产出 accepted 假图资产（表同款 S2） | 2026-09-28 11:00 | 2026-09-28 14:10 | 已修复 | 根因：`FIGURE_LINE_RE`/`TABLE_LINE_RE` 的 label 正则 `(?:Figure \| Fig\\.?)` 不消费复数尾巴 s，`re.IGNORECASE` 下 `(S\\s*)` 分支把 "Figures 3" 的 s 吞为 S 前缀产出 S3。修复：label 改 `(?:Figures?\|Figs?\\.?\|…)` / `(?:Tables?\|Tabs?\\.?\|表)`，与 QC 正则 `QC_FIGURE_REF_EN_RE` 的 `Figures?` 写法对齐。合成 PDF（真实 Figure 1 + 复数正文句）端到端复测：修复前产出 `Figure_S3_…` / `Table_S2_…`，修复后仅 `Figure_1_Architecture_of_the_proposed_model.png`，index 中无 S3/S2。 |
| BUG-084 | 修复 | 双栏检测恒失效：`candidate_gap` 公式把右页边距当栏宽相减，标准 Letter 双栏实测恒 -62pt 必判单栏 | 2026-09-28 11:00 | 2026-09-28 14:10 | 已修复 | `layout_model.py` 旧式 `peak_sep - (page_width - peak2_x)` 在对称布局下恒等于 栏间距-页边距（≈30-54<0）。修复：采样段落行宽，用行宽中位数估计栏宽，`candidate_gap = peak_sep - median(width)`。合成单元直调：标准双栏（峰 54/321、行宽 237）判 2 栏、column 标注 60/60；单栏全宽+居中标题仍判 1 栏。 |
| BUG-085 | 修复 | 【回归 15f4e08】图路径验收门被写死 `allow_low_ratio_keep=True` 架空：正文污染且低比例的精裁框被强留为 accepted，reason 文本仍写「不通过」 | 2026-09-28 11:00 | 2026-09-28 14:10 | 已修复 | 参数机制为 V0.5.10（a1affd6）引入、调用点写死 True 为 15f4e08。注意不能简单翻回 False：15f4e08 同时放宽了回退链判据（`max(80, base*min(0.20, h_ratio))`），False 会使 Kimi F12/F14、Kearns F7 的合理精裁框被误杀后回退到切顶小框（4 个结构审查用例回归，已 bisect 确认）。最终方案与表路径 `table_like_refined` 同构：`detect_text_pollution` 提前到验收之前，`allow_low_ratio_keep=not polluted`——污染框必拒（直调验证 8/8 wide_lines + height_ratio 0.19 → accepted=False），干净图形框低比例保留（benchmark 8 份输出与旧基准零差异）。 |
| BUG-086 | 修复 | 方向回退哨兵 0.5 与采用门槛重合：对象覆盖率总和为 0 时返回 (dir, 0.5)，与真实证据 0.5 不可区分，零证据页面锁死默认方向并压制全局锚点 | 2026-09-28 11:00 | 2026-09-28 14:10 | 已修复 | `score_local_direction()` 无证据分支改返回 (dir, 0.0)；`determine_direction()` 门槛 `local_conf >= 0.5` 不变，0.0 落入 `< 0.5` 分支让位全局锚点。直调验证：local(0.0)+anchor=below → below；local(0.0) 无锚点无启发式 → 默认 above（与原哨兵方向一致，无锚点场景行为不变）；真实证据 0.8 仍优先于锚点。 |
| BUG-087 | 修复 | 子图题注 "Figure 3a:" 不算显式题注（主正则支持 1a/2b 但 `_EXPLICIT_CAPTION_PREFIX_RE` 不支持），inventory reconcile 系统性缺子图 | 2026-09-28 11:00 | 2026-09-28 14:10 | 已修复 | 正则补可选子图尾巴 `(?:\s*[-–]?\s*[A-Za-z]\|\s*\([A-Za-z]\))?`，与 idents.py 主正则同一套模式。直调：`Figure 3a:` / `Figure 3-b:` / `Figure 3 (a):` 均 True，裸标签 `Figure 3a` True；原有负向用例 `Table 6. Also, we…`、`Table 3 对齐符 Ablation`、`Figure 3 shows the architecture` 行为均不变（对齐符 `\|` 不在 `[A-Za-z]` 内，可选组空匹配）。 |
| BUG-088 | 修复 | 引用语境判据缺负向模式："Table 4 shows that …" 正文句得 caption 语境满分且 ref_ctx=False，正文句只赚不赔 | 2026-09-28 11:00 | 2026-09-28 14:10 | 已修复 | `is_likely_reference_context()` 补两条模式：复数并列 `^(?:tables\|figures\|figs\.?)…N…(?:and\|,\|;\|–\|-\|to)…M…`（真 caption 极少复数列举开头）；`标签+编号+描述动词+that/how 从句`（动词表与 caption 语境判据对齐）。限定 that/how 避免误伤 "Figure 3 shows the architecture" 句式 caption——直调验证后者仍不判引用。 |
| BUG-089 | 修复 | `quality.py::detect_truncation` 判据 2 docstring 与实现相反：文档写「候选内存在被切对象」，实现是「无实质对象时」才启用整体覆盖率分支，且对象非空时判据 1 优先并直接 return | 2026-09-28 11:00 | 2026-09-28 14:10 | 已修复 | 纯文档修正（历史遗留）：docstring 改为按优先级描述——有实质对象只看对象覆盖率；无对象可用时退而检查 final 对候选整体的覆盖率。实现未动。 |
| BUG-090 | 修复 | 对象口径不一致：图路径主循环与 `score_local_direction` 只收 `orient=='O'`，而 `compute_global_anchor` 收 O+H+V，纯折线/柱状图页出现「锚点看得见线段、局部证据为空」的方向对撞 | 2026-09-28 11:00 | 2026-09-28 14:10 | 已修复 | `compute_global_anchor()` 按 `is_table` 分口径：图路径只收 'O'（与主循环 Phase A/B 及局部证据一致），表格路径保持收 H/V/O（与表格主循环一致，表格线是表格主要证据）。原代码两个 if/elif 分支本就等价于全收，现为显式分口径。 |
| BUG-091 | 修复 | inventory 对账范围无视用户开关：`--no-figures`/`--no-tables` 仍为禁用类型产出 inventory_gap PNG 与 review_required；`--min/--max-figure` 收窄后范围外编号仍算「缺失」 | 2026-09-28 14:15 | 2026-09-28 18:20 | 已修复 | `finalize_caption_inventory()` 新增 `kinds`/`min_figure`/`max_figure` 参数过滤 `expected`；`extract_pdf_assets.py` 按 `include_figures`/`include_tables` 构造 `inventory_kinds`（空集是合法输入，不能写 `or None`，否则坍缩成 None 反而放开过滤）。**并发版本首版用 `ident.isdigit()` 过滤范围，会把 S1/3a 等非数字编号误丢**——CLI 默认即传 min=1/max=999，该分支每次运行都走，凡有补充图的文档其 S1 会被判 unexpected 并被 `apply_unexpected_rejects` 误杀。已改为与 `extract_figures.py:294-299` 同口径（`int()` 抛 ValueError 即保留）。 |
| BUG-092 | 修复 | inventory payload 自相矛盾：`expected=9, exported=9, missing=[], missing_count=9` | 2026-09-28 14:15 | 2026-09-28 18:20 | 已修复 | `missing_count`/`unexpected_count` 原取自补裁前的 `report`，而列表取自补裁后的 `final_report.to_dict()`。改为同源自 `final_report`。 |
| BUG-093 | 修复 | `run_all.py` 清单遗漏 6 个套件（实际收集 254 例、入口只跑 156 例并以 0 退出），且清单硬编码，新增测试文件仍会静默跳过 | 2026-09-28 14:15 | 2026-09-28 18:20 | 已修复 | 补登记 6 个套件使清单覆盖 `tests/scripts/` 下全部非 golden 套件；并新增 `find_unregistered_suites()` 闸门——`main()` 开跑前比对目录里实际存在的 `test_*.py`，有未登记者打印清单并 return 1。golden 由 `--with/--update-golden` 单独驱动，不计入。 |
| BUG-094 | 修复 | 表格外框线被切在导出框外：Qwen T6 底线差 3.6pt、T17 差 3.4pt（双线 419.68/420.10）、Kimi T5 顶线差 0.9pt，截图缺一条边并触发 object_truncation/table_band_open | 2026-09-28 14:20 | 2026-09-28 18:20 | 已修复 | 新增 `expand_table_clip_to_border_rules()`：把距 clip 上下边缘 ≤4pt、宽 ≥55% clip、水平显著重叠的横线并回（pad 1.5）。**硬约束：不得切开文字行**——Qwen T6/T17 底线正下方 0.9pt 就是脚注首行（`a These 19 languages…`，上标 5.5pt + 正文 7.3pt），无约束时并线会把该行切掉 1pt 并引入 far_side_body 告警；现检测到扩展带内有文字行即把该侧收到行首。效果：T6/T17 由 review_required 升为 accepted、告警清零（旧框实际把末行 `Fleurs-xx2zh` 等 9 个单元格切在框外 1.7pt；new PNG 像素级确认底部出现贯穿全宽的 booktabs 双线，旧图无）。 |
| BUG-095 | 修复 | figure/table 对 `text_crosses_clip_boundary` 传不同阈值（figure 用默认 0.0、table 显式 0.5），同一几何在两侧得出相反的截断结论 | 2026-09-28 14:20 | 2026-09-28 18:20 | 已修复 | 函数默认值改为 0.5 并在 `extract_figures.py` 调用点显式传 0.5（只改调用点不够——默认值退回时新增调用点会静默用回旧口径）。实测对 benchmark 无输出影响：attention F4 的 object_truncation 实际来自 `objects_truncated_on_far_side` 那一支，文本分支两个阈值都返回 False。 |
| BUG-096 | 修复 | `summarize_pdf --reuse-existing` 只查文件存在性：默认 `out_dir` 是 `<pdf_dir>/images`，同目录放第二份 PDF 时会静默复用上一份的 index.json 与文本 | 2026-09-28 14:25 | 2026-09-28 18:20 | 已修复 | 复用前读取 index.json 的 `meta.pdf` 与当前 PDF basename 比对，不一致则报错退出 1 并提示改用 `--out-dir`；index.json 损坏/不可读同样拒绝复用。 |
| BUG-097 | 修复 | argparse 允许选项缩写，`collect_explicit_args` 只登记完整选项串，前缀查不到 dest，导致 preset 判定「未显式传参」并覆盖用户值（实测 `--text-trim-width 0.8` 被 robust preset 改回 0.5） | 2026-09-28 14:25 | 2026-09-28 18:20 | 已修复 | `collect_explicit_args()` 在精确查表未命中时按 argparse 同款前缀规则补 dest，唯一前缀才认（歧义时 argparse 自己会报错）。验证 `--text-trim-width 0.8` / `--text-trim-width-ratio 0.8` / `--text-trim-w 0.8` 均保住 0.8；未显式传参时 preset 仍生效 0.5。 |
| BUG-098 | 修复 | 尾注识别三处收紧：①回扩排在所有 trim 之后，绕过 far_side_body 与章节标题清理；②续行判据用 `continue` 跳过纵向重叠的同行外来行，会跨过它继续把正文桥接成尾注；③回扩无题注防护 | 2026-09-28 14:25 | 2026-09-28 18:20 | 已修复 | ①`expand_clip_to_table_notes` 移到 `expand_table_clip_to_text_bounds` 之后、各 trim 之前（`trim_table_clip_far_side_body` 已共用尾注判别，故先扩安全）；②重叠行改 `break`；③新增 `caption_rect` 参数，只按「尾注行本身是否压到题注」判（不用「回扩后整块 vs 题注」相交的粗判——clip 本就贴着题注，那样会否掉正常回扩）。 |
| BUG-099 | 修复 | 尾注阈值余量过薄：字号容差 1.0（DeepSeek T4 实测差 0.72，余量仅 0.28pt）、总高上限 48pt（实测 47.3，余量 0.7pt），排版稍一抖动即截断 | 2026-09-28 14:25 | 2026-09-28 18:20 | 已修复 | 放宽为字号容差 1.5、总高上限 64。保留其余约束（同列 ±8pt、起始字号 ≤10、行距 ≤4pt、不以 •/Table/Figure 开头），并新增「超过上限仍要截断」的反向用例防止放宽成无界。 |
| BUG-100 | 修复 | 页眉/页脚文本判据两侧不对称：`trim_far_side_noise_before_content` 的 below 分支漏掉冒号条件，`NeurIPS 2024: Foo et al.` 这类非全大写页脚在 below 方向不被判为 running margin，作为图内文字证据把页脚框进截图 | 2026-09-28 14:25 | 2026-09-28 18:20 | 已修复 | 抽出共用判据 `looks_like_running_margin = 含冒号 or (len>=8 且全大写)`，above/below 共用。 |
| BUG-101 | 修复 | `expand_clip_to_nearby_figure_objects` 的邻题注停止线只认「完全在 clip 之上」的题注，已被部分框进 clip 的邻题注被忽略，扩边会把它剩余部分一起吞掉 | 2026-09-28 14:25 | 2026-09-28 18:20 | 已修复 | 判据由 `rect.y1 < limited_clip.y0 - 0.5` 改为 `rect.y0 < limited_clip.y0 - 0.5`（有重叠即停止线）。远处不与 clip 相接的邻题注仍不阻断（实测 y=[20,40] 不阻断、y=[95,115] 阻断）。 |
| BUG-102 | 优化 | `_table_cells_beyond`（`table_refine.py`）为死代码，全仓 0 调用 | 2026-09-28 14:25 | 2026-09-28 18:20 | 已修复 | 删除。 |
| BUG-103 | 修复 | 跨类型吞没无守卫：图与表各自在独立主循环收边，`detect_conflicts` 仅在 layout-backend 开启时运行且只比对同类型，主链上无任何跨类型重叠校验，图框压住上表末行会静默 accepted | 2026-09-28 18:00 | 2026-09-28 18:20 | 已修复 | 新增 `mark_cross_kind_overlaps()`：同页 figure×table 交叠占较小框 ≥5% 时双方加 `cross_kind_overlap_with_*` 告警并置 review_required；**只打标不改几何**，不用未经验证的规则去动已在 benchmark 验证过的收边结果。结果写入 inventory payload 的 `cross_kind_overlaps` 字段（可观测而非静默）。benchmark 8 份实测跨类型重叠 0 例，故不影响既有输出。 |
| BUG-104 | 修复 | golden 测试存在假绿：`--update-golden` 把基准写进它自己刚提取的批次，`_find_golden_index`（最新含基准的批次）与 `_find_existing_index`（最新含 index.json 的批次）落到同一目录，此后比较必然全绿 | 2026-09-28 18:10 | 2026-09-28 18:20 | 已修复 | 新增 `golden_is_self_comparison()`（比**父目录**，不比文件名——文件名本就不同，比文件永远为 False 判不到自比状态），在 golden 用例中显式断言非自比。真实防回归需要「另一次运行的产物 vs 基准」，已把基准独立放在 `20260928-024`、产物在 `20260928-023`。 |
| BUG-105 | 修复 | run.log.jsonl 观测缺口：BUG-047 之后回退类事件只在「拒绝」时写入，验收门收紧（如 BUG-085 `allow_low_ratio_keep=not polluted`）会让全部资产直接通过，文件静默变成 0 字节——「零回退」与「日志系统坏了」无法区分 | 2026-09-28 18:30 | 2026-09-28 19:10 | 已修复 | `main_modular` 收尾在 prune_images 后、return 前无条件写一条 `run_end` 事件（带 figures/tables 统计），文件永不空且保留顺带核对数量的能力。端到端测试 `test_run_end_always_written_even_when_no_fallback`：text-only PDF 全通过路径下 run.log.jsonl 非空、含 run_end、`details.figures=0/tables=0`（kwargs 落在 details 子字典而非顶层，测试按此断言）。 |
| BUG-106 | 修复 | `analyze_debug_batch.py` 的 `fallback_to_baseline` 判据过松：只看 final/baseline 高度比值 ≈1，BUG-079 的 `expand_clip_to_nearby_figure_title` 把图内标题扩回来后 final 高度恰好接近 baseline 但 y 边界不重合，属预期精修却被当回退——批次 045 的 7 个信号中 6 个是这类误报（唯一真题注回退 gpt-5 Figure 2 p13 的 y 边界与 baseline 差 <0.1pt） | 2026-09-28 18:30 | 2026-09-28 19:10 | 已修复 | `StageDelta` 补 `y0`/`y1` 字段，判据收紧为「高度比 ≈1 **且** final 的 y0/y1 与 baseline 均差 <2pt」才算真回退。新增 `test_analyze_debug_batch.py` 三用例：y 边重合→标记；Kimi Figure 9 p15（y0 差 5.8pt 的标题回扩）→不标记；final 高度比 0.42<0.55→仍按小框标记。并已登记进 `run_all.py` 清单（清单闸门 BUG-093 强制要求）。 |
| BUG-107 | 修复 | 句点题注被误判正文：`_BODY_DISCOURSE_RE`/`_PERIOD_BODY_CITATION_RE` 把句点后的 also/we/this/the/in 一律当正文接续，而 `Figure 1. The proposed architecture`、`Table 2. This comparison…` 是最常见的题注写法——题注既不被提取、也不进 inventory 补裁，**整条资产静默消失**（合成 PDF 复现：修复前输出目录 0 个 PNG，修复后 `Figure_1_The_proposed_architecture_of_our_method.png`） | 2026-09-29 10:20 | 2026-09-29 11:05 | 已修复 | 句首常见词不能作判据，改为只认「几乎不可能出现在题注开头」的接续词：`_PERIOD_BODY_OPENER_RE = also\|we\|our\|here\|note that\|let us\|in this\|in the following\|as shown\|as we\|as discussed`；`_PERIOD_BODY_CITATION_RE` 改为捕获句点后全文 + 共用判据 `_period_tail_reads_as_body()`，`is_explicit_caption_format` 与 `is_caption_reference` 两处口径同步。BUG-077/088 用例全部保持（`Table 6. Also, we…`、`Table 4 presents the results. The six factors…` 仍判正文）。基准 8 份 PDF 扫描「Figure/Table N. The\|This」命中 **0** 行，故 golden 不变——这类题注正是基准覆盖不到的盲区，靠合成用例防回归。 |
| BUG-108 | 修复 | 邻题注未过栏位检查：`score_local_direction` 只用纵向位置判断「向下关联的邻题注」，双栏页面两栏各有一张表时，另一栏较早的题注被认作向下邻题注，`_owned_by_neighbor` 随即认领当前栏题注上方的**全部**表格行并清空上方证据，方向由 `above` 翻成 `below`（直调复现：无邻题注 `above` 0.95 → 含左栏题注 `below` 0.00），截取到错误区域 | 2026-09-29 10:20 | 2026-09-29 11:05 | 已修复 | 新增 `direction.captions_share_column()`（横向重叠 ≥ 较窄者 50%；同栏/通栏≈1，跨栏为 0 或栏间距级擦边），`neighbors` 与 clip 收窄分支均先过滤；归属判断只由同栏题注参与。新增 `test_two_column_neighbor_caption_does_not_steal_rows`。 |
| BUG-109 | 修复 | 【BUG-108 同根因，自查发现】`clip_limit.limit_clip_by_neighbor_captions` 与 `figure_post.expand_clip_to_nearby_figure_objects` 的纵向停止线同样只看纵向：跨栏题注把本栏 clip 从邻栏题注处截断（直调复现 y0 240→318，丢 78pt 图形内容）、把扩边卡住（y0 由 244 卡到 318，图顶部 74pt 被切） | 2026-09-29 10:20 | 2026-09-29 11:05 | 已修复 | 两处纵向边界的邻题注列表改用 `captions_share_column` 过滤（`figure_post` 在函数入口统一过滤，`clip_limit` 竖向收窄用 `column_neighbors`；**左右并列拆 X 的那段仍用全量邻题注**，BUG-080 行为不变）。新增 `test_cross_column_caption_does_not_limit_vertical_bounds`，并断言同栏题注仍收紧到 318.0 防止过滤过头。 |
| BUG-110 | 修复 | 等距并列两图被合并成多框资产：`_find_multi_frames` 的「没有更近的其他题注」判据只比 edge_distance，左右并列两图两题注时两侧距离完全相等（各 10pt），右框被并入左图的 multi-frame，右题注成孤儿；A3 还可能把两图一起裁进第一张 PNG（直调复现：pairs=1 且 content_bboxes 含两框、orphan_caps=1） | 2026-09-29 11:30 | 2026-09-29 12:10 | 已修复 | 距离相等时改用配对代价 tie-break：`_cost_function`（含水平对齐奖励）更优的题注视为存在独立配对关系，该框留给它。验证：两图两题注 → 2 对各 1 框、零孤儿；单题注两框（真 multi-panel）仍合并 2 框；居中题注三框仍合并 3 框；不等距场景行为不变。回归 `test_two_captions_two_contents_pair_one_to_one`。 |
| BUG-111 | 修复 | Layout 题注回退不筛类型：`pair_layout_regions` 在外部候选缺某页某类型时回退到 `caption_regions`（figure/table 共用池），Layout 把某页表格题注识别成 figure 类时，table 分组拿 figure 题注配表格内容（直调复现：p2 的 table pair 挂上 `[50,410,300,430]` figure-caption）；若表格记录缺 caption_bbox，A3 会用这个错题注推断裁剪方向 | 2026-09-29 11:30 | 2026-09-29 12:10 | 已修复 | 新增 `_filter_layout_captions_by_kind()`：raw_class 带 figure/table 字样的按类型筛；无法判别的通用 `caption` 不筛（否则单类型文档题注被误丢）。验证：figure-caption 不再配 table 内容（成孤儿由外部候选/A3 兜底）；raw_class='caption' 仍正常配对。回归 `test_layout_caption_fallback_filters_by_kind`。 |
| BUG-112 | 修复 | A3 一对一匹配用纯 IoU 贪心：与两个候选都高重叠的记录先占用另一记录的唯一候选，后者彻底失去精修机会（直调复现：候选 `[0,0,100,100]`/`[65,0,165,100]`、记录 `[5,0,105,100]`/`[0,0,80,100]` 只匹配 1 条，实际可匹配 2 条） | 2026-09-29 11:30 | 2026-09-29 12:10 | 已修复 | `_match_records_to_candidates` 改用 Kuhn 增广求最大基数匹配（邻接表按 IoU 降序访问，天然倾向高 IoU 的最大基数解）；候选按 (page,kind,rounded bbox) 折叠成同一图节点，同框多候选只被一条记录占用，跨页同框互不冲突。链式冲突 3×3 全配、同框折叠 1 条、跨页 2 条均验证。回归 `test_matching_prefers_maximum_cardinality`。 |
| BUG-113 | 修复 | `quality.detect_truncation` 的对象分支屏蔽覆盖率判据：候选框同时含对象和文字、final 保留对象却裁掉文字带时（直调复现：final 覆盖候选 0.820<0.85，对象全保留），`objs_in_cand` 分支直接返回未截断，该裁剪以 accepted_with_margin 静默放行 | 2026-09-29 11:30 | 2026-09-29 12:10 | 已修复 | 对象检查通过后继续检查候选整体覆盖率（对象之外的文字同样是候选内容），reason 标注 `objects kept` 以区分。验证：0.82 报截断、全保留/95% 容差内不误报、对象被切仍报。回归 `test_truncation_flags_text_cut_even_with_objects_kept`。 |
| BUG-114 | 修复 | 多框归属只看外部候选题注池：外部候选来自「有 legacy record 的题注」，只在 Layout 检测到题注的图不在池里，`_find_multi_frames` 的「没有更近的其他题注」判据看不到邻居自己的题注，把上下相邻（gap 20pt≤30pt）的独立图并进上一张图的多框——两张图合成一张截图，第二张图**彻底丢失**（直调复现：pairs=1、content_bboxes 含两框、第二张图的题注也没被用上） | 2026-09-29 11:50 | 2026-09-29 12:25 | 已修复 | `pair_page` 新增 `ownership_captions`（归属判断的题注全集，默认等于 `captions`），`pair_layout_regions` 传入 `caps + _filter_layout_captions_by_kind(page_region.caption_regions, kind)`（`_dedup_caption_regions` 按几何去重）。验证：场景 B 由「1 对含两框」变为「1 对 1 框 + fig2 记为孤儿内容」，题注齐全的场景 A 与 multi-panel 合并行为不变。回归 `test_multi_frame_keeps_figure_whose_caption_is_layout_only`。 |
| BUG-115 | 修复 | A3 的 record↔候选匹配只看内容框 IoU，不看图注身份：上下相邻两图的 legacy 截图框漂移后 IoU 互相倒挂（正确配对 0.139/0.162 低于 0.25 阈值，错误配对 0.519/0.536 通过），两张图**互换绑定**，A3 随后用对方的候选框重渲染 = 截图串图（直调复现：ident=1 绑到 [72,320,520,520]） | 2026-09-29 11:50 | 2026-09-29 12:25 | 已修复 | 新增 `_captions_identical()`（caption_bbox IoU ≥ `_MIN_CAPTION_IOU=0.5` 即同一条图注）：身份一致的边不受 `_MIN_MATCH_IOU` 限制（身份是真值、几何是估计），Kuhn 邻接表按（身份, IoU）降序访问，最大基数性质不变。验证：互换场景恢复 ident=1→图1、ident=2→图2；无 caption_bbox 的记录行为不变。回归 `test_matching_uses_caption_identity_over_content_iou`。 |
| BUG-116 | 修复 | `--no-refine` 只管 legacy 阶段，A3 精修完全不看这个列表：`run_refinement_pipeline(records=...)` 把全部 record 交给匹配与精修，被用户显式排除的 id 照样进入匹配、生成 refined_bbox，是否覆盖仅取决于质量门（实测 HEAD 源码 `--no-refine 4`：table 4 仍被匹配并评估精修，只是恰好被质量门拒；`--no-refine 2`：ident 2 同样进入匹配）——排除语义不被遵守，输出对错取决于几何运气 | 2026-09-29 11:50 | 2026-09-29 12:25 | 已修复 | `run_refinement_pipeline` 新增 `skip_idents`：排除的 record 不进入匹配（不占用候选），也不做精修，但在报告中留 `skipped: id listed in --no-refine` 一条；`extract_pdf_assets` 传 `skip_idents=set(no_refine_figs)`（该列表本就同时作用于 figure 与 table）。验证：`--no-refine 2` 下 matched 12→10、figure 2 与 table 2 两条 skipped、最终框保持 legacy。回归 `test_refinement_skips_no_refine_idents`。 |
| BUG-117 | 修复 | `conftest.py` 的假绿闸门只统计「已收集后被 -m/-k 排除」和「运行期 skip」两类，收集数为 0 的整类假绿漏网：`pytest tests/scripts --ignore=tests/scripts/test_extraction_golden.py` 全程 0 退出，回归验证根本没跑（AGENTS §8 明确要求「golden 收集数为 0 一律判失败」） | 2026-09-29 11:50 | 2026-09-29 12:25 | 已修复 | 新增 `pytest_collection_modifyitems` 统计 golden 收集数 + `_selection_covers_golden()` 判定目录级选择（裸 pytest / 目录参数 / golden 套件的祖先目录），二者与既有 skip 统计一起在 `pytest_sessionfinish` 强制退出码非 0；逐文件调用（run_all.py 的套件式用法，golden 由 run_all 单独整轮执行）不触发，`PDF_SKILL_ALLOW_GOLDEN_SKIP=1` 仍可放行（仅 WARNING）。验证：HEAD 版 conftest 下同一命令 exit 0，修复后 exit 1 且打印「未收集到任何 golden 用例」；逐文件非 golden 套件仍 exit 0。回归 `test_golden_zero_collection_fails_session` 等 3 例。 |
| BUG-118 | 修复 | 上下相距不超过 30pt 的两张独立图仍被多框分组吞并：第一张题注夹在两图之间，到下一张图的边距小于等于该图自己的题注，`_find_multi_frames` 的「更近题注 / 等距比代价」判据不成立，于是在第二张题注配对前占用其内容框。直调复现为 1 对含两框、1 条孤儿题注 | 2026-09-29 12:10 | 2026-09-29 12:16 | 已修复 | 分组前排除「另一条题注的唯一最佳内容」（`_unique_best_content`，代价打平不认领）。边距更近的夹缝题注不再并走下一张图；单题注的上下两块仍合并。回归 `test_vertical_neighbors_are_not_merged_before_second_caption_pairs`。 |
| BUG-119 | 修复 | 评审#4 第 1 条：A3 匹配只保最大基数，不保 IoU 总和最优——Kuhn 增广找到的第一条可行路径不一定是总分最高的分配。确定性复现：2 记录 2 候选总 IoU 0.808，另一同基数分配 1.084；随机搜索 5 万例（n=2..4）另命中 3 周旋转反例（2.862 对最优 2.892），该改进形态任何 2-opt 交换都够不到，必须精确求解 | 2026-09-29 13:30 | 2026-09-29 14:10 | 已修复 | `_match_records_to_candidates` 改为按 (page,kind) 分组、同框折叠后用位掩码 DP（`_optimal_assignment`）精确求「先最大化身份边数、再最大化 IoU 总和」的分配；状态数 2^m×n（单页个位数）可忽略，frame>12 时退回贪心防御。身份边仍不受 IoU 阈值限制且字典序最优先。回归 `test_matching_maximizes_iou_sum_within_cardinality`（含 2×2 与 3 周旋转两个反例）。 |
| BUG-120 | 修复 | 评审#4 第 2 条：混合类型页上 `raw_class="caption"` 的通用题注进入 `untyped` 分支，figure 与 table 两个分组都拿它配对——同一条题注产出两张配对（直调复现：一页一图一表一通用题注 → 2 pairs，题注同时绑 figure 框和 table 框） | 2026-09-29 13:30 | 2026-09-29 14:10 | 已修复 | `_filter_layout_captions_by_kind` 新增 `mixed_page` 参数：本页 figure/table 内容并存时通用题注不进任何分组（留作孤儿，原 review「无法判别时保留孤儿」的落实）；单类型页行为不变（否则单类型文档题注全变孤儿）。归属证据池同步排除。回归 `test_untyped_caption_not_shared_across_kinds_on_mixed_page`。 |
| BUG-121 | 修复 | 评审#4 第 3 条：golden 零收集闸门只对目录级选择生效，单文件选择（`pytest tests/scripts/test_xxx.py`）零收集照常 exit 0——与 AGENTS §8「golden 收集数为 0 一律判失败；定向排除需显式设置环境变量」不符 | 2026-09-29 13:30 | 2026-09-29 14:10 | 已修复 | conftest `_selection_covers_golden` 恒 True（单文件零收集同样判失败）；新增 `PDF_SKILL_GOLDEN_EXTERNAL` 供 run_all.py 逐文件套件调用显式声明「golden 由本入口另行整轮执行」（`run_pytest_suite` 经 `extra_env` 传入，golden 本体调用不声明）。人工定向调试仍用 `PDF_SKILL_ALLOW_GOLDEN_SKIP=1`（仅 WARNING）。回归 `test_single_suite_selection_zero_collection_fails` 等 4 例。 |
| BUG-122 | 修复 | `Our` 题注只要引用 Section/Table 等编号对象仍会静默漏提：`_period_tail_reads_as_body` 将 `our` 开头且含交叉引用的 tail 一律判正文，真实题注正常引用章节或另一张表时丢资产 | 2026-09-29 00:00 | 2026-09-29 00:00 | 已修复 | P2。修复：删除「our 开头 + tail 含 Section/Table/Equation 引用」就否定题注的特例；显式 `Figure/Table N.` 题注只在 tail 以 `we/also/in this/as shown` 等强正文接续词开头时拒绝，题注描述内交叉引用不再导致资产静默消失。原记录于文件尾部「2026-09-29 第五轮复查遗留」日志小节，2026-09-30 台账整理转入本分区；回归验证明细见该日志小节。 |
| BUG-123 | 修复 | 通栏表保护启发式双向误判，且恢复阈值救不回典型半栏误收：同行判定固定 3.5pt 中心距离误收偏 5pt 的通栏表，反向把双栏短正文当通栏单元格 | 2026-09-29 00:00 | 2026-09-29 00:00 | 已修复 | P2。修复：同行判定改为垂直框重叠率（至少 30%），容忍字形框 5~7pt 偏移；加入正文句形判定（含无句号但有谓语的短正文）。原记录于文件尾部「2026-09-29 第五轮复查遗留」日志小节，2026-09-30 台账整理转入本分区；回归验证明细见该日志小节。 |
| BUG-124 | 修复 | 罗马/字母编号修复会把小字号表头判为 Markdown 标题：`P. Value`/`N. Samples`/`M. Mean` 被切碎（BUG-097 同类问题回归） | 2026-09-29 00:00 | 2026-09-29 00:00 | 已修复 | P2。修复：单字母/罗马数字标题放行前，对正文字号的明确统计度量表头做定向排除；`A. Introduction`/`IV. Experiments` 任意字号章节识别保持不变。原记录于文件尾部「2026-09-29 第五轮复查遗留」日志小节，2026-09-30 台账整理转入本分区；回归验证明细见该日志小节。 |
| BUG-125 | 修复 | A3 最优分配 `_optimal_assignment` 在同页同类型候选超过 12 个时退回贪心，违反自身硬约束（13 frame 构造只返回 12 条匹配） | 2026-09-29 00:00 | 2026-09-29 00:00 | 已修复 | P3。修复：移除 m>12 贪心降级，改为多项式最小费用流，整数权重精确实现字典序目标（身份边数→匹配基数→IoU 总和）；13 frame 反例恢复 13/13。原记录于文件尾部「2026-09-29 第五轮复查遗留」日志小节，2026-09-30 台账整理转入本分区；回归验证明细见该日志小节。 |

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
| CHK-020 | 检查 | 对照三轮审查逐条核对句点题注、双栏归属、缺口补裁、golden 分批、配对与精修、benchmark 路径 | 2026-09-29 12:00 | 2026-09-29 12:16 | 已完成 | 17 项中 16 项在当前工作区已有对应实现与回归；仍复现的是上下相邻独立图被多框吞并，见 [[BUG-118]]。通用 raw_class=caption 仍参与回退配对（否则无类型标注的单类型页会全部变成孤儿）；逐文件 pytest 不因未收集 golden 失败，避免 run_all 的套件式调用全红，目录级零收集仍失败。 |
| CHK-021 | 检查 | 独立复核 0.6.5 三篇案例修复后的裁剪与 Markdown，并执行台账/插图/T7 回归收尾 | 2026-09-30 11:20 | 2026-09-30 11:29 | 已完成 | 三篇共 24 资产全部 accepted，词坐标核对无截词/污染/漏行。Markdown 由文末附录改为题注旁插入。PARADISE T7 框约 [59.6, 108.1, 286.2, 169.3]。 |
| CHK-022 | 检查 | 核对 Basic 结构定位修复计划与提取状态/题注对账设计的完成情况 | 2026-09-30 16:27 | 2026-09-30 16:27 | 已完成 | 逐项核对 design/3-plans/basic结构定位修复计划-20260922.md 与 extraction-status-inventory-20260907.md、正式 assess/pipeline 实现、回归及历史验收；Basic 6项待办均已落地，状态对账及2026-09-28五项补充已实现。A3“状态只降不升”文案需限定为 legacy rejected 不恢复 Markdown 插入资格：实际可转 review_required，非所有状态单调。执行 python3 -m pytest tests/scripts/test_structure_review_20260922.py tests/scripts/test_review_fixes_20260922.py tests/scripts/test_extraction_status_inventory.py tests/scripts/test_bugfix_20260928.py tests/scripts/test_extraction_golden.py -q --basetemp=tests/results/20260930-028/pytest-tmp：111 passed、0 failed、0 skipped，含Golden；日志 tests/results/20260930-028/pytest.log。本轮为相关套件复核，未重跑全目录套件；未修改业务源码或两份计划，功能编号与SVG无需更新。 |

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
| TST-047 | 检查 | 补 PARADISE 第 9 页 Table 7 真实页面回归，防止宽度恢复吞右栏正文 | 2026-09-30 11:20 | 2026-09-30 11:29 | 已完成 | test_real_layout_regressions_20260929.py：优先从 1-参考素材 PARADISE PDF 抽第 9 页跑完整 extract_tables；另用该页实测坐标约束 restore_table_clip_width。去掉短单元格过滤时 x1=524.8，过滤恢复后保持左栏。 |

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
| DOC-059 | 文档 | 更正 task-list 中三篇外部 PDF 不在本机的错误记录，并同步 Markdown 插图策略文档 | 2026-09-30 11:20 | 2026-09-30 11:29 | 已完成 | 更正 2026-09-30 P2 修复节误写；补独立复核收尾节；更新 references/pdf-to-markdown.md 与 Skill Output Rules。 |
| DOC-060 | 文档 | 将顶层 `docs/` 正式改名为 `design/`，并同步当前文档与规则引用 | 2026-09-30 12:48 | 2026-09-30 12:55 | 已完成 | `git mv docs design`；更新 AGENTS.md、README.md、现行设计文档、`tests/eval/` 引用；`design/2-ref/` 内部文件未改内容；`old-version/` 与 `design/1-archive/` 历史快照未改写；task-list 已完成历史条目中的 `docs/` 路径为当时事实，保持不动 |
| DOC-061 | 文档 | 按实际能力建立全部维护代码的功能模块全集、稳定编号与 SVG 反查 | 2026-09-30 | 2026-09-30 14:50 | 已完成 | 26 域、394 项（正式 334、测试评测 60）；85 个 Python 文件、1106 个源码定义覆盖；详见 design/4-analysis/ 功能全集、编号 JSON、覆盖索引及三张 SVG；源码快照、3943 个链接、图形与语法检查通过，记录 tests/results/20260930-025/ |
| DOC-062 | 文档 | 在 AGENTS.md 与 CLAUDE.md 固化函数变更时功能全集与编号持续维护规则 | 2026-09-30 15:17 | 2026-09-30 15:18 | 已完成 | AGENTS.md 新增第 9 节；新建 CLAUDE.md 作为 Claude 规则入口；函数/类/方法变更须检查并按影响更新功能全集、编号表、源码覆盖索引及相关 SVG；编号稳定，新功能追加，删除功能标记弃用；两份功能维护条款一致，13 个文件链接有效；台账 check 与 git diff --check 通过。本轮仅改规则，功能编号和 SVG 无需变化。 |
| DOC-063 | 文档 | 逐条分析全部具名历史 BUG 的功能编号归属并生成降序排行报告 | 2026-09-30 16:00 | 2026-09-30 16:00 | 已完成 | 新增 design/4-analysis/BUG历史记录与功能编号归属分析-20260930.md、归属统计 JSON 与排行 SVG。125 标准记录完整覆盖，123 有叶编号、069/102保留无直接编号；另纳入2重号日志与BUG-A/B共4补充记录，综合129。函数首位extract_figures=12，综合extract_tables=11；F07.010/F09.008/F19.013各5并列；F14域标准21/综合23。已独立回算编号与函数归属，85源码哈希未漂移，2345文档链接有效；compileall、台账check和git diff --check通过。正式函数未改，功能全集/编号/原流程SVG无需变化；统计历史报告频次，不代表当前未修BUG。验证详录见本轮日志。 |
| DOC-064 | 文档 | 将已完成的 Basic 结构定位修复计划与提取状态对账设计归档 | 2026-09-30 16:29 | 2026-09-30 16:35 | 已完成 | `git mv` 至 `design/1-archive/`：`basic结构定位修复计划-20260922.md`、`extraction-status-inventory-20260907.md`。依据 CHK-022：Basic 6 项待办与状态对账及 2026-09-28 五项补充均已落地。未改写文档正文、历史 task-list 路径、`design/2-ref/`、`old-version/`。现行文档无指向这两份文件的链接。功能编号与 SVG 无需更新。 |

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
| DEV-017 | 开发 | Markdown 把 accepted 图表插回正文对应题注位置，不再一律堆到文末 | 2026-09-30 11:20 | 2026-09-30 11:29 | 已完成 | `pdf_to_markdown.py` 新增 `_place_assets_in_document`：按题注段落匹配 Figure/Table ident，内容在题注上方则插在题注前，否则插在题注后；正文引用不抢槽；未匹配资产仍进文末提取资产节。见 test_pdf_to_markdown_cli.py 三条新用例。 |

## 配置运维

| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| OPS-001 | 运维 | 检查并维护 .gitignore，符合 Windows 开发现状 | 2026-06-13 00:00 | 2026-06-13 00:00 | 已完成 | 删除无效规则 `tests-basic-benchmark/`（笔误，实际输入目录 `tests/basic-benchmark/` 需跟踪）与 `ref/`（无对应目录）；新增 Windows 系统缓存（Thumbs.db/ehthumbs.db/desktop.ini）、编辑器临时文件（\*.swp/\*.swo/\*~）、环境密钥（.env/.env.*）；保留 `__pycache__/`、`tests/results/` 等现有规则；经 `git check-ignore` 验证 tests/results 仍忽略、tests/basic-benchmark 未被误伤，`git diff --check` 通过 |
| OPS-002 | 运维 | 将 docs/3-experiments/ 加入 .gitignore | 2026-07-29 23:30 | 2026-07-29 23:30 | 已完成 | 新增规则 `docs/3-experiments/`；该目录此前未被 git 跟踪（仅有未跟踪文件），无需 `git rm --cached`；`git check-ignore` 确认生效 |
| OPS-003 | 运维 | `.gitignore` 随顶层 `docs/` 改名为 `design/` 同步忽略路径 | 2026-09-30 12:48 | 2026-09-30 12:55 | 已完成 | `docs/_build/` → `design/_build/`；`docs/4-experiments/` → `design/4-experiments/`；`git check-ignore` 确认 `design/4-experiments/` 仍被忽略、`design/3-plans/` 不被忽略 |
| OPS-004 | 运维 | 将 `design/4-experiments/` 移到仓库根目录并改名为 `experiments/` | 2026-09-30 14:19 | 2026-09-30 14:22 | 已完成 | 目录仍整目录 gitignore；同步 AGENTS.md、tests/eval、实施方案现行路径；历史 task-list 条目不改写 |

## 统计摘要

| 分类 | 总数 | 已完成 | 待开发/待修复 | 完成率 |
| --- | --- | --- | --- | --- |
| 代码 Bug | 125 | 125 | 0 | 100% |
| 调整事项 | 13 | 12 | 1 | 92.3% |
| 检查事项 | 22 | 22 | 0 | 100% |
| 测试数据 | 47 | 47 | 0 | 100% |
| 文档维护 | 64 | 64 | 0 | 100% |
| 功能开发 | 17 | 15 | 2 | 88.2% |
| 配置运维 | 4 | 4 | 0 | 100% |
| **总计** | 292 | 289 | 3 | 99% |

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


## Basic Benchmark 全量提取复跑（--debug-visual，2026-09-23，批次 20260923-004）

应用户要求，使用当前正式 Skill（v0.6.3）对 Basic Benchmark 8 份 PDF 全量运行资产提取，启用 `--debug-visual --debug-captions`，`--preset robust`，`--layout-backend` 保持默认 `off`。结果保存于 `tests/results/20260923-004/`，运行脚本为批次目录内 `run_benchmark.sh`，basic-benchmark 目录保持只读。

### 结果汇总（明细见 `tests/results/20260923-004/run-status.tsv`）

| PDF | 退出码 | Figure | Table | 正式 PNG | Debug 叠加图 | 文本 (字节) |
| --- | --- | --- | --- | --- | --- | --- |
| 1706.03762v7-attention_is_all_you_need | 0 | 5 | 4 | 9 | 9 | 39,681 |
| 2509.17765v1-Qwen3-Omni Technical Report | 0 | 3 | 18 | 21 | 21 | 92,561 |
| 2607.24653v2-Kimi-K3 | 0 | 16 | 5 | 21 | 21 | 190,669 |
| DeepSeek_V41_Tech_Report | 0 | 12 | 5 | 17 | 17 | 162,862 |
| FunAudio-ASR | 0 | 4 | 8 | 12 | 12 | 49,538 |
| KearnsNevmyvakaHFTRiskBooks | 0 | 8 | 1 | 9 | 9 | 69,017 |
| gemini_v2_5_report | 0 | 16 | 15 | 31 | 31 | 219,693 |
| gpt-5-system-card | 0 | 31 | 26 | 57 | 57 | 132,374 |
| 合计 | 全部 0 | 95 | 82 | 177 | 177 | 约 1.05 MB |

### 与上次 debug 批次（20260907-002，v0.6.2）对比

- 6/8 份逐项一致（attention、Qwen3-Omni、Kimi-K3、FunAudio、Kearns、gpt-5-system-card）。
- `gemini_v2_5_report`：15 fig/12 tab/27 PNG → 16 fig/15 tab/31 PNG（v0.6.3 提取行为变化，多出 1 图 3 表）。
- DeepSeek 源文件已由 V4 更换为 V4.1（benchmark 输入集 2026-09 更新），两组数字不可直接对比。

### 验证记录

| 操作 | 结果 |
| --- | --- |
| 8 份 PDF 逐份退出码 | 全部 0。 |
| Debug 叠加图 | 177 张 `images/debug/*_debug_stages.png` + 配套 `stages_legend.txt`，批次总量约 84 MB；无零字节 PNG。 |
| 抽查 `Figure_1_p3_debug_stages.png`（attention） | 图内含 caption、文本块（Hot Pink）与 baseline/phase_a/phase_b/phase_d/final 五阶段边界框；legend 坐标齐全；1224×1584、5408 唯一色，渲染正常。 |

### 过程备注

- 首次运行时 `run_benchmark.sh` 中仓库根定位误写为 `../..`（应 为 `../../..`），相对路径失效并误建 `tests/tests/`；已修正脚本、删除误建目录后重跑成功，未影响 benchmark 只读目录。

## 补齐 Kimi-K3 与 DeepSeek V4.1 的 bootstrap 标注（2026-09-23）

用户确认要把换入 benchmark 的两份 PDF 加入 `tests/annotations/`。先核对来源：DEV-007 与 SCHEMA §6 写明现有 gt.json 是 agent bootstrap（annotator=`agent-bootstrap`、reviewer 空），坐标来自 2026-07-28 Layout 实验的 provisional GT，不是人工框。旧实验目录没有这两份新 PDF，不能把 V3.2/V4 的框改名搬过来。

### 操作

- 新增一次性脚本 `docs/3-experiments/20260923-bootstrap-gt/build_two.py`：只对这两份 PDF 跑 PyMuPDF4LLM Layout，再用实验脚本 `03_build_gt_and_eval.py` 的文本层题注扫描和邻近配对生成内容框。不读取正式提取链的 `final_bbox`。
- 写出 `tests/annotations/2607.24653v2-Kimi-K3/gt.json`（23 条，Table 2 p26 未配到内容框）和 `tests/annotations/DeepSeek_V41_Tech_Report/gt.json`（19 条，Figure 9 p34、Figure 12 p48 未配到）。`source=agent-bootstrap-from-layout-pair-provisional`，reviewer 仍为空。
- 将仍留在现用目录的 `tests/annotations/DeepSeek_V3_2/` 原样移到 `tests/annotations/archive/DeepSeek_V3_2/`，与已归档的 `DeepSeek_V4` 一样不再被单层 GT 发现。
- 更新 `tests/annotations/SCHEMA-20260731.md` §6 的数据状态。

### 结果

| 命令 | 结果 |
| --- | --- |
| `python3 docs/3-experiments/20260923-bootstrap-gt/build_two.py` | exit 0。Kimi-K3 Layout 21.44s、47 个 page chunk；DeepSeek V4.1 Layout 10.39s、51 个 page chunk。 |

这仍是自动粗标，不能当作人工真值或准确率依据。未配对的 3 条 `content_bboxes` 为空，待人工补全。

## DeepSeek Table 5 表下注释遗漏修复（2026-09-23）

用户指出004批次Table_5_p48_debug_stages.png的小瑕疵。核对原页文字与debug各阶段：autocrop后底边156.4pt，显式Note行在157.5–165.6pt，表格被标accepted但遗漏该行。后续Claude Code正文从188.6pt开始，不能一起带入。

- 新增贴近表底、同列、小字号的显式Note./Notes:/注:识别，可关联紧邻同字号续行；恢复尾注后保留3pt边距。对远距离、异栏、大字号和后续列表保持排除。
- 表后正文清理与验收共用尾注判别，避免恢复后又被裁掉或误报far_side_body。此为结构恢复，不修改原PDF，也不人工编辑PNG。
- 新增test_table_notes_20260923.py：原页Note范围、连续尾注与正文分离、远距/异栏负例，及真实导出状态/范围检查。前三项先运行失败，修复后3通过，真实导出随完整套件验证。
- 输出集中tests/results/20260923-005/；原004用户图片保持不变。compileall与四入口--help均exit0，help.log保存输出。

## 删除 bootstrap 标注（2026-09-23）

用户确认这套 annotation 没有正确性用途，要求删除。

这些 gt.json 是 agent bootstrap（Layout 粗配对，reviewer 为空），不是人工框；golden 与 pytest 都不读它们。`tests/eval/` 只在显式传入 `--gt-dir` 时才用，删除数据不影响现有测试。

已删除 `tests/annotations/` 下全部文档目录和 `archive/`（含 Attention、Qwen3-Omni、Kimi-K3、FunAudio、Gemini、GPT-5、Kearns、DeepSeek V4.1，以及归档的 DeepSeek_V3_2、DeepSeek_V4）。保留 `SCHEMA-20260731.md`，并改写 §6 说明数据已清空。`tests/eval/` 评测器代码未动。该目录本就在 `.gitignore` 中。

后续验证记录：
- 首次完整pytest：251 passed、1 failed、0 skipped，唯一Golden差异为DeepSeek。图片对比确认T5单行注释已完整；同时发现T4的多行注释混合字体平均字号差0.72pt，原0.5pt续行阈值仅保留第一行。未更新此中间基准。
- 新增T4原页回归先失败，续行字号容差调整为1pt（仍要求小字号起始、同列、紧邻行距和48pt总高度上限）。T4五行Note范围397.2–444.5pt，与后文分离；四个定向正反例全部通过。
- 最终8份重提取以3个独立文档进程并行执行，输出20260923-008，完整命令/输入哈希/退出码在run-status.json；完成后写入当前脚本指纹再运行Golden，避免复用旧代码产物。

最终Golden更新前逐项验收：
- DeepSeek Table 4 p35：底边393.7→447.5pt，恢复397.2–444.5pt的完整五行Note及3pt边距；混合字号与数学符号均保留，未带后文，目视Table_4_final.png通过。
- DeepSeek Table 5 p48：底边156.4→168.6pt，恢复157.5–165.6pt的Note及3pt边距；Claude Code列表从188.6pt开始，保持排除，目视Table_5_final.png通过。
- 8份全量重提取均exit0；仅上述2个PNG发生变化，其余175项图片哈希不变，比较记录在005/diffs.json。Golden仅作为变更检测器，按上述原因更新，不视为人工GT。

最终验证：`python3 tests/scripts/test_extraction_golden.py --update-golden` 8/8通过；`python3 -m pytest tests/scripts/ -q --basetemp=tests/results/20260923-005/pytest-final` **254 passed、0 failed、0 skipped（含Golden）**，日志pytest-final.log；compileall、四入口--help、git diff --check均通过。新增5项回归用例，保留用户既有task-list修改，未改输入PDF或覆盖用户提供的004图片。

## 删除空的 annotations 与 holdout 目录（2026-09-23）

用户询问这两个目录是否还有用处。核对结果：`tests/annotations/` 在删除 bootstrap gt.json 后只剩 `SCHEMA-20260731.md`；`tests/holdout/` 只有 README 和空的 `pdfs/`、`annotations/`、`results/`，从未放入 PDF 或标注。pytest 与正式提取都不读取它们。`tests/eval/` 仅在命令行显式传入 `--gt-dir` 时才找标注目录。两个路径都在 `.gitignore` 中。

已删除 `tests/annotations/` 与 `tests/holdout/`。`.gitignore` 中的对应条目保留，以免以后重建时误提交。AGENTS.md、README 和实施方案里仍把它们写成将来人工 GT / holdout 的存放位置，那些是计划说明，不是当前依赖。

## docs 目录重编号对应的 gitignore 与规则同步（2026-09-23）

用户将 docs 子目录重命名调整：`docs/2-plans/` → `docs/3-plans/`，`docs/3-experiments/` → `docs/4-experiments/`（193MB 实验产物随目录原样保留）。本次同步仓库规则引用：

| 文件 | 修改内容 |
| --- | --- |
| `.gitignore` | 忽略条目 `docs/3-experiments/` → `docs/4-experiments/`（其余忽略规则未动）。 |
| `AGENTS.md` 第 4 节 | 目录描述同步为 `docs/3-plans/`（计划类文档）与 `docs/4-experiments/`（实验产物，gitignore）；删除原 `docs/2-plans/`、`docs/3-experiments/` 条目。 |
| `AGENTS.md` 第 8 节 | 「一次性探索脚本与大体积产物」去处由 `docs/3-experiments/` 改指 `docs/4-experiments/`。 |
| `task-list.md` | 本节记录。 |

说明：task-list.md 历史条目中对 `docs/2-plans/`、`docs/3-experiments/` 的引用为当时事实记录，不改写；`docs/2-ref/`、`docs/1-archive/` 未触碰；目录移动本身为用户手动操作（git 中表现为旧路径删除 + 新路径未跟踪），未做 git add/commit。

### 验证记录

| 命令或操作 | 结果 |
| --- | --- |
| `git check-ignore -v docs/4-experiments/ tests/results/ tests/annotations/ tests/holdout/` | 四条均命中 .gitignore 对应行。 |
| `git check-ignore docs/3-plans/` | exit 1（未被忽略，可提交，符合预期）。 |
| `grep "docs/2-plans\|docs/3-experiments" AGENTS.md .gitignore README.md` | 除历史重编号说明外无活引用残留。 |
| `git status --short` | `docs/4-experiments/` 已从未跟踪列表消失；仅余用户既有修改与 `docs/3-plans/` 待提交。 |

## .gitignore 全面复核（2026-09-23）

对本地目录结构与 .gitignore 逐项核对（顶层、tests/、docs/、skills/、old-version/，含大文件扫描与已跟踪文件冲突检查）。

| 检查项 | 结论 |
| --- | --- |
| 已跟踪文件命中 ignore 模式（`git ls-files -i -c`） | 空，无冲突。 |
| 未跟踪未忽略文件 | 仅 `docs/3-plans/` 两份 md 与 `tests/scripts/test_table_notes_20260923.py`，均为应提交内容，无需新增忽略。 |
| `tests/annotations/`、`tests/holdout/` 条目 | 目录当前不存在且从未被 git 跟踪；按 AGENTS.md 规划（人工 GT bootstrap、冻结 holdout）属将来建了就不该入库的内容，条目作前瞻性保护，**保留**。 |
| `docs/_build/`、`node_modules/` 条目 | 目录不存在，通用防御性条目，保留。 |
| `.DS_Store`（skills/、old-version/ 等多处） | 已被 `**/.DS_Store` 全局覆盖，且无一被跟踪。 |
| `.agents/` | 空目录，与 `.claude/` 同类的本地 agent 配置路径；新增忽略条目 `.agents/` 防御。 |
| `package.json` / `package-lock.json` | 内容为空的 node 空壳文件，但**已被 git 跟踪**，gitignore 无法作用于已跟踪文件；是否 `git rm` 移除属用户决策，本轮不动。 |
| `docs/2-ref/` 三份大 PDF（>5MB） | 已跟踪的只读参考资料，按规则不动。 |
| `tests/basic-benchmark/` PDF | 回测输入集，按规则可提交、保持只读，无需忽略。 |

修改：`.gitignore` Editors/tools 区新增 `.agents/` 一行。验证：`git check-ignore` 与 `git status` 复核无异常。

## 子代理 D 几何/诊断 8 项缺陷修复（2026-09-28）

来源：子代理 D 对 skills 提取链路的 8 条核查结论（含 1 条 15f4e08 回归），全部经真实函数直调或端到端复现确认后修复。对应 BUG-083 ~ BUG-090。

### 修改清单

| 文件 | 修改内容 |
| --- | --- |
| `lib/idents.py` | `FIGURE_LINE_RE` label 改 `(?:Figures?\|Figs?\.?\|图表\|附图\|图)`、`TABLE_LINE_RE` 改 `(?:Tables?\|Tabs?\.?\|表)`，并更新 P1-08 注释说明复数支持的原因。 |
| `lib/layout_model.py` | `detect_columns()` 采样段落行宽；`candidate_gap = peak_sep - median(行宽)` 取代误用右页边距的旧式，附注释说明旧公式在对称布局下恒等于 栏间距-页边距。 |
| `lib/extract_figures.py` | 图路径验收门 `allow_low_ratio_keep=True`（15f4e08 写死）改为 `not polluted`；`detect_text_pollution` 提前到 `evaluate_refinement_acceptance` 之前（与表路径 extract_tables.py:798 的 table_like_refined 先算后评顺序同构）。 |
| `lib/direction.py` | `score_local_direction()` 无证据分支 `(dir, 0.5)` 改 `(dir, 0.0)`；`compute_global_anchor()` 对象收集按 `is_table` 分口径（图 'O' / 表 O+H+V），附口径一致性理由注释。 |
| `lib/caption_detection.py` | `_EXPLICIT_CAPTION_PREFIX_RE` 补可选子图尾巴（3a / 5-b / 6(c)，与 idents 主正则同套模式）；`is_likely_reference_context()` 补复数并列与「描述动词+that/how」两条正文句负向模式。 |
| `lib/quality.py` | `detect_truncation()` docstring 改为按优先级描述，与实现对齐（纯文档，实现未动）。 |

### 过程要点：③ 不能简单翻回 False

初版直接把 `allow_low_ratio_keep` 改回 `False` 后，4 个结构审查用例回归（Kimi F12 图内文字被切、Kimi F14 页眉混入、Kearns F7 子图标题被切）。经 git 基线对照（stash 本轮 6 个文件后 8 用例全绿）与逐项 bisect（回滚②无效、回滚④⑧无效、回滚③复绿）确认根因：15f4e08 除写死 True 外还放宽了回退链判据并重排后处理链（新增 `_trim_lingering_body_before_objects`），False 会误杀合理精裁框并落入被放宽的回退链选出的更差框。最终采用 `not polluted` 门控：污染框必拒（恢复防护）、干净图形框低比例保留（保持 benchmark 行为）。

### 验证记录

| 命令或操作 | 结果 |
| --- | --- |
| `python3 -m compileall -q lib/` | 通过。 |
| `tests/results/20260928-001/verify_fixes_20260928.py`（函数直调 34 项） | 全过：①复数标识符 14 例（含 S1/III/1a/(a)/A1 回归用例）；⑤显式题注与裸标签 12 例；⑥引用负向 5 例；②合成单元双栏/单栏判定与 column 标注 4 例；④方向让位逻辑 3 例。 |
| 合成 PDF 端到端（`synthetic_plural_refs.pdf`，`extract_pdf_assets.py --pdf … --out-dir …`） | figures=1（仅 `Figure_1_Architecture_of_the_proposed_model.png`，status=accepted）、tables=0，无 S3/S2 假资产；产物在 `tests/results/20260928-001/e2e_v2/`。 |
| ③ 门控直调（污染 8/8 wide_lines + height_ratio 0.19） | polluted 框 accepted=False（防护恢复）；干净框 accepted=True（后门设计意图）。 |
| 四入口 `--help`（extract_pdf_assets / pdf_to_markdown / process_pdf / summarize_pdf） | 全部 OK。 |
| `python3 -m pytest tests/scripts/ -q` | **254 passed, 0 failed**（golden 8 份全绿、结构审查全绿）。 |
| Golden 基准 | **无需更新**：最终版输出与现有基准（`tests/results/20260923-008/…/golden_index.json`，golden 查找逻辑取最新含基准批次且不校验指纹）在 8 份 benchmark 上完全一致；本轮行为差异只发生在 benchmark 未覆盖的场景（复数引用句、子图题注、双栏公式、污染框防护、方向哨兵、锚点口径）。中间曾出现 8 份 golden 红 + 4 结构红系初版 False 方案所致，已随门控方案修正消失。 |
| 清理 | bisect 中间批次 `tests/results/20260928-002 ~ -008` 已删除（无 golden_index.json，纯当日自动提取产物）；保留 `20260928-001`（本轮验证产物）与 `20260928-009`（最终代码指纹批次）；`20260928-cli` 非本轮产物未触碰。 |

未提交 git（用户未要求）；本轮 6 个代码文件的修改与用户既有未提交修改（extract_tables.py、table_refine.py 等）无文件重叠。

## 22 条审查缺陷全量修复（2026-09-28，BUG-091 ~ BUG-104）

来源：4 个子代理的审查结论合并为 22 条（用户已剔除 3 条站不住、1 条自认存疑）。本轮按「先核实、再修改、后回归」推进，**每条结论都独立复现或证伪后才动代码**。

### 核实与处置

| 分组 | 条目 | 处置 |
| --- | --- | --- |
| P0 | 1 图路径验收门被架空 | 已修（上一轮 BUG-085），复核在位 |
| P0 | 2 inventory 无视开关 | 已修（BUG-091），**并纠正并发版本引入的新缺陷** |
| P0 | 3 inventory payload 自相矛盾 | 已修（BUG-092） |
| P0 | 4 run_all 静默跳 84 例 | 已修（BUG-093），另加结构性闸门 |
| P1 | 5 A3 把 legacy rejected 改写成 accepted | 已修，补充真正打到晋升分支的回归（变异测试验证有效） |
| P1 | 6 双栏检测恒失效 | 已修（上一轮 BUG-084） |
| P1 | 7 「Figures 3 and 4」幻影 S3 资产 | 已修（上一轮 BUG-083） |
| P1 | 8 表格截图缺外框线 | 已修（BUG-094），原页横线坐标 + PNG 像素双重取证 |
| P1 | 9 figure/table 阈值不一致 | 已修（BUG-095） |
| P2 | 尾注阈值余量 / 顺序 / continue / caption 防护 | 已修（BUG-098、BUG-099） |
| P2 | direction.py 0.5 哨兵 | 已修（上一轮 BUG-086） |
| P2 | caption_detection 子图题注与正文句 | 已修（上一轮 BUG-087、BUG-088） |
| P2 | `_table_cells_beyond` 死代码 | 已修（BUG-102） |
| P2 | `--reuse-existing` 串档 | 已修（BUG-096） |
| P2 | argparse 缩写被 preset 覆盖 | 已修（BUG-097） |
| P2 | figure_post 页眉不对称 + 邻题注 | 已修（BUG-100、BUG-101） |
| P2 | quality.py 判据文档与实现不符 | 已修（上一轮 BUG-089） |
| 存疑 | 跨类型吞没无告警 | 用户复现不出「静默通过」，但我确认**主链确实无此守卫** → 补只读告警（BUG-103） |
| 存疑 | 线稿图吞进正文（y0=0.0） | 两次构造均不复现，**未改代码**；仅记录代码事实（主循环只收 `orient=='O'`）待后续定位 |
| 存疑 | `file: ""` | 结论不成立：代码用 `rel` 变量而非字面量，且 `pdf_to_markdown.py:172` 已有 `if not file_value: continue` 防护，空 file 语料 0 例 |

### 并发冲突处置

期间检测到另一进程在并发修改同一批文件（14:17-14:29），已按用户指示停掉并逐份审查其改动：

- **接受**：`expand_table_clip_to_border_rules`（get_drawings 实现优于我原写的像素扫描版，且已接入主链；宽 ≥55% 恰好排除 Kimi 那条 236pt 题注下划线）；run_all 补 6 套件；assess 计数同源；P1#9 阈值统一；尾注容差放宽。
- **纠正后接受**：assess 的 `ident.isdigit()` 范围过滤（会误杀 S1/3a，见 BUG-091）。
- **删除我自己的重复实现**：`expand_clip_to_rendered_outer_rule`（与并发版功能重复，留着就是新的死代码）；仅保留其中对像素扫描的纯提取 `_rendered_rule_rows()` 供 `expand_clip_to_rendered_horizontal_rule` 复用。
- **清理**：`tests/basic-benchmark/text/` 是并发进程写进只读 benchmark 目录的产物，违反 AGENTS.md 第 8 节，已删除，目录复原为 8 份 PDF。

### 关键取证

| 事项 | 取证方式 |
| --- | --- |
| 表格缺外框线 | 回原页 `get_drawings()` 取全部横线坐标，与导出 bbox 逐条比对：Kimi T5 顶线 106.16 vs 框 107.1；Qwen T6 底线 719.29 vs 框 715.7；T17 双线 419.68/420.10 vs 框 416.3。修复后 24 处 bbox 变化**逐条验证**新边 = 边外横线 + pad（Qwen T17 取最外侧那条 420.10 + 1.5 = 421.6）。 |
| T6/T17 告警清零是否掩盖问题 | 旧框实际把末行 `Fleurs-xx2zh` 等 9 个单元格（y1=717.4）切在框外 1.7pt 并排除底线 719.29——`object_truncation` 是真实告警。新框把整行与底线一并纳入，属真实修复。PNG 像素级确认底部出现贯穿全宽的 booktabs 双线（末 6 行暗占比 0.978/0.979）。 |
| 并入外框线会切脚注 | Qwen T6 底线下方 0.9pt 即脚注首行（`a These 19 languages…`）。`collect_text_lines` 只保留行的最大字号（7.3pt），上标 5.5pt 信息已丢失，无法可靠识别此类脚注——故不做脆弱的脚注启发式，改为「扩展不得切开文字行」的通用硬约束。 |
| P1#5 守卫有效性 | 临时把 `pipeline.py` 守卫改回旧行为，回归立即失败（`legacy rejected 被晋升为 accepted`），随后还原——确认测试能抓住该回归，而非恒真断言。 |
| run_all 闸门 | `find_unregistered_suites([])` 报出全部 17 个未登记套件；登记齐后返回空。 |

### golden 假绿陷阱（本轮额外发现并修复）

`--update-golden` 会把基准写进它自己刚提取的批次，而 `_find_golden_index` 取「最新含基准的批次」、`_find_existing_index` 取「最新含 index.json 的批次」——两者落到同一目录，此后**无论产物对不对比较都必然全绿**。本轮一度出现「278 passed」但实际是自比，已加 `golden_is_self_comparison()` 显式拦截，并将基准与产物分置 `20260928-024`（基准）/ `20260928-023`（产物）做真实跨批次对比。

### 验证记录

| 命令或操作 | 结果 |
| --- | --- |
| `python3 -m pytest tests/scripts/ -q -p no:randomly` | **278 passed、0 failed、0 skipped**（含 golden 9 例，跨批次非自比）。较修复前 254 例新增 24 例。 |
| `python3 tests/scripts/run_all.py` | 17 个套件，**278 通过 / 0 失败 / 0 跳过**，耗时 11.6s。 |
| `python3 -m compileall -q skills/pdf-markdown-summary/scripts` | exit 0。 |
| 四入口 `--help`（extract_pdf_assets / pdf_to_markdown / process_pdf / summarize_pdf） | 4/4 exit 0。 |
| benchmark 8 份全量重提取（批次 `20260928-023`） | 8/8 exit 0，177 张 PNG。 |
| 014 与 023 两次**独立进程**提取互比 | 177 项资产 0 差异 → 输出可复现。 |
| 与修复前基准（20260923-008）逐项比对 | bbox 差异 24 项（全部为外框线并入，已逐条验算）、PNG 差异 24 项、status 变化 2 项（T6/T17 review_required→accepted）、告警变化 2 项（清零）。**无资产增删。** |
| 新增回归 `tests/scripts/test_bugfix_20260928.py` | 24 例，覆盖 P0#2/#3/#4、P1#5/#8/#9、P2 尾注三项、reuse 串档、argparse 缩写、页眉对称、邻题注、跨类型告警、golden 自比。其中 1 例经变异测试验证可抓回归；替换了并发版中带恒真断言与废弃构造过程的用例。 |

未提交 git（用户未要求）。`tests/results/` 下 20260928-001 ~ -024 各批次均为本轮及并发进程的提取产物，其中 `-023`（产物）与 `-024`（基准）需保留，其余可由用户决定清理。

## Basic Benchmark 当前代码与 visual-debug 独立复查（2026-09-28）

- 操作范围：只读取 8 份 `tests/basic-benchmark/*.pdf`、正式 Skill 脚本、`20260923-008` 与 `20260928-021/022/023/024` 测试批次；未修改 benchmark 输入、正式 Skill 代码、旧版归档和只读参考目录。审查报告写入 `tests/results/20260928-020/visual-debug-review-20260928.md`，复现脚本及数值证据同目录。前期逐一查看 8 份 PDF 共 177 项的 contact sheet，并对疑点回看原 PDF 页与最终截图。
- 并行修复核对：当前 `20260928-023` 八份产物与正式 Skill 脚本的 SHA256 指纹同为 `3fabeae8adbf5958642389559d01c11300a8fcf1f5b203a68459b223d5fea2bb`；此前 `--no-figures --no-tables` 仍补漏的问题已修。并行代理新增边框恢复与本地基准分批校验，不能将旧的 7 个 golden 变化失败视为当前测试结论。
- 仍需处理的视觉/业务问题：P1 Qwen Table 6 p10、Table 17 p17 的 a/b/c 表下注释未进入截图，状态却为 accepted（文本层仍保留脚注）；P2 Kimi Figure 2 p3 接收运行页眉；P2 Kimi Table 5 p32 因下方 Figure 13 标签误报 `table_band_open`；P2 Attention Figure 4 p14 图底仍截断，但已正确标为 review_required；P2 inventory 补漏同编号同题注跨页时文件名碰撞。详细坐标、代码位置和影响见上述报告。
- 验证命令 `python3 tests/results/20260928-020/verify_remaining.py`：以上 5 组问题在最新 `20260928-023` 产物上全部复现，退出码 0；`remaining-evidence.json` 已更新。`python3 -m compileall -q tests/results/20260928-020/verify_remaining.py`：通过。
- 验证命令 `python3 -m pytest tests/scripts/ -q -p no:randomly > tests/results/20260928-020/pytest-current.log 2>&1`：278 passed、0 failed、0 skipped（含跨批次 golden），5 条第三方 SWIG deprecation warning。此前 `pytest.log` 的 269 passed、7 failed 是更新本地 golden 前的中间结果。全绿仅说明当前回归用例通过，不代表图表内容已人工验收无误。


## 2026-09-28 后续接手：golden 独立批次与最终复验

- 接手此前未完成的 golden 自比修复。新增回归 `test_update_golden_writes_to_a_separate_batch`，先确认旧实现会将基准写回产物目录而失败，再修改 `run_golden_tests(update_golden=True)`：一次更新中的全部 PDF 使用同一个独立批次保存 `golden_index.json`。更新路径不覆盖旧基准，也不与当前 `index.json` 同目录。同步修正模块说明和错误提示。
- 本地独立基准写入 `tests/results/20260928-039/`；逐一确认 8 份 PDF 的基准批次均为 `20260928-039`，当前产物分布在 `20260928-034` 至 `-037`，无同目录自比。该目录仅含本地忽略的 golden 基准，不纳入 Git。
- 更新基准前以旧基准实际比较：8 份中 5 份无差异，3 份有已核实的修复差异：Attention Figure 4 底部恢复（y1 587.9→612.3）；Qwen Table 6/17 尾注恢复（y1 分别 719.7→774.0、420.3→473.0）；Kimi Figure 2 排除页眉（y0 20.9→47.9）、Table 5 消除 `table_band_open` 误告警，以及 Table 1 边界微调 0.6pt。资产身份集合未变；变化涉及的 PNG 尺寸/哈希随截图内容更新。上述均为本轮修复的预期行为变化，故更新本地检测基准。
- 修正此前遗留的验证陷阱：历史记录中的 278 全绿曾因同批自比而无效；本轮启用自比拦截后真实对比先得到 282 passed / 3 failed（仅上述三份 PDF 的陈旧基准差异），分批更新基准后最终全套通过。
- 处理只读 benchmark 的意外产物：此前误写入的两份 `text/` 文件已移出 `tests/basic-benchmark/`，转存至忽略目录 `tests/results/20260928-025/benchmark-accidental-text/`；复核 benchmark 目录仅有预期 8 份 PDF 和既有 `.DS_Store`，未删除或改写 PDF。

### 最终验证

| 命令或操作 | 结果 |
| --- | --- |
| `python3 -m pytest tests/scripts/ -q -p no:randomly` | **285 passed、0 failed、0 skipped**；含 8 份真实 golden 对比及自比保护；5 条第三方 SWIG deprecation warning。日志：`tests/results/20260928-038/pytest-full-final.log`。 |
| `python3 tests/scripts/test_extraction_golden.py --update-golden` | 8 份基准更新成功，写入独立批次 `20260928-039`。 |
| 更新批次检查 | 8/8 `golden_is_self_comparison=False`，每份产物和基准跨批次。 |
| `run_all.py --skip-p0 --skip-p1 --skip-regex --skip-golden`（设置 `PDF_SKILL_ALLOW_GOLDEN_SKIP=1`） | **253 通过、0 失败、1 跳过**；结构守卫接受显式排除。按定义该次不是全绿。 |
| 四入口 `--help` | `extract_pdf_assets.py`、`pdf_to_markdown.py`、`process_pdf.py`、`summarize_pdf.py` 均 exit 0。 |
| `python3 -m compileall -q skills/pdf-markdown-summary/scripts` | exit 0。 |
| `git diff --check` | 通过。 |
| benchmark 目录清点 | 8 份 PDF + `.DS_Store`；没有测试输出/临时文件。 |

未提交 git。工作区内其余并行修复、计划文档迁移和既有未提交变更均保留。

## 2026-09-28 复查收尾：修复审查发现的两个轻微问题（BUG-091/092）

对全部未提交修改做整体复查后发现的两个遗留问题，本轮修复：

- **BUG-091（文档不一致）**：`tests/scripts/run_all.py` 模块说明写「测试套件（共 16 个）」且编号清单缺第 17 项，与 `main()` 实际登记的 17 个套件不符（漏列 `test_bugfix_20260928.py`）。运行行为不受影响（守门用 append 清单），仅修正文档：改为「共 17 个」并补第 17 行。
- **BUG-092（无效防御）**：`skills/pdf-markdown-summary/scripts/lib/table_refine.py` 的 `expand_table_clip_to_border_rules` 末行 `return (fitz.Rect(...) & page_rect) or clip`——PyMuPDF 1.28 实测空交集 `Rect`（x0>=x1）布尔值仍为 `True`，`or clip` 兜底永不生效，退化交集时会把畸形框直接返回。改为显式 `is_empty` 判断，退化时回退原 clip。真实几何下该分支不可达（golden 对比证明零输出变化），属防御修正。
- 新增回归 `tests/scripts/test_bugfix_20260928.py::test_border_rules_fallback_to_clip_on_degenerate_intersection`：Mock 页外 clip + 贴近横线构造退化交集。已用旧表达式独立验证：旧写法返回 `Rect(100,800,400,792)`（y0>y1），新代码返回原 clip，测试确实锁定修复。

### 验证

| 命令或操作 | 结果 |
| --- | --- |
| `python3 -m compileall -q skills/pdf-markdown-summary/scripts tests/scripts` | exit 0。 |
| `python3 -m pytest tests/scripts/ -q` | **286 passed、0 failed、0 skipped**（285 既有 + 1 新增）。 |
| golden 跨批次对比 | `table_refine.py` 改动使代码指纹变化，8 份 PDF 自动重提取至 `tests/results/20260928-040/`，与既有基准批次 `20260928-039` 逐项对比全部通过 → 修复零输出变化。 |
| 四入口 `--help` | 4/4 exit 0。 |

未提交 git。`tests/results/20260928-040/` 为本轮指纹触发的重提取产物批次，golden 基准仍在 `20260928-039/`，无需更新。

## 2026-09-28 补齐外框线切字（BUG-094 残余）

复查确认 BUG-094 的「不准切字、也不丢外框线」只覆盖行首落在新增带里的文字。补上两类缺口：

- 字框已经跨过原 clip 边，或短脚注压住横线时，收到行首会切字或把横线排除。短行改为整行纳入；相邻短脚注 bbox 重叠时沿短行走到外侧。
- 与横线重叠的高正文不整段吞入，这一侧放弃扩展。
- 线稿图 `y0=0.0` 吞正文仍无可以稳定复现的构造，未改图路径。

### 验证

| 命令或操作 | 结果 |
| --- | --- |
| 新增 5 个回归（先失败后修复） | 旧实现 4 失败（跨边切字、压线丢边、高正文被扩进、顶边丢线）；重叠短脚注补丁前再失败 1 项。 |
| `python3 -m pytest tests/scripts/test_bugfix_20260928.py tests/scripts/test_table_notes_20260923.py -q` | 40 passed。 |
| Qwen T6/T17、Kimi T5 原页带文字行直调 | 底/顶线仍在框内，补边不落在文字行内部。 |
| `python3 -m pytest tests/scripts/ -q -p no:randomly` | **291 passed、0 failed、0 skipped**（286 既有 + 5 新增）。golden 对比通过，基准无需更新。 |
| `python3 -m compileall -q skills/pdf-markdown-summary/scripts` | exit 0。 |
| 四入口 `--help` | 4/4 exit 0。 |

未提交 git。

## 2026-09-28 V0.6.4 批次 045 visual-debug 全量复查

- 复查范围：`tests/results/20260928-045/` 的 8 份 PDF、177 个资产、177 张 debug 阶段图、177 份 legend 和最终 PNG；逐项查看 final 红框是否切内容、吞正文、漏边线或混入相邻图表。
- 为便于全量目视检查，在忽略目录 `tests/results/20260928-045/_visual-review/` 生成 21 张联系表：101 个调参信号项与 76 个无信号项全部覆盖。联系表仅为本地审查产物，不修改正式 Skill 或 benchmark。
- 目视结论：177 个 final 框均完整覆盖目标资产；没有发现切表头/末行/脚注、截断图形、混入题注后正文或跨图表吞并。7 个 `fallback_to_baseline` 均为合理保守回退。
- 重点复查最低高度比：Qwen Table 3（0.14）和 GPT-5 System Card Table 18（0.13）均完整；0.13 项实际属于 GPT-5 Table 18，并非 Gemini。另复查 Kimi Table 5（0.27）、FunAudio Figure 3（0.26）、FunAudio Table 1（0.25），均无截断。
- `index.json` 复核：8 份共 177 项，全部 `status=accepted`、`review_required=false`、无 warnings。逐份计数均满足 `items == debug PNG == legend`，总计 177/177/177。
- 日志复核：未发现 traceback、exception、fatal 或真实 error；正则命中的 `error` 均来自 `Word_Error_Rate` / `Health_error_rates` 文件名。
- 新发现一处分析报告问题：`analyze_debug_batch.py` 每份文档只打印 `flagged[:12]`，但没有输出截断提示。批次实际 flagged 为 **101**（GPT-5 34、DeepSeek 14、Kimi 12、Qwen 12、Gemini 10、FunAudio 9、Attention 5、Kearns 5），`_analyze.txt` 可见 FLAG 行只有 **77**。这不会影响提取结果，但会让人工审查误以为只需检查 77 项；本轮仅做检查取证，未改分析器代码。

### 验证记录

| 命令或操作 | 结果 |
| --- | --- |
| 独立解析 177 份 legend | 101 个有调参信号、76 个无信号；7 个 fallback，5 个最终高度比低于 0.30。 |
| 21 张联系表逐项目视 | 177/177 已看，未发现实际裁切或污染缺陷。 |
| `index.json` / debug PNG / legend 对账 | 8 份逐一相等，总计 177 / 177 / 177。 |
| 日志关键字复核 | 0 个真实异常；命中项均为文件名中的 `error`。 |

## 2026-09-28 版本号提升 0.6.3 → 0.6.4

- 版本号更新三处：`README.md`（当前版本行）、`skills/pdf-markdown-summary/SKILL.md`（Current package version）、`skills/pdf-markdown-summary/scripts/__init__.py`（`__version__`）。全仓无其他 0.6.3 残留引用；`__version__` 无调用方（不影响提取行为与 golden 基准）。
- 验证：`compileall` 通过；四入口 `--help` 4/4 正常；全量 pytest 最终 **291 passed、0 failed、0 skipped**（含 8 份 PDF 跨批次 golden 对比，指纹复用批次 `20260928-043/044`，基准仍在 `20260928-039`，未更新）。

### 过程异常：并发工作流干扰一次测试运行（非本仓缺陷）

- 版本提升后的第一次 pytest 出现 **2 failed / 284 passed**。排查确认根因为**另一并发工作流在同一工作区改代码**：`table_refine.py` 于 18:19 被外部修改（重写 `expand_table_clip_to_border_rules`，新增 `_overlapping_text_lines`、`_edge_inside_any`、`_short_line_past_rule`、`_extend_through_short_lines`、`_clear_bottom_edge`、`_clear_top_edge`、`_fit_border_edge_around_text` 等辅助函数，本轮 BUG-092 的 `is_empty` 修复被保留），恰逢 FunAudio-ASR 提取子进程运行中，撞上文件改写导致提取失败，产生批次 `20260928-041`（7 份指纹 + FunAudio 空目录）。
- 后续两次运行均通过；并发方还新增了 5 个测试（`test_bugfix_20260928.py` 内，总测试数 286→291），并产生批次 `20260928-042`（中间指纹 be8aa92b，非当前代码）、`20260928-043/044`（当前指纹 7d007d4e，8 份完整）。
- 结论：版本提升与 BUG-091/092 修复本身无回归；`041`/`042` 为并发干扰产生的废批次（无 golden，不影响基准），可由用户决定清理；并发工作流的改动（外框线逻辑重写 + 5 个新测试）在最终 291 全绿中已一并验证通过。

未提交 git。

## 2026-09-28 全量文档检查与更新（对齐 0.6.4 当前状态）

逐份检查了全部活跃文档（README.md、AGENTS.md、SKILL.md、references/×3、docs/3-plans/×2、tests/eval/README、task-list.md），`docs/2-ref/` 按只读约束未动，`docs/1-archive/`、`docs/4-experiments/` 为归档/产物目录不适用。更新如下：

- **README.md**（中英对称共 4 处）：表格精修能力清单补「底线外显式尾注恢复、外框线并入」；回归基线 249 passed（2026-09-23 复验）→ **291 passed、0 failed、0 skipped（2026-09-28 复验）**，并注明 golden 基准独立批次、杜绝同批自比。
- **skills/pdf-markdown-summary/SKILL.md**：Extraction Capabilities 的 Table refinement 清单同步补 table-note recovery 与 border-rule inclusion。
- **references/cli-options.md**：`--reuse-existing` 补充归属校验说明（index.json 记录源 PDF 名 + sha256 内容哈希，不匹配即拒绝复用 exit 1）；对照 argparse 实测 67 个提取器旗标全部在文档内（仅 --help 不列）。
- **docs/3-plans/basic结构定位修复计划-20260922.md**：头部补「已完成（2026-09-23）」状态标记。
- **docs/3-plans/extraction-status-inventory-20260907.md**：追加「2026-09-28 更新」节——cross_kind_overlap 告警、对账范围与用户开关同口径（kinds/min-max/非数字编号）、计数与补裁后对账同源、补裁文件名带页码、A3 状态只降不升。
- **tests/eval/README-20260731.md**：两处旧路径 `docs/3-experiments/` 更新为重编号后的 `docs/4-experiments/`（其一为可执行命令示例，原路径已失效），并注明重编号历史。

未改动项及理由：`docs/PDF图表提取架构根因复盘…-20260721.md` 与 `docs/PDF图表提取技术迭代实施方案-20260731.md` 为时点性分析/方案文档且被 tests/eval README 引用为口径依据，内容按历史原样保留（未迁移、未改写）；`references/pdf-summary.md`、`pdf-to-markdown.md` 为工作流级文档，无过时内容；AGENTS.md 本轮已随目录重编号更新过。

验证：全仓 grep 无「249 passed」残留、活跃文档无失效 `docs/3-experiments` 引用（AGENTS.md 与 eval README 中的两处为刻意保留的重编号说明）；`python3 -m pytest tests/scripts/ -q` **291 passed、0 failed、0 skipped**（本轮仅改 .md，指纹未变，复用现有批次）。

未提交 git。

## 2026-09-28 复跑四类缺陷（Alexa / PARADISE / SASSI）

对照参考 PDF 复跑，修四处会静默放行的问题：

- 正文句 `Table 4 presents the results.... The six factors...` 不再当题注。SASSI 假表 4 消失，真题注落到第 35 页。
- 短粗体里的页码、公式、单字母、正文字号表头不再变成 Markdown 标题。编号加标题的真章节保留。
- 双栏页上，题注在单栏且没有通栏横线时，表框收到该栏。Alexa 表 2 宽从约 560pt 收到 250pt；PARADISE 表 1/5/6 不再横贯右栏。通栏横线仍保持整页宽。
- 未插入 Markdown 的 review/rejected 资产写入 `conversion_report.json` 的 `assets.omitted`，顶层 status 改为 `review`，不再报成干净的 `ready`。

复跑目录 `tests/results/20260928-041/`。PARADISE 表 3/4 仍是通栏且 `object_truncation`；图 5 与表 6 重叠仍为 rejected。这些裁切还不对，但不再被报告成无告警成功。

### 验证

| 命令或操作 | 结果 |
| --- | --- |
| 新增回归先失败后修复 | 正文句引用、假标题、单栏收窄、omitted 报告 4 项均先失败。 |
| `python3 -m pytest tests/scripts/ -q -p no:randomly` | **295 passed、0 failed、0 skipped**。golden 通过，基准未改。 |
| 三份参考 PDF `--preset robust` 重跑 | 报告均为 `review` 并列出 omitted；SASSI 不再导出说明文句的假表 4。 |
| compileall 与四入口 `--help` | 通过。 |

未提交 git。

## 2026-09-28 跨类型重叠覆盖 accepted_with_margin

`mark_cross_kind_overlaps` 只把 `accepted` 降为 `review_required`。`accepted_with_margin` 只加告警和 `review_required` 标志，状态不变；`markdown_insertable` 对有状态的记录只看状态，重叠资产仍会插入 Markdown。现与 `accepted` 一并降级。回归先失败后通过：`test_cross_kind_overlap_marked`。

未提交 git。

## 2026-09-29 外部评审 4 条意见的逐条核实

评审引用的行号（`caption_detection.py:183-189`、`direction.py:353-359`、`extract_pdf_assets.py:543-548`、`assess.py:525-530`）与 **V0.6.3（15f4e08）** 逐行吻合，即评审基于 V0.6.3 而非 V0.6.4。逐条在合成 PDF 上实测（`/tmp` 内临时用例，未入库）：

| 评审条目 | 结论 | 证据 |
| --- | --- | --- |
| P1 句点题注被判正文 | **复现，已修（BUG-107）** | `Figure 1. The proposed architecture of our method.` 修复前输出目录 0 PNG（提取与补裁同时丢失），修复后产出该图 |
| P2 双栏邻题注认领表格行 | **复现，已修（BUG-108）** | 直调 `score_local_direction`：无邻题注 `above` 0.95，含左栏题注 `below` 0.00 |
| P2 `--no-figures/--no-tables` 仍产出 gap PNG | **不复现，V0.6.4 已修** | `--no-figures --no-tables` 输出 0 个 PNG；同一 PDF 不禁用时产出 `Figure_1_Sample_plot.png` + `Table_1_Sample_results.png`（反证过滤生效而非整体失效）。V0.6.3 的 `finalize_caption_inventory` 无 `kinds` 参数，V0.6.4 已加并在 `extract_pdf_assets.py` 接通 |
| P2 gap 文件名缺页码 | **不复现，V0.6.4 已修** | 合成两页重复 `Figure 1: Sample plot` → 文件名 `Figure_1_p2_inventory_gap_Figure_1_Sample_plot.png` 带页码，无覆盖 |

自查同根因（评审未提）：`clip_limit.py` / `figure_post.py` 的纵向边界同样未过滤跨栏题注，见 BUG-109。

### 验证

| 命令或操作 | 结果 |
| --- | --- |
| 新增回归先失败后修复 | 3 个新用例在回退到 HEAD 源码时全部失败（`跨栏题注不应改变本栏方向`、`Figure 1. The proposed architecture of our method.`、`test_cross_column_caption_does_not_limit_vertical_bounds`），恢复后全绿；文件 sha256 前后一致 |
| `python3 tests/scripts/run_all.py` | **302 通过、0 失败、0 跳过**；代码指纹变更触发基准 8 份重新提取（结构审查 143s、表格尾注 51s），golden 9/9 通过 → 四份修复对真实基准输出零影响 |
| 基准 PDF 扫描「Figure/Table N. The\|This」 | 命中 0 行，说明该类题注不在基准覆盖范围（合成用例是唯一防线） |

未提交 git。

## 2026-09-29 第二轮外部评审 5 条意见的逐条核实

| 评审条目 | 结论 | 证据 |
| --- | --- | --- |
| P1 golden 基准与产物同批自比 | **不复现，V0.6.4 已修（BUG-104）** | 评审行号 810-813 对应 V0.6.3 的 `golden_write_path = images_dir / "golden_index.json"`（同目录）；当前树已改为 `update_batch_dir/stem/images/`（独立批次）+ `golden_is_self_comparison` 显式拒绝同批比较 + 回归测试 `test_update_golden_writes_to_a_separate_batch`。实测当前 golden：index 在 20260929-013、基准在 20260928-039，非自比；`update_batch_dir` 序号恒大于任何被比较批次，碰撞不可能。历史 6 个 SELF-RISK 批次（0810/0922/0923）为旧遗留，非当前代码产物 |
| P1 等距两图被合并（pairing.py:219-225） | **复现，已修（BUG-110）** | 直调 `pair_page`：pairs=1 且 content_bboxes 含两框、orphan_caps=1；修复后 2 对各 1 框零孤儿，multi-panel 合并行为保留 |
| P2 Layout 题注回退不筛类型（pairing.py:298-301） | **复现，已修（BUG-111）** | 直调 `pair_layout_regions`：p2 的 table pair 挂 figure-caption `[50,410,300,430]`；修复后该内容成孤儿、通用 caption 不受影响 |
| P2 IoU 贪心压制匹配数量（pipeline.py:215-222） | **复现，已修（BUG-112）** | 直调 `_match_records_to_candidates`：2 候选 2 记录只匹配 1 条；修复后最大基数 2 条，同框折叠 1 条、链式 3×3 全配、跨页互不冲突 |
| P2 对象分支屏蔽覆盖率（quality.py:184-190） | **复现，已修（BUG-113）** | 直调 `detect_truncation`：对象全保留 + 候选覆盖 0.820<0.85 时返回未截断；修复后报截断且 reason 带 `objects kept` |

### 验证

| 命令或操作 | 结果 |
| --- | --- |
| 新增回归先失败后修复 | 4 个新用例在回退到 HEAD 源码时全部失败，恢复后全绿，文件 sha256 前后一致 |
| `python3 tests/scripts/run_all.py` | **306 通过、0 失败、0 跳过**；指纹变更触发基准重新提取（20260929-013~016 均为当前指纹），golden 9/9 通过 → 4 份修复对真实基准输出零影响 |
| compileall 与 pytest A2/A3 套件 | 通过 |

未提交 git。

## 2026-09-29 第三轮外部评审意见的逐条核实

评审标题称「提交后的 golden 测试仍按已移除的目录和样本查找 PDF，无法完成回归验证；启用 Layout 后端时，配对和精修还可能把不同图表绑定到同一截图」，正文列出 **8 条**（P1 4 条 + P2 4 条）。逐条结论：

| 评审条目 | 结论 | 证据 |
| --- | --- | --- |
| P1 多框分组吞并相邻独立图（pairing.py:143-152） | **复现，已修（BUG-114）** | 直调 `pair_layout_regions`：上下两图（gap 20pt）+ 两图各有自己的题注（其中 fig2 的题注只在 Layout 池）→ 修复前 pairs=1 且 `content_bboxes` 含两框（fig2 被吞、其题注被弃）；修复后 pairs=1 只含 fig1 框、fig2 记为孤儿内容 |
| P1 匹配不看图注身份（pipeline.py:178-188） | **复现，已修（BUG-115）** | 直调 `_match_records_to_candidates`：两记录图注框与各自候选完全一致，内容框漂移后 IoU 倒挂 → 修复前 ident=1 绑到 [72,320,520,520]（图2 的框，即用对方候选重渲染）；修复后 ident=1→[72,100,520,300]、ident=2→[72,320,520,520] |
| P1 golden 测试仍查 `回测组1/回测组2`（test_extraction_golden.py:647-649） | **不复现** | 当前树与 V0.6.3/V0.6.4 两版该文件 `grep -c 回测组` 均为 **0**；`_resolve_golden_paths` 为 `pdf_path = TESTS_DIR / spec.pdf_file`（`TESTS_DIR = tests/basic-benchmark`，扁平）；`tests/basic-benchmark/` 下**没有任何子目录**（`ls -d */` 无匹配），且 `test_golden_baseline_coverage` 先 `TESTS_DIR.glob("*.pdf")`（扁平优先、子目录布局仅作兼容兜底），8 份 PDF 全部解析成功、9/9 通过 |
| P1 golden 样本清单仍在列已删除的 `DeepSeek_V3_2.pdf`（:237-244） | **不复现** | `grep -rn "DeepSeek_V3_2" tests/scripts/` 命中 **0**（仅历史产物 `tests/results/**` 的旧文件名里出现）；`CORE_REGRESSION_SET` 实测 **8 条**，与 `tests/basic-benchmark/*.pdf` 的 8 份一一对应，已含 `2607.24653v2-Kimi-K3.pdf`；覆盖断言「扫描到的 PDF 必须全部纳入清单」通过（0 未覆盖） |
| P2 `--update-golden` 写到 benchmark 目录（:789-791） | **不复现** | 基准写入路径为 `update_batch_dir / stem / "images" / "golden_index.json"`，`update_batch_dir = _compute_batch_dir()`（`tests/results/<yyyymmdd-NNN>/`，序号取当日最大值 +1）；全文件 grep 无任何向 `tests/basic-benchmark/` 写入的路径。实测本轮基准批次 20260928-039、被比较批次 20260929-019，`golden_is_self_comparison=False`，8 份基准全部落在 `tests/results/` 下 |
| P2 A3 不遵守 `--no-refine`（extract_pdf_assets.py:494-500） | **复现（结构性），已修（BUG-116）** | HEAD 源码 + `--no-refine 4`：table 4 仍进入匹配、生成 `candidate_bbox`/`refined_bbox`（仅被质量门拒）；`--no-refine 2`：ident 2 同样进入匹配。即排除列表对 A3 完全不可见，覆盖与否取决于几何运气。修复后 `--no-refine 2` 下 matched 12→10、figure 2 与 table 2 两条 `skipped`、最终框保持 legacy |
| P2 未收集 golden 时会话不判失败（conftest.py:37-42） | **复现，已修（BUG-117）** | `pytest tests/scripts --ignore=tests/scripts/test_extraction_golden.py -q` 在 HEAD 版 conftest 下 **exit 0**（golden 一条没跑）；修复后 exit 1 并打印「未收集到任何 golden 用例」。逐文件套件调用（run_all.py 用法）与豁免变量路径均实测不受影响 |
| P2 按页回退 Layout 题注区域（pairing.py:272-284） | **不复现** | 当前树回退分支在 `pair_layout_regions`（:334-350）：外部候选非空但本页为空时 `if not caps: caps = _filter_layout_captions_by_kind(page_region.caption_regions, kind)`（HEAD 同位置亦有 `caps = list(page_region.caption_regions)`）；直调验证：外部候选只覆盖第 2 页时，第 1 页仍由 Layout 题注配对成功（pairs=1），未出现空 caps。另：评审所指 272-284 行在当前树是 `_region_to_candidate` 辅助函数，另一处 P2 说明与本条重复 |

### 验证

| 命令或操作 | 结果 |
| --- | --- |
| 新增回归先失败后修复 | 4 个 A2/A3 新用例 + 2 个闸门新用例在回退到 HEAD 源码/conftest 时全部失败，恢复后全绿，文件 sha256 前后一致（`pairing.py`/`pipeline.py`/`extract_pdf_assets.py`/`conftest.py` 逐对校验） |
| `python3 tests/scripts/run_all.py` | **313 通过、0 失败、0 跳过** |
| golden 真伪核查 | 8 份 PDF 的产物批次（20260929-017~020）指纹与当前代码 `_compute_code_fingerprint()` 全部 MATCH（真实重新提取），基准批次 20260928-039 ≠ 被比较批次 → 非自比，9/9 通过 |
| `--no-refine` 端到端 | FunAudio-ASR + `--layout-backend pymupdf4llm`：修复前 `--no-refine 2` 的 A3 报告含 ident 2 的 candidate/refined；修复后该 id 变 `skipped: id listed in --no-refine`，matched 12→10 |
| 闸门端到端 | 目录级选择 + `--ignore` golden：HEAD exit 0 → 修复后 exit 1；逐文件套件调用 exit 0；`PDF_SKILL_ALLOW_GOLDEN_SKIP=1` exit 0（仅 WARNING） |

未提交 git。

## 2026-09-29 未提交代码全量审查与 run_end 统计修复

对全部未提交改动（24 个已修改文件 + 1 个未跟踪文件，约 1400 行新增）做了一轮完整审查。总体可提交，发现 1 个中等问题并已修复：

| 条目 | 结论 | 说明 |
| --- | --- | --- |
| `extract_pdf_assets.py:590-591` `run_end` 统计误用 `getattr(r, "type")` | **已修** | `AttachmentRecord` 只有 `kind` 字段，`figures/tables` 统计永远为 0/0，合成带图 PDF 实测复现；改为 `getattr(r, "kind", "")`（该文件 :459-460 原本就用 `kind`） |
| 其余轻微项 | 未改，不阻塞提交 | `quality.py` docstring 滞后、`caption_detection.py:263` 双口径并存、`pairing.py` or/and 优先级依赖、`pipeline.py` 死变量、`test_caption_anchor_quality.py:1582` 未登记 main()、`references/pdf-to-markdown.md` 未同步 `status: "review"` 契约 |

新增回归 `test_run_end_counts_match_index_json`（带位图 PDF → `run_end` details 与 `index.json` 的 figures/tables 对账），并登记进 `main()` 清单。

### 验证

| 命令或操作 | 结果 |
| --- | --- |
| 回归先失败后修复 | 新用例在还原旧代码（`kind`→`type`）时失败，恢复后通过 |
| `python3.13 -m pytest tests/scripts/ -q` | **315 通过、0 失败、0 跳过**，golden 实际执行 |
| `python3.13 -m compileall` skills + tests/scripts | 通过 |
| 四入口脚本 `--help` | 全部正常 |

未提交 git。

## 2026-09-29 未提交代码二次全量审查（只读取证）

对当前 24 个已修改文件和 1 个未跟踪测试文件重新审查。上一节“总体可提交”的结论被新的可复现反例推翻，当前仍有 5 项待修复：

| 优先级 | 问题 | 复现与影响 |
| --- | --- | --- |
| P1 | A3 最大匹配会把已由图注身份确认的记录挤到另一候选框 | `pipeline.py::_try_augment` 的增广路径只按当前记录边排序，后处理记录可踢走 confirmed 边；合成 2×2 输入实测 R0 由 C0 串到 C1，A3 会按错框重渲染。算法只保最大基数，也未实现注释声称的同基数最大 IoU。 |
| P2 | `Figure 1. Our proposed ...` 类真题注静默漏提 | `caption_detection.py` 把 `our` 列为正文接续词；函数级实测 explicit/anchor 均为 false，合成 PDF 端到端运行 exit 0 但 index 0 项、0 PNG，inventory 也无法补漏。 |
| P2 | 无边框通栏表可被误裁成半栏 | `limit_table_clip_to_caption_column` 把右半页表格单元文字当成“邻栏正文”；合成输入中全宽框 `x=30..570` 被收到 `x=30..292`，右侧两行数据全部落在框外。`extract_tables.py` 同时收窄 base/search，后续恢复仍以已收窄 base 为上限。 |
| P2 | 中文章节标题被整类降为正文 | `looks_like_structural_heading` 的编号标题和字母数判定均限定 ASCII；字号 18、粗体的“绪论”“第一章 绪论”“1 绪论”“研究方法”均返回 false，Markdown 丢失层级。 |
| P3 | visual-debug 报告仍会漏列和误报 | 批次 `20260928-045` 当前规则计算 98 个 flagged，但 `flagged[:12]` 只打印 76 行且无截断提示；`fallback_to_baseline` 只比高度和 y 边界，对 x 已大幅收窄的框仍误报为回退原框。 |

### 验证

| 命令或操作 | 结果 |
| --- | --- |
| `python3 -m pytest tests/scripts/ -q` | **315 passed、0 failed、0 skipped**，golden 已收集并执行。 |
| `python3 -m pytest tests/scripts/test_extraction_golden.py -q` | **9 passed**。 |
| `python3 tests/scripts/run_all.py` | **315 通过、0 失败、0 跳过**。 |
| `python3 -m compileall -q skills/pdf-markdown-summary/scripts tests/scripts` | 通过。 |
| 四入口脚本 `--help` | `extract_pdf_assets.py`、`pdf_to_markdown.py`、`process_pdf.py`、`summarize_pdf.py` 全部 exit 0。 |
| `git diff --check` | 通过。 |

本轮除按仓库规则更新本台账外，未修改正式 Skill 代码和测试。未提交 git。

## 2026-09-29 第四轮外部评审 5 条意见修复（P1×1 + P2×3 + P3×1）

| 评审条目 | 结论 | 修复要点 |
| --- | --- | --- |
| P1 A3 增广匹配挤走 confirmed 题注绑定（pipeline.py:268） | **复现，已修** | `_match_records_to_candidates` 的 Kuhn 增广换成位掩码 DP 精确求解（`_optimal_assignment`，按 (page, kind) 分组，m≤12 精确、>12 退贪心），目标字典序为 **(身份边数, 匹配基数, IoU 总和)**——confirmed 边不可被普通几何边挤走，且真正实现「最大基数下最大总 IoU」；同时删除匹配落盘前的死循环残留 |
| P2 `Our` 开头题注静默消失（caption_detection.py:192） | **复现，已修** | `_PERIOD_BODY_OPENER_RE` 移除 `our`（接续词表抽成共享常量 `_PERIOD_BODY_OPENER_ALT`）；新增 `_PERIOD_TAIL_CROSS_REF_RE` 护栏：`our` 开头但 tail 交叉引用其它编号对象（`...in Section 3`）仍判正文；:263 旧模式与之一并统一口径，顺带清理 `this/the/in` 死分支 |
| P2 无边框通栏表被切成半栏（table_refine.py:355-400） | **复现，已修** | 新增 `_other_side_line_continues_table`：另一侧文字行须确认不是通栏表跨栏延续行（非整句 + 与表内行 y 居中 ≤3.5pt 对齐）才计入收窄证据；收窄时把原始框挂在 `_pre_caption_column_clip` 属性上，`restore_table_clip_width` 优先以此为恢复上限，解决收窄不可逆 |
| P2 中文章节标题整体降为正文（text_extract.py:44-69） | **复现，已修** | 新增 `_CJK_SECTION_HEADING_RE`（第X章/节、一、（一）、数字编号+空白后跟中文）；非编号路径 CJK 字符计入「字母」计数（≥2 个即过，英文 ≥4 ASCII 不变）；`len<=2` 门槛豁免含 CJK 的文本。初次修复把 `1 - P(E)` 粗体公式片段误判为标题（与 BUG-097 守卫冲突），已补 lookahead 要求编号后必须是字母或 CJK |
| P3 visual-debug 漏列与误判回退（analyze_debug_batch.py:118-200） | **复现，已修** | `flagged[:12]` 改为打印全部 flagged 项；`StageDelta` 补 `x0/x1`，`fallback_to_baseline` 加入 x 向比较（与 y 相同的 2pt 阈值），x 向显著收缩不再误报「回退原框」 |

### 验证

| 命令或操作 | 结果 |
| --- | --- |
| 回归先失败后修复 | 各条均有红灯证据：confirmed 挤占/最大基数/最大权重 3 例、`Our` 题注 explicit/anchor 双 False、通栏表 30..570→30..292、中文标题 15 例失败、flagged 截断 12/15、x 缩 60% 误报回退；修复后全绿 |
| `python3.13 -m pytest tests/scripts/ -q` | **357 通过、0 失败、0 跳过**，golden 实际执行 |
| `python3.13 tests/scripts/test_caption_anchor_quality.py` | main() 手工清单 61 通过、0 失败（补登记了此前漏登的 `test_body_sentence_after_table_verb_is_reference`） |
| compileall 与四入口 `--help` | 通过 |
| 新增/改动测试文件 | `test_a2_a3_fixes.py`（+2）、`test_caption_anchor_quality.py`（+2）、`test_bugfix_20260929.py`（新建 5 例）、`test_text_extract_headings.py`（新建 26 例）、`test_analyze_debug_batch.py`（+2） |

行为取舍备注：双栏排版中「右栏短行且与左栏表行基线对齐」的极端场景现在保守不收窄（可能带入少量右栏内容），为「确认无关正文才收窄」方向的固有取舍；正文长句不受影响。

未提交 git。

## 2026-09-29 第四轮外部评审意见的逐条核实与修复

评审结论「还没有全部完成」，指出 3 处未完全满足原 review 要求。逐条实测核实，**3 条全部复现**：

| 评审条目 | 结论 | 证据 |
| --- | --- | --- |
| 匹配数优先已修，IoU 总和优化未保证（pipeline.py:258） | **复现，已修（BUG-119）** | 确定性反例：2 记录 2 候选（[87,0,178,100]/[131,0,219,100] 对 [111,0,188,100]/[150,0,187,100]），旧匹配总 IoU **0.808**，同基数另一分配 **1.084**。根因：Kuhn 增广只保基数，边排序探试锁死次优解；随机搜索 5 万例（n=2..4）另命中 3 周旋转反例（2.862 对 2.892）——该改进形态是任何 2-opt 交换够不到的局部最优，必须精确求解。修复：位掩码 DP（`_optimal_assignment`）按 (page,kind) 分组精确求字典序最优（身份边数 → IoU 总和），两反例均达最优，5 万例随机复测 0 反例 |
| 无类型图注仍可能跨类型配对（pairing.py:324） | **复现，已修（BUG-120）** | 直调复现：混合页（一 figure 一 table 一 `raw_class="caption"` 通用题注）→ figure 和 table **各产出 1 对，同一条题注绑两张图**。根因：`untyped` 分支让通用题注进两个 kind 分组。修复：`_filter_layout_captions_by_kind` 新增 `mixed_page` 参数——figure/table 并存页的通用题注不进任何分组（落实原 review「无法判别时保留孤儿」）；单类型页行为不变（测试 :422 要求的「通用题注参与 Table 配对」是单类型场景，保持通过） |
| Golden 零收集门禁对单文件运行仍放行（conftest.py:128） | **复现，已修（BUG-121）** | `pytest test_a2_a3_fixes.py::test_detect_truncation_ok…` 在旧 conftest 下 **exit 0**（golden 零收集）；`test_run_all.py` 旧用例把这种放行写成预期行为。修复：`_selection_covers_golden` 恒 True（单文件零收集同样判失败）；`run_all.py` 逐文件套件调用经 `PDF_SKILL_GOLDEN_EXTERNAL=1` 显式声明 golden 另行整轮执行（golden 本体调用不声明，仍受闸门约束）；人工定向调试用 `PDF_SKILL_ALLOW_GOLDEN_SKIP=1`（仅 WARNING、不算全绿）。旧用例改写为「单文件零收集必须失败」+ 3 个新用例 |

### 验证

| 命令或操作 | 结果 |
| --- | --- |
| 新增回归先失败后修复 | 6 个新用例（A2/A3 2 例 + 闸门 4 例，其中 1 例改写）在回退到修复前源码时**全部失败**，恢复后全绿；4 个文件（pipeline.py/pairing.py/conftest.py/run_all.py）sha256 逐对校验一致 |
| 反例复测 | 2×2 反例 0.808→1.084（最优）；3 周旋转反例 2.862→2.892（最优）；5 万例随机搜索（n=2..4，宽漂移 ±50pt）修复后 0 反例 |
| `python3 tests/scripts/run_all.py` | **357 通过、0 失败、0 跳过**（19 套件 + golden 9/9） |
| 附带修复 | run_all 清单闸门拦到 2 个未登记的并行会话产物（`test_bugfix_20260929.py`、`test_text_extract_headings.py`），已补登记（17→19 套件）并同步 docstring |
| AGENTS §8 | 四个入口 `--help` 通过；`compileall` 通过 |

未提交 git。

## 2026-09-29 版本号提升 0.6.4 → 0.6.5

- 版本号更新三处：`README.md`（当前版本行）、`skills/pdf-markdown-summary/SKILL.md`（Current package version）、`skills/pdf-markdown-summary/scripts/__init__.py`（`__version__`）。全仓代码与 Skill 文档无其他 0.6.4 残留引用（`task-list.md` 与 `test_qa04_structured_log.py` 中的 V0.6.4 为历史记录，保留）。
- 验证：`compileall` 通过；四入口 `--help` 4/4 正常；全量 pytest **357 passed、0 failed、0 skipped**（golden 实际执行，含基准重新提取）。

未提交 git。

## 2026-09-29 第五轮审查 2 个确认 bug 修复（BUG-A/B）+ 2 个小问题

| 条目 | 结论 | 修复要点 |
| --- | --- | --- |
| BUG-A（P1）罗马数字标题回归（text_extract.py:94） | **复现，已修** | `I. Introduction`/`II. Related Work`/`IV. Experiments`/`V. Conclusion`/`A. Introduction` 实测全部 False（走到句点检查被误杀；基准 8 份全是阿拉伯数字编号，golden 覆盖不到）。新增 `_ROMAN_ALPHA_HEADING_RE`（`^(?:[IVXLCDM]{1,5}\|[A-Z])\.\s+[A-Za-z]`）并入编号标题分支，任何字号保留；守卫 `IV.`/`A.` 裸编号、`1 - P(E)` 公式片段、非粗体均仍为 False |
| BUG-B（P2）收窄恢复在主链路失效（extract_tables.py:426→433→706） | **复现，已修** | 按评审建议放弃矩形自定义属性方案：`limit_table_clip_to_caption_column` 不再挂 `_pre_caption_column_clip`；`restore_table_clip_width` 新增显式参数 `pre_narrow_clip`；extract_tables 在收窄前显式保存原始框（`:422`）并在 `:710` 显式传入。旧属性方案在 `limit_clip_by_neighbor_captions`（clip_limit.py:243 `fitz.Rect(clip)` 重建）处必丢，多表页（恢复最需要生效的场景）是常态 |
| 小问题 3：run_all.py docstring 计数错 | **已修** | 「共 19 个」→「共 20 个」，编号列表补登 test_analyze_debug_batch.py（实际注册 20 个套件） |
| 小问题 4：pipeline.py 死代码 | **已修** | 删除只写不读的 `used_recs`/`used_cands`/`used_bbox_ids`（BUG-112 Kuhn 版残留）；注意 `cand_bbox_ids` 并非死代码（`_same_frame` 在用），误删后 10 个匹配用例立刻 NameError，已恢复——评审对该变量的判断不准确 |

### 验证

| 命令或操作 | 结果 |
| --- | --- |
| 回归先失败后修复 | BUG-A：修复前 5 例全 False，修复后全 True；BUG-B：旧测试只直调函数级链路（不经过 433 重建），新增 `test_restore_works_after_neighbor_caption_rebuild` 走完整 收窄→邻题注重建→恢复 链路，并断言重建后属性确已丢失、不传原始框时退化为旧行为 |
| `python3.13 -m pytest tests/scripts/ -q` | **366 通过、0 失败、0 跳过**，golden 实际执行 |
| compileall 与四入口 `--help` | 通过 |
| 新增/更新测试 | `test_text_extract_headings.py` +8（罗马/字母编号 6 参数例 + 裸编号 + 非粗体）、`test_bugfix_20260929.py` +1 链路用例并改 1 例为显式传参 |

未提交 git。

## 2026-09-29 第五轮修复后复查（旧 5 项已转绿，新发现 4 项边界漏洞）

上一轮指出的 5 项原始复现均已通过：confirmed 题注绑定不再被普通几何边挤走；普通 `Our proposed...` 题注恢复；左右行严格对齐的无边框通栏表保留全宽；中文章节标题恢复；visual-debug 打印全部 flagged 且 x 向收缩不再误报完整回退。继续审查修复分支后，确认 4 项新问题：

| 优先级 | 问题 | 复现与影响 |
| --- | --- | --- |
| P2 | `Our` 题注只要引用 Section/Table 等编号对象仍会静默漏提 | `_period_tail_reads_as_body` 将 `our` 开头且含交叉引用的 tail 一律判正文；`Figure 1. Our architecture is described in Section 3.` 函数级 explicit/anchor 均为 false，合成带图 PDF 端到端 exit 0 但 index 0 项。真实题注正常引用章节或另一张表时会丢资产。 |
| P2 | 通栏表保护启发式双向误判，且恢复阈值救不回典型半栏误收 | 无边框通栏表右侧单元格中心比左侧偏 5pt 时，超过 3.5pt 对齐阈值，`x=30..570` 被收到 `30..292`；宽度仍为原框 48.5%，`restore_table_clip_width` 的 40% 门槛即使 `table_band_changed=True` 也不恢复。反向场景中，左右双栏短正文基线对齐且每行不足 50/80 字时被当成通栏表延续，框保持全宽并吞入右栏正文。 |
| P2 | 罗马/字母编号修复会把小字号表头判为 Markdown 标题 | `_ROMAN_ALPHA_HEADING_RE` 在字号门槛前接受任意单个大写字母；粗体 9pt 的常见表头 `P. Value`、`N. Samples`、`M. Mean` 均返回 heading=True，重新引入“表头切碎 Markdown”的 BUG-097 同类问题。 |
| P3 | A3 最优分配在同页同类型候选超过 12 个时退回贪心，违反自身硬约束 | `_optimal_assignment` 的 `m>12` 分支不再保证最大基数/字典序最优。13 个 frame 的确定性构造返回 12 条匹配，存在 13 条可行解；高密度单页可能少精修一个资产。m≤12 主路径经 n/m≤6、每组 500 个随机图与穷举最优对比，全部一致。 |

### 验证

| 命令或操作 | 结果 |
| --- | --- |
| `python3 -m pytest tests/scripts/ -q` | **366 passed、0 failed、0 skipped**，golden 实际执行。 |
| `python3 tests/scripts/run_all.py` | **366 通过、0 失败、0 跳过**，20 个登记套件 + golden 9/9。 |
| 5 个修复相关文件定向 pytest（未设豁免） | 选中用例 **152 passed**，但按当前 golden 零收集门禁预期 exit 1；该命令不算全绿。 |
| `python3 -m compileall -q skills/pdf-markdown-summary/scripts tests/scripts` | 通过。 |
| 四入口脚本 `--help` | 全部 exit 0。 |
| visual-debug 批次 `20260928-045` 当前分析 | flagged=97、实际打印 97；`fallback_to_baseline` 计数 0。 |
| `_optimal_assignment` 随机小图对穷举最优 | n/m=1..6、每组 500 例，全部一致；仅 m>12 贪心退路复现缺陷。 |
| `git diff --check` | 通过。 |

本轮除按仓库规则更新本台账外，未修改正式 Skill 代码和测试。未提交 git。

## 2026-09-29 第五轮复查遗留 4 项边界漏洞修复（BUG-122~125）

4 项修复的正式记录已转入「代码 Bug」标准分区（BUG-122~125，含问题描述与修复要点，2026-09-30 台账整理）；本小节的回归验证明细如下。

### 回归测试与验证

| 命令或操作 | 结果 |
| --- | --- |
| 4 组缺陷定向回归（修复前） | **7 失败**：交叉引用题注 1、通栏表/双栏正文 2、小字号表头 3、13 frame 匹配 1；红灯均与复现一致。 |
| 无句号短正文追加回归（修复后扩展） | 先复现「对齐短正文保持全宽」失败，补充谓语形态后通过；`test_bugfix_20260929.py` **7/7** 通过。 |
| 4 个相关测试文件定向 pytest | **152 passed**；本地定向调试使用 `PDF_SKILL_ALLOW_GOLDEN_SKIP=1`，按规则不计全绿。 |
| 新最优分配器随机小图对穷举解 | n/m=1..6，每组 250 个随机图，共 **9000/9000** 组的（身份边数、匹配基数、IoU 总和）与穷举最优完全一致。 |
| `python3 -m pytest tests/scripts/ -q` | 最终 **371 passed、0 failed、0 skipped**，golden 实际执行；代码指纹变更后 8 份 Basic Benchmark 重新提取并完成真实跨批比较。 |
| `python3 tests/scripts/run_all.py` | **371 通过、0 失败、0 跳过**；20 个登记套件 + golden 9/9。 |
| `python3 -m compileall -q skills/pdf-markdown-summary/scripts tests/scripts` | 通过。 |
| 四个入口脚本 `--help` | `extract_pdf_assets.py`、`pdf_to_markdown.py`、`process_pdf.py`、`summarize_pdf.py` 全部 exit 0。 |
| 交叉引用题注端到端合成 PDF | 产物在 `tests/results/20260929-036/caption-crossref-e2e/`；`Figure 1. Our architecture is described in Section 3.` 成功产出 1 张 PNG，index 记录 1 个 accepted figure，stderr 无异常。 |
| `analyze_debug_batch.py tests/results/20260928-045` | 正常完成，原 visual-debug 批次分析器无回归。 |
| `git diff --check` | 通过。 |

本轮修改了正式 Skill 的 `caption_detection.py`、`table_refine.py`、`text_extract.py`、`pipeline.py`，以及对应回归测试。未修改 `tests/basic-benchmark/`，未提交 git。

## 2026-09-29 最新代码 Basic Benchmark visual-debug 全量跑批

- 使用正式 Skill V0.6.5，对 `tests/basic-benchmark/*.pdf` 8 份 PDF 逐一运行：`extract_pdf_assets.py --preset robust --debug-visual` 。
- 所有产物写入 `tests/results/20260929-038/<pdf-stem>/` 下的 `images/`、`txt/`、stdout/stderr log；批次汇总 log 和 debug 分析文件放在批次根目录。Benchmark 目录仅读，未写入。

| PDF | Figures | Tables | assets | exit |
| --- | ---: | ---: | ---: | ---: |
| `1706.03762v7-attention_is_all_you_need.pdf` | 5 | 4 | 9 | 0 |
| `2509.17765v1-Qwen3-Omni Technical Report.pdf` | 3 | 18 | 21 | 0 |
| `2607.24653v2-Kimi-K3.pdf` | 16 | 5 | 21 | 0 |
| `DeepSeek_V41_Tech_Report.pdf` | 12 | 5 | 17 | 0 |
| `FunAudio-ASR.pdf` | 4 | 8 | 12 | 0 |
| `KearnsNevmyvakaHFTRiskBooks.pdf` | 8 | 1 | 9 | 0 |
| `gemini_v2_5_report.pdf` | 16 | 15 | 31 | 0 |
| `gpt-5-system-card.pdf` | 31 | 26 | 57 | 0 |
| **总计** | **95** | **82** | **177** | **8/8 成功** |

### 结果核对

| 检查 | 结果 |
| --- | --- |
| index 资产状态和 warnings | 177 个资产全部 `accepted`，0 warnings。 |
| debug 图一一对应 | 177 张产物 PNG + 177 张 `*_debug_stages.png` + 177 份 stage legend；每个资产一份 debug。 |
| PNG 完整性 | PIL `verify()` 和 `load()` 检查 **354/354 通过**，索引文件、资产图和 debug 图均无缺项。 |
| 日志 | 8/8 exit=0；stdout/stderr 和 JSONL 中无 traceback、异常或 ERROR。 |
| visual-debug 分析信号 | analyzer 计出 97 个 flagged（phase_d 收缩>25%: 89，phase_a>15%: 63，phase_b>25%: 45）。这些是调参信号，不直接等于裁切错误。 |
| 最小高度提示 | 31 个 flagged 含 `final_small_h` 提示；对两个最极值案例目视核对：Qwen3 Table 3 p7（0.14）、GPT-5 Table 18 p44（0.13），最终框均包住完整表头与数据行，旁边正文/下方图表组件被排除；短表格高度低属结构正常。 |
| 命令 | 结果 |
| --- | --- |
| `python3 tests/scripts/analyze_debug_batch.py tests/results/20260929-038` | 成功生成 `_analyze.txt`；97/97 flagged 全部输出。 |
| 354 个 PNG 逐个完整性校验 + index/debug 对账 | 全部通过。 |
| 人工目视查看两个 `final_small_h` 最小案例 | 表头、所有数据行都在最终框内，提示属短表格的正常小高度。 |

本次运行仅生成 `tests/results/20260929-038/` 产物，未更改 Skill 代码或 benchmark PDF。

## 2026-09-29 版本 0.6.5 全量文档检查与提交信息准备

- 版本号确认已提升至 0.6.5，三处（README.md / SKILL.md / scripts/__init__.py）一致，全仓无 0.6.4 残留引用。
- 逐份检查全部活跃文档（README.md、AGENTS.md、SKILL.md、references/×3、docs/3-plans/×2、tests/eval/README、task-list.md）；`docs/2-ref/` 只读未动，`1-archive/`、`4-experiments/` 为归档/产物目录不适用。更新两处：
  - README.md：回归基线 291 passed → **371 passed、0 failed、0 skipped（2026-09-29 复验）**，中英各一处。
  - references/pdf-to-markdown.md：补齐 conversion_report 顶层 status 三态契约（`failed`/`review`/`ready`；`review` 表示有 review/rejected 资产未插入 Markdown，见 `assets.omitted`），对齐 `pdf_to_markdown.py` 实际逻辑。
- 未改动项及理由：cli-options.md 与 argparse 逐项核对无缺口；pdf-summary.md 工作流级无过时内容；docs/3-plans 两份均带完成/更新标记。
- 验证：`python3 -m pytest tests/scripts/ -q` **371 passed、0 failed、0 skipped**，golden 实际执行（本轮仅改 .md，代码指纹未变）。
- 撰写 commit message（≤350 字，标题 V0.6.5-Build0932-20260929，Build 号顺延上一版 0931，待用户按自身计数确认）。

未提交 git。


## 2026-09-29 三篇真实案例裁剪回归修复（进行中）

- 复核用户提供的 Alexa / PARADISE / SASSI 原始 PDF 与 `1-参考素材/debug-0.6.5/` 的 index、debug legend 和页面文字坐标；外部素材仅只读。
- 已确认：分栏后的表格被宽度恢复跨回整页；稀疏宽表的分段横线未合并；图、表只用同类型题注限界；SASSI 问卷行被正文规则误截后回退宽松 baseline。
- 新增真实排版缩减回归 `test_real_layout_regressions_20260929.py`，改正 `test_bugfix_20260929.py` 将错误整页恢复写成期望的断言。先运行定向测试确认 6 条失败（其中跨类型测试先纠正参数名后确认几何断言失败），修复后 11 passed。
- 定向命令：`PDF_SKILL_ALLOW_GOLDEN_SKIP=1 python3 -m pytest tests/scripts/test_bugfix_20260929.py tests/scripts/test_real_layout_regressions_20260929.py -q`。该轮不含 golden，不称全绿。
- 正式实现修改：宽度恢复受已确认 baseline 栏界约束；同高且间隙不超过 2pt 的分段横线合并判断；图表双方均索引异类题注用于边界限制；识别至少 5 条同列独立问句，保留问卷截图。
- 第一轮真实验证写入 `tests/results/20260929-039/`；完整命令保存在各批次 `run_cases.py` / `run_manifest.json`，使用正式脚本 `--preset robust --debug-visual --debug-captions`，文字写入 `txt/`，图片和 debug 写入 `images/`。
- 同时执行 `PDF_SKILL_ALLOW_GOLDEN_SKIP=1 python3 -m pytest tests/scripts/ -q -m 'not golden'`，日志在该批次 `pytest-targeted.log`；完成后另跑含 golden 的全套。

## 2026-09-29 三篇案例修复轮验证与 F6/F1/FunAudio-T8 补充修复

接上一节。先复核 20260929-044 批次（当前未提交代码的产物）确认三大主诉已修复，再补齐剩余缺陷：

- **主诉复核**（044 批次 + 词坐标/目视取证）：Alexa Table 1 方向已正确（表在题注上方、无正文污染）；PARADISE Table 2 恢复为题注上方的小矩阵（x 列全覆盖、accepted）；SASSI Table 4 完整（289 词全在框内、含 "Percentage of Variance" 汇总行、y 到 736.6 越过 520pt 上限）；PARADISE 七张表内容纯净。
- **PARADISE Figure 6（扫描页）修复**：旧框顶部混入两行正文、右侧竖排标签被切 38pt。三处修复：
  1. `expand_clip_to_nearby_figure_title` 补正文判据：换行尾巴与上行配对（`_links_to_wrapped_tail_below`）；`_is_wrapped_body_line` 阈值 60→50 字符、gap 下界 -2（扫描行框交叠）、字号容差 0.5→1.5（OCR 字号抖动 0.93 实测）。曾用「小写开头即正文」的钝判据，误杀 Kimi F12 图内注释 "physical cache block (6144 tokens)"（该注释上方无正文行、下方 11.6pt 外是大写行，配对/宽度判据可精确区分），已回退为配对型。
  2. 新增 `recover_clip_label_columns_without_objects`（figure_post.py）：仅对象全无的 OCR 扫描页启用，按文本几何收回题注 x 范围内的竖排/旁注标签列（宽度≥基线 70% 的正文行不收回）。
  3. 新增 `snap_clip_to_contained_text_lines`（clip_limit.py）：把 ≥50% 在框内、越出 ≤6pt 的字形框行收回，消除 `text_crosses_clip_boundary` 假性截断。F6 终框 [321.0, 87.1, 546.2, 434.7]，目视确认顶部干净、标签完整。
- **PARADISE Figure 1 回归修复**：'l' 伪块（OCR 把树图左边线误读成 title_h1，10×52pt）把 baseline 卡在 y146.4，丢根节点标签。`limit_clip_by_text_blocks` 候选过滤退化 OCR 块（单词 + 高>2.5×宽 + 高≥30pt）。F1 恢复 [60.6, 45.4, 301.3, 273.0]，目视确认树完整。
- **FunAudio Table 8 方向翻转修复**：正文句 "Table 8 shows that RL plays..." 被多行合并成 64.5pt 假题注，作为邻居把真题注方向挤成 below（045 批次起翻车，实测复现：假邻居 below 0.843 / 首行邻居 above 0.88）。`merge_caption_lines` 增加 `_BODY_CITATION_OPENER_RE`（编号对象+陈述动词开头的正文引用不合并，回退首行矩形）。曾用「合并高度>3.5 行高」判据，误杀 Kimi F12 的 4 行 60.6pt 真题注，已改句式判据。
- **会话冲突**：另一会话 23:09 基于旧版重写 `extract_figures.py`（丢 recover/snap 接线）与测试文件（丢 6 条测试）；已恢复接线并重录测试（含新增 `test_title_recovery_keeps_kimi_internal_annotation`、`test_tall_genuine_caption_still_merges`）。
- **golden 基准更新**（更新前逐项人工核对差异方向）：
  - FunAudio T2：y0 580.4→579.0（snap 收回 1.4pt 字形框）；T8：方向回正至题注上方真表格（golden 值即真表格位置）。
  - gpt-5 Figure 6 (p18)：golden 混入右栏另一图表（右栏 y190-370 有 37 个图表标签词），现仅左栏；Table 1 (p5)：golden 全宽松框，现收紧至真表格 x195-400（内容 x206-341）；Table 7 (p12)：golden 超出内容 81pt，现收紧；Table 9 (p15)：仅 PNG 字节差异（bbox 不变）。
  - gemini Table 12 (p70)：仅 PNG 6 字节差异（bbox 不变，050/051/052 三批次复跑确定非抖动）。
- 新测试 9 条（snap×3、title 恢复×2、recover×2、退化块×1、题注合并×2 中改 1 增 1），文件 `test_real_layout_regressions_20260929.py` 现 17 条。

### 验证

| 命令或操作 | 结果 |
| --- | --- |
| `PDF_SKILL_ALLOW_GOLDEN_SKIP=1 python3 -m pytest tests/scripts/test_real_layout_regressions_20260929.py tests/scripts/test_bugfix_20260929.py -q` | 31 passed |
| `python3 -m pytest tests/scripts/ -q`（golden 更新前） | 392 passed + 3 golden 差异（已逐项核对为改进/良性） |
| `python3 tests/scripts/test_extraction_golden.py --update-golden` | 8 通过、0 失败，基准写入独立新批次 |
| `python3 -m pytest tests/scripts/ -q`（golden 更新后） | **395 passed、0 failed、0 skipped**，golden 实际执行 |
| 三篇参考 PDF 终验（`--preset robust --debug-visual --debug-captions`，批次 20260929-053） | Alexa 7/7、PARADISE 13/13、SASSI 4/4 全部 accepted，0 warnings；F1/F6 框目视确认正确 |
| `python3 -m compileall -q skills tests/scripts` | 通过 |
| 四入口 `--help` | 4/4 exit 0 |
| `git diff --check` | 通过 |

未提交 git。


## 2026-09-30 当前未提交修复独立复查

- 用户要求“都修复了，再仔细检查”。本轮仅复查，未修改正式实现；完整结论与证据：`tests/results/20260930-001/复查报告-20260930.md`。
- 阅读全部 10 个修改实现文件及新增回归测试；确认 5 处 P2：PARADISE T7 跨栏正文污染、F4 扫描图顶部边框丢失、扫描图题注在上时空白 accepted、snap above/below 约束颠倒、分组局部横线错误推翻通栏单元格证据。
- `python3 -m pytest tests/scripts/ -q --basetemp tests/results/20260930-001/pytest-tmp` 实际 **392 passed / 3 failed / 0 skipped**，日志 `pytest.log`；FunAudio / gemini / GPT-5 golden 差异。当前选中 20260928-039 基准及 20260929-052 产物；上一节 395 全绿在本工作区不可复现，未擅自更新 golden。
- 三篇真实重跑 `extract_pdf_assets.py --preset robust --debug-visual --debug-captions`，输出 `tests/results/20260930-002/`；完整参数和时长见 `run_manifest.json`。3/3 exit 0，24/24 accepted；逐张检查联系表并放大 debug 后，确认 PARADISE T7/F4 有实际错误，状态 accepted 不代表正确。
- 用 PIL 对 48 个正式资产/debug PNG 执行 verify/load，全部成功；为目视复核生成每篇联系表。记录脚本 SHA256，重跑前后代码一致。
- 三篇 `pdf_to_markdown.py --tables screenshot --images figures --preset robust` 独立验证：7/13/4 图片链接、0 死链，三个报告 ready 且 omitted=0；这两张错误截图也进入 Markdown。详细命令见 002 批次 `markdown_commands.json`。
- `tests/results/20260930-001/repro/` 保存两份合成 PDF 及 robust CLI 产物；一个空白图、一个缺右侧数值列的表均错误 accepted。`python3 -m pytest tests/results/20260930-001/test_review_repro.py -q`：6 个正确期望断言失败，覆盖 5 个问题，日志 `repro.log`。
- `git diff --check` 通过；外部 PDF 和 benchmark 只读，未提交 git。

## 2026-09-30 复查确认的 5 处 P2 修复 + golden 基准更新

- 上一节独立复查确认的 5 处 P2 全部修复，本轮为修复轮，改正式实现。
- **P2-1 通栏表被当成双栏切掉**（`extract_tables.py` + `table_refine.py`）。新增判据 `table_spans_both_columns()`：题注偏居一栏、框宽 ≥ 页宽 75%、且另一侧存在与题注侧表内行同高的短单元格时判为通栏表。`generic_column_inference_allowed` 只在该判据为真（或框已被题注栏收窄）时才置 `infer_columns=False`，不再无条件关闭通用列推断。配套新增 `_wraps_from_previous_line()`、`_detect_column_boundary()`（窄栏排版用真实栏界而非页中线）。
- **P2-2 扫描图丢失无文字的图形边框**（`figure_post.py` + `pixel_detect.py` + `extract_figures.py`）。新增 `pixel_detect.estimate_region_ink_ratio` / `make_ink_probe`；`trim_far_side_noise_before_content` 的远端裁切加 `ink_probe` 闸门——只有该带区确实无墨迹才允许裁掉，扫描页整页位图里的可见图形因此保留。调用侧仅在页面无 image/vector 对象（扫描页）时传入探针。
- **P2-3 扫描页方向写死 `above`，空白裁剪也判 accepted**（`direction.py`）。新增 `score_scan_structure_for_caption()`：遮蔽文字行后按题注上/下两侧的结构墨迹占比出证；`compute_global_anchor` 在 `caption_count == 0` 分支用像素证据定方向，纯文字页（证据为零）才退回常规约定。
- **P2-4 字形补全方向约束反向**（`clip_limit.py`）。`snap_clip_to_contained_text_lines` 中题注约束改为只限外扩：`above` 只夹 `y1`、`below` 只夹 `y0`，不再反向收窄已有框。
- **P2-5 分组局部横线错误截断跨栏表**（`table_refine.py`）。`continuation_cells` 非零（跨栏同行单元格证据成立）时否决 `ruled_column`，局部横线不再推翻通栏判据。
- 配套（前几轮遗留，本轮一并收敛）：`caption_detection.py` 增加正文引用句式 `_BODY_CITATION_OPENER_RE` 与跨行合并边界检查，避免 "Table 8 shows that ..." 段首被合并成 60pt+ 假题注；`extract_helpers.py` 抽出 `is_page_background_image` / `collect_image_rects`（整页背景位图在含文字页面不计入对象）；`acceptance.py` 新增 `looks_like_questionnaire_rows`；`text_extract.py` 在报告里记录扫描文字页号；`clip_limit.py` 新增 `_is_degenerate_ocr_block`（OCR 把竖线误读成单字长条时不当作 baseline 边界）。
- **新增回归测试**：`tests/scripts/test_real_layout_regressions_20260929.py` 补 P2-3 两条（`test_top_caption_scan_crop_contains_graphic` / `test_bottom_caption_scan_crop_still_reads_above`，用整页位图 + 深色图形 + 不可见 OCR 文字合成，方向完全由像素证据决定）与 P2-1 四条（通栏表跨栏单元格判真、双栏正文判假、窄框判假、居中题注判假）；该文件已在 `tests/scripts/run_all.py` 注册为「真实排版布局回归 (20260929)」。
- **全量回归**：`python3 tests/scripts/run_all.py` → **EXIT 0，405 通过 / 0 失败 / 0 跳过**（13218ms），其中「真实排版布局回归 (20260929)」34/34、「Golden 对比测试」9/9。修复前同入口为 392 通过 / 3 失败。
- **强制重抽取复核**：`PDF_GOLDEN_REEXTRACT=1 python3 -m pytest tests/scripts/test_extraction_golden.py -q` → 9 passed（223.00s），8 篇 benchmark 全部从 PDF 重新抽取后与基准逐条比对（final_bbox ≤0.5pt + PNG 尺寸/sha256 严格相等）通过，产物落在 `tests/results/20260930-017/`（无 golden_index，未污染基准）。
- **golden 基准更新**：`python3 tests/scripts/test_extraction_golden.py --update-golden` → 8 passed，新基准批次 `tests/results/20260930-016/`。相对上一基准 `20260928-039`，**全部差异只有 2 条，均为表格**，逐条说明：
  1. `FunAudio-ASR` Table 2 (p9)：`final_bbox` `[103.0, 580.4, 509.1, 689.9]` → `[103.0, 579.0, 509.1, 689.9]`（y0 +1.4pt），PNG 94506B → 94604B。根因经逐阶段插桩与单文件回退定位在 `caption_detection.py`：该页 Table 1 题注实际是两行（`534.12-544.28` + `545.20-555.16`）。未合并时相邻题注上限给出 `y0 = 544.28 + 6 = 550.28`，**落在相邻题注第二行内部**，属真实缺陷；合并后 `y0 = 555.16 + 6 = 561.16` 正确避开整条题注。两张裁剪都含表顶线 y=581.9，新结果留白 2.9pt（旧 1.5pt）。判定为改善。
  2. `gpt-5-system-card` Table 1 (p5)：`[26.0, 350.4, 569.3, 480.2]` → `[195.0, 350.4, 400.4, 480.2]`，PNG 64130B → 54807B。旧框是整条文字栏，左侧带 169pt 空白边距；该页表线实际位于 x 199.9–395.4、表内文字 x 205.84–389.41，新框完整包含表格且四周留 ~5pt 边距，无内容丢失。判定为改善。
  - 另 `gpt-5-system-card` Table 18 (p44) 有 0.1pt 级抖动（95.5→95.4 / 500.1→500.0），在 0.5pt 容差内，PNG 哈希未变，不构成基准差异。
- **三篇真实 PDF 重跑的限制**：上一节复查所用的 PARADISE / Alexa / SASSI 三篇外部 PDF **在本机**，路径为 `.../1-参考素材/`。2026-09-30 独立复核已用当前代码重跑（输出 `/tmp/exp/out/V4` 与 Markdown `out/md4`）：24/24 accepted，词坐标核对无截词/无正文污染/无漏行；三篇 `pdf_to_markdown.py` 均为 ready、omitted=0、死链=0。本轮此前误写「不在本机、无法重跑」，已更正。`test_real_layout_regressions_20260929.py` 的缩减几何回归仍保留，并补了 PARADISE 第 9 页真实页面 T7 用例。
- **清理**：诊断探针误写入只读输入目录的 `tests/basic-benchmark/text/`（4 个今日生成的文本转储）已删除，该目录恢复为纯只读输入。
- `git diff --check` 通过；`python3 -m compileall -q skills tests/scripts` 通过；未提交 git。

## 2026-09-30 三篇外部 PDF 用当前代码实跑验证（批次 20260930-018）

上一节台账「三篇外部 PDF 不在本机，无法重跑」**记录有误**：三份 PDF 实际位于 `/Users/fenix-macmini/Documents/Haier/6-HaierVibeCoding/2-新需求设计/20260924-分布式唤醒主观体验测试方案/1-参考素材/`（Alexa端到端设备仲裁、PARADISE-口语对话系统评价框架、SASSI-语音系统界面主观评价量表）。本轮用当前未提交代码实际重跑验证。

### 提取验证（`extract_pdf_assets.py --preset robust --debug-visual --debug-captions`）

3/3 exit 0（23s / 24s / 5s），共 24 资产全部 accepted。逐张目视核对关键截图：

| 资产 | 历史问题 | 本轮结果 |
| --- | --- | --- |
| PARADISE Table 7 | P2-1：右栏正文被截入（x 到 526） | `[60,108,286,169]` 单栏纯净属性矩阵，目视无邻栏污染 |
| PARADISE Figure 4 | P2-2：根节点顶部边框被切 ~14pt | `[311,41,529,266]` y0=41 高于边框 47.5，树结构完整 |
| SASSI Table 4 | 底部 ~7 行与汇总行被拦腰切断 | `[62,95,550,737]` 六列因子矩阵完整，含 "Percentage of Variance" 汇总行 |
| Alexa Table 2 | 方向翻转：截的是题注下方正文 | `[327,67,547,140]` 为题注上方真实表格（Train/Test/Rel.error 矩阵） |
| PARADISE Table 6 | 右栏 "3 Generality" 整节正文被拖入 | 单栏完整矩阵，含 information flow 列，无污染 |
| PARADISE Table 2 | 曾退化 rejected（text_pollution） | `[367,212,467,259]` accepted，题注上方小矩阵 |
| SASSI Table 2 | 曾被 restore 撑到整页宽 | 窄框 `[62,96,248,297]`，12 组形容词对完整（表格本身即窄） |

### Markdown 端到端（`pdf_to_markdown.py --tables screenshot --images figures --preset robust`）

| PDF | 图片链接 | 死链 | conversion_report |
| --- | --- | --- | --- |
| Alexa | 7/7 | 0 | ready，omitted=[] |
| PARADISE | 13/13 | 0 | ready，omitted=[] |
| SASSI | 4/4 | 0 | ready，omitted=[] |

对照 0.6.5 基线（`1-参考素材/debug-0.6.5/`）：PARADISE 图片入 md 从 2/13 → 13/13，SASSI 从 2/4 → 4/4，Alexa 保持 6→7（Table 2 方向修正后入文）。

输出位置：`tests/results/20260930-018/<pdf-name>/{images,txt,markdown,assets}/`。未提交 git。

## 2026-09-30 独立复核收尾：台账更正、正文插图、PARADISE 第 9 页回归

独立复核确认裁剪修复有效后，按复核意见补了三处收尾（见 [[DEV-017]] [[TST-047]] [[CHK-021]] [[DOC-059]]）：

- 更正上一节「三篇外部 PDF 不在本机」的错误记录；三份 PDF 在 `1-参考素材/`，复核已实跑。
- Markdown 不再把全部图表堆到文末「## 提取资产」。`pdf_to_markdown.py` 把 accepted 截图插到对应题注段落旁（内容在题注上方则图在题注前，否则在题注后）；正文引用句不抢槽位；找不到题注的资产仍追加到文末。
- 新增 PARADISE 第 9 页 Table 7 回归：优先抽取真实 PDF 第 9 页跑完整 `extract_tables`，并用该页实测坐标约束 `restore_table_clip_width`（去掉短单元格过滤时 x1 会扩到 524.8，过滤恢复后保持左栏）。

### 验证

| 命令或操作 | 结果 |
| --- | --- |
| `python3 -m pytest tests/scripts/ -q` | **410 passed、0 failed、0 skipped**（405 基线 + 5 条新用例），golden 实际执行 |
| 四入口 `--help` | 4/4 exit 0 |
| `python3 -m compileall -q skills tests/scripts tests/eval` | 通过 |
| `git diff --check` | 通过 |
| PARADISE `pdf_to_markdown.py --preset robust --tables screenshot --images figures`（批次 `tests/results/20260930-019/`） | 13/13 图链均在对应题注旁，无文末「提取资产」；Table 7 截图紧挨题注之前 |

未提交 git。

## 2026-09-29 版本号提升 0.6.5 → 0.6.6

- 版本号更新三处：`README.md`（当前版本行）、`skills/pdf-markdown-summary/SKILL.md`（Current package version）、`skills/pdf-markdown-summary/scripts/__init__.py`（`__version__`）。全仓无其他 0.6.5 残留引用（`task-list.md` 与 `test_qa04_structured_log.py` 中的 V0.6.5 为历史记录，保留）。
- 验证：`compileall` 通过；四入口 `--help` 4/4 正常；全量 pytest **410 passed、0 failed、0 skipped**（`__init__.py` 变更触发指纹变化，golden 重新提取 8 份基准后全过；测试数较上轮 395 增加，为并行会话新增测试）。

未提交 git。


## 2026-09-30 当前修复独立复验（批次 20260930-021/022）

上一轮 5 处 P2 裁剪/方向问题已全部通过独立复验，但新增题注旁插图逻辑尚有两处 P2：中文无空格题注 `图1：` / `表1：` 被词边界拒绝；子图 `Figure 3a:` / `Figure 3(a):` 的新匹配编号与正式提取器的 `3` 不一致，均导致截图退回文末。取证测试使用正式编号解析与 Markdown 结构，4 条用例稳定失败。本轮仅复验并记录，保留所有已有业务代码；详细报告及复现脚本在 `tests/results/20260930-021/`。

验证命令与结果：

- `PDF_GOLDEN_REEXTRACT=1 python3 -m pytest tests/scripts/ -q --basetemp tests/results/20260930-021/pytest-tmp`：410 passed / 0 failed / 0 skipped，248.47s。包含 9 个 golden 用例；Basic 8 篇强制重抽取到 022，独立对比 016 基准，未更新 golden；177 张实际资产 PNG 全部有效。
- `python3 tests/results/20260930-021/run_cases.py`：三篇 Alexa/PARADISE/SASSI 全新 robust + debug-visual + debug-captions，3/3 exit=0，24/24 accepted、无 warnings；全部成品及 T7/F4 阶段图目视核对通过。
- `python3 tests/results/20260930-021/run_markdown.py`：3/3 exit=0；图片链接 7/7、13/13、4/4，0 死链，conversion_report 均 ready、omitted=[]。
- 原扫描顶置题注 PDF 重新执行 `extract_pdf_assets.py --preset robust --debug-visual`；`python3 -m pytest tests/results/20260930-021/test_review_repro.py -q`：6 passed。
- `python3 -m pytest tests/results/20260930-021/test_caption_placement_repro.py -q`：4 failed，确认上述 2 处新增 Markdown 缺陷；这些取证用例尚未纳入正式 tests/scripts 套件。
- 四个正式入口 `extract_pdf_assets.py`、`pdf_to_markdown.py`、`process_pdf.py`、`summarize_pdf.py` 的 `--help` 均 exit=0；`python3 -m compileall -q skills/pdf-markdown-summary/scripts tests/scripts` exit=0。
- 021 中实际提取的 74 张 PNG 全部 PIL verify + load 成功；正式 Python 代码复验前后 SHA256 无变化。
- 台账校验预先存在第 96 行列数、第 1400 行表格空行及摘要统计旧不一致；本轮保留原状，未迁移格式。全部运行结果保存在 tests/results，不写入只读 benchmark。

## 2026-09-30 Markdown 题注旁插图 2 处 P2 修复（中文题注 / 子图编号）

复验报告（`tests/results/20260930-021/复验报告-20260930.md`）确认上轮 5 处裁剪/方向问题全部修复，但新增 2 处插图匹配 P2。逐条复现后修复：

| 条目 | 结论 | 修复要点 |
| --- | --- | --- |
| P2 中文无空格题注匹配失败（pdf_to_markdown.py:218-220） | **复现，已修** | `_asset_kind_matches_text` 用 `\b` 词边界，而「图」与紧随数字同属正则 word 字符，「图1：」「表1：」匹配失败 → 图片退回文末。英文前缀保留 `\b`，中文前缀（图/图表/附图/表）单独匹配、不要求词边界。实测修复前 `kind_match=False`，修复后命中 |
| P2 子图编号解析口径不一致（pdf_to_markdown.py:244-249） | **复现，已修** | 删除自建的 `_CAPTION_IDENT_RE`（Figure 3a → `3a`），改为复用正式提取链的 `FIGURE_LINE_RE`/`TABLE_LINE_RE` + `extract_figure_ident`/`extract_table_ident`（Figure 3a/3(a) → `3`），编号比较与资产 id 同源 |

### 验证

| 命令或操作 | 结果 |
| --- | --- |
| 复验复现 `test_caption_placement_repro.py` | 修复前 **4 failed**，修复后 **4 passed** |
| 回归先失败后修复 | 临时还原两处修复后，3 条新正式用例全部失败（红灯）；恢复后全绿 |
| `pytest tests/scripts/test_pdf_to_markdown_cli.py` | 16 passed（新增 3 条：中文题注图/表、子图 3a/3(a)、编号不一致守卫）；独立 `main()` 15 通过 0 失败 |
| `python3.13 -m pytest tests/scripts/ -q` | **413 passed / 0 failed / 0 skipped**，指纹变更触发 golden 重新提取，9/9 通过 |
| compileall 与四入口 `--help` | 通过 |

过程备注：红灯验证时误用 `git stash push -- <path> -q`（`-q` 被当作 pathspec，stash 未创建）；随后的 `git stash pop` 因与旧 stash（V0.6.4 时代遗留的 stash@{0}）冲突被 git 拒绝，工作区未被改动。`stash@{0}`/`stash@{1}` 均为历史遗留，未动。

未提交 git。

## 2026-09-30 PDF Python 协作流程 SVG 绘图

- 用户要求仔细绘制 SVG，解释拿到 PDF 后各个 Python 文件怎样协调工作，优先泳道图。本轮只增加图形文档与阅读说明，保留当前所有已有业务修改，不修改正式 Skill Python。
- 只读梳理正式 `skills/pdf-markdown-summary/scripts/` 全部 54 个 Python 文件、四个包装入口、四个 core 入口及 lib 调用顺序；通过 AST 盘点文件、导入、函数与源码位置。未使用历史归档或只读参考代码建立新逻辑。
- 新增 `design/PDF脚本协作泳道图-20260930.svg`（1900×2200）：输入/Agent、core 编排、文本模型、图表提取、产物交付五条泳道，展示 process 先 Markdown 后摘要材料复用、Figure→Table 顺序、质量筛选、相对图片链接与错误返回。
- 新增 `design/PDF图表提取模块展开图-20260930.svg`（2100×2550）：按证据、两类裁剪、专用补全、验收、可选语义 Layout 与对账分组，标注兼容再导出层、共享数据契约与包入口；明确双列是职责对照，运行顺序并非并行。
- 新增 `design/PDF脚本协作图阅读说明-20260930.md`：四入口路由、关键执行边界、产物用途、全部 54 个正式 Python 职责与实际文件链接、关键函数源码行号。摘要由 Agent 同时阅读全文及图片后撰写；OCR 和结构化表格当前能力按实际实现标注。
- 绘图源、AST 清单、说明生成器、文档校验脚本与 PNG 预览位于已忽略的 `experiments/svg-flow-20260930/`；未归档、移动、删除任何现有文件，未写入只读 benchmark 或 design/2-ref。
- 渲染过程：CairoSVG 导入失败（系统缺少 libcairo），改用 macOS `qlmanage` 对本地 SVG 离线渲染；第一次缩略图截断长图尾部，使用独立正方形预览画布生成全幅图，再生成完整 PNG 预览。尝试 IAB 打开本地 file URL 被浏览器 URL 策略阻止；未绕过策略，采用本地离线图形渲染与 Codex 文件预览。
- 生成命令：`python3 experiments/svg-flow-20260930/draw_flows.py`、`python3 experiments/svg-flow-20260930/write_guide.py`，成功。渲染命令：`qlmanage -t -s 2550 -o experiments/svg-flow-20260930 experiments/svg-flow-20260930/*全幅预览.svg`，2/2 成功；对两张全幅预览逐张目视检查中文、箭头与底部内容，修正一处过长卡片文案并补上质量警告门控说明。
- 验证命令：`python3 experiments/svg-flow-20260930/verify_artifacts.py`，**54/54 模块覆盖、66 个文档链接均存在、2/2 SVG XML/标记引用/文字基准点范围/无外部资源检查通过、2/2 PNG verify+load 通过**。结果记录在 `tests/results/20260930-024/SVG验证结果-20260930.json`。
- `python3 -m compileall -q experiments/svg-flow-20260930` 通过；`git diff --check` 通过。未修改正式 Skill 脚本，本轮不重跑 CLI/PDF/pytest 回归，不将文档检查表述为代码套件全绿。未提交 git。

## 2026-09-30 顶层 docs/ 正式改名为 design/

用户要求将仓库顶层 `docs/` 正式改名为 `design/`，并同步 `.gitignore` 与全部当前文档引用。

操作：`git mv docs design`（文件系统整目录改名，含未跟踪的 `4-experiments/`）。`design/2-ref/` 仅随父目录移动，内部文件内容未改。

| 文件 | 修改内容 |
| --- | --- |
| `.gitignore` | `docs/_build/` → `design/_build/`；`docs/4-experiments/` → `design/4-experiments/`。 |
| `AGENTS.md` | 第 2 节目录职责、第 4 节改名为 «design 目录规则»、第 8 节验证规则全部改为 `design/` 路径。 |
| `README.md` | 中英两处归档流程文档链接改为 `design/1-archive/`。 |
| `design/PDF图表提取技术迭代实施方案-20260731.md` | 现行路径改为 `design/`；实验目录现行位置改为 `design/4-experiments/`。 |
| `design/PDF图表提取架构根因复盘与技术路线分析报告-20260721.md` | 现行引用改为 `design/`。 |
| `tests/eval/` | README、CLI 示例与模块 docstring 中的路径改为 `design/`。 |
| `task-list.md` | 新增 DOC-060、OPS-003；今日 SVG 绘图节中的现行文件路径改为 `design/`。 |

未改写范围（沿用 DOC-022 / 2026-09-23 重编号惯例）：

- task-list 已完成历史条目中的 `docs/` 路径为当时事实，保持不动。
- `old-version/` 不维护。
- `design/1-archive/` 与 `design/2-ref/` 内部文件内容不改。

### 验证记录

| 命令或操作 | 结果 |
| --- | --- |
| `test ! -e docs && test -d design` | 通过：`docs/` 已不存在，`design/` 存在。 |
| `git check-ignore -v design/4-experiments/` | 命中 `.gitignore` 的 `design/4-experiments/`。 |
| `git check-ignore design/3-plans/` | exit 1（未被忽略，可提交）。 |
| 现行文档 grep `docs/`（排除 old-version、1-archive、历史 task-list 条目） | AGENTS.md / 实施方案 / eval README 中残留的 `docs/` 仅为原路径说明。 |

## 2026-09-30 实验目录移到仓库根目录 experiments/

用户要求将 `design/4-experiments/` 移到项目根目录并改名为 `experiments/`，继续整目录 gitignore。

操作：`mv design/4-experiments experiments`（该目录本就未跟踪）。五个子目录原样保留。

| 文件 | 修改内容 |
| --- | --- |
| `.gitignore` | `design/4-experiments/` → `experiments/`。 |
| `AGENTS.md` | 第 2 节新增顶层 `experiments/`；第 4 节删除 `design/4-experiments/` 条目；第 8 节产物去处改为 `experiments/`。 |
| `tests/eval/` | README、CLI 示例与模块 docstring 改为 `experiments/`。 |
| `design/3-plans/PDF图表提取技术迭代实施方案-20260731.md` | 实验路径改为 `experiments/`。 |
| `task-list.md` | 新增 OPS-004；今日 SVG 绘图节中的实验路径改为 `experiments/`。 |

历史完成条目中的 `docs/4-experiments/`、`design/4-experiments/` 为当时事实，保持不动。

### 验证记录

| 命令或操作 | 结果 |
| --- | --- |
| `test -d experiments && test ! -e design/4-experiments` | 通过。 |
| `git check-ignore -v experiments/` | 命中 `.gitignore` 的 `experiments/`。 |
| `git check-ignore design/3-plans/` | exit 1（未被忽略）。 |
| `git status --short -- experiments` | 无输出（整目录仍被忽略）。 |


## 2026-09-30 全部功能模块分析、编号与 SVG 同步

用户要求按实际功能建立全集（一个 Python 文件可以包含多个功能），给每项分配编号、记录到文档并同步已有流程图。

- 只读分析正式 `skills/pdf-markdown-summary/scripts/` 的 54 个 Python 文件，以及 `tests/scripts/`、`tests/eval/` 的 31 个维护 Python 文件。按职责与策略边界拆解为 26 个功能域、394 项功能：正式 334 项、测试评测 60 项。归档、只读参考、生成产物与一次性实验不作为正式能力；空 package.json 没有额外 JavaScript 工作流。
- 编号为 `Fxx.nnn`；现有编号保持身份，新功能追加，弃用编号不复用。最终 Agent 同时阅读全文与图片后撰写摘要另记为 `EXT-01`，不计入 Python 功能数量。
- 新增 `design/4-analysis/PDF功能模块全集与编号-20260930.md`：每项包含职责、适用状态、输入输出与实现位置；区分默认、可选、底层备用、数据契约、兼容和占位功能。
- 新增 `design/4-analysis/PDF功能模块编号表-20260930.json` 与 `PDF功能模块源码覆盖索引-20260930.md`：保存功能 ID、全量实现引用、位置、源码 SHA256 与声明反查。AST 复核 1106 个顶层、类方法、嵌套和条件声明，全部有归属；声明覆盖仅用于防漏，不代表业务分支正确性验证。
- 新增 `design/4-analysis/PDF功能模块全集索引图-20260930.svg`（3140×5522）：26 个分组卡片逐项显示全部 394 个编号，每项链接到文档锚点；同步泳道图、提取展开图与阅读说明。流程卡片标注功能域并提供该域子编号索引，索引用于反查，不表示本阶段逐项执行。
- 修正文档对 Markdown 准入的说明：已有 status 时仅 accepted / accepted_with_margin 准入；缺少 status 的旧索引才按复核标记与警告兜底。复核确认正式 assess 已写入启发式 pairing/boundary 置信度，未把旧注释中的占位说法当作当前事实；OCR/结构化表格参数的未接通边界、A1 报告过滤与备用候选种子的边界亦已说明。
- 本会话未执行目录迁移；输出路径跟随其他会话的 docs→design、实验移到顶层 experiments 结果。迁移期间 tests/eval 四个文件只修改 docstring 路径，已检查差异后更新分析快照。阅读说明的源码链接改为适配 `design/4-analysis/` 的相对路径。
- 分析中间 JSON、AST 清单、生成器、验证器、绘图源和离线 PNG 位于已忽略的 `experiments/feature-registry-20260930/` 与 `experiments/svg-flow-20260930/`。使用 qlmanage 正方形外画布渲染三张全幅预览后裁回原比例；目视检查三张图，修正卡片过长正文的宽度适配。未修改正式 Python 实现，未改归档和只读目录，未提交 git。

### 本轮验证记录

| 命令或操作 | 结果 |
| --- | --- |
| `python3 experiments/feature-registry-20260930/build_crop_features.py`、`build_test_features.py` | 完成功能拆解；裁剪分析 13 文件、114 项；测试评测 60 项。 |
| `python3 experiments/feature-registry-20260930/build_catalog.py` | 394 项编号、26 域；85 文件 SHA256 与分析快照一致；1106/1106 声明归属；无遗漏或无效源码引用。集成阶段补充了条件日志回退声明。 |
| `python3 experiments/feature-registry-20260930/draw_feature_index.py` | 三张 XML 有效 SVG 生成；全集图逐项显示全部编号。 |
| `python3 experiments/feature-registry-20260930/render_previews.py` | 调用 `qlmanage -t -s 4400`，3/3 本地离线渲染成功，全幅 PNG 底部完整。 |
| `python3 experiments/feature-registry-20260930/verify_catalog.py` | 功能编号唯一且全部一致；全量源码引用位置有效；3943 个文档链接有效；3/3 SVG XML、标记引用、文字坐标、无外部图片、功能映射/全集文档锚点检查通过；3/3 PNG verify+load 与比例检查通过。 |
| `python3 -m compileall -q experiments/feature-registry-20260930 experiments/svg-flow-20260930`（验证器内执行） | 通过。 |
| `git diff --check`（验证器内执行） | 通过。 |

验证报告：`tests/results/20260930-025/功能编号与SVG验证结果-20260930.json`。本轮仅修改文档、SVG 与一次性生成/校验脚本，没有运行 PDF 或 pytest 回归；不将上述检查表述为业务测试全绿。


## 2026-09-30 历史 BUG 功能归属与排行分析

- DOC-063：按用户要求在 `design/4-analysis/` 新增 `BUG历史记录与功能编号归属分析-20260930.md`、`BUG功能归属与统计明细-20260930.json` 和 `BUG功能报告频次排行-20260930.svg`。报告包含统计口径、完整功能域/叶功能/函数/文件降序排名、集中问题分析及 125 条标准 BUG 的逐项依据；额外四条具名日志单列并给出综合完整排名。
- 全量标准表为 BUG-001 至 BUG-125，125 条均标已修复；123 条可关联当前叶编号，BUG-069 文档遗漏与 BUG-102 已删除死代码没有当前直接叶编号。保留 BUG-019、BUG-050 中未能精确定位的局部问题，不用推测填满。标准口径关联 128 项功能、121 个函数/方法、217 个 BUG×功能与 234 个 BUG×函数；同一条在同一对象内去重，普通调用方与验证测试不机械算缺陷。
- 额外识别日志中复用 BUG-091/092 的两条异根因问题，以及未转入标准表的 BUG-A/B；使用报告内局部 key 保存，共 129 条具名记录。未改台账历史 ID。BUG-124 错引 BUG-097 已在报告提示；同根因不同报告记录和合并审查条目按既定口径解释，频次不等于当前缺陷率。
- 标准函数榜 extract_figures=12、extract_tables=10；纳入补充日志后为 12/11。F07.010/F09.008/F19.013 各 5 条并列叶功能首位；F14 域标准 21/综合 23。独立复核确认主循环计数来自直接策略、传参、数据字段或顺序责任；修正 BUG-054 的测试函数依据文案为 ReturnNotNoneWarning，与 BUG-053 的假绿根因区分，计数未变。
- 正式功能全集/编号表和 85 个源码文件 SHA256 均核对一致。本次没有修改正式/测试函数、职责或流程，不需重编功能编号或修改既有流程 SVG。分析器、中间映射、快照和 PNG 预览位于已忽略的 `experiments/bug-feature-audit-20260930/`；未改归档、只读参考和 benchmark，未提交 git。

### 验证命令与结果

| 命令或操作 | 结果 |
| --- | --- |
| 标准 BUG 行提取及逐项人工核对 | 125/125 唯一 ID 全覆盖；3 个分批只读分析及交叉复核；另找到 4 条具名补充日志。验证阶段发现宽匹配 BUG 前缀会包含 BUG-A/B，已收窄标准行匹配并将 A/B 单独纳入综合口径。 |
| `python3 experiments/bug-feature-audit-20260930/build_report.py` | 报告、JSON、15 栏 SVG 排行图生成；同分排名稳定；源证据与完整映射持久保存。 |
| `python3 experiments/bug-feature-audit-20260930/verify_report.py` | 全部编号/源码声明位置/引用匹配；85 份源码哈希无漂移；标准及综合排行独立回算一致；125 个报告锚点和 2345 个文件/锚点链接通过；4 条日志原文及当前位置核对；SVG XML 和 15 个功能条形 ID 有效，无外部图片；PNG verify+load 通过。 |
| 排行图目视检查 | 中文标题、标签、数值、刻度完整，条形值与正式 125 条口径一致；综合口径在报告另表显示。 |
| `python3 -m compileall -q experiments/bug-feature-audit-20260930`（验证器内执行） | 通过。 |
| `python3 /Users/fenix-macmini/.codex/skills/task-list-initialization/scripts/task_list_cli.py check --file task-list.md` | 写入 DOC-063 前后均通过；无 ID、格式、预览或统计摘要错误。 |
| `git diff --check` | 通过。 |

初次完整验证记录：`tests/results/20260930-026/BUG归属分析验证结果-20260930.json`；台账写入后重生成报告并核对日志行号，最终验证记录：`tests/results/20260930-027/BUG归属分析验证结果-20260930.json`。本轮不运行 PDF/pytest 业务回归，不将分析检查称为业务测试全绿。

## 2026-09-30 已完成计划文档归档

用户确认两份 `design/3-plans/` 文档内容是否已完成后，要求移入 archive。

完成情况（对照 CHK-022 与正式实现，本轮不再改业务源码）：

- `basic结构定位修复计划-20260922.md`：文档已标「已完成（2026-09-23）」；6 项待办均有对应回归（`test_structure_review_20260922.py`、`test_review_fixes_20260922.py`、Golden 更新）。CHK-022 相关套件 111 passed、0 skipped。
- `extraction-status-inventory-20260907.md`：三态评估、题注对账及 2026-09-28 五项补充（`mark_cross_kind_overlaps`、对账范围与 CLI 同口径、计数与补裁后同源、gap 文件名带页码、legacy rejected 不恢复 Markdown 插入资格）已在 `lib/assess.py` / `lib/pipeline.py` 落地。A3「状态只降不升」指不可插入状态不回升，不是所有状态单调。

操作：`git mv` 两份文件到 `design/1-archive/`。`design/3-plans/` 仍保留实施方案与架构根因报告。历史 task-list 中的 `docs/2-plans/`、`docs/3-plans/` 路径为当时事实，不改写。功能模块全集与 SVG 无函数/流程变化，无需更新。

### 验证记录

| 命令或操作 | 结果 |
| --- | --- |
| `test -f design/1-archive/basic结构定位修复计划-20260922.md && test -f design/1-archive/extraction-status-inventory-20260907.md` | 通过。 |
| `test ! -e design/3-plans/basic结构定位修复计划-20260922.md && test ! -e design/3-plans/extraction-status-inventory-20260907.md` | 通过。 |
| 现行文档 grep 这两份文件名（排除 task-list 历史条目） | README / AGENTS / SKILL / design/4-analysis / 实施方案无现行链接。 |
| `python3 .../task_list_cli.py check --file task-list.md` | 通过。 |

## 2026-09-30 全部未提交改动复核与 commit message 撰写

- 复核当前全部未提交内容（相对 V0.6.5 / 997a6e7）：裁剪与方向修复、Markdown 题注旁插图（含中文题注/子图编号两处 P2 修复）、`docs/`→`design/` 目录改名、`experiments/` 移至根目录、计划文档归档、`design/4-analysis/` 功能编号体系（394 项）与 BUG 归属分析、`tests/eval` 路径同步、`CLAUDE.md`/`.claude/`（Stop hook 入库、仅 `settings.local.json` 忽略）、版本 0.6.6。
- 核查 `git status` 中三处 RD 状态：两份顶层报告经 `git mv` 后又移入 `design/3-plans/`（该目录未暂存）；`design/2-ref` Uni-Parser v1 删除、v4 新增。**提交时需 `git add -A` 让暂存区与工作区一致**，否则两份报告会以 `design/` 顶层的旧位置入库。
- 验证：`compileall`（skills + tests/scripts + tests/eval）通过；四入口 `--help` 4/4；`git diff --check` 通过；全量 pytest **413 passed、0 failed、0 skipped**。
- 撰写 commit message（292 字 ≤300，标题 V0.6.6-BuildXXXX-20260930，Build 号留待用户填写）。

未提交 git。
