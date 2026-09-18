"""L1 Graph-Service (:8001) — FastAPI

接口 (对齐 6/28 文档 Graph-Service 定义):
  GET  /health                      健康检查
  POST /ingest                      写入图 (entities/facts/rules/relations)
  POST /query                       Cypher 查询
  POST /check_axiom                 公理检查 → 触发规则
  POST /verify                      验证结论是否违反公理
  GET  /stats                       图规模
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
        gc.upsert_rule(r)


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
