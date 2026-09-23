#!/bin/bash
# 扩大样本：每臂 6 次，统计「情境性」标签的出现率与落点。
cd /Users/miaoliwang/.openclaw/workspace || exit 1
OUT=/tmp/ab3
rm -rf $OUT && mkdir -p $OUT

for tag in base sit; do
  for i in 1 2 3 4 5 6; do
    python3 luna_pipeline/l5_insight.py /tmp/ab_$tag.json $OUT/${tag}_$i.md --provider deepseek >/dev/null 2>&1
    echo "run $tag #$i done"
  done
done

python3 - <<'EOF'
import re, glob, os
rows = []
for f in sorted(glob.glob('/tmp/ab2/*.md')):
    arm = os.path.basename(f).split('_')[0]
    t = open(f).read()
    status = re.search(r'状态: (\w+) \| 候选链: (\d+) \| 结构链: (\d+) \| 障碍: (\d+) \| 丢弃: (\d+)', t)
    cls = re.search(r'缺失分类: 文本内 (\d+) \| 情境性 (\d+) \| 未定 (\d+)', t)
    obs = []
    in_obs = False
    for line in t.splitlines():
        if line.strip().startswith('**障碍**'):
            in_obs = True
            continue
        if in_obs and line.startswith('- '):
            m = re.match(r'- \[(文本内缺失|情境性缺失)\]\s*(.+?)[：:]\s*(.*)$', line)
            if m:
                obs.append((m.group(1), m.group(2)[:26]))
            else:
                obs.append(('未定', line[2:40]))
    rows.append((arm, os.path.basename(f), status.groups() if status else None,
                 cls.groups() if cls else None, obs))

summary = []
for arm in ('base', 'sit'):
    sub = [r for r in rows if r[0] == arm]
    n_obs = [int(r[3][2]) for r in sub if r[3]]
    n_sit = [int(r[3][1]) for r in sub if r[3]]
    n_uns = [int(r[3][2]) for r in sub if r[3]]
    runs_with_sit = sum(1 for r in sub if r[3] and int(r[3][1]) > 0)
    sit_targets = [t for r in sub for (lab, t) in r[4] if lab == '情境性缺失']
    txt_targets = [t for r in sub for (lab, t) in r[4] if lab == '文本内缺失']
    summary.append(f"[{arm}] runs={len(sub)} 障碍数={n_obs} 情境性计数={n_sit} 未定={n_uns} "
                   f"出现情境性的run数={runs_with_sit}/{len(sub)}")
    summary.append(f"    情境性落点: {sit_targets}")
    summary.append(f"    文本内落点: {txt_targets}")

print('\n'.join(summary))
EOF
echo "AB2 DONE"
