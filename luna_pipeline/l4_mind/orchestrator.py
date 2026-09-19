"""L4 编排层 — 神经符号控制器 (LangGraph)

数据流 (对齐 6/28 文档 NeuroSymbolicOrchestrator.process):
  extract ──▶ symbolic(L1) ──▶ route
                                ├─(公理直答, conf≥0.9)─▶ verify ─▶ synthesize ─┐
                                └─(需增强)─▶ geometry(L2) ─▶ topology(L3) ─▶ upscale?
                                                                  └▶ verify ─▶ synthesize ─▶ END

L2/L3 服务未就绪时优雅降级 (记 not_ready)，不阻断链路。
"""
from __future__ import annotations
import sys, os
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "l1_graph"))

from typing import Any, Dict, List, TypedDict

from langgraph.graph import StateGraph, END

import llm_client as LLM
import clients as C


class State(TypedDict, total=False):
    input_text: str
    intent: str
    entities: List[dict]
    facts: List[dict]
    symbolic: dict
    geometric: dict
    topological: dict
    verification: dict
    output: dict
    trace: List[str]


def _t(state: State, msg: str) -> List[str]:
    return (state.get("trace") or []) + [msg]


# ---------------- nodes ----------------

def node_extract(state: State) -> State:
    d = LLM.extract(state["input_text"])
    return {"intent": d.get("intent", ""), "entities": d.get("entities", []),
            "facts": d.get("facts", []), "trace": _t(state, "extract:ok")}


def node_symbolic(state: State) -> State:
    C.l1_ingest({"entities": state.get("entities", []), "facts": state.get("facts", [])})
    fields = [f.get("fields", {}) for f in state.get("facts", [])]
    fields = [f for f in fields if f]
    res = C.l1_check_axiom(fields)
    triggered = res.get("triggered", [])
    conf = max([t.get("confidence", 0.0) for t in triggered], default=0.0)
    symbolic = {"triggered_rules": [t["rule_id"] for t in triggered],
                "triggered_detail": triggered, "facts_fields": fields,
                "confidence": conf, "n": len(triggered),
                "unclassified": len(triggered) == 0}  # P2
    return {"symbolic": symbolic, "trace": _t(state, f"symbolic:rules={symbolic['triggered_rules']}")}


def _detect_pattern_alert(geometric: dict) -> dict:
    """P2: 基于 L2 几何特征检测异常模式信号。"""
    pts = geometric.get("points", [])
    if not pts:
        return {"alert": False}
    max_norm = max([p.get("poincare_norm", 0) for p in pts], default=0.0)
    conflict = geometric.get("conflict", {})
    base_dim = geometric.get("dimension", 64)
    need_dim = conflict.get("need_dim", base_dim)
    alert = False
    reasons = []
    if max_norm > 0.75:
        alert = True
        reasons.append(f"high_specificity(max_norm={max_norm:.2f})")
    if need_dim > base_dim * 1.5:
        alert = True
        reasons.append(f"dimension_spike(need={need_dim}, base={base_dim})")
    return {"alert": alert, "reasons": reasons, "max_norm": round(max_norm, 4)}


def _build_points(state: State):
    """构造 L2 投影点集: 图节点(实体[带事实上下文] + 事实) + 文档锚点。"""
    import re
    ents = state.get("entities") or []
    facts = state.get("facts") or []
    pts = []
    seen = set()

    def key(s):
        return re.sub(r"\W", "", s or "")[:80]

    for e in ents:
        name = e.get("name")
        if not name:
            continue
        ctx = [f.get("content", "") for f in facts if name in (f.get("content", "") or "")]
        text = name + ("：" + "；".join(c for c in ctx if c) if ctx else "")
        if key(text) in seen:
            continue
        seen.add(key(text)); pts.append((name, text))

    for i, f in enumerate(facts):
        c = (f.get("content") or "").strip()
        if not c or key(c) in seen:
            continue
        seen.add(key(c)); pts.append((f.get("id") or f"fact{i}", c))

    doc = (state.get("input_text") or "").strip()
    if doc and key(doc) not in seen:
        pts.append(("DOC", doc))

    return [p[0] for p in pts], [p[1] for p in pts]


def node_geometry(state: State) -> State:
    labels, texts = _build_points(state)
    res = C.l2_project(state.get("entities", []), texts, labels=labels)
    res.setdefault("status", "not_ready" if "__error__" in res else "ok")
    res.setdefault("n_points", len(texts))
    # P2: 未覆盖时附加模式检测
    if (state.get("symbolic") or {}).get("unclassified"):
        res["pattern_alert"] = _detect_pattern_alert(res)
    return {"geometric": res, "trace": _t(state, f"geometry:{res.get('status')}")}


def node_topology(state: State) -> State:
    pts = (state.get("geometric") or {}).get("embedding")
    if not pts:
        return {"topological": {"status": "skipped", "reason": "no embedding"},
                "trace": _t(state, "topology:skipped")}
    res = C.l3_analyze(pts)
    res.setdefault("status", "not_ready" if "__error__" in res else "ok")
    return {"topological": res, "trace": _t(state, f"topology:{res.get('status')}")}


def node_upscale(state: State) -> State:
    return {"trace": _t(state, "upscale:requested")}


def node_verify(state: State) -> State:
    violates = (state.get("symbolic") or {}).get("triggered_rules", [])
    res = C.l1_verify(violates)
    res.setdefault("consistent", True)
    return {"verification": res, "trace": _t(state, "verify:done")}


def node_synthesize(state: State) -> State:
    out = LLM.synthesize(dict(state))
    if not out.get("conclusion"):
        trig = (state.get("symbolic") or {}).get("triggered_detail", [])
        out["conclusion"] = trig[0]["conclusion"] if trig else "无显著信号"
        out.setdefault("explanation", "（LLM 综合降级：给出符号层直接结论）")
        out.setdefault("confidence", (state.get("symbolic") or {}).get("confidence", 0.5))
    return {"output": out, "trace": _t(state, "synthesize:done")}


# ---------------- routing ----------------

def route_after_symbolic(state: State) -> str:
    """公理直答 or 进入几何增强。"""
    s = state.get("symbolic") or {}
    if s.get("confidence", 0) >= 0.9:
        return "verify"          # 快速路径
    return "geometry"            # 增强路径


def route_after_topology(state: State) -> str:
    t = state.get("topological") or {}
    if t.get("critical_transition") or t.get("has_conflict"):
        return "upscale"
    return "verify"


def build_graph():
    g = StateGraph(State)
    g.add_node("extract", node_extract)
    g.add_node("symbolic", node_symbolic)
    g.add_node("geometry", node_geometry)
    g.add_node("topology", node_topology)
    g.add_node("upscale", node_upscale)
    g.add_node("verify", node_verify)
    g.add_node("synthesize", node_synthesize)

    g.set_entry_point("extract")
    g.add_edge("extract", "symbolic")
    g.add_conditional_edges("symbolic", route_after_symbolic,
                            {"verify": "verify", "geometry": "geometry"})
    g.add_edge("geometry", "topology")
    g.add_conditional_edges("topology", route_after_topology,
                            {"upscale": "upscale", "verify": "verify"})
    g.add_edge("upscale", "verify")
    g.add_edge("verify", "synthesize")
    g.add_edge("synthesize", END)
    return g.compile()


APP = build_graph()


def run(text: str, article_id: str = None, title: str = None) -> dict:
    result = APP.invoke({"input_text": text, "trace": []})
    # P2: 归档未覆盖案例
    sym = result.get("symbolic", {})
    geo = result.get("geometric", {})
    if sym.get("unclassified"):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from unclassified_store import UncoveredStore
        store = UncoveredStore()
        hint = {}
        pa = geo.get("pattern_alert", {})
        if pa.get("alert"):
            hint = {
                "max_poincare_norm": pa.get("max_norm"),
                "reasons": pa.get("reasons", [])
            }
        store.add(
            article_id=article_id or f"auto_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            title=title or text[:50],
            text=text,
            reason="pattern_alert" if pa.get("alert") else "no_axiom_hit",
            geometric_hint=hint
        )
    return result
