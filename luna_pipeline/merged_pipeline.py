"""
Luna SGP v5.0 / luna_pipeline 合并版管线
本地记忆 + 自我增强
"""
import asyncio, json, os, sys, time
from typing import List, Dict, Any
import numpy as np

sys.path.insert(0, '/Users/miaoliwang/.openclaw/workspace/luna_pipeline')

from l4_mind.llm_client import extract, synthesize
from l4_mind.clients import l1_ingest, l1_check_axiom, l2_project, l3_analyze
from memory_store import MemoryStore

# nomic embedding helper
OLLAMA_EMBED = "http://localhost:11434/api/embeddings"

def get_nomic_embedding(text: str) -> np.ndarray:
    import urllib.request
    req = urllib.request.Request(OLLAMA_EMBED,
        data=json.dumps({"model": "nomic-embed-text:latest", "prompt": text}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
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


async def process_article(article_id: str, title: str, content: str, memory: MemoryStore) -> dict:
    full_text = f"{title}\n\n{content}"
    t0 = time.time()

    # === L1: DeepSeek extract (symbolic) ===
    print(f"\n[1/6] L1 extract: {title[:50]}...")
    ex = extract(full_text)
    print(f"      Entities: {len(ex.get('entities',[]))}, Facts: {len(ex.get('facts',[]))}, Violations: {len(ex.get('violations',[]))}")

    # Check axioms
    facts = ex.get("facts", [])
    axiom_result = l1_check_axiom(facts)
    triggered = axiom_result.get("triggered", [])
    print(f"      Axioms triggered: {[a['id'] for a in triggered]}")

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
    if faiss_hits:
        # 从最近 hit 扩展 graph neighbors
        graph_hits = memory.graph_neighbors(faiss_hits[0]['id'], depth=1)
    print(f"      FAISS hits: {len(faiss_hits)}, Graph neighbors: {len(graph_hits)}")

    # === L3: Topology (TDA via HTTP service) ===
    print("[4/6] L3 TDA analysis...")
    l3_res = l3_analyze(points)
    topology = l3_res if "__error__" not in l3_res else {"status": "not_ready"}
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
        f"触发公理: {[a['id'] for a in triggered]}\n"
        f"几何层: {geo_note}\n"
        f"拓扑层: {topo_note}\n"
        f"{mem_ctx}\n"
        f"请基于上述信息给出 Luna SGP 四层综合分析。"
    )

    syn = synthesize({"input_text": synthesis_input})
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

    return {
        "id": article_id,
        "title": title,
        "l1_extract": ex,
        "axioms_triggered": triggered,
        "l2_points": len(points),
        "l3_topology": topology,
        "memory_hits": len(faiss_hits),
        "synthesis": syn.get("conclusion", "") + "\n" + syn.get("explanation", ""),
        "conclusion": syn.get("conclusion", ""),
        "explanation": syn.get("explanation", ""),
        "confidence": conf,
        "latency_seconds": latency
    }


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
        print(f"Axioms: {[a['id'] for a in r['axioms_triggered']]}")
        print(f"Memory hits: {r['memory_hits']}")
        print(f"\nSynthesis:\n{r['synthesis']}")
        print(f"\nConclusion:\n{r.get('conclusion','')}")
        print(f"\nExplanation:\n{r.get('explanation','')}")

    print(f"\nMemory stats after run: {memory.get_stats()}")


if __name__ == "__main__":
    asyncio.run(main())
