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


def l2_project(entities: list, texts: list):
    """L2 几何层：投影到流形空间 (P3 实现前返回 not_ready)。"""
    return _post(L2, "/project", {"entities": entities, "texts": texts})


def l3_analyze(points: list):
    """L3 拓扑层：持续同调 (P4 实现前返回 not_ready)。"""
    return _post(L3, "/analyze", {"points": points}, timeout=300)
