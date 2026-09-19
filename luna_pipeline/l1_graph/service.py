"""L1 Graph-Service (:8001) — FastAPI

接口 (对齐 6/28 文档 Graph-Service 定义):
  GET  /health                      健康检查
  POST /ingest                      写入图 (entities/facts/rules/relations)
  POST /query                       Cypher 查询
  POST /check_axiom                 公理检查 → 触发规则
  POST /verify                      验证结论是否违反公理
  GET  /stats                       图规模

--- 公理管理 (P1 持久化) ---
  GET  /axioms                      列出全部公理
  GET  /axioms/{rule_id}            获取单条公理
  POST /axioms                      新增/更新公理
  DELETE /axioms/{rule_id}          删除公理
  POST /axioms/{rule_id}/feedback   反馈 (tp/fp/deprecated)
  GET  /axioms/stats                公理命中统计
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

import axioms as AX
from graph_client import GraphClient

app = FastAPI(title="Luna Graph-Service", version="0.1.0")
gc = GraphClient()


@app.on_event("startup")
def _startup():
    gc.verify()
    gc.init_schema()
    for r in AX.all_axioms():
        # Neo4j 不支持 Map 类型属性 → 剥离 stats 后再写入图
        rule_clean = {k: v for k, v in r.items() if k != "stats"}
        gc.upsert_rule(rule_clean)


class IngestBody(BaseModel):
    entities: List[Dict[str, Any]] = []
    facts: List[Dict[str, Any]] = []
    rules: List[Dict[str, Any]] = []
    relations: List[Dict[str, Any]] = []


class QueryBody(BaseModel):
    cypher: str
    params: Optional[Dict[str, Any]] = None


class AxiomBody(BaseModel):
    facts: List[Dict[str, Any]]


class VerifyBody(BaseModel):
    violates: List[str] = []
    conclusion: Optional[str] = None


class AxiomRuleBody(BaseModel):
    id: str
    name: str
    field: str
    op: str
    threshold: Any = None
    conclusion: str = ""
    severity: str = "medium"
    confidence: float = 0.85


class AxiomFeedbackBody(BaseModel):
    feedback: str  # tp | fp | deprecated


class AxiomRefreshBody(BaseModel):
    dry_run: bool = False
    decay_base: float = 0.95
    deprecated_threshold: float = 0.30


@app.get("/health")
def health():
    try:
        gc.verify()
        return {"status": "ok", "layer": "L1", "stats": gc.stats()}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.post("/ingest")
def ingest(body: IngestBody):
    return {"ingested": gc.ingest_bundle(body.dict())}


@app.post("/query")
def query(body: QueryBody):
    return {"rows": gc.query(body.cypher, body.params)}


@app.post("/check_axiom")
def check_axiom(body: AxiomBody):
    triggered = AX.check_axiom(body.facts)
    return {"triggered": triggered, "n": len(triggered)}


@app.post("/verify")
def verify(body: VerifyBody):
    return AX.verify_conclusion(body.violates)


@app.get("/stats")
def stats():
    return gc.stats()


# ---------- 公理管理 API (P1) ----------

@app.get("/axioms")
def list_axioms():
    return {"axioms": AX.all_axioms(), "n": len(AX.all_axioms()), "version": AX._STORE.get("version")}


@app.get("/axioms/stats")
def get_axiom_stats():
    return AX.axiom_stats()


@app.post("/axioms/refresh")
def refresh_axioms(body: AxiomRefreshBody):
    return AX.refresh_confidence(dry_run=body.dry_run, decay_base=body.decay_base,
                                 deprecated_threshold=body.deprecated_threshold)


@app.get("/axioms/{rule_id}")
def get_axiom(rule_id: str):
    ax = AX.axiom_by_id(rule_id)
    if not ax:
        return {"status": "not_found", "rule_id": rule_id}
    return ax


@app.post("/axioms")
def create_or_update_axiom(body: AxiomRuleBody):
    return AX.add_axiom(body.dict())


@app.delete("/axioms/{rule_id}")
def remove_axiom(rule_id: str):
    return AX.delete_axiom(rule_id)


@app.post("/axioms/{rule_id}/feedback")
def feedback_axiom(rule_id: str, body: AxiomFeedbackBody):
    return AX.update_axiom_stats(rule_id, body.feedback)
