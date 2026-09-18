"""L1 专家规则 (公理) — 从 6/28 文档的资本公理出发，做成可扩展的表。

每条公理 = 一个 (field, op, threshold) → conclusion 的约束。
""check_axiom(facts)"" 遍历公理，命中则返回触发记录。
"""
from __future__ import annotations
from typing import Any, Dict, List

from models import Rule


def _cmp(op: str, val: Any, thr: Any) -> bool:
    try:
        if op == "gt":  return val > thr
        if op == "gte": return val >= thr
        if op == "lt":  return val < thr
        if op == "lte": return val <= thr
        if op == "eq":  return val == thr
        if op == "in":  return val in (thr or [])
        if op == "is_false": return val is False or val in (0, "false", "False", None)
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
]


def check_axiom(facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """facts: [{field:value,...}]；返回命中公理列表。"""
    triggered: List[Dict[str, Any]] = []
    for f in facts:
        for r in AXIOMS:
            if r.field in f and _cmp(r.op, f[r.field], r.threshold):
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
