"""
Luna SGP v5.0 / luna_pipeline 合并版管线
本地记忆 + 自我增强
"""
import asyncio, json, os, sys, time
from typing import List, Dict, Any
import numpy as np

sys.path.insert(0, '/Users/miaoliwang/.openclaw/workspace/luna_pipeline')

from l4_mind.llm_client import extract, synthesize, classify as llm_classify
from l4_mind.clients import l1_ingest, l1_check_axiom, l2_project, l3_analyze
from memory_store import MemoryStore
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Jev 桥接器在 workspace 根，不在 luna_pipeline 内
_WS_ROOT = str(Path(__file__).resolve().parent.parent)
if _WS_ROOT not in sys.path:
    sys.path.insert(0, _WS_ROOT)


def _resolve_use_jev(use_jev) -> bool:
    """use_jev 优先级：显式参数 > 环境变量 LUNA_JEV_ENABLED > 默认关（回归安全）。"""
    if use_jev is not None:
        return bool(use_jev)
    return os.getenv("LUNA_JEV_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def _classify_and_judge(full_text, title):
    """并行跑 LLM classify 与 Jev 6 问（ThreadPoolExecutor，避免阻塞事件循环）。

    Returns: (cls, jev) — 两者任一失败不抛异常。
    """
    from luna_sgp_jev_bridge import jev_judge
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_cls = pool.submit(llm_classify, full_text)
        f_jev = pool.submit(jev_judge, full_text, title)
        try:
            cls = f_cls.result(timeout=300) or {}
        except Exception as e:
            cls = {}
            print(f"      [jev] classify failed: {type(e).__name__}: {e}")
        try:
            jev = f_jev.result(timeout=60)
        except Exception as e:
            jev = {"error": f"{type(e).__name__}: {e}"}
    return cls, jev

# nomic embedding helper
OLLAMA_EMBED = "http://localhost:11434/api/embeddings"

def get_nomic_embedding(text: str) -> np.ndarray:
    import urllib.request
    # Ollama 新端点 /api/embed 接受长文本（自动截断）；旧 /api/embeddings 中文 ≥2500 字符会 500
    req = urllib.request.Request("http://localhost:11434/api/embed",
        data=json.dumps({"model": "nomic-embed-text:latest", "input": text}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode())
        vec = (data.get("embeddings") or [[]])[0]
        if vec:
            return np.array(vec, dtype=np.float32)
    except Exception:
        pass
    # 兜底：旧端点 + 截断到 1800 字符
    req2 = urllib.request.Request(OLLAMA_EMBED,
        data=json.dumps({"model": "nomic-embed-text:latest", "prompt": text[:1800]}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req2, timeout=60) as r:
        data = json.loads(r.read().decode())
    return np.array(data.get("embedding", []), dtype=np.float32)


def build_points_from_extract(ex: dict, title: str, content: str) -> tuple:
    """从 extract 输出构造 L2 points + labels"""
    entities = ex.get("entities", [])
    facts = ex.get("facts", [])
    # 构造 entities 列表（带事实上下文）
    ent_texts = []
    labels = []
    for e in entities:
        ent_texts.append(f"{e.get('name','')}({e.get('type','')})")
        labels.append(e.get('name',''))
    # fact 节点
    for f in facts:
        ent_texts.append(f"{f.get('subject','')} {f.get('predicate','')} {f.get('object','')}")
        labels.append(f"fact:{f.get('subject','')}")
    # DOC 锚点
    ent_texts.append(f"DOC: {title}")
    labels.append("DOC")
    return ent_texts, labels


async def process_article(article_id: str, title: str, content: str, memory: MemoryStore,
                          use_jev: bool = None) -> dict:
    """处理单篇文章。

    use_jev: None 时读环境变量 LUNA_JEV_ENABLED（默认关）。
             关闭时行为与未接入 Jev 前完全一致（不额外调用、不改写 prompt/返回字段）。
    """
    use_jev = _resolve_use_jev(use_jev)
    full_text = f"{title}\n\n{content}"
    t0 = time.time()

    # === L1: DeepSeek extract (symbolic) ===
    print(f"\n[1/6] L1 extract: {title[:50]}...")
    ex = extract(full_text)
    print(f"      Entities: {len(ex.get('entities',[]))}, Facts: {len(ex.get('facts',[]))}, Violations: {len(ex.get('violations',[]))}")

    # === Jev 并联（问题2/3）: L1 之后并行跑 classify + jev_judge，融合为 fused ===
    fused = None
    jev_out = None
    if use_jev:
        print("      [jev] classify + jev_judge (parallel)...")
        cls, jev = _classify_and_judge(full_text, title)
        from luna_sgp_jev_bridge import fuse_l2, jev_summary
        llm_for_fuse = {
            "confidence": 0.75,
            "themes": ex.get("entities", []) and [e.get("name", "") for e in ex.get("entities", [])] or [],
            "sentiment": "neutral",
        }
        if cls:
            llm_for_fuse["classify"] = cls
        fused = fuse_l2(llm_for_fuse, jev)
        jev_out = jev_summary(fused)
        jev_out["raw_status"] = fused.get("jev_status")
        jev_out["llm_classify"] = cls or None
        print(f"      [jev] status={fused.get('jev_status')} confidence={fused.get('confidence')} "
              f"conflicts={len(fused.get('conflict_flags', []))} "
              f"nonlinear={(fused.get('nonlinear_signal') or {}).get('probability')}")

    # Check axioms（展平 extract 的嵌套 fields，与 orchestrator.node_symbolic 一致）
    facts = ex.get("facts", [])
    facts_fields = [f.get("fields", {}) for f in facts if f.get("fields")]
    axiom_result = l1_check_axiom(facts_fields)
    triggered = axiom_result.get("triggered", [])
    print(f"      Axioms triggered: {[a['rule_id'] for a in triggered]}")

    # === L2: Geometry (nomic + Poincaré via service) ===
    print("[2/6] L2 geometry projection...")
    ent_texts, labels = build_points_from_extract(ex, title, content)
    l2_res = l2_project(entities=ex.get("entities", []), texts=ent_texts, labels=labels)
    points = l2_res.get("embedding", [])  # L3 需要数值坐标，不是 label dict
    print(f"      Points: {len(points)} (dim={len(points[0]) if points else 0})")

    # === Memory search ===
    print("[3/6] Memory search...")
    emb = get_nomic_embedding(full_text)
    faiss_hits = memory.search(emb, k=5)
    graph_hits = []
    # 以"当前文章自己抽出的实体"为准做邻居判定（而非 FAISS 首条命中，后者可能完全不相关）
    cur_entities = [e.get("name", "") for e in ex.get("entities", []) if e.get("name")]
    if cur_entities:
        graph_hits = memory.graph_neighbors_by_entities(cur_entities, k=3, exclude_id=article_id)
    print(f"      FAISS hits: {len(faiss_hits)}, Graph neighbors: {len(graph_hits)}")

    # === L3: Topology (TDA via HTTP service) ===
    print("[4/6] L3 TDA analysis...")
    l3_rel = None
    l3_priority = None
    if use_jev and fused is not None:
        from luna_sgp_jev_bridge import apply_to_l3_l4
        if (fused.get("nonlinear_signal") or {}).get("flag"):
            l3_rel = 0.25          # 非线性 → 更密连接
            l3_req = apply_to_l3_l4(fused, {"points": points, "rel": l3_rel})
            l3_rel = l3_req.get("rel", l3_rel)
            l3_priority = l3_req.get("l3_priority")
            print(f"      [jev] nonlinear flag → rel={l3_rel}, l3_priority={l3_priority}")
    l3_res = l3_analyze(points, rel=l3_rel)
    topology = l3_res if "__error__" not in l3_res else {"status": "not_ready"}
    if use_jev and fused is not None:
        from luna_sgp_jev_bridge import apply_to_l3_l4
        topology = apply_to_l3_l4(fused, topology)   # 向 L3 结果注入 jev_nonlinear_prior
    print(f"      Status: {topology.get('status','ok')}")

    # === L4: Synthesize with memory injection ===
    print("[5/6] L4 synthesize (with memory)...")
    # Build memory context
    mem_ctx = ""
    if faiss_hits:
        mem_ctx += "\n【历史相似案例】(FAISS 检索):\n"
        for h in faiss_hits[:3]:
            mem_ctx += f"- [{h['id']}] {h['title']} (相似度 {h.get('similarity',0):.3f})\n"
    if graph_hits:
        mem_ctx += "\n【关联案例】(图邻居):\n"
        for h in graph_hits[:3]:
            mem_ctx += f"- {h.get('title','')} (共享实体: {', '.join(h.get('edge_shared',[])[:3])})\n"

    # Prepare synthesis input
    geo_note = l2_res.get("geo_note", "")
    topo_note = topology.get("topology_note", "") if isinstance(topology, dict) else ""

    synthesis_input = (
        f"标题: {title}\n"
        f"内容摘要: {content[:500]}...\n\n"
        f"提取实体: {json.dumps(ex.get('entities',[]), ensure_ascii=False)}\n"
        f"触发公理: {[a['rule_id'] for a in triggered]}\n"
        f"几何层: {geo_note}\n"
        f"拓扑层: {topo_note}\n"
        f"{mem_ctx}\n"
        f"请基于上述信息给出 Luna SGP 四层综合分析。"
    )

    # 问题1: 非线性/冲突信号写入 L4 合成提示
    syn_state = {"input_text": synthesis_input}
    if use_jev and fused is not None:
        syn_state["jev"] = jev_out
        if fused.get("conflict_flags"):
            cf = "; ".join(
                f"{c['dimension']}(LLM={c.get('llm') or c.get('llm_score')} vs Jev={c.get('jev') or c.get('jev_score')})"
                for c in fused["conflict_flags"]
            )
            synthesis_input += (
                f"\n\n【Jev 结构化判断与文本分析存在冲突】{cf}。"
                "你的解释必须显式讨论这些冲突点，说明你采信哪一方及理由，不得忽略。"
            )
            syn_state["input_text"] = synthesis_input
        if (fused.get("nonlinear_signal") or {}).get("flag"):
            synthesis_input += (
                f"\n\n【非线性信号】Jev 判定该事件具非线性特征"
                f"（概率 {(fused['nonlinear_signal']).get('probability')}）。"
                "分析必须围绕突变/范式转移展开，而非线性外推。"
            )
            syn_state["input_text"] = synthesis_input

    syn = synthesize(syn_state)
    conf = syn.get("confidence", 0.0)
    print(f"      Confidence: {conf}")

    # === Update memory (self-enhancement) ===
    print("[6/6] Update memory...")
    entity_names = [e.get("name","") for e in ex.get("entities",[])]
    fact_strs = [f"{f.get('subject','')} {f.get('predicate','')} {f.get('object','')}" for f in facts]
    memory.add(
        article_id=article_id,
        embedding=emb,
        title=title,
        entities=entity_names,
        facts=fact_strs
    )

    latency = time.time() - t0
    print(f"\n✅ Done in {latency:.1f}s")

    result = {
        "id": article_id,
        "title": title,
        "l1_extract": ex,
        "axioms_triggered": triggered,
        "l2_points": len(points),
        "l3_topology": topology,
        "memory_hits": len(faiss_hits),
        "synthesis": syn.get("synthesis") or (syn.get("conclusion", "") + "\n" + syn.get("explanation", "")),
        "conclusion": syn.get("conclusion", ""),
        "explanation": syn.get("explanation", ""),
        "confidence": conf,
        "latency_seconds": latency
    }
    if use_jev and fused is not None:
        # Jev confidence 覆盖最终 confidence（问题3）
        result["llm_confidence"] = conf
        result["confidence"] = fused.get("confidence", conf)
        result["jev"] = {
            **(jev_out or {}),
            "conflict_flags": fused.get("conflict_flags", []),
            "nonlinear_signal": fused.get("nonlinear_signal"),
            "policy_certainty": fused.get("policy_certainty"),
            "cross_signals": fused.get("cross_signals", []),
        }
    return result


async def main():
    memory = MemoryStore(dim=768)
    print(f"Memory stats: {memory.get_stats()}")

    articles = [
        {
            "id": "anthropic-bio-lab-20260918",
            "title": "Anthropic设立生物实验室，推进AI药物研发项目",
            "content": (
                "Anthropic已悄然建立一个实验室，用于开展实体生物学研究，将人工智能(AI)雄心拓展至药物科学领域。"
                "据两位知情人士透露，Anthropic在旧金山湾区建立了一个实体实验室(wet lab)。"
                "Anthropic曾表示希望开发出治疗罕见病的疗法，其生物学研究已超越了'计算机模拟'范畴。"
                "Anthropic生命科学负责人埃里克·考德勒-艾布拉姆斯（Eric Kauderer-Abrams）周二接受专访时，证实公司已设立实体实验室一事。"
                "一位发言人随后澄清称，Anthropic的实验室并非专门用于药物研发，但拒绝进一步说明。\n\n"
                "据两位不愿透露姓名的知情人士透露，与其他生物技术公司一样，Anthropic正在积极推进实体自动化(physical automation)。"
                "其中一位人士表示，Anthropic希望推动Claude AI系统能够在人类有限干预的情况下，指挥机器人单元进行科学实验。"
                "不过，Anthropic的发言人表示，该公司认为人类的监督和参与对于安全至关重要。（路透）"
            )
        }
    ]

    results = []
    for art in articles:
        res = await process_article(art["id"], art["title"], art["content"], memory)
        results.append(res)

    print("\n" + "="*60)
    print("FINAL SYNTHESIS")
    print("="*60)
    for r in results:
        print(f"\n[{r['id']}] {r['title']}")
        print(f"Confidence: {r['confidence']:.2f} | Latency: {r['latency_seconds']:.1f}s")
        print(f"Axioms: {[a['rule_id'] for a in r['axioms_triggered']]}")
        print(f"Memory hits: {r['memory_hits']}")
        print(f"\nSynthesis:\n{r['synthesis']}")
        print(f"\nConclusion:\n{r.get('conclusion','')}")
        print(f"\nExplanation:\n{r.get('explanation','')}")

    print(f"\nMemory stats after run: {memory.get_stats()}")


if __name__ == "__main__":
    asyncio.run(main())
