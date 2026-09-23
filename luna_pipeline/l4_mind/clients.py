"""各层的 HTTP 客户端 (供 L4 编排调用)。未起的服务优雅降级。"""
from __future__ import annotations
import json, urllib.request, os

L1 = os.getenv("L1_URL", "http://localhost:8001")
L2 = os.getenv("L2_URL", "http://localhost:8002")
L3 = os.getenv("L3_URL", "http://localhost:8004")


def _post(base: str, path: str, body: dict, timeout: int = 60):
    try:
        req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"__error__": str(e)}


def l1_ingest(bundle: dict):
    return _post(L1, "/ingest", bundle)


def l1_check_axiom(facts: list):
    return _post(L1, "/check_axiom", {"facts": facts})


def l1_verify(violates: list):
    return _post(L1, "/verify", {"violates": violates})


def l2_project(entities: list, texts: list, labels: list = None):
    """L2 几何层：投影到流形空间。labels 显式指定点标签(实体名/fact id/DOC)。"""
    body = {"entities": entities, "texts": texts}
    if labels:
        body["labels"] = labels
    return _post(L2, "/project", body)


def l3_analyze(points: list, rel: float = None, maxdim: int = None):
    """L3 拓扑层：持续同调 (P4 实现前返回 not_ready)。

    rel: 显著空洞阈值比例 (越小连接越密)。未指定时不发 rel，沿用服务端默认 0.4。
    maxdim: 未指定时不发，沿用服务端默认 1 —— 保证未接入 Jev 时请求体与原先完全一致。
    """
    body = {"points": points}
    if maxdim is not None:
        body["maxdim"] = maxdim
    if rel is not None:
        body["rel"] = rel
    return _post(L3, "/analyze", body, timeout=300)
