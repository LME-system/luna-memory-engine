#!/usr/bin/env python3
"""Luna SGP v5.0 批量处理（通用版）

用法: python3 run_batch.py <src.jsonl> <out.md> <log> [标题]

源文件兼容两种键：
  - 老格式: id / title / text / time
  - 新捕获: uri / title / content (+article_full) / time  → 自动归一化
可选键 situation（说话人处境，dict）→ 原样透传给 L5：
  {role 位置 / venue 场合 / audience 在场 / constraints 约束 / source_type 源型}
缺省时空 dict，行为与旧版一致。
"""
import sys, os, json, asyncio, time, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['LUNA_LLM_PROVIDER'] = os.environ.get('LUNA_LLM_PROVIDER', 'deepseek')
JEV_ENABLED = os.environ.get('LUNA_JEV_ENABLED', '').strip().lower() in ('1', 'true', 'yes', 'on')
os.environ['LUNA_JEV_ENABLED'] = '1' if JEV_ENABLED else '0'   # 透传给 merged_pipeline

# L5 全局洞察：默认开（0/false/no/off 关）。关闭时不调 L5、不写 .l5.json。
L5_ENABLED = os.environ.get('LUNA_L5_ENABLED', '1').strip().lower() in ('1', 'true', 'yes', 'on')
L5_MIN_ITEMS = 5


def _reset_id_enabled() -> bool:
    """LUNA_MEMORY_RESET_ID=1/true/yes/on 时，每条处理前先删同 id 旧记忆。默认关（行为不变）。"""
    return os.environ.get('LUNA_MEMORY_RESET_ID', '').strip().lower() in ('1', 'true', 'yes', 'on')

from merged_pipeline import process_article
from memory_store import MemoryStore


def load(src):
    recs = []
    for line in open(src, encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        rid = r.get('id')
        if not rid:
            uri = (r.get('uri') or '').rstrip('/')
            rid = uri.split('/')[-1] if uri else f"item{len(recs)+1}"
        text = r.get('text') or ''
        if not text:
            text = r.get('content') or ''
            if r.get('article_full'):
                text += '\n\n' + r['article_full']
            if r.get('article_title') and r.get('article_full'):
                text = f"[关联长文] {r['article_title']}\n{text}"
        recs.append({
            'id': str(rid),
            'title': r.get('title') or r.get('article_title') or '',
            'text': text,
            'time': r.get('time', ''),
            'situation': r.get('situation') if isinstance(r.get('situation'), dict) else {},
        })
    return recs


def w(log, s):
    with open(log, 'a', encoding='utf-8') as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {s}\n")


def strip_md(out):
    """<out.md> → <out>（去 .md 后缀），用于 items.json / l5.json 命名。"""
    return out[:-3] if out.endswith('.md') else os.path.splitext(out)[0]


def maybe_l5(struct_items, mem, out, log):
    """跑完批后调 L5：写 md 末尾「全局洞察」段 + <out>.l5.json。

    LUNA_L5_ENABLED 关闭 → 不调 L5、不写 .l5.json；条数 < L5_MIN_ITEMS → 跳过并记一行日志。
    返回 L5 结果 dict，跳过或失败返回 None。
    """
    if not L5_ENABLED:
        w(log, "L5: disabled (LUNA_L5_ENABLED=0) → skip")
        return None
    if len(struct_items) < L5_MIN_ITEMS:
        w(log, f"L5: items={len(struct_items)} < {L5_MIN_ITEMS} → skip")
        return None
    try:
        from l5_insight import build_insight, render_md
    except Exception as e:
        w(log, f"L5: import failed {type(e).__name__}: {e}")
        return None
    provider = os.getenv("LUNA_L5_PROVIDER") or os.getenv("LUNA_LLM_PROVIDER")
    model = os.getenv("LUNA_L5_MODEL") or None
    t0 = time.time()
    try:
        ins = build_insight(struct_items, mem, provider=provider, model=model)
    except Exception as e:
        w(log, f"L5: FAILED {type(e).__name__}: {e}")
        return None
    with open(strip_md(out) + '.l5.json', 'w', encoding='utf-8') as f:
        json.dump(ins, f, ensure_ascii=False, indent=2)
    with open(out, 'a', encoding='utf-8') as f:
        f.write('\n' + render_md(ins) + '\n')
    w(log, f"L5: status={ins['status']} candidates={ins['candidates_n']} "
           f"chains={len(ins['chains'])} obstacles={len(ins['obstacles'])} "
           f"dropped={len(ins['dropped'])} {time.time()-t0:.1f}s")
    return ins


async def main():
    src, out, log = sys.argv[1], sys.argv[2], sys.argv[3]
    header = sys.argv[4] if len(sys.argv) > 4 else os.path.basename(src)
    items = load(src)
    mem = MemoryStore(dim=768)
    w(log, f"START items={len(items)} stats={mem.get_stats()}")

    with open(out, 'w', encoding='utf-8') as f:
        f.write(f"# Luna SGP v5.0 — {header}\n\n")
        f.write(f"> 条目: {len(items)} | 源: {os.path.basename(src)} | "
                f"引擎: {os.environ['LUNA_LLM_PROVIDER']} | "
                f"Jev: {'ON' if JEV_ENABLED else 'OFF'} | "
                f"生成: {time.strftime('%Y-%m-%d %H:%M')}\n\n")

    ok = fail = 0
    struct_items = []          # L5 输入：每条结构摘要（真实 id / 真实实体 / 结论）
    for i, it in enumerate(items, 1):
        t0 = time.time()
        try:
            if _reset_id_enabled():
                if mem.remove(str(it['id'])):
                    w(log, f"[{i}/{len(items)}] reset: removed old memory {it['id']}")
            r = await process_article(str(it['id']), it.get('title', ''), it.get('text', ''), mem)
            ax = [a.get('rule_id') for a in r.get('axioms_triggered', [])]
            mh = r.get('memory_hits')
            mh = len(mh) if isinstance(mh, list) else (mh or 0)
            block = [
                f"## [{i}/{len(items)}] {it.get('time','')} · {r.get('title','') or '(无标题)'}",
                "",
                f"- 置信度: {r.get('confidence')} | 延迟: {r.get('latency_seconds', 0):.1f}s",
                f"- 公理: {ax}",
                f"- 记忆命中: {mh}",
            ]
            jv = r.get('jev')
            if jv:
                nl = (jv.get('nonlinear_signal') or {}).get('probability')
                block.append(f"- Jev: {jv.get('status')} | conflict: {len(jv.get('conflict_flags', []))} | "
                             f"nonlinear: {nl}")
            for label, key in (("综合", "synthesis"), ("结论", "conclusion"), ("解释", "explanation")):
                v = (r.get(key) or '').strip()
                if v:
                    block += ["", f"**{label}**", "", v]
            block.append("")
            with open(out, 'a', encoding='utf-8') as f:
                f.write('\n'.join(block) + '\n')
            topo = r.get('l3_topology') or {}
            jev_sum = None
            if isinstance(jv, dict):
                jev_sum = {
                    'status': jv.get('status'),
                    'conflict_flags': len(jv.get('conflict_flags') or []),
                    'nonlinear': (jv.get('nonlinear_signal') or {}).get('probability'),
                }
            struct_items.append({
                'id': str(it['id']),
                'title': r.get('title') or it.get('title', ''),
                'time': it.get('time', ''),
                'situation': it.get('situation') or {},
                'entities': [e.get('name', '') for e in ((r.get('l1_extract') or {}).get('entities') or [])
                             if e.get('name')],
                'l3': {'status': (topo or {}).get('status'),
                       'note': ((topo or {}).get('topology_note') or '')[:300]},
                'jev': jev_sum,
                'conclusion': r.get('conclusion') or r.get('synthesis') or '',
                'text_excerpt': (it.get('text') or '')[:1500],   # 原文摘要：L5 据以找文本内线索
            })
            ok += 1
            w(log, f"[{i}/{len(items)}] ok {it['id']} axioms={ax} {time.time()-t0:.1f}s")
        except Exception as e:
            fail += 1
            w(log, f"[{i}/{len(items)}] FAIL {it['id']} {type(e).__name__}: {e}")
            traceback.print_exc()

    # 结构摘要总是落盘（无论 L5 开关/条数）
    base = strip_md(out)
    with open(base + '.items.json', 'w', encoding='utf-8') as f:
        json.dump({'count': len(struct_items), 'items': struct_items}, f, ensure_ascii=False, indent=2)
    w(log, f"items.json written: {base}.items.json (n={len(struct_items)})")
    maybe_l5(struct_items, mem, out, log)
    w(log, f"DONE ok={ok} fail={fail} stats={mem.get_stats()}")


if __name__ == '__main__':
    asyncio.run(main())
