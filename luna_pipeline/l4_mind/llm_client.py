"""LLM 客户端 — 本地 ollama gemma4:31b (chat + think=false)。
用于 L4 的实体提取 (extract) 与综合输出 (synthesize)。
"""
from __future__ import annotations
import json, urllib.request, os

OLLAMA = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
MODEL = os.getenv("LUNA_LLM", "gemma4:31b")


def chat(system: str, user: str, num_predict: int = 1200, temperature: float = 0.3,
         timeout: int = 600, fmt=None) -> str:
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False, "think": False,
        "options": {"num_predict": num_predict, "temperature": temperature},
    }
    if fmt is not None:
        payload["format"] = fmt           # ollama 结构化输出 (JSON schema)
    req = urllib.request.Request(OLLAMA, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode())
    return d.get("message", {}).get("content", "")


# ---- extract 公理字段清单: 从 L1 axioms 动态生成 (单一真源) ----
try:
    import axioms as _AX
    _AXSPEC = _AX.axiom_field_spec()
except Exception:  # 兜底
    _AXSPEC = [
        {"axiom": "AX-002", "field": "premium_ratio", "op": "gt", "threshold": 5, "meaning": "高溢价风险", "hint": "收购溢价倍数 (数值)"},
        {"axiom": "AX-001", "field": "control_confidence", "op": "gte", "threshold": 0.9, "meaning": "控制权集中+关联交易", "hint": "实控人控制置信度 (数值 0..1)"},
        {"axiom": "AX-003", "field": "liquidity_support", "op": "is_false", "threshold": None, "meaning": "流动性支撑断裂", "hint": "是否存在流动性支撑 (布尔)"},
        {"axiom": "AX-004", "field": "core_inflation_yoy", "op": "gt", "threshold": 4.0, "meaning": "二次通胀螺旋", "hint": "核心通胀同比 (数值, 去 %)"},
    ]


def _build_extract_system() -> str:
    lines = []
    for s in _AXSPEC:
        thr = "" if s["threshold"] is None else f", 公理判定 {s['op']} {s['threshold']}"
        lines.append(f"- {s['field']} ({s['hint']}) —— {s['meaning']}{thr}")
    fields_block = "\n".join(lines)
    return f"""你是实体/意图提取器。只输出 JSON，不要解释。

【公理字段】只允许用下列字段名 (逐字一致)，从文本抽取可被公理检验的证据：
{fields_block}

【硬规则】
1. 有确切数字就直接填数，如 "4.5%" → 4.5、"7.1倍" → 7.1。
2. 只给方向没有确切值时，填对象 {{"value": X, "cmp": "gt|gte|lt|lte"}}，
   不要改写成相等。如 "高于4%" → {{"value": 4, "cmp": "gt"}}；"不足3%" → {{"value": 3, "cmp": "lt"}}。
3. 文本没有证据的公理字段不要填，不要臆造数字。
4. 允许附非公理字段，但公理字段名必须逐字一致。

【输出 JSON】
{{"intent": "...", "entities": [{{"id":"e:1","name":"...","type":"Company|Person|Country|Commodity|Asset"}}],
 "facts": [{{"id":"f:1","content":"...","fields": {{...}}}}]}}

【示例】
文本: 光智科技以7.1倍溢价收购关联方资产
输出: {{"intent":"m&a","entities":[{{"id":"e:1","name":"光智科技","type":"Company"}}],"facts":[{{"id":"f:1","content":"7.1倍溢价收购","fields":{{"premium_ratio":7.1}}}}]}}
文本: 英国核心通胀高于4%
输出: {{"intent":"macro","entities":[{{"id":"e:1","name":"英国","type":"Country"}}],"facts":[{{"id":"f:1","content":"核心通胀高于4%","fields":{{"core_inflation_yoy":{{"value":4,"cmp":"gt"}}}}}}]}}"""


EXTRACT_SYSTEM = _build_extract_system()

# 结构化输出 schema (约束外层结构; fields 内部放开以容纳数值/对象)
EXTRACT_FORMAT = {
    "type": "object",
    "properties": {
        "intent": {"type": "string"},
        "entities": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "name": {"type": "string"},
                           "type": {"type": "string"}},
            "required": ["name", "type"]}},
        "facts": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "content": {"type": "string"},
                           "fields": {"type": "object"}},
            "required": ["content"]}},
    },
    "required": ["entities", "facts"],
}


def extract(text: str) -> dict:
    try:
        raw = chat(EXTRACT_SYSTEM, text, num_predict=800, temperature=0.0, fmt=EXTRACT_FORMAT)
    except Exception:
        raw = chat(EXTRACT_SYSTEM, text, num_predict=800, temperature=0.0)
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
