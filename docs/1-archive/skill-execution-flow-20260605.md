# pdf-markdown-summary Skill 执行流程图

> 生成日期: 2026-06-05（2026-06-13 更新：Step B 复用机制）

## 整体架构

```
                         pdf-markdown-summary Skill
                         ========================
                                    |
           +------------------------+------------------------+
           |                        |                        |
    process_pdf.py            pdf_to_markdown.py        summarize_pdf.py
    (完整工作流)                (PDF转Markdown)          (摘要准备)
           |                        |                        |
           +----------+-------------+          +-------------+
                      |                        |
               extract_pdf_assets.py   (提取资产 + 文本)
               (核心提取引擎)           |
                      |                |
                      v                v
                lib/ 组件库        输出产物
```

## 1. process_pdf.py 完整工作流

```
 process_pdf.py
     |
     |--[1] 加载 pdf_to_markdown.py
     |--[2] 加载 summarize_pdf.py
     |
     v
 +----+------------------------+
 | Step A: Markdown 转换       |
 |   pdf_to_markdown.py       |
 +----+------------------------+
     |
     |--[A1] pre_validate_pdf()    -> PDFValidationResult
     |--[A2] gather_structured_text() -> MarkdownDocument(blocks)
     |--[A3] extract_pdf_assets.main() -> images/ + text/
     |--[A4] _append_asset_section()   -> image blocks
     |--[A5] render_markdown()         -> {stem}.md
     |--[A6] write blocks.json + report.json
     |
     v
 +----+------------------------+
 | Step B: 摘要准备 (--reuse-existing) |
 |   summarize_pdf.py                   |
 +----+------------------------+
     |
     |--[B1] 复用 Step A 产物: 命中 index.json + text/ 则跳过提取 (BUG-019/M2)
     |--[B2] 未命中时才 extract_pdf_assets.main() -> images/ + text/
     |--[B3] 打印摘要建议路径
     |
     v
 输出: {stem}.md + images/ + text/ + 摘要提示
```

## 2. extract_pdf_assets.py 核心提取引擎

```
 extract_pdf_assets.py (main_modular)
     |
     |--[1] parse_args_modular()       -> argparse.Namespace
     |--[2] apply_preset_robust()      -> 设置稳健默认参数
     |--[3] 解析输出路径
     |       out_dir, text_dir, index_json, gathered_json ...
     |--[4] configure_logging()        -> run_id, run.log.jsonl
     |
     v
 +----+------------------------+
 | Phase 1: 文本提取           |
 +----+------------------------+
     |
     |--[P1-1] pre_validate_pdf()      -> 检查加密/文本层
     |--[P1-2] try_extract_text()      -> text/{stem}.txt
     |--[P1-3] gather_structured_text() -> gathered_text.json
     |--[P1-4] extract_text_with_format() -> layout_model.json (可选)
     |
     v
 +----+------------------------+
 | Phase 2: Figure 提取        |
 +----+------------------------+
     |
     |--[P2-1] build_caption_index()   -> CaptionIndex
     |       + find_all_caption_candidates()
     |       + select_best_caption()
     |
     |--[P2-2] compute_global_anchor() -> 方向判断(above/below)
     |
     |--[P2-3] 逐页扫描 caption
     |       + extract_figure_ident()  -> 标识符解析
     |       + ident_in_range()        -> 范围过滤
     |
     |--[P2-4] 4阶段裁剪精化
     |       + Phase A: text-trim    (文字遮罩裁边)
     |       + Phase B: object-align (对象区域对齐)
     |       + Phase C: layout-driven(版式驱动调整)
     |       + Phase D: autocrop     (自动裁剪白边)
     |
     |--[P2-5] 验收检查 + fallback
     |       + adaptive_acceptance_thresholds()
     |       + 不达标时回退到原始 clip
     |
     |--[P2-6] 渲染保存 PNG
     |       + Figure_{id}_{caption}.png
     |       + build_output_basename() -> 文件名生成
     |
     v
 +----+------------------------+
 | Phase 3: Table 提取         |
 +----+------------------------+
     |
     |--[P3-1~P3-6] 与 Figure 类似流程
     |       + 使用 Table 专用参数
     |       + table_clip_height / table_margin_x 等
     |       + Table_{id}_{caption}.png
     |
     v
 +----+------------------------+
 | Phase 4: 后处理与输出       |
 +----+------------------------+
     |
     |--[P4-1] build_figure_contexts() -> figure_contexts.json
     |       (图表在正文中的引用上下文)
     |
     |--[P4-2] write_manifest()        -> manifest.csv
     |--[P4-3] write_index_json()      -> index.json
     |       + figures[] + tables[] + items[]
     |       + meta (hash, preset, run_id)
     |       + layout + validation
     |
     |--[P4-4] prune_unindexed_images() -> 清理孤立 PNG
     |
     v
 输出产物:
   images/Figure_*.png       (图表图片)
   images/Table_*.png        (表格图片)
   images/index.json         (索引清单)
   images/manifest.csv       (CSV 清单)
   images/figure_contexts.json (引用上下文)
   images/layout_model.json  (版式模型)
   images/run.log.jsonl      (结构化日志)
   text/{stem}.txt           (提取文本)
   text/gathered_text.json   (结构化文本)
```

## 3. lib/ 组件库依赖关系

```
                    models.py (数据结构)
                    AttachmentRecord, GatheredText, ...
                    /    |    \     \      \
                   /     |     \     \      \
        idents.py   env_priority.py   extraction_logger.py
        (正则/标识)  (参数优先级)     (日志系统)
            |
     +------+------+
     |             |
 caption_detection   direction.py
 (Caption 检测)     (方向判断)
     |             |
     v             v
 extract_figures.py  extract_tables.py
 (Figure 提取)       (Table 提取)
     |             |
     +------+------+
            |
      figure_contexts.py
      (引用上下文构建)
            |
            v
        output.py
        (索引/清单/清理)
            |
            v
        index.json + manifest.csv
```

```
  text_extract.py (文本提取/验证)
  pdf_backend.py  (PDF 后端抽象)
  layout_model.py (版式模型)
  refine.py       (裁剪精化)
  debug_visual.py (调试可视化)
  markdown_models.py (Markdown 数据结构)
  markdown_render.py (Markdown 渲染)
```

## 4. 数据流转总览

```
 PDF 文件 (输入)
     |
     v
 +---+---+---+---+---+---+---+---+
 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
 +---+---+---+---+---+---+---+---+
  |   |   |   |   |   |   |   |
  v   v   v   v   v   v   v   v
 txt  gt  lm  fig tbl ctx idx log
  |   |   |   |   |   |   |   |
  |   |   |   |   |   |   |   v
  |   |   |   |   |   |   | run.log.jsonl
  |   |   |   |   |   |   v
  |   |   |   |   |   | index.json
  |   |   |   |   |   v
  |   |   |   |   | figure_contexts.json
  |   |   |   |   v
  |   |   |   |   Table_*.png
  |   |   |   v
  |   |   |   Figure_*.png
  |   |   v
  |   |   layout_model.json
  |   v
  |   gathered_text.json
  v
  {stem}.txt
     |
     v (pdf_to_markdown.py 读取上述所有产物)
     |
  {stem}.md (最终 Markdown 输出)
```

## 5. 三种使用场景

```
 场景 A: 只提取资产
 $ python extract_pdf_assets.py --pdf paper.pdf --preset robust
 输出: images/ + text/ (不生成 Markdown)

 场景 B: PDF 转 Markdown
 $ python pdf_to_markdown.py --pdf paper.pdf --preset robust
 输出: {stem}.md + images/ + text/

 场景 C: 完整处理 (Markdown + 摘要)
 $ python process_pdf.py --pdf paper.pdf --preset robust
 输出: {stem}.md + images/ + text/ + 摘要提示
```