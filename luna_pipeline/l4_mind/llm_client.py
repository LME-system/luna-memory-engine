"""LLM 客户端 — 本地 ollama gemma4:31b (chat + think=false)。
用于 L4 的实体提取 (extract) 与综合输出 (synthesize)。
"""
from __future__ import annotations
import json, urllib.request, os

OLLAMA = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
MODEL = os.getenv("LUNA_LLM", "gemma4:31b")


def chat(system: str, user: str, num_predict: int = 1200, temperature: float = 0.3,
         timeout: int = 600) -> str:
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False, "think": False,
        "options": {"num_predict": num_predict, "temperature": temperature},
    }
    req = urllib.request.Request(OLLAMA, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode())
    return d.get("message", {}).get("content", "")


EXTRACT_SYSTEM = """你是实体/意图提取器。只输出 JSON，不要解释：
{"intent": "...", "entities": [{"id":"e:xxx","name":"...","type":"Company|Person|Country|Commodity|Asset"}],
 "facts": [{"id":"f:x1","content":"...", "fields": {"premium_ratio": 7.1}}]}
fields 里放可被公理检验的数值字段 (如 premium_ratio, control_confidence, core_inflation_yoy, liquidity_support)。"""


def extract(text: str) -> dict:
    raw = chat(EXTRACT_SYSTEM, text, num_predict=800, temperature=0.1)
    return _parse_json(raw)


SYNTH_SYSTEM = """你是 Luna SGP 编排层的综合器。基于给定的符号/几何/拓扑/验证结果，
输出：结论、解释、置信度。锐利、密度高、不空话。只输出 JSON：
{"conclusion": "...", "explanation": "...", "confidence": 0.0}"""


def _slim_geo(geo, max_points: int = 40):
    """剔除 L2 结果里的重型原始数组(768d embedding / 测地线矩阵), 只留 LLM 可读摘要。
    否则 synthesize prompt 会被撑到 30k+ tokens (旧 bug: prompt 处理 >6min 卡死)。"""
    if not isinstance(geo, dict):
        return geo
    keep = {k: v for k, v in geo.items() if k not in ("embedding", "geodesic")}
    pts = keep.get("points")
    if isinstance(pts, list) and len(pts) > max_points:
        keep["points"] = pts[:max_points]
    nbr = keep.get("neighbors")
    if isinstance(nbr, list) and len(nbr) > max_points:
        keep["neighbors"] = nbr[:max_points]
    return keep


def _slim_topo(topo):
    """剔除原始持续图(persistence), 保留摘要。"""
    if not isinstance(topo, dict):
        return topo
    return {k: v for k, v in topo.items() if k != "persistence"}


def synthesize(state: dict) -> dict:
    user = json.dumps({
        "input": state.get("input_text"),
        "symbolic": state.get("symbolic"),
        "geometric": _slim_geo(state.get("geometric")),
        "topological": _slim_topo(state.get("topological")),
        "verification": state.get("verification"),
    }, ensure_ascii=False)
    raw = chat(SYNTH_SYSTEM, user, num_predict=1000, temperature=0.4)
    d = _parse_json(raw)
    d.setdefault("conclusion", "")
    d.setdefault("explanation", "")
    d.setdefault("confidence", 0.5)
    return d


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw)
    except Exception:
        i, j = raw.find("{"), raw.rfind("}")
        if 0 <= i < j:
            try:
                return json.loads(raw[i:j + 1])
            except Exception:
                pass
    return {}
