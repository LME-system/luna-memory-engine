"""L4 Mind-Service (:8003) — FastAPI

接口 (对齐 6/28 文档 Mind-Service 定义):
  GET  /health
  POST /orchestrate   完整编排流程
  POST /extract       实体/意图提取
  POST /synthesize    综合输出
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

import orchestrator as ORCH
import llm_client as LLM

app = FastAPI(title="Luna Mind-Service", version="0.1.0")


class OrchestrateBody(BaseModel):
    text: str


class ExtractBody(BaseModel):
    text: str


class SynthBody(BaseModel):
    state: Dict[str, Any]


@app.get("/health")
def health():
    return {"status": "ok", "layer": "L4", "graph": "extract→symbolic→(geo→topo)→verify→synthesize"}


@app.post("/orchestrate")
def orchestrate(body: OrchestrateBody):
    return ORCH.run(body.text)


@app.post("/extract")
def extract(body: ExtractBody):
    return LLM.extract(body.text)


@app.post("/synthesize")
def synthesize(body: SynthBody):
    return LLM.synthesize(body.state)
