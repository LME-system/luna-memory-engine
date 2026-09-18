"""L1 专家规则 (公理) — 从 6/28 文档的资本公理出发，做成可扩展的表。

每条公理 = 一个 (field, op, threshold) → conclusion 的约束。
""check_axiom(facts)"" 遍历公理，命中则返回触发记录。
"""
from __future__ import annotations
from typing import Any, Dict, List

from models import Rule


_DIRECTIONS = ("eq", "gt", "gte", "lt", "lte")


def _parse_fact(val: Any):
    """事实值 → (value, cmp)。支持方向保真: {"value":4,"cmp":"gt"} 表示'高于4'。"""
    if isinstance(val, dict):
        v = val.get("value", val.get("v"))
        c = str(val.get("cmp", val.get("op", "eq"))).lower()
        return v, (c if c in _DIRECTIONS else "eq")
    return val, "eq"


def _cmp(op: str, val: Any, thr: Any) -> bool:
    """判定事实 val 是否落在公理 (op, thr) 的满足域内。

    方向保真: '高于4%' 记为 (4, 'gt'), 与公理 gt 4 相交 → 命中 (边界安全)。
    纯相等值 (4, 'eq') 对 gt 4 不命中。
    """
    value, cmp = _parse_fact(val)
    try:
        if op == "is_false":
            return (value is False) or (cmp == "eq" and value in (0, "false", "False", None))
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


def axiom_field_spec() -> List[Dict[str, Any]]:
    """公理字段清单 (单一真源) — 供 extract prompt 动态构建, 保证 prompt 与公理不脱节。"""
    hints = {
        "premium_ratio": "收购溢价倍数 (数值)",
        "control_confidence": "实控人控制置信度 (数值 0..1)",
        "liquidity_support": "是否存在流动性支撑 (布尔 true/false)",
        "core_inflation_yoy": "核心通胀同比 (数值, 百分数去 % 如 4.5)",
    }
    return [{"axiom": r.id, "field": r.field, "op": r.op, "threshold": r.threshold,
             "meaning": r.conclusion, "hint": hints.get(r.field, "")} for r in AXIOMS]
