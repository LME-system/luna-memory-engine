"""L1 专家规则 (公理) — 从 6/28 文档的资本公理出发，做成可扩展的表。

每条公理 = 一个 (field, op, threshold) → conclusion 的约束。
""check_axiom(facts)"" 遍历公理，命中则返回触发记录。
"""
from __future__ import annotations
from typing import Any, Dict, List

from models import Rule


_DIRECTIONS = ("eq", "gt", "gte", "lt", "lte")

# 有序等级标度 (定性 → 可比较): 供 level_* 公理使用。低 → 高。
LEVEL_SCALES: Dict[str, List[str]] = {
    "inflation_pressure": ["low", "moderate", "high", "very_high"],
    "policy_tightening_probability": ["unlikely", "possible", "likely", "near_certain"],
    "liquidity_stress": ["none", "mild", "severe"],
    "governance_risk": ["low", "moderate", "high"],
    "ai_embodiment_level": ["digital_only", "hybrid", "physical_lab", "full_automation"],
}

_TRUEISH = (True, 1, "true", "True", "yes", "是")


def _parse_fact(val: Any):
    """事实值 → (value, cmp)。支持方向保真: {"value":4,"cmp":"gt"} 表示'高于4'。"""
    if isinstance(val, dict):
        v = val.get("value", val.get("v"))
        c = str(val.get("cmp", val.get("op", "eq"))).lower()
        return v, (c if c in _DIRECTIONS else "eq")
    return val, "eq"


def _rank(field: str, label: Any):
    """把等级标签映射到序号; 未知返回 None。"""
    scale = LEVEL_SCALES.get(field)
    if not scale or not isinstance(label, str):
        return None
    key = label.strip().lower().replace("-", "_").replace(" ", "_")
    return scale.index(key) if key in scale else None


def _cmp(op: str, val: Any, thr: Any, field: Optional[str] = None) -> bool:
    """判定事实 val 是否落在公理 (op, thr) 的满足域内。

    - 数值: 方向保真 (区间相交, 边界安全)。'高于4%'=(4,'gt') 命中 gt 4; '等于4' 不命中。
    - 等级 (level_*): 按 LEVEL_SCALES 序号比较。
    - 布尔: is_true / is_false。
    """
    value, cmp = _parse_fact(val)

    if op in ("level_gte", "level_gt", "level_lte", "level_lt"):
        rv, rt = _rank(field, value), _rank(field, thr)
        if rv is None or rt is None:
            return False
        return {"level_gte": rv >= rt, "level_gt": rv > rt,
                "level_lte": rv <= rt, "level_lt": rv < rt}[op]

    try:
        if op == "is_false":
            return (value is False) or (cmp == "eq" and value in (0, "false", "False", "no", None))
        if op == "is_true":
            return (value is True) or (cmp == "eq" and value in _TRUEISH)
        if op == "eq":
            return cmp == "eq" and value == thr
        if op == "in":
            return cmp == "eq" and value in (thr or [])
        if op == "gt":
            return value > thr or (cmp in ("gt", "gte") and value >= thr)
        if op == "gte":
            return value >= thr or (cmp in ("gt", "gte") and value >= thr)
        if op == "lt":
            return value < thr or (cmp in ("lt", "lte") and value <= thr)
        if op == "lte":
            return value <= thr or (cmp in ("lt", "lte") and value <= thr)
    except TypeError:
        return False
    return False


# --- 公理库 (可继续编码) ---
AXIOMS: List[Rule] = [
    Rule(id="AX-002", name="高溢价风险", field="premium_ratio", op="gt", threshold=5,
         conclusion="极高溢价/泡沫风险", severity="high", confidence=0.85),
    Rule(id="AX-001", name="控制权集中+关联交易", field="control_confidence", op="gte",
         threshold=0.9, conclusion="利益输送风险 (实控人高置信控制)", severity="high",
         confidence=0.80),
    Rule(id="AX-003", name="流动性支撑断裂", field="liquidity_support", op="is_false",
         conclusion="支撑结构断裂 / 流动性坍缩", severity="high", confidence=0.75),
    Rule(id="AX-004", name="二次通胀螺旋", field="core_inflation_yoy", op="gt", threshold=4.0,
         conclusion="通胀二轮传导 → 央行被迫鹰派", severity="medium", confidence=0.80),
    # --- 定性/等级公理 (覆盖无数值的定性证据) ---
    Rule(id="AX-005", name="通胀压力高企", field="inflation_pressure", op="level_gte",
         threshold="high", conclusion="通胀压力高企 → 紧缩预期升温", severity="medium",
         confidence=0.70),
    Rule(id="AX-006", name="政策转鹰概率", field="policy_tightening_probability", op="level_gte",
         threshold="likely", conclusion="央行转向鹰派概率上升", severity="medium",
         confidence=0.70),
    Rule(id="AX-007", name="关联交易", field="related_party_deal", op="is_true",
         conclusion="关联交易 → 利益输送/掏空风险", severity="high", confidence=0.70),
    Rule(id="AX-008", name="流动性压力严峻", field="liquidity_stress", op="level_gte",
         threshold="severe", conclusion="流动性压力严峻 → 再融资风险", severity="high",
         confidence=0.72),
    # --- AI 产业/安全/生物融合公理 ---
    Rule(id="AX-009", name="AI实体化临界点", field="ai_embodiment_level", op="level_gte",
         threshold="physical_lab", conclusion="AI 实体化临界点：从模拟进入物理闭环", severity="high",
         confidence=0.80),
    Rule(id="AX-010", name="AI安全叙事升温", field="ai_safety_concern", op="is_true",
         conclusion="AI 安全叙事升温 → 监管/放缓/第三方评估预期", severity="medium",
         confidence=0.75),
    Rule(id="AX-011", name="递归自我改进信号", field="ai_self_improvement", op="is_true",
         conclusion="递归自我改进信号 → 能力跃迁/控制忧虑", severity="high",
         confidence=0.78),
    Rule(id="AX-012", name="AI生物融合", field="bio_ai_integration", op="is_true",
         conclusion="AI-生物融合 → 罕见病/药物研发范式转移", severity="medium",
         confidence=0.72),
]


def check_axiom(facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """facts: [{field:value,...}]；返回命中公理列表。"""
    triggered: List[Dict[str, Any]] = []
    for f in facts:
        for r in AXIOMS:
            if r.field in f and _cmp(r.op, f[r.field], r.threshold, field=r.field):
                triggered.append({
                    "rule_id": r.id,
                    "name": r.name,
                    "conclusion": r.conclusion,
                    "severity": r.severity,
                    "confidence": r.confidence,
                    "field": r.field,
                    "value": f[r.field],
                    "threshold": r.threshold,
                })
    return triggered


def verify_conclusion(conclusion_violates: List[str]) -> Dict[str, Any]:
    """给定结论声称违反的公理 id，返回验证结果。"""
    known = {r.id: r for r in AXIOMS}
    hit = [known[i] for i in conclusion_violates if i in known]
    return {
        "consistent": len(hit) == 0,
        "violations": [{"rule_id": r.id, "name": r.name, "conclusion": r.conclusion} for r in hit],
        "checked": len(conclusion_violates),
    }


def all_axioms() -> List[Dict[str, Any]]:
    return [r.to_props() for r in AXIOMS]


def axiom_field_spec() -> List[Dict[str, Any]]:
    """公理字段清单 (单一真源) — 供 extract prompt 动态构建, 保证 prompt 与公理不脱节。"""
    hints = {
        "premium_ratio": "收购溢价倍数 (数值)",
        "control_confidence": "实控人控制置信度 (数值 0..1)",
        "liquidity_support": "是否存在流动性支撑 (布尔 true/false)",
        "core_inflation_yoy": "核心通胀同比 (数值, 百分数去 % 如 4.5)",
        "inflation_pressure": "通胀压力等级 (定性)",
        "policy_tightening_probability": "央行收紧政策的可能性 (定性)",
        "related_party_deal": "是否关联方交易 (布尔 true/false)",
        "liquidity_stress": "流动性压力等级 (定性)",
        "ai_embodiment_level": "AI 实体化等级 (定性: digital_only/hybrid/physical_lab/full_automation)",
        "ai_safety_concern": "是否存在 AI 安全担忧、监管呼吁或放缓开发 (布尔 true/false)",
        "ai_self_improvement": "是否提及递归自我改进、AI 自我迭代或自主运行 (布尔 true/false)",
        "bio_ai_integration": "是否 AI 与生物学/药物研发/实体实验室融合 (布尔 true/false)",
    }
    return [{"axiom": r.id, "field": r.field, "op": r.op, "threshold": r.threshold,
             "meaning": r.conclusion, "hint": hints.get(r.field, ""),
             "scale": LEVEL_SCALES.get(r.field)} for r in AXIOMS]
