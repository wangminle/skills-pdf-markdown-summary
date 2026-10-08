# GitHub Issue 修复审查报告（2026-10-06）

审查对象：GitHub 全部 8 个 issue（#2–#9），提交 `97eafff`（V0.6.8）及当前未提交修复。包括 issue 评论中的更正；#2 已明确“存疑资产不进入 Markdown”是设计，仅需解决可见性与误报。8 个 issue 当前仍为 OPEN。本轮只审查、复现与记录，没有修改业务源码、维护测试、编号资料，也没有提交或修改 GitHub 状态。

## 逐项结论

| Issue | 对应修复与当前证据 | 结论 |
| --- | --- | --- |
| [#2](https://github.com/wangminle/skills-pdf-markdown-summary/issues/2) | Alexa Figure 1 / Table 1 均恢复，实跑共 7 项；PARADISE 共 13 项且全部嵌入，无 object_truncation 误报；Figure 5 现为紧凑的对话截图；Figure 6 题注含完整的 `1997), with AVM tagging`。报告、index 与控制台已有嵌入统计和遗漏原因。 | 原报告四项在当前真实样本上已修复；无需恢复“无条件插入存疑图”的旧行为。 |
| [#3](https://github.com/wangminle/skills-pdf-markdown-summary/issues/3) | `--asset-dir` 保持相对 Markdown 目录解析的既定契约；help、SKILL、CLI reference 与控制台均已说明。真实三篇报告分别为 extracted/embedded 7/7、13/13、4/4，逐项有 referenced_in_markdown/embed_mode，遗漏逻辑与原因报告已有回归覆盖。 | 两项已修复。 |
| [#4](https://github.com/wangminle/skills-pdf-markdown-summary/issues/4) | 三篇共 24 张截图已目检，未复现整页正文当表格、跨元素污染、身份互换或 SASSI Table 4 重复导出；24 个 type/id/page 唯一，全部嵌入。旧假页码标题/表头标题已消除，但 PARADISE 仍有 6 个标题只剩编号，公式仍拆成多个段落。 | 资产相关问题在当前样本已修复；问题 5 的正文结构仍需继续修复（BUG-141、BUG-145）。 |
| [#5](https://github.com/wangminle/skills-pdf-markdown-summary/issues/5) | 加密 PDF、0 页 PDF × 两个正式 CLI，共 4 组合均 rc=1，含 PDF validation failed，均无 Traceback。正常三篇 PDF 转换没有被错误拒绝。 | 当前修复正确。 |
| [#6](https://github.com/wangminle/skills-pdf-markdown-summary/issues/6) | 非正 DPI/裁剪高度已被 argparse 拒绝；Figure 主保存路径清理零字节文件。但 Table 与 inventory 补裁路径未统一处理；注入真实保存失败行为后，补裁仍留下零字节 PNG，两入口均 rc=0。 | 部分修复，必须继续处理渲染失败与残骸（BUG-142）。 |
| [#7](https://github.com/wangminle/skills-pdf-markdown-summary/issues/7) | 原报的输出文件/目录自身冲突已提前返回 2；但父路径为已有文件、默认 text 目录为已有文件时，校验仍通过，后续抛 FileExistsError。 | 部分修复，必须补全父路径及隐式输出目录校验（BUG-143）。 |
| [#8](https://github.com/wangminle/skills-pdf-markdown-summary/issues/8) | Figure/Table 的日志与两个高度判据一致；Table 另含 table_band_is_valid，低 DPI 重建页回归实际通过。 | 修复正确。 |
| [#9](https://github.com/wangminle/skills-pdf-markdown-summary/issues/9) | 去除作者绝对路径，始终使用重建页；y0 断言按重建页标定，保留左右栏、上下边界和污染断言；完整测试中实际执行通过。 | 修复正确；新的独立测试脚本另有运行器缺陷（BUG-144），与此修复无关。 |

## 必须继续处理的代码问题

### BUG-141（P2）：多行标题序列化导致标题内容掉到正文

位置：[`lib/markdown.py:57`](../../skills/pdf-markdown-summary/scripts/lib/markdown.py#L57)。`gather_structured_text` 正确识别的 heading 块含文本 `2.1 \nTasks as Attribute Value Matrices`，`render_block` 只 strip，没有把内部换行转为空格。

实际 Markdown：

```markdown
## 2.1
Tasks as Attribute Value Matrices
```

PARADISE 另有 `2.4`、`2.5`、`3`、`4`、`5` 同类问题。不是纯数字标题识别器失效：块内仍有完整标题，而 Markdown 序列化把它拆开。应仅在 heading 渲染时将换行/连续空白归一为单行，补实际 Markdown 解析与真实样本回归，保留段落换行策略。

### BUG-142（P2）：渲染失败仍报成功，补裁留下零字节 PNG

位置：[`lib/assess.py:629`](../../skills/pdf-markdown-summary/scripts/lib/assess.py#L629)、[`lib/extract_tables.py:976`](../../skills/pdf-markdown-summary/scripts/lib/extract_tables.py#L976)、[`core/extract_pdf_assets.py:632`](../../skills/pdf-markdown-summary/scripts/core/extract_pdf_assets.py#L632)。Figure 主路径已有清理，但补裁 `pix.save` 异常直接 return None；Table 主路径也未统一清理。主入口仍无条件返回 0。

一页真实生成 PDF + 对 `fitz.Pixmap.save` 注入“先创建零字节文件再抛异常”的行为，重现 PyMuPDF 原 issue 的失败次序：提取入口 rc=0，留下 `Figure_1_p1_inventory_gap_Figure_1_Checkerboard_sample.png`（0 字节）；转换入口 rc=0，report.status=review，assets.exit_code=0，extracted=1/embedded=0。此为渲染/I/O 硬失败，不应只作为普通质量存疑。应统一各渲染出口的失败清理与错误传播；没有 caption 的文档或用户关闭某类资产时仍可正常成功。

补充参数缺口：`_positive_float` 只比较 `<=0`，`nan`/`inf` 被接受，正式 CLI 仍 rc=0；可一起加有限数校验。`--dpi 1` 也仍产出低分辨率 accepted 图片，但原修复建议是 `>0`，本轮没有擅自定义最低可用 DPI，作为后续质量策略观察。

### BUG-143（P2）：输出父路径与默认 text 目录冲突仍裸异常

位置：[`lib/output.py:59`](../../skills/pdf-markdown-summary/scripts/lib/output.py#L59)、[`core/pdf_to_markdown.py:551`](../../skills/pdf-markdown-summary/scripts/core/pdf_to_markdown.py#L551)。当前助手只检查目标本身，文件类型输出不检查父链；转换入口没有将 text_dir 纳入校验。

三个已复现反例：`--out blocker/out.md` 且 blocker 是文件；`--index-json blocker/index.json` 且 blocker 是文件（此时文本/图片已生成，最终写 index 才失败）；Markdown 所在目录的 text 是文件（即使 images/tables 都关闭仍失败）。应在写盘前校验全部输出目录和最近存在的祖先，并将实际写入时的 OSError 转成可读错误；保留已有文件内容。

### BUG-144（P3）：新测试脚本独立运行固定失败

位置：[`test_issue_regressions_20261006.py:198`](../../tests/scripts/test_issue_regressions_20261006.py#L198)。`main_test` 对所有测试传入 Path(td)，其中 `test_parser_accepts_positive_geometry()` 不接收参数。直接运行脚本为 9 通过、1 失败、rc=1；pytest 直接收集并调用该函数，所以 620 项全绿无法发现此问题。应统一该测试签名或采用 pytest 作为独立入口。

### BUG-145（P2）：公式仍拆成不可可靠消费的多个段落

PARADISE Markdown L352–355 仍为 `P(A) - P(E)`、`K--` 与空行后的 `1 - P(E)`；分子、分母和等式关系没有作为完整公式保留。其他 P(E)/P(A) 公式也有同类 OCR 碎片。现有标题守卫消除了把分母变成 heading 的问题，但没有完成 #4 的公式区域保留诉求。应基于原页证据保留完整公式区域（例如独立截图/有边界的公式块），避免凭 OCR 碎片自动编造公式。详见原 PDF 第 4–5 页与本轮 Markdown；本轮未实现公式恢复。

## 维护门禁与验证

DOC-070：动态编号校验实际 rc=1，共 60 项失败。包括新测试文件不在编号表内、源码哈希陈旧、助手未归属、行号与实现引用漂移。前轮“待以后同步”的理由不能满足 AGENTS 第 9 节收尾要求。应对已有功能更新实现引用/职责/参数，对独立新能力才追加编号，并同步三件套及有实际变化的图示。本轮仅审查，未改函数或职责，不替前轮做不完整同步。

| 验证 | 当前结果 |
| --- | --- |
| `python3 -m pytest tests/scripts/ -q` | 620 passed、0 failed、0 skipped，rc=0；golden 默认纳入。8 份 benchmark 当前产物的源码指纹均匹配，复用 20261006-001，与已有基准比较，未更新 golden。 |
| 三篇原始 PDF，正式 pdf_to_markdown CLI，images=figures/tables=screenshot/preset=robust | Alexa 7/7、PARADISE 13/13、SASSI 4/4，rc=0、ready；24 张截图目检，无原报资产污染/重复；与 20261002-003 的 caption/final_bbox/status 零漂移，原 PDF SHA256 不变。 |
| 四正式入口 `--help` | 4/4 通过。 |
| `python3 -m compileall -q skills/pdf-markdown-summary/scripts tests/scripts tests/eval` | 通过。 |
| `git diff --check` | 通过。 |
| 加密/0 页 PDF × 两入口独立进程验证 | 4/4 正确非零退出且无 traceback。 |
| 输出冲突、渲染硬失败、多行 heading、独立测试运行器补充反例 | 已确认上述遗漏；这些反例未被现有 620 项覆盖。 |
| `verify_numbering_dynamic_20260930.py` | 60 项失败，rc=1。 |
| task-list skill 的 `check --file task-list.md` | 本轮写前通过；写后结果记录于 CHK-042。 |

证据目录：[`tests/results/20261006-002/issue-audit/assets/`](../../tests/results/20261006-002/issue-audit/assets/)，含 GitHub issue 快照、完整测试日志、检查日志、counterexamples.json、actual-geometry.json、invalid-pdf.json、real-pdfs.json、real-checks.json、三篇截图联系表。一次性反例脚本位于 `experiments/issue-audit-20261006/probes.py`（忽略目录）。真实转换产物按 PDF 名称存放于同一批次的 markdown/images/txt 子目录。所有持久运行产物未写入 benchmark、design/2-ref 或 old-version。
