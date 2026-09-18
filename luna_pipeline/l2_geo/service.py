"""L2 Geo-Service (:8002) — FastAPI

接口 (对齐 6/28 文档 Geo-Service 定义):
  GET  /health
  POST /project    投影到流形空间 (Dual-Embedding)
  POST /analogy    两区域形状同构检测
  POST /upscale    动态升维
  POST /embed      纯嵌入 (768d)
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

import manifold as M
import embedding as E

app = FastAPI(title="Luna Geo-Service", version="0.1.0")


class ProjectBody(BaseModel):
    entities: List[Dict[str, Any]] = []
    texts: List[str] = []
    labels: List[str] = []      # 显式点标签 (实体名 / fact id / DOC); 空则从 entities 推
    k: int = 5


class AnalogyBody(BaseModel):
    labels: List[str]
    texts: List[str]
    a: str
    b: str
    k: int = 5


class UpscaleBody(BaseModel):
    texts: List[str]
    target: float = 0.95


class EmbedBody(BaseModel):
    texts: List[str]


def _labels_texts(body: ProjectBody):
    # 优先用显式 labels (L4 传入: 实体+事实节点)
    if body.labels and body.texts:
        labels = list(body.labels)
        texts = list(body.texts)
    else:
        names = [e.get("name") for e in body.entities if e.get("name")]
        texts = body.texts[:] or names
        labels = names[:len(texts)]
    if len(labels) < len(texts):
        labels += [f"t{i}" for i in range(len(labels), len(texts))]
    return labels[:len(texts)], texts


@app.get("/health")
def health():
    return {"status": "ok", "layer": "L2", "space": "dual(euclidean+poincare)"}


@app.post("/project")
def project(body: ProjectBody):
    labels, texts = _labels_texts(body)
    if len(texts) < 2:
        return {"status": "not_ready", "reason": "need >=2 points"}
    return M.project(labels, texts, k=body.k)


@app.post("/analogy")
def analogy(body: AnalogyBody):
    return M.analogy_between(body.labels, body.texts, body.a, body.b, k=body.k)


@app.post("/upscale")
def upscale(body: UpscaleBody):
    return M.upscale([f"t{i}" for i in range(len(body.texts))], body.texts, target=body.target)


@app.post("/embed")
def embed(body: EmbedBody):
    return {"vectors": E.embed(body.texts)}
