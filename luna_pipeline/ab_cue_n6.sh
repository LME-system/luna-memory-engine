#!/bin/bash
# 第二轮 A/B：验证「文本内线索」这条授权路径（无 situation 的条目也能判情境性）。
# 与第一轮的差别：items.json 带 text_excerpt（原文摘要），基座臂无 situation。
# 每臂 6 次（第一轮教训：温度 0.35 下单次对照会骗人）。
cd /Users/miaoliwang/.openclaw/workspace || exit 1
OUT=${OUT:-/tmp/ab4}
rm -rf $OUT && mkdir -p $OUT

python3 - <<'EOF'
import json
d = json.load(open('/Users/miaoliwang/.openclaw/workspace/luna_sgp_pipeline_article_1877086054316976655.items.json'))
it = d['items'][0]
ex = open('/Users/miaoliwang/.openclaw/workspace/news_raw_article_1877086054316976655.txt').read()[:1500]
base = dict(it); base.pop('situation', None); base['text_excerpt'] = ex
sit = dict(it); sit['text_excerpt'] = ex
if not sit.get('situation'):
    sit['situation'] = {"role": "外资行 / 机构首席经济学家", "venue": "公开论坛·圆桌实录",
                        "audience": "主持人、其他机构经济学家、媒体在场", "source_type": "实录",
                        "constraints": ["实录受提问框窄化，每人只被问一个问题"]}
json.dump({'count': 1, 'items': [base]}, open('/tmp/ab_cue_base.json', 'w'), ensure_ascii=False)
json.dump({'count': 1, 'items': [sit]}, open('/tmp/ab_cue_sit.json', 'w'), ensure_ascii=False)
print('probes written')
EOF

for tag in base sit; do
  for i in 1 2 3 4 5 6; do
    python3 luna_pipeline/l5_insight.py /tmp/ab_cue_$tag.json $OUT/${tag}_$i.md --provider deepseek >/dev/null 2>&1
    echo "run $tag #$i done"
  done
done
echo "RUNS DONE"
