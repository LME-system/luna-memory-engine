"""L3 Topo-Service (:8004) — FastAPI

接口 (对齐 6/28 文档 TopologicalMonitor):
  GET  /health          健康检查
  POST /analyze         持续同调分析 → 空洞/连通分量/持续图/临界转变
  POST /fractal         Hausdorff(盒计数) 分形维
  GET  /history         历史快照 (临界转变依据)
  POST /reset           清空历史

运行环境: 独立 venv `.venv_topo` (giotto-tda + numpy<2)。
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from pydantic import BaseModel

import topology as T
import fractal as F

app = FastAPI(title="Luna Topo-Service", version="0.1.0")


class AnalyzeBody(BaseModel):
    points: List[List[float]] = []
    maxdim: int = 1
    rel: float = 0.4


class FractalBody(BaseModel):
    points: List[List[float]] = []


@app.get("/health")
def health():
    return {"status": "ok", "layer": "L3",
            "backend": "giotto-tda/VietorisRips" if T._HAS_GTDA else "fallback(single-linkage)",
            "history_len": len(T.MONITOR.history)}


@app.post("/analyze")
def analyze(body: AnalyzeBody):
    if len(body.points) < 2:
        return {"status": "not_ready", "reason": "need >=2 points"}
    return T.MONITOR.analyze(body.points, maxdim=body.maxdim, rel=body.rel)


@app.post("/fractal")
def fractal(body: FractalBody):
    return {"fractal_dimension": round(F.box_counting_dimension(body.points), 4),
            "n_points": len(body.points)}


@app.get("/history")
def history(limit: int = 20):
    return {"n": len(T.MONITOR.history), "history": T.MONITOR.history[-limit:]}


@app.post("/reset")
def reset():
    T.MONITOR.reset()
    return {"status": "ok", "history_len": 0}
