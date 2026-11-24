from pathlib import Path
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET
import json
import unicodedata
REGISTRY = json.loads((Path(__file__).resolve().parents[2] / "design/4-analysis/PDF功能模块编号表-20260930.json").read_text(encoding="utf-8"))
FUNCTIONS = REGISTRY["features"]

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'design' / '4-analysis'
WORK = Path(__file__).resolve().parent
C = {'ink':'#192d40','muted':'#62758a','line':'#a8b7c6','blue':'#2563a6','teal':'#087f83','amber':'#b67a17','violet':'#7654ac','red':'#ba4d48'}
class SVG:
 def __init__(self,w,h,title,desc):
  self.w,self.h=w,h; self.bg=[];self.edges=[];self.nodes=[]
  self.start=f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-labelledby="title desc"><title id="title">{escape(title)}</title><desc id="desc">{escape(desc)}</desc><defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto" markerUnits="userSpaceOnUse"><path d="M0 0 L9 4.5 L0 9 Z" fill="#62758a"/></marker><marker id="data" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto" markerUnits="userSpaceOnUse"><path d="M0 0 L9 4.5 L0 9" fill="none" stroke="#087f83" stroke-width="1.6"/></marker><style>text{{font-family:'Hiragino Sans GB','PingFang SC','Noto Sans CJK SC',sans-serif;fill:#192d40}} .mono{{font-family:'DejaVu Sans Mono',monospace}} .muted{{fill:#62758a}}</style></defs>'''
  self.rect(0,0,w,h,'#f5f7fa',stroke='none',r=0,bg=True)
 def rect(self,x,y,w,h,fill='white',stroke='#dce4ec',r=14,bg=False,dash=False):
  s=f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}"'+(' stroke-dasharray="7 5"' if dash else '')+'/>'
  (self.bg if bg else self.nodes).append(s)
 def text(self,x,y,t,size=18,color=None,weight='400',mono=False,anchor='start'):
  self.nodes.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}"'+(' class="mono"' if mono else '')+(f' style="fill:{color}"' if color else '')+f'>{escape(t)}</text>')
 def lines(self,x,y,lines,size=17,gap=28,color=None,mono=False,max_width=None):
  for i,t in enumerate(lines):
   units=sum(1 if unicodedata.east_asian_width(c) in ('W','F') else .62 for c in t)
   fitted=min(size,max_width/max(units,1)) if max_width else size
   self.text(x,y+i*gap,t,fitted,color,mono=mono)
 def card(self,x,y,w,h,title,code=(),body=(),accent='blue',fill='white',dash=False):
  groups = self.card_groups(title, x)
  ids = [f['id'] for f in FUNCTIONS if f['group'] in groups]
  self.nodes.append('<g data-feature-domains="'+','.join('F'+g for g in groups)+'" data-feature-ids="'+','.join(ids)+'"><title>'+escape(title+'；相关功能域索引（供反查，不表示本阶段逐项执行）：'+', '.join(ids))+'</title>')
  self.rect(x,y,w,h+20,fill,C[accent] if dash else '#d8e2ec',dash=dash)
  self.nodes.append(f'<rect x="{x}" y="{y+15}" width="4" height="{h-10}" rx="2" fill="{C[accent]}"/>')
  badges = '  /  '.join('F'+g for g in groups) if groups else 'EXT-01' if 'Agent' in title or '最终阅读摘要' in title else 'INPUT' if '输入' in title else '产物'
  self.text(x+20,y+17,badges,11,C[accent],'600',mono=True)
  self.text(x+20,y+42,title,20,C[accent],'600')
  self.lines(x+20,y+70,code,14,22,mono=True,max_width=w-40)
  self.lines(x+20,y+74+22*len(code),body,16,25,max_width=w-40)
  self.nodes.append('</g>')
 def card_groups(self,title,x):
  mappings={
  '统一入口':['01','24'], '第一步：生成 Markdown':['21'], '提取正文与标题':['05','21'],
  '统一图表提取入口':['01'], '预检、文本与版式证据':['02','05','06','18'],
  '先处理 Figure':['09'], '再处理 Table':['10','15'], '汇总与索引落盘':['17','20','22'],
  '可追溯的资产包':['22'], '质量筛选 + 正文插图':['16','21'], '渲染与结构化保存':['21'],
  'Markdown 交付':['21'], '第二步：准备摘要材料':['01'],
  '入口参数与共享 PDF 接口':['01','02','03'], '文本、基础版式与页面证据':['05','06'],
  '题注身份与裁剪方向':['07','08'], '可选：先取得语义区域':['18'],
  '01  建立 baseline 大窗':['11'], '02  文字、对象与栏位精裁':['06','11','12'],
  '03  像素收边与远端清理':['11','12'], '04  类型专用补全':['13'] if x<700 else ['14'],
  '05  验收、回退与导出':['09' if x<700 else '10','16'],
  '共享辅助：日志与调试':['23'], '可选：提取完成后的配对与精修':['19','20'],
  '质量状态：控制进入 Markdown 的资产':['16'], 'Figure 的结果':['04','09'],
  'Table 的结果 + 自动恢复无题注续表':['04','10','15'],
  '先构建上下文，再执行可选后精修':['20','22'], '题注清单对账 + 最终资产与索引':['17','22']}
  return mappings.get(title,[])
 def arrow(self,points,dashed=False,data=False):
  d='M '+' L '.join(f'{x} {y}' for x,y in points)
  self.edges.append(f'<path d="{d}" fill="none" stroke="{C["teal"] if data else C["muted"]}" stroke-width="{2 if dashed else 2.3}" stroke-linejoin="round"'+(' stroke-dasharray="7 5"' if dashed else '')+f' marker-end="url(#{"data" if data else "arrow"})"/>')
 def label(self,x,y,t,color=None):
  self.text(x,y,t,15,color or C['muted'])
 def header(self,no,title,subtitle):
  self.text(54,58,f'PDF MARKDOWN SUMMARY  /  {no}',16,C['teal'],'600')
  self.text(54,108,title,36,C['ink'],'700')
  self.text(54,148,subtitle,19,C['muted'])
 def save(self,name):
  s=self.start+''.join(self.bg+self.edges+self.nodes)+'</svg>'; p=OUT/name;p.write_text(s, encoding="utf-8", newline="\n")
  ET.fromstring(s)

  return p

s=SVG(1900,2200,'PDF 脚本协作泳道图','当前工作区正式 scripts 的端到端流程。实线表示控制顺序，青色虚线表示数据传递。process 先调用 Markdown，再复用资产准备摘要。摘要由 Agent 撰写。')
s.header('01','拿到一份 PDF 后，脚本怎样接力？','正式目录 skills/pdf-markdown-summary/scripts/ · 当前工作区 0.6.12 · 2026-11-24')
s.rect(54,181,1792,94,'#eaf3f5',stroke='none')
s.lines(76,212,['编号读法：Fxx 是功能域；完整 Fxx.nnn 子功能编号见全集索引图与编号文档。卡片提示所涉及的功能域。','从上到下跟随实线；青色虚线传递数据。泳道表示职责边界，Python 主步骤顺序执行。'],18,30)
lanes=[(54,290,290,'① 输入与 Agent','#eef2f6'),(360,290,360,'② 业务编排 · core/','#edf3fb'),(736,290,330,'③ 文本与文档模型','#eef7f6'),(1082,290,365,'④ 图表资产提取','#fff8ec'),(1463,290,383,'⑤ 文件产物与交付','#f3eff8')]
for x,y,w,title,fill in lanes:
 s.rect(x,y,w,1645,fill,stroke='none',bg=True);s.text(x+18,y+35,title,20,weight='600')
s.card(73,357,252,119,'输入：paper.pdf',body=['检查路径；选择入口','推荐参数：robust'],accent='teal')
s.card(380,357,320,119,'统一入口',code=['scripts/process_pdf.py','→ core/process_pdf.py'],accent='blue')
s.arrow([(325,416),(380,416)])
s.card(380,523,320,144,'第一步：生成 Markdown',code=['core/pdf_to_markdown.py'],body=['先构建正文文档对象','然后调用图表提取器','公式碎片区域整块保留'])
s.arrow([(540,476),(540,523)]);s.label(551,505,'调用 main()')
s.card(755,523,292,144,'提取正文与标题',code=['lib/text_extract.py','lib/markdown.py'],body=['预检 + 结构化段落','构造 MarkdownDocument'],accent='teal')
s.arrow([(700,570),(755,570)])
s.arrow([(755,633),(722,633),(722,689),(540,689)],dashed=True,data=True);s.label(754,696,'返回文档对象（内存）',C['teal'])
s.card(1101,720,327,117,'统一图表提取入口',code=['core/extract_pdf_assets.py'],body=['默认启用 Figure 与 Table'],accent='amber')
s.arrow([(540,667),(540,711),(1065,711),(1065,778),(1101,778)])
s.label(670,738,'正文准备完毕 → 调用 extract_main()')
s.card(1101,884,327,151,'预检、文本与版式证据',code=['lib/env_priority.py','lib/text_extract.py'],body=['纯文本 / 段落 JSON / 版式模型','语义后端可选，默认关闭'],accent='amber')
s.arrow([(1264,837),(1264,884)])
s.card(1101,1073,327,109,'先处理 Figure',code=['lib/extract_figures.py'],body=['题注 → 方向 → 精裁 → 验收'],accent='amber')
s.arrow([(1264,1035),(1264,1073)])
s.card(1101,1220,327,109,'再处理 Table',code=['lib/extract_tables.py'],body=['表格边界 / 表注 / 自动续表'],accent='amber')
s.arrow([(1264,1182),(1264,1220)])
s.card(1101,1367,327,144,'汇总与索引落盘',code=['figure_contexts.py / assess.py','lib/output.py'],body=['可选 Layout 后精修；题注对账','写 PNG、文本、index.json'],accent='amber')
s.arrow([(1264,1329),(1264,1367)])
s.card(1482,1367,345,144,'可追溯的资产包',code=['images/*.png + index.json','text/paper.txt'],body=['页码、题注、裁剪框、状态','辅助 JSON / 日志 / 可选调试图'],accent='violet')
s.arrow([(1428,1440),(1482,1440)],dashed=True,data=True)
s.card(380,1372,320,166,'质量筛选 + 正文插图',code=['core/pdf_to_markdown.py','lib/assess.py'],body=['通过质量门的两类可入正文','按页码、类型、编号匹配题注','无匹配的可用资产追加到文末'])
s.arrow([(1101,1460),(700,1460)],dashed=True,data=True);s.label(773,1440,'读取 index.json',C['teal'])
s.card(755,1571,292,143,'渲染与结构化保存',code=['lib/markdown.py'],body=['输出 Markdown、结构化块与报告','图片链接写相对路径'],accent='teal')
s.arrow([(540,1538),(540,1642),(755,1642)])
s.card(1482,1571,345,143,'Markdown 交付',code=['paper.md','text/markdown_blocks.json','text/conversion_report.json'],body=['报告：ready / review / failed'],accent='violet')
s.arrow([(1047,1642),(1482,1642)],dashed=True,data=True)
s.card(380,1752,320,140,'第二步：准备摘要材料',code=['core/summarize_pdf.py'],body=['--reuse-existing：复用资产包','核对文件、PDF 文件名与哈希'])
s.arrow([(755,1693),(720,1693),(720,1728),(540,1728),(540,1752)])
s.label(380,1713,'返回成功后，由 process 再调用')
s.arrow([(1463,1435),(1453,1435),(1453,1735),(720,1735),(720,1820),(700,1820)],dashed=True,data=True)
s.card(73,1752,252,140,'Agent 撰写阅读摘要',body=['同时阅读全文与图表图片','理解方法、结果与局限','默认中文，并解释关键图表'],accent='teal')
s.arrow([(380,1820),(325,1820)])
s.card(1482,1752,345,140,'最终阅读摘要',code=['paper_阅读摘要-YYYYMMDD.md'],body=['由 Agent 编写','summarize 脚本只提示建议路径'],accent='violet')
s.arrow([(198,1892),(198,1935),(1654,1935),(1654,1892)],dashed=True,data=True)
s.rect(54,1970,1792,171,'white')
s.text(77,2003,'其他入口与执行边界',22,C['ink'],'600')
s.lines(77,2035,['pdf_to_markdown.py：直接进入第一步。summarize_pdf.py：不带 --reuse-existing 时先提取，再提示材料与摘要路径。','extract_pdf_assets.py：直接提取文本与图表，用于调参；其薄包装还保留历史导入接口。','提取失败：Markdown 仍可能写出，但报告为 failed、返回非零；process 随即停止。review 报告不会让 process 自动停止。'],18,29)
s.text(77,2132,'当前限制：--ocr auto / force 仅记录 not_implemented；--tables auto / structure 当前仍走截图资产路径。',17,C['red'])
s.save('PDF脚本协作泳道图-20260930.svg')

s=SVG(2100,2550,'PDF 图表提取模块协作展开图','图表提取内部的证据层、Figure 和 Table 精裁模块、可选 Layout 后端与最终资产汇总。模块按职责分组，不表示并行执行。')
s.header('02','展开资产提取：每个 lib 模块负责什么？','scripts/ 路径均相对正式 Skill；两条裁剪列用于对照职责，实际运行顺序仍为 Figure → Table。')
s.rect(54,180,1992,89,'#eaf3f5',stroke='none')
s.lines(75,213,['主线：准备证据 → 提取 Figure → 提取 Table → 图表上下文 → 可选 Layout 后精修 → 题注对账 → 索引落盘。','右侧紫色虚线框为可选扩展；基础字体 / 双栏版式模型默认开启，语义 Layout 后端默认关闭。'],18,28)
# Top evidence band
s.card(54,302,423,221,'入口参数与共享 PDF 接口',code=['core/extract_pdf_assets.py','lib/env_priority.py','lib/pdf_backend.py'],body=['解析 CLI / robust / 环境配置','统一 PDF 句柄、页面、文字、对象、渲染','主流程顺序组织下方模块'],accent='blue')
s.card(514,302,455,221,'文本、基础版式与页面证据',code=['lib/text_extract.py','lib/layout_model.py','lib/extract_helpers.py'],body=['预检；纯文本；结构化段落；字体与栏位','每页采集文字行、位图框与矢量图形','提供裁剪边界、密度与内容证据'],accent='teal')
s.arrow([(477,410),(514,410)])
s.card(1006,302,470,221,'题注身份与裁剪方向',code=['lib/caption_detection.py','lib/idents.py','lib/direction.py'],body=['候选评分、正文过滤、词形证据合并','统一编号解析与命名；判断 above / below','综合局部、全局及扫描结构墨迹证据'],accent='teal')
s.arrow([(969,410),(1006,410)])
s.card(1513,302,533,257,'可选：先取得语义区域',code=['lib/backends/base.py','lib/backends/pymupdf_layout.py','lib/regions.py'],body=['工厂 / 协议 → pymupdf4llm 区域提取','缓存；统一图、表、题注区域结构','显式启用后取得 LayoutResult','依赖缺失或异常：回到默认提取路径'],accent='violet',fill='#fbf9ff',dash=True)
s.arrow([(265,302),(265,284),(1779,284),(1779,302)],dashed=True)
# Figure / table grouped panels
for x,w,title,fill in [(54,705,'FIGURE · lib/extract_figures.py','#edf6f7'),(791,705,'TABLE · lib/extract_tables.py','#fff7e9')]:
 s.rect(x,586,w,1020,fill,stroke='none',bg=True);s.text(x+23,622,title,24,C['ink'],'600')
s.label(54,565,'以下模块在每个图 / 表候选的裁剪过程中协作；精裁失败先择阶段框回退，再验收。')
s.arrow([(1240,523),(1240,548),(406,548),(406,660)],data=True,dashed=True)
s.arrow([(1240,548),(1143,548),(1143,660)],data=True,dashed=True)
rows=[
(660,158,'01  建立 baseline 大窗',['lib/clip_limit.py'],['用题注方向建立窗口；限制相邻题注与正文边界','结合基础版式决定栏位与 X 范围']),
(852,172,'02  文字、对象与栏位精裁',['lib/text_trim.py','lib/object_refine.py'],['Phase A：去题注侧正文；Phase B：对象边缘对齐','结合 clip_limit.py 与 layout_model.py 约束边界']),
(1058,172,'03  像素收边与远端清理',['lib/pixel_detect.py','lib/far_side.py'],['Phase D：遮罩 autocrop 与原框文字保全','远端清理；X 单独收窄需对象支撑（F12.012）']),
(1264,144,'04  类型专用补全',[],[]),
(1442,136,'05  验收、回退与导出',['lib/acceptance.py  +  lib/assess.py'],['比例 / 正文污染 / 截断检查；择优保留或回退','记录状态、警告与最终裁剪框；渲染 PNG'])]
for x in (76,813):
 for y,h,title,code,body in rows:
  if y==1058 and x==813:
   body=['Phase D：文字遮罩辅助 autocrop；检测实际墨迹','远端正文清理与像素收边相互配合']
  if y==1264:
   if x==76:code=['lib/figure_post.py'];body=['补回图内标题、短标签与邻近图形','保护近题注边；清理页眉噪声']
   else:code=['lib/table_refine.py'];body=['恢复表头 / 表尾 / 宽度；保护跨栏单元格','补全横线、表注、边框；清理章节正文']
  s.card(x,y,661,h,title,code,body,accent='teal' if x==76 else 'amber')
 for y,h,_,_,_ in rows[:-1]:s.arrow([(x+330,y+h),(x+330,y+h+34)])
# Right optional post workflow
s.card(1513,629,533,169,'共享辅助：日志与调试',code=['lib/extraction_logger.py','lib/debug_visual.py'],body=['记录 run.log.jsonl / 事件 / run_end','debug 开关输出候选与阶段框叠图'],accent='blue')
s.card(1513,858,533,309,'可选：提取完成后的配对与精修',code=['lib/layout_integration.py','lib/page_scene.py / lib/pairing.py','lib/pipeline.py','lib/refiners/base.py','lib/refiners/figure.py / table.py','lib/quality.py'],body=['先生成冲突报告；再全页题注—内容配对','FigureRefiner / TableRefiner 做保守校正','身份、质量、覆盖率通过才替换框并重新渲染','否则保留原提取结果；输出三份 Layout 报告'],accent='violet',fill='#fbf9ff',dash=True)
s.arrow([(1779,559),(1779,603),(2058,603),(2058,1012),(2046,1012)],dashed=True)
s.card(1513,1210,533,368,'质量状态：控制进入 Markdown 的资产',code=['lib/assess.py / lib/quality.py'],body=['accepted：可插入','accepted_with_margin：可插入','review_required：暂不插入，进入 omitted','rejected：不插入，进入 omitted','','Markdown 入口使用 assess.markdown_insertable()',
'无 status 才按复核标记/警告兜底。','legacy 评估由 assess.py 写入 AttachmentRecord；','quality.py 也供可选 Layout 精修器使用。','状态是程序判断；仍需查看关键截图。'],accent='violet')
# Outputs row
s.card(54,1650,705,146,'Figure 的结果',code=['models.py → AttachmentRecord[]'],body=['记录图编号、页码、caption_bbox、final_bbox、PNG、状态','连同 Table 记录按主流程顺序汇总'],accent='teal')
s.arrow([(406,1578),(406,1650)])
s.card(791,1650,705,146,'Table 的结果 + 自动恢复无题注续表',code=['lib/table_continuation.py'],body=['extract_tables 末尾以续表标记 / 重复表头 / 横线补片段','--allow-continued 另管“重复题注”条目；二者机制不同'],accent='amber')
s.arrow([(1143,1578),(1143,1650)])
s.card(54,1850,940,168,'先构建上下文，再执行可选后精修',code=['lib/figure_contexts.py','lib/models.py'],body=['用 GatheredText + 已提取记录关联正文引用、章节与题注','写 figure_contexts.json；之后才进入右侧配对 / pipeline','因此上下文是在 Layout 替换裁剪框之前生成的'],accent='blue')
s.arrow([(406,1796),(406,1824),(524,1824),(524,1850)])
s.arrow([(1143,1796),(1143,1824),(524,1824)],dashed=True,data=True)
s.arrow([(994,1934),(1506,1934),(1506,1012),(1513,1012)],dashed=True)
s.card(1030,1850,1016,168,'题注清单对账 + 最终资产与索引',code=['lib/assess.py → lib/output.py'],body=['finalize_caption_inventory：对齐预期题注与导出记录；保留待复核缺口','写 index.json（含 PDF 哈希与状态）；可选 manifest CSV；清理本轮无索引图片','文本 JSON、版式 JSON、图表 PNG、日志 → 返回给 Markdown 或摘要材料入口'],accent='blue')
s.arrow([(994,1969),(1030,1969)])
s.arrow([(2046,1116),(2070,1116),(2070,1825),(1538,1825),(1538,1850)],dashed=True)
s.label(1108,1813,'可选分支结束后，仍回到同一汇总出口')
# supporting modules map all files
s.rect(54,2073,1992,404,'white')
s.text(77,2110,'其余 Python 文件：数据契约、Markdown 渲染与兼容导出层',24,C['ink'],'600')
s.lines(77,2150,['models.py：共享文本、题注、版式、附件记录数据类。','assets.py：Layout 候选、配对、裁剪、冲突报告数据类。','regions.py：语义区域坐标、页面与 LayoutResult。','markdown.py：MarkdownBlock / Document + 实际渲染实现。','markdown_models.py / markdown_render.py：历史导入兼容层。'],18,32)
s.lines(1053,2150,['refine.py：旧精裁 API 的兼容再导出层；实际实现在各专责模块。','__init__.py / core/__init__.py / lib/__init__.py：包与导出入口。','backends/__init__.py / refiners/__init__.py：后端与精修器导出。','四个 scripts/*.py：CLI 包装；四个 core/*.py：真实工作流。','tests/ 与 old-version/ 不参与这条正式处理链。'],18,32)
_st=json.loads((OUT/'PDF功能模块编号表-20260930.json').read_text(encoding="utf-8"))['stats'];_rf=_st['runtime_features'];_tf=_st['testing_features']
s.text(77,2350,f'功能编号：F01–F24 对应 {_rf} 项正式功能；F25–F26 对应 {_tf} 项评测/测试能力。全部叶编号见全集索引 SVG。',18,C['muted'])
s.text(77,2390,'产物默认目录：images/ 与 text/；Markdown 自定义 --out 时，它们相对于 Markdown 所在目录。',18,C['muted'])
s.text(77,2430,'F04：数据契约；F24：兼容导出。卡片附相关功能域的子编号索引供反查，不表示本阶段逐项执行。',18,C['muted'])
s.save('PDF图表提取模块展开图-20260930.svg')
print('Generated 2 XML-valid SVGs')
