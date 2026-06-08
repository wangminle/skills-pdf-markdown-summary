# 任务跟踪列表

记录本项目所有任务：代码 bug、需求调整、功能开发、代码审查、测试数据、文档维护、配置运维等。

> 说明：本文件是当前项目的任务清单。所有新增事项、状态变更和完成记录都应同步写入本文件。
> 字段说明：动作字段只允许以下 8 个固定枚举：修复、开发、优化、调整、规划、检查、文档、运维。
> 归并规则：审计、复核、核查、审查、验证、评估统一记为“检查”；重构、清理统一记为“优化”；方案、梳理统一记为“规划”；记录类文档事项统一记为“文档”。

## 代码 Bug

| ID | 动作 | 问题描述 | 发现日期 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- |
| BUG-001 | 修复 | 图表 caption 索引候选未评分，导致最佳 caption 过滤失效并把正文引用当作截图锚点 | 2026-06-05 | 已修复 | `build_caption_index()` 现在会为候选项计算 score；`get_best_for_page()` 对跨页兜底也执行最低分限制 |
| BUG-002 | 修复 | 截图正文污染检测失败后回退到 baseline 继续保存错误图片 | 2026-06-05 | 已修复 | 新增 `detect_text_pollution()`；Figure/Table 主循环遇到污染结果直接拒绝当前候选 |
| BUG-003 | 修复 | 双栏右栏 X 方向裁剪把 `margin_right` 当作边距数值使用，导致右栏边界计算错误 | 2026-06-05 | 已修复 | `refine_clip_x_range()` 改为把 `layout_model.margin_right` 作为页面右边界坐标使用 |
| BUG-004 | 修复 | 同页相邻 Figure/Table caption 未限制 baseline 窗口，导致连续图表场景混截上一张或下一张图 | 2026-06-05 | 已修复 | 新增 `limit_clip_by_neighbor_captions()`；Figure/Table baseline 使用同页高分 caption 收紧 y 边界，DeepSeek Figure 3 已验证不再混入 Figure 2 |
| BUG-005 | 修复 | Figure 精裁结果低于高度/面积比例阈值时被误回退到 baseline，导致正文重新混入截图 | 2026-06-05 | 已修复 | Figure 路径将比例阈值调整为软告警：未污染且不过窄的精裁结果会保留；Table 路径保持严格回退，避免正文段落误保留为表格 |
| BUG-006 | 修复 | PDF-to-Markdown 自定义 `blocks-json/report-json` 父目录未创建，且相对 `asset-dir` 与资产提取文本输出错误落到 PDF 源目录 | 2026-06-06 | 已修复 | `pdf_to_markdown.py` 现在以 Markdown 输出目录为相对资源根，自动创建 JSON 父目录，并向资产提取显式传入 `--out-text` |
| BUG-007 | 修复 | `--debug-visual` 因阶段对象字段和 PDF 后端调用不兼容而静默失败，且输出未写入附件记录 | 2026-06-06 | 已修复 | 统一通过 `create_debug_stage()` 创建阶段信息，改用后端兼容的 `dpi` 渲染，并将画线图与图例写入 `debug_artifacts` |
| BUG-008 | 修复 | Table caption 位于表格下方时仍默认向下截图，且无矢量线表格缺少方向证据 | 2026-06-06 | 已修复 | Table 局部方向判定加入短单元格行、宽正文行和 caption 距离等文本结构证据 |
| BUG-009 | 修复 | 短图表的固定最小高度和标题宽度门槛导致章节标题混入截图 | 2026-06-06 | 已修复 | 版式裁剪允许标题作为远端边界，并降低短内容最小高度限制 |
| BUG-010 | 修复 | Table 精裁被通用比例回退和正文污染检测误拒绝，导致 FunAudio 多个表格缺失或混入正文 | 2026-06-06 | 已修复 | 新增表格文本结构识别和连续表格行带裁剪；已确认的表格行带可绕过通用高度回退与远端宽文本清理 |
| BUG-011 | 修复 | 两单元格小节标题被误识别为表头，导致 FunAudio Table 4 混入章节标题 | 2026-06-06 | 已修复 | 两单元格行只有横跨大部分候选宽度时才视为表格行 |
| BUG-012 | 修复 | GPT-5 System Card 的短表、单文本块表格被拒绝，部分表格被对象裁切缩成局部列 | 2026-06-06 | 已修复 | 表格行带增加弱结构模式；短表支持三行结构验收；可靠行带成立且最终 X 范围异常窄时恢复 baseline 宽度 |
| BUG-013 | 修复 | 表格方向评分把短数字单元格误当页脚，并被相邻 Figure、下一张表和章节标题干扰 | 2026-06-06 | 已修复 | 页脚过滤限定到页面底部；方向评分改用最近结构化多单元格行；编号式章节标题不再作为稀疏表格尾行 |
| BUG-014 | 修复 | Gemini 正文句子 `Table 4, we compare...` 被当作图注，真实 Table 4 未提取 | 2026-06-06 | 已修复 | 新增该类正文引用模式，并在 Table 扫描入口实际调用 `is_caption_reference()` 跳过引用候选 |

## 调整事项

| ID | 动作 | 事项 | 完成日期 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- |
| ADJ-001 | 调整 | 项目定位从“PDF 论文图表提取与摘要脚本”调整为正式 Skill 项目 | 2026-06-05 | 已完成 | Skill 目标明确为 PDF 转 Markdown、PDF 带图摘要、完整处理流程三类能力 |
| ADJ-002 | 调整 | 正式 Skill 工作目录确定为 `skills/pdf-markdown-summary/` | 2026-06-05 | 已完成 | `SKILL.md`、`references/`、`examples/`、`scripts/` 均以该目录为最新版事实来源 |
| ADJ-003 | 调整 | 旧版脚本和旧资料统一归档到 `old-version/` | 2026-06-05 | 已完成 | `old-version/` 仅供参考，不再修改和维护 |
| ADJ-004 | 调整 | `docs/` 目录重新分层 | 2026-06-05 | 已完成 | `docs/1-archive/` 存旧文档，`docs/2-plans/` 存当前计划，`docs/3-ref/` 只读不写 |
| ADJ-005 | 调整 | `AGENTS.md` 从长说明书压缩为执行约束清单 | 2026-06-05 | 已完成 | 保留目录职责、只读规则、Skill 目录规则、task-list 记录规则和基础验证规则 |
| ADJ-006 | 调整 | 根目录启用 `task-list.md` 作为后续任务记录文件 | 2026-06-05 | 已完成 | 参考 `examples/task-list.md` 的分类和字段创建，本次未修改样例文件 |
| ADJ-007 | 调整 | 统一正式 Skill 命名为 `pdf-markdown-summary` | 2026-06-05 | 已完成 | 目录已改为 `skills/pdf-markdown-summary/`，`SKILL.md` frontmatter `name` 已改为 `pdf-markdown-summary`，当前文档引用已同步 |
| ADJ-008 | 调整 | 修复 `skill-creator` 审查发现的 Skill 规范缺口 | 2026-06-05 | 已完成 | 新增 `agents/openai.yaml`；删除 Skill 内 `examples/README.md`；清理 `.DS_Store`、`__pycache__` 和 `.pyc` 发布垃圾文件 |

## 检查事项

| ID | 动作 | 事项 | 完成日期 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- |
| CHK-001 | 检查 | 确认现有 PDF skill 能支撑 PDF 转 Markdown，但不是一键专用转换器 | 2026-06-05 | 已完成 | 明确普通 PDF 可提取文本/表格/图片后组织为 Markdown，扫描版 PDF 需要 OCR fallback |
| CHK-002 | 检查 | 对照 `wangminle/docs-to-markdown` 思路，梳理当前项目实现 PDF-to-Markdown 所需改造 | 2026-06-05 | 已完成 | 结论为需要独立 `pdf_to_markdown` 能力、OCR fallback、表格 Markdown 化、图片抽取和结构清洗 |
| CHK-003 | 检查 | 检查根目录 `scripts/` 与 Skill 内 `scripts/` 的同步关系 | 2026-06-05 | 已完成 | 之前已按 `diff -qr` 排除缓存文件核对，确认 Skill 脚本与根目录脚本保持一致 |
| CHK-004 | 检查 | 读取 `examples/task-list.md` 的分类和字段 | 2026-06-05 | 已完成 | 仅参考样例结构，未修改 `examples/` 中的内容 |
| CHK-005 | 检查 | 核对新建 `task-list.md` 和样例文件状态 | 2026-06-05 | 已完成 | 已读取根目录清单结构，并通过 `git diff -- examples/task-list.md` 确认样例文件无改动 |
| CHK-006 | 检查 | 使用 `skill-creator` 规范完整检查 `skills/pdf-markdown-summary/` | 2026-06-05 | 已完成 | `quick_validate.py` 通过；三个入口脚本 `--help` 通过；`compileall` 通过；发现目录名含 `&`、frontmatter 名称与目录不一致、缺少推荐 `agents/openai.yaml`、存在 `examples/README.md` 和缓存/系统文件等规范问题 |
| CHK-007 | 检查 | 复核 Skill 命名规范第 1、2 点修复结果 | 2026-06-05 | 已完成 | `quick_validate.py skills/pdf-markdown-summary` 通过；三个入口脚本 `--help` 通过；当前文件中已无 `pdf-markdown-&-summary` 残留引用 |
| CHK-008 | 检查 | 复核 Skill 规范缺口修复结果 | 2026-06-05 | 已完成 | `quick_validate.py skills/pdf-markdown-summary` 通过；三个入口脚本 `--help` 通过；确认 Skill 内无 README 类辅助文档，发布目录无 `.DS_Store`、`__pycache__`、`.pyc` |
| CHK-009 | 检查 | 提交前检查 GitHub 与本地 Git 状态 | 2026-06-05 | 已完成 | `main` 与 `origin/main` 同步；确认远端仓库为 `wangminle/skills-pdf-markdown-summary`；`old-version/` 既有文件修改为换行符变化，不纳入本次 stage |
| CHK-010 | 检查 | 提交前重新运行基础验证 | 2026-06-05 | 已完成 | `python3 -m compileall skills/pdf-markdown-summary/scripts` 通过；三个入口脚本 `--help` 通过；排除 `old-version/` 后 `git diff --check` 通过 |
| CHK-011 | 检查 | 清理 `main` 历史中的重复提交与空 merge | 2026-06-05 | 已完成 | 已保留备份分支 `codex-main-before-rebase-20260605`；删除重复 patch `760a1d1`、`a02a33c` 和空 merge `dc38520`；保留非空 merge 内容为普通提交；新旧树内容一致 |
| CHK-012 | 检查 | 将 `V0.2.1` 的三次提交压缩为单个提交 | 2026-06-05 | 已完成 | 已保留备份分支 `codex-main-before-v021-squash-20260605`；将 `c9b8737`、`8a353c2`、`5031fe7` 重写为单个 `aef4f25`；新旧 `main` 顶端树内容一致 |
| CHK-013 | 检查 | 逐张检查 `tests/results/20250605` 下 140 张图表截图效果 | 2026-06-05 | 已完成 | 结论为代码有修复入口但实际输出未达标，主要问题是 caption 索引未评分和污染结果仍被保存 |

## 测试数据

| ID | 动作 | 事项 | 完成日期 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- |
| TST-001 | 开发 | 新增 caption 锚点与正文污染回归测试 | 2026-06-05 | 已完成 | 新增 `tests/scripts/test_caption_anchor_quality.py`，覆盖候选评分、最低分过滤、正文污染检测和同页相邻 caption 边界限制；`run_all.py --skip-golden` 当前 146 通过、0 失败 |
| TST-002 | 检查 | 使用 Basic Benchmark 7 个 PDF 重新实测最终图表抽取效果 | 2026-06-05 | 已完成 | 输出位于 `tests/results/20260605/*_after_final_accept/`；7 个 PDF 共写入 113 张有效图表截图，其中 figures=69、tables=44 |
| TST-003 | 检查 | 实测 PDF-to-Markdown 导出功能并补充 CLI 输出路径回归测试 | 2026-06-06 | 已完成 | 新增 `tests/scripts/test_pdf_to_markdown_cli.py` 并接入 `run_all.py`；`run_all.py --skip-golden` 当前 149 通过、0 失败；DeepSeek Markdown 导出产物位于 `tests/results/20260606/DeepSeek_V3_2_markdown_export_fixed2/` |
| TST-004 | 检查 | 反复对照画线输出验证 DeepSeek_V3_2 与 FunAudio-ASR 截图区域 | 2026-06-06 | 已完成 | 最终输出位于 `tests/results/20260606-012/`；逐图核对 DeepSeek 4 图 + 1 表、FunAudio 4 图 + 8 表均完整且未混入正文/章节标题；`run_all.py --skip-golden` 为 158 通过、0 失败 |
| TST-005 | 检查 | 使用 GPT-5 System Card、Gemini 2.5 Report 扩展验证截图算法，并确保 DeepSeek/FunAudio 不退化 | 2026-06-06 | 已完成 | 最终输出位于 `tests/results/20260606-022/`；GPT-5 为 31 图 + 26 表，Gemini 为 14 图 + 12 表；画线与总览目视确认 GPT Table 7/8、Gemini Table 3/4/11 等关键边界正确；DeepSeek 4 图 + 1 表、FunAudio 4 图 + 8 表与 `20260606-012` 逐图 SHA-256 完全一致；`run_all.py --skip-golden` 为 166 通过、0 失败 |

## 文档维护

| ID | 动作 | 事项 | 完成日期 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- |
| DOC-001 | 文档 | 写入 PDF-to-Markdown 重构出发点与五步实施路径 | 2026-06-05 | 已完成 | 文档位于 `docs/PDF-to-Markdown重构出发点与实施路径-20260605.md` |
| DOC-002 | 文档 | 新增 PDF Markdown Summary Skill 设计文档 | 2026-06-05 | 已完成 | 文档位于 `docs/2-plans/2026-06-05-pdf-summary-agent-skill-design.md` |
| DOC-003 | 文档 | 新增 PDF Markdown Summary Skill 实施计划 | 2026-06-05 | 已完成 | 文档位于 `docs/2-plans/2026-06-05-pdf-summary-agent-skill-implementation-plan.md` |
| DOC-004 | 文档 | 重写根目录 `README.md` | 2026-06-05 | 已完成 | 中文在前、英文在后，简要说明 Skill 作用、效果、安装和使用方法 |
| DOC-005 | 文档 | 更新根目录 `AGENTS.md` | 2026-06-05 | 已完成 | 记录目录职责、`old-version/` 规则、`docs/3-ref/` 只读规则和 `task-list.md` 规则 |
| DOC-006 | 文档 | 整理 `docs/` 下历史文档 | 2026-06-05 | 已完成 | 与当前重构无关的旧文档已移动到 `docs/1-archive/legacy-docs-before-skill-refactor-20260605/` |
| DOC-007 | 文档 | 创建根目录 `task-list.md` | 2026-06-05 | 已完成 | 参考 `examples/task-list.md` 的分类和字段，并整理今天对话形成的任务记录 |
| DOC-008 | 文档 | 在 `AGENTS.md` 中新增 Markdown 文档命名规则 | 2026-06-05 | 已完成 | 所有新建 Markdown 文档文件名必须增加 `-yyyyMMDD` 时间后缀 |
| DOC-009 | 文档 | 从 `AGENTS.md` 顶层目录职责中删除根目录 `scripts/` 说明 | 2026-06-05 | 已完成 | 按用户要求移除“当前开发源码与兼容入口；有效更新需要同步到正式 Skill”这一条 |
| DOC-010 | 文档 | 提交前修正 `README.md` 的过期结构说明和空白问题 | 2026-06-05 | 已完成 | 将根目录 `scripts/` 表述改为 Skill 包内脚本源码，移除不存在的 Skill `examples/README.md` 说明，并修复 `git diff --check` 报告的 README 空白问题 |
| DOC-011 | 文档 | 提交前规范化正式 Skill 脚本和当前文档的换行与行尾空白 | 2026-06-05 | 已完成 | 仅处理正式 Skill、当前 docs、README、AGENTS、task-list 和 examples 样例；未处理 `docs/3-ref/` 参考文件和既有 `old-version/` 文件 |
| DOC-012 | 文档 | 在 `AGENTS.md` 中新增 Basic Benchmark 实测输出目录规则 | 2026-06-05 | 已完成 | 实际 PDF 文档测试优先使用 `tests/basic-benchmark/`，输出写入 `tests/results/<YYYYMMDD>/<pdf-name>/`，并按 `markdown/`、`assets/`、`images/`、`txt/` 分层保存 |
| DOC-013 | 文档 | 记录 DeepSeek_V3_2 与 FunAudio-ASR 截图区域调优和修复完整过程 | 2026-06-06 | 已完成 | 新增 `docs/PDF图表截图区域调优与修复完整记录-20260606.md`，记录初始问题、逐轮调优、根因、最终流程、代码改动、验证结果和后续建议；已核对文档关键记录并通过 `git diff --check` |
| DOC-014 | 文档 | 补充 GPT-5 System Card 与 Gemini 2.5 Report 扩展调优全过程 | 2026-06-06 | 已完成 | 在 `docs/PDF图表截图区域调优与修复完整记录-20260606.md` 增补批次 `20260606-013` 至 `20260606-022`、新增根因、最终结果和回归结论 |

## 功能开发

| ID | 动作 | 事项 | 完成日期 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- |
| DEV-001 | 开发 | 创建正式 Skill 包 `skills/pdf-markdown-summary/` | 2026-06-05 | 已完成 | 包含 `SKILL.md`、`references/`、`examples/`、`scripts/` |
| DEV-002 | 开发 | 新增 PDF 转 Markdown 入口能力 | 2026-06-05 | 已完成 | 入口脚本为 `skills/pdf-markdown-summary/scripts/pdf_to_markdown.py`，核心实现位于 `scripts/core/pdf_to_markdown.py` |
| DEV-003 | 开发 | 新增 PDF 带图摘要素材准备入口能力 | 2026-06-05 | 已完成 | 入口脚本为 `skills/pdf-markdown-summary/scripts/summarize_pdf.py`，复用现有图表提取与摘要业务逻辑 |
| DEV-004 | 开发 | 新增完整处理流程入口能力 | 2026-06-05 | 已完成 | 入口脚本为 `skills/pdf-markdown-summary/scripts/process_pdf.py`，用于串联 Markdown 转换和摘要素材准备 |
| DEV-005 | 开发 | 补充 Skill 参考文档与示例说明 | 2026-06-05 | 已完成 | 包含 `references/pdf-to-markdown.md`、`references/pdf-summary.md`、`examples/README.md` |
