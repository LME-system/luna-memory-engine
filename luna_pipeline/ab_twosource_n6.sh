#!/bin/bash
# 第三条验证：同一位发言人 / 同一场论坛的「两个来源」对照。
#   A = 圆桌实录 1877086054316976655（张斌主持，刘元春/陆挺/邢自强/汪涛）
#   B = 专题稿/专访 cbgc7971942（川观·金融投资报，邢自强）
# 两臂都不填 situation —— 只靠「文本内线索」这条路，看 L5 能不能把
# 「被提问框窄化」认出来（A 有主持人限定句，B 是自己选的结构）。
# 每臂 = 同一份 items.json 跑 6 次（温度 0.35，单次对照会骗人）。
cd /Users/miaoliwang/.openclaw/workspace || exit 1
OUT=${OUT:-/tmp/ab6}
rm -rf "$OUT" && mkdir -p "$OUT"

python3 - <<'PY'
import json
A='luna_sgp_pipeline_article_1877086054316976655.items.json'
B='luna_sgp_pipeline_article_cbgc7971942.items.json'
EX={'1877086054316976655':'news_raw_article_1877086054316976655.txt',
    'cbgc7971942':'news_raw_article_cbgc7971942.txt'}
items=[]
for p in (A,B):
    it=json.load(open(p))['items'][0]
    it.pop('situation',None)                      # 两臂都不给处境
    it['text_excerpt']=open(EX[it['id']],encoding='utf-8').read()[:1500]
    items.append(it)
json.dump({'count':len(items),'items':items},open('/tmp/ts_pair.json','w'),ensure_ascii=False)
print('probes written:',[i['id'] for i in items])
PY

for i in 1 2 3 4 5 6; do
  python3 luna_pipeline/l5_insight.py /tmp/ts_pair.json "$OUT/run_$i.md" --provider deepseek >/dev/null 2>&1
  echo "run #$i done"
done

python3 - "$OUT" <<'PY'
import re,sys,glob,os
d=sys.argv[1]
def load(p):
    t=open(p,encoding='utf-8').read()
    m=re.search(r'缺失分类: 文本内 (\d+) \| 情境性 (\d+)（处境码本 (\d+) / 文本内线索 (\d+)） \| 未定 (\d+)',t)
    g=re.search(r'无依据降级: (\d+) 条',t)
    obs=[]
    for line in t.splitlines():
        mm=re.match(r'^- \[([^\]]+)\](.*)（证据: ([^）]*)）\s*$',line)
        if mm: obs.append((mm.group(1),mm.group(3),mm.group(2)[:50]))
    return (tuple(map(int,m.groups())) if m else None, int(g.group(1)) if g else 0, obs)
print('==== 逐次 ====')
agg={}
for f in sorted(glob.glob(f'{d}/run_*.md')):
    cls,gat,obs=load(f)
    per={}
    for tag,ids,_ in obs:
        for i in ids.split(','):
            i=i.strip()
            per.setdefault(i,[]).append(tag)
    print(os.path.basename(f),'缺失分类',cls,'降级',gat)
    for k,v in per.items(): print('    ',k,v)
    for k,v in per.items(): agg.setdefault(k,[]).append(v)
print('==== 汇总（6 次）====')
for k,v in agg.items():
    sit=[x for run in v for x in run if '情境性' in x]
    cue=[x for x in sit if '线索' in x or '观察' in x]
    tex=[x for run in v for x in run if '文本内' in x]
    print(f'  {k}: 情境性 {len(sit)}（其中走线索 {len(cue)}） | 文本内 {len(tex)} '
          f'| 出现情境性的 run 数 {sum(1 for run in v if any("情境性" in x for x in run))}/{len(v)}')
PY
echo "AB6 DONE"
