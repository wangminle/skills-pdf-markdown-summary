# PDF Summary Workflow

Use this workflow when the user asks for a PDF summary, paper reading note, or figure-aware summary.

For the full list of command-line flags, see `cli-options.md`.

## Preferred Flow

1. Run `scripts/summarize_pdf.py` to prepare text and image assets.
2. Read `text/<paper>.txt`.
3. Read `images/index.json` and inspect all `images/*.png`.
4. Rename figures and tables when needed.
5. Write `<paper>_阅读摘要-YYYYMMDD.md`.

## Command

```bash
python3 scripts/summarize_pdf.py --pdf "<paper>.pdf" --preset robust
```

## Summary Requirements

- Default language: Chinese.
- Length: 1500-3000 Chinese characters unless the user asks otherwise.
- Audience: senior undergraduate students in the same field.
- Include all important figures and tables.
- Use relative image links.

## Recommended Structure

```markdown
# <paper>_阅读摘要-YYYYMMDD

## 研究动机

## 方法

## 训练与后训练

## 评测与效率

## 局限与展望

## 结论
```

## Asset Rule

Always use both:

- `text/<paper>.txt`
- `images/*.png`

Do not write the summary from text only when figures are available.
