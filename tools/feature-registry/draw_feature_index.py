from pathlib import Path
import runpy,json,math
from xml.sax.saxutils import escape
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'design/4-analysis'
# Reuse the same visual language, while generating the two annotated flow diagrams.
ns=runpy.run_path(str(Path(__file__).resolve().parent/'draw_flows.py'))
SVG,C=ns['SVG'],ns['C'];r=json.loads((OUT/'PDF功能模块编号表-20260930.json').read_text(encoding="utf-8"))
_st=r['stats'];_rf=_st['runtime_features'];_tf=_st['testing_features'];_defs=_st['definitions']
_nfiles=len({p for pre in ['skills/pdf-markdown-summary/scripts','tests/scripts','tests/eval'] for p in (ROOT/pre).rglob('*.py') if '__pycache__' not in p.parts})
def partition_groups(groups,column_count=3):
 base,extra=divmod(len(groups),column_count);columns=[];start=0
 for i in range(column_count):
  size=base+(1 if i<extra else 0);columns.append(groups[start:start+size]);start+=size
 return columns
def scope_range(groups,features,scope):
 ids=[g['id'] for g in groups if any(f['group']==g['id'][1:] and f.get('scope')==scope for f in features)]
 return f'{ids[0]}–{ids[-1]}' if ids else '无'
columns=partition_groups(r['groups'])
width=3140;card_w=990;gap=28;row_gap=28
heights=[sum(87+g['count']*row_gap+24 for g in col) for col in columns]
height=390+max(heights)+100
s=SVG(width,height,'PDF功能模块全集索引图',f'{len(r["groups"])}个功能域、{_rf+_tf}个编号功能。正式实现{_rf}个，测试与评测{_tf}个。每个编号可在配套功能全集和源码覆盖索引中查询。')
s.header('03','PDF 功能模块全集 · 每个能力都有自己的编号',f'{scope_range(r["groups"],r["features"],"runtime")}：正式实现 {_rf} 项  /  {scope_range(r["groups"],r["features"],"testing")}：测试与评测 {_tf} 项  /  {_nfiles} 个维护 Python 文件  /  2026-09-30')
s.rect(54,181,width-108,134,'#eaf3f5',stroke='none')
s.lines(78,217,['编号规则：Fxx 是功能域；Fxx.nnn 是域内功能模块。每个编号对应职责、适用状态、输入/输出与函数/类实现位置。','阅读路径：端到端泳道图 → 提取展开图 → 本全集索引 → 功能模块全集文档 → 源码覆盖反查。','功能按职责划分；一个函数可以实现多项功能，一项功能也可以引用多个函数。已有编号不因文件移动或排序变化重排。','EXT-01 是 Agent 的文本+图像阅读与摘要撰写步骤，不纳入 Python 已实现功能总数。'],18,27)
for col_i,col in enumerate(columns):
 x=54+col_i*(card_w+gap);y=356
 for g in col:
  group=g['id'][1:];fs=[f for f in r['features'] if f['group']==group]
  h=87+len(fs)*row_gap;color=C['violet'] if group in ['18','19','20','25','26'] else C['teal'] if group in ['03','04','05','06','07','08','11','12','13'] else C['blue']
  s.rect(x,y,card_w,h,'white')
  s.rect(x+1,y+1,card_w-2,57,'#f0f5fa',stroke='none')
  s.text(x+20,y+36,g['id']+'  '+g['name'],23,color,'600')
  s.text(x+card_w-23,y+36,str(g['count'])+' 项',17,C['muted'],anchor='end')
  for i,f in enumerate(fs):
   yy=y+83+i*row_gap;anchor=f['id'].replace('.','-').lower()
   s.nodes.append(f'<a href="PDF功能模块全集与编号-20260930.md#{anchor}" data-feature-id="{f["id"]}"><title>{escape(f["description"]+"；状态："+f["mode"])}</title>')
   s.text(x+20,yy,f['id'],15.5,color,'600',mono=True)
   s.text(x+131,yy,f['name'],16,C['ink'])
   s.nodes.append('</a>')
  y+=h+24
s.text(54,height-44,f'核对口径：全部 {_defs:,} 个声明均有功能归属。AST 覆盖检查用于防漏，不能替代运行验证或人工语义分析。',18,C['muted'])
s.save('PDF功能模块全集索引图-20260930.svg')
print('3 SVGs generated; all numbered capabilities:',len(r['features']))
