#!/bin/bash
# A/B: 同一条文本，唯一变量是「说话人处境」行是否进 prompt。
# A = 无 situation（旧版等价）；B = 带 situation。各跑 2 次以估温度噪声。
cd /Users/miaoliwang/.openclaw/workspace || exit 1

python3 - <<'EOF'
import json, copy
src = json.load(open('luna_sgp_pipeline_article_1877086054316976655.items.json'))
base = {'count': 1, 'items': [copy.deepcopy(src['items'][0])]}
for it in base['items']:
    it.pop('situation', None)
sit = copy.deepcopy(base)
sit['items'][0]['situation'] = {
    'role': '首席经济学家（外资投行）',
    'venue': '公开论坛·圆桌问答实录',
    'audience': '主办方主持人、同场其他经济学家、媒体在场',
    'source_type': '实录',
    'constraints': ['问答由主持人框定议题，只答被问到的题'],
}
json.dump(base, open('/tmp/ab_base.json', 'w'), ensure_ascii=False)
json.dump(sit, open('/tmp/ab_sit.json', 'w'), ensure_ascii=False)
print('inputs written')
EOF

for tag in base sit; do
  for i in 1 2; do
    echo "=== RUN $tag #$i ==="
    python3 luna_pipeline/l5_insight.py /tmp/ab_$tag.json /tmp/ab_${tag}_$i.md --provider deepseek 2>&1 | tail -6
    echo "exit=$?"
  done
done
echo "AB DONE"
