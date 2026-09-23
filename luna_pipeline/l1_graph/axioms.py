"""L1 专家规则 (公理) — 持久化版 P1

公理从 data/axioms_store.json 加载，运行时 CRUD + 命中追踪。
硬编码公理作为首次初始化兜底。
"""
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from models import Rule

_DIRECTIONS = ("eq", "gt", "gte", "lt", "lte")

# 有序等级标度 (定性 → 可比较)
LEVEL_SCALES: Dict[str, List[str]] = {}

_TRUEISH = (True, 1, "true", "True", "yes", "是")

# ---------- 持久化 ----------
_STORE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "axioms_store.json")


def _load_store() -> Dict[str, Any]:
    if os.path.exists(_STORE_PATH):
        with open(_STORE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return _build_default_store()


def _save_store(store: Dict[str, Any]):
    store["updated_at"] = datetime.now(timezone.utc).isoformat()
    os.makedirs(os.path.dirname(_STORE_PATH), exist_ok=True)
    with open(_STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def _build_default_store() -> Dict[str, Any]:
    """首次初始化：从硬编码公理生成 store。"""
    axioms = [
        {"id":"AX-001","name":"控制权集中+关联交易","field":"control_confidence","op":"gte","threshold":0.9,"conclusion":"利益输送风险 (实控人高置信控制)","severity":"high","confidence":0.80,"stats":_fresh_stats("2026-09-17")},
        {"id":"AX-002","name":"高溢价风险","field":"premium_ratio","op":"gt","threshold":5,"conclusion":"极高溢价/泡沫风险","severity":"high","confidence":0.85,"stats":_fresh_stats("2026-09-17")},
        {"id":"AX-003","name":"流动性支撑断裂","field":"liquidity_support","op":"is_false","threshold":None,"conclusion":"支撑结构断裂 / 流动性坍缩","severity":"high","confidence":0.75,"stats":_fresh_stats("2026-09-17")},
        {"id":"AX-004","name":"二次通胀螺旋","field":"core_inflation_yoy","op":"gt","threshold":4.0,"conclusion":"通胀二轮传导 → 央行被迫鹰派","severity":"medium","confidence":0.80,"stats":_fresh_stats("2026-09-17")},
        {"id":"AX-005","name":"通胀压力高企","field":"inflation_pressure","op":"level_gte","threshold":"high","conclusion":"通胀压力高企 → 紧缩预期升温","severity":"medium","confidence":0.70,"stats":_fresh_stats("2026-09-18")},
        {"id":"AX-006","name":"政策转鹰概率","field":"policy_tightening_probability","op":"level_gte","threshold":"likely","conclusion":"央行转向鹰派概率上升","severity":"medium","confidence":0.70,"stats":_fresh_stats("2026-09-18")},
        {"id":"AX-007","name":"关联交易","field":"related_party_deal","op":"is_true","threshold":None,"conclusion":"关联交易 → 利益输送/掏空风险","severity":"high","confidence":0.70,"stats":_fresh_stats("2026-09-18")},
        {"id":"AX-008","name":"流动性压力严峻","field":"liquidity_stress","op":"level_gte","threshold":"severe","conclusion":"流动性压力严峻 → 再融资风险","severity":"high","confidence":0.72,"stats":_fresh_stats("2026-09-18")},
        {"id":"AX-009","name":"AI实体化临界点","field":"ai_embodiment_level","op":"level_gte","threshold":"physical_lab","conclusion":"AI 实体化临界点：从模拟进入物理闭环","severity":"high","confidence":0.80,"stats":_fresh_stats("2026-09-19")},
        {"id":"AX-010","name":"AI安全叙事升温","field":"ai_safety_concern","op":"is_true","threshold":None,"conclusion":"AI 安全叙事升温 → 监管/放缓/第三方评估预期","severity":"medium","confidence":0.75,"stats":_fresh_stats("2026-09-19")},
        {"id":"AX-011","name":"递归自我改进信号","field":"ai_self_improvement","op":"is_true","threshold":None,"conclusion":"递归自我改进信号 → 能力跃迁/控制忧虑","severity":"high","confidence":0.78,"stats":_fresh_stats("2026-09-19")},
        {"id":"AX-012","name":"AI生物融合","field":"bio_ai_integration","op":"is_true","threshold":None,"conclusion":"AI-生物融合 → 罕见病/药物研发范式转移","severity":"medium","confidence":0.72,"stats":_fresh_stats("2026-09-19")},
    ]
    scales = {
        "inflation_pressure": ["low", "moderate", "high", "very_high"],
        "policy_tightening_probability": ["unlikely", "possible", "likely", "near_certain"],
        "liquidity_stress": ["none", "mild", "severe"],
        "governance_risk": ["low", "moderate", "high"],
        "ai_embodiment_level": ["digital_only", "hybrid", "physical_lab", "full_automation"],
    }
    return {"version": "5.0-p1", "updated_at": None, "axioms": axioms, "level_scales": scales}


def _fresh_stats(created: str) -> Dict[str, Any]:
    return {"hits": 0, "true_positives": 0, "false_positives": 0,
            "last_triggered": None, "created_at": created, "source": "manual"}


def _days_since(iso_ts: Optional[str]) -> int:
    if not iso_ts:
        return 0  # 无记录=刚创建，不衰减
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except Exception:
        return 0


# 全局 store（模块级单例，启动加载）
_STORE = _load_store()
LEVEL_SCALES = _STORE.get("level_scales", {})


def _axioms_list() -> List[Rule]:
    """从 store 构造 Rule 列表。"""
    return [Rule(
        id=a["id"], name=a["name"], field=a["field"], op=a["op"],
        threshold=a.get("threshold"), conclusion=a.get("conclusion", ""),
        severity=a.get("severity", "medium"), confidence=a.get("confidence", 0.85)
    ) for a in _STORE.get("axioms", [])]


def _find_axiom(rule_id: str) -> Optional[Dict[str, Any]]:
    for a in _STORE.get("axioms", []):
        if a["id"] == rule_id:
            return a
    return None


# ---------- 判定逻辑（不变） ----------

def _parse_fact(val: Any):
    if isinstance(val, dict):
        v = val.get("value", val.get("v"))
        c = str(val.get("cmp", val.get("op", "eq"))).lower()
        return v, (c if c in _DIRECTIONS else "eq")
    return val, "eq"


def _rank(field: str, label: Any):
    scale = LEVEL_SCALES.get(field)
    if not scale or not isinstance(label, str):
        return None
    key = label.strip().lower().replace("-", "_").replace(" ", "_")
    return scale.index(key) if key in scale else None


def _cmp(op: str, val: Any, thr: Any, field: Optional[str] = None) -> bool:
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


# ---------- 核心 API（带追踪） ----------

def check_axiom(facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """facts: [{field:value,...}]；返回命中公理列表（同一条公理一次调用最多记一条），并更新 store 命中统计。"""
    triggered: List[Dict[str, Any]] = []
    seen: set = set()
    now_iso = datetime.now(timezone.utc).isoformat()
    axioms = _axioms_list()

    for f in facts:
        for r in axioms:
            if r.id in seen:
                continue
            if r.field in f and _cmp(r.op, f[r.field], r.threshold, field=r.field):
                seen.add(r.id)
                triggered.append({
                    "rule_id": r.id, "name": r.name, "conclusion": r.conclusion,
                    "severity": r.severity, "confidence": r.confidence,
                    "field": r.field, "value": f[r.field], "threshold": r.threshold,
                })
                # 更新命中统计
                ax = _find_axiom(r.id)
                if ax:
                    stats = ax.setdefault("stats", _fresh_stats("2026-09-19"))
                    stats["hits"] = stats.get("hits", 0) + 1
                    stats["last_triggered"] = now_iso

    if triggered:
        _save_store(_STORE)
    return triggered


def verify_conclusion(conclusion_violates: List[str]) -> Dict[str, Any]:
    known = {r.id: r for r in _axioms_list()}
    hit = [known[i] for i in conclusion_violates if i in known]
    return {
        "consistent": len(hit) == 0,
        "violations": [{"rule_id": r.id, "name": r.name, "conclusion": r.conclusion} for r in hit],
        "checked": len(conclusion_violates),
    }


def all_axioms() -> List[Dict[str, Any]]:
    return _STORE.get("axioms", [])


def axiom_by_id(rule_id: str) -> Optional[Dict[str, Any]]:
    return _find_axiom(rule_id)


def add_axiom(rule: Dict[str, Any]) -> Dict[str, Any]:
    """新增公理；若 ID 已存在则覆盖（保留 stats）。"""
    existing = _find_axiom(rule.get("id", ""))
    if existing:
        old_stats = existing.get("stats", _fresh_stats("2026-09-19"))
        existing.update(rule)
        existing["stats"] = old_stats
        msg = "updated"
    else:
        rule.setdefault("stats", _fresh_stats(datetime.now(timezone.utc).strftime("%Y-%m-%d")))
        rule["stats"]["source"] = "auto" if rule.get("auto") else "manual"
        _STORE["axioms"].append(rule)
        msg = "added"
    _save_store(_STORE)
    return {"status": msg, "rule_id": rule["id"]}


def update_axiom_stats(rule_id: str, feedback: str) -> Dict[str, Any]:
    """反馈更新: feedback='tp'/'fp'/'deprecated'。"""
    ax = _find_axiom(rule_id)
    if not ax:
        return {"status": "not_found", "rule_id": rule_id}
    stats = ax.setdefault("stats", _fresh_stats("2026-09-19"))
    if feedback == "tp":
        stats["true_positives"] = stats.get("true_positives", 0) + 1
    elif feedback == "fp":
        stats["false_positives"] = stats.get("false_positives", 0) + 1
    elif feedback == "deprecated":
        ax["confidence"] = 0.0
        ax["severity"] = "deprecated"
    _save_store(_STORE)
    return {"status": "ok", "rule_id": rule_id, "feedback": feedback}


def axiom_stats(rule_id: Optional[str] = None) -> Dict[str, Any]:
    if rule_id:
        ax = _find_axiom(rule_id)
        return ax.get("stats", {}) if ax else {}
    return {a["id"]: a.get("stats", {}) for a in _STORE.get("axioms", [])}


def delete_axiom(rule_id: str) -> Dict[str, Any]:
    before = len(_STORE.get("axioms", []))
    _STORE["axioms"] = [a for a in _STORE.get("axioms", []) if a["id"] != rule_id]
    after = len(_STORE["axioms"])
    if after < before:
        _save_store(_STORE)
        return {"status": "deleted", "rule_id": rule_id}
    return {"status": "not_found", "rule_id": rule_id}


# ---------- 兼容旧接口 ----------

def axiom_field_spec() -> List[Dict[str, Any]]:
    """公理字段清单 (单一真源) — 供 extract prompt 动态构建。"""
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
        "geo_conflict_escalation": "是否存在地缘冲突升级（军事打击、空袭、封锁、报复威胁、海峡/航运中断）(布尔 true/false)",
        "export_control_tightening": "是否存在关键技术与物项出口管制收紧（出口许可、禁运、实体清单）(布尔 true/false)",
        "ai_safety_narrative_clash": "是否存在 AI 安全/能力叙事的公开对抗（末日论 vs 加速论、监管呼吁 vs 驳斥）(布尔 true/false)",
        "ai_capital_burn_rate": "AI 资本投入/烧钱强度等级 (定性)",
        "semiconductor_cost_transmission": "是否存在半导体产业链成本传导（原材料/代工涨价转嫁下游）(布尔 true/false)",
        "ai_chip_architecture_shift": "是否存在 AI 芯片架构从 GPU 通用向 ASIC/XPU 定制的转型信号 (布尔 true/false)",
        "regulatory_systematization": "是否存在政策/监管体系化规制信号（准入-退出-价格-竞争-平台-标准组合拳，而非单点表态）(布尔 true/false)",
        "alliance_deterrence_decay": "是否存在联盟威慑/军援承诺贬值信号（对盟友交付延迟、库存见底、盟友自寻安全替代）(布尔 true/false)",
        "domestic_advanced_memory_mass_production": "是否存在国产高端存储（DRAM/LPDDR/HBM 等）量产或新一代技术平台量产 (布尔 true/false)",
        "vulnerability_monetization": "是否存在脆弱性变现/成瘾剥削信号：以行为数据建模识别用户成瘾或认知偏差、将营销/供给资源定向倾斜至最易受损群体、且有反向防护/干预方案被关停或搁置 (布尔 true/false)",
    }
    return [{"axiom": a["id"], "field": a["field"], "op": a["op"], "threshold": a.get("threshold"),
             "meaning": a.get("conclusion", ""), "hint": hints.get(a["field"], ""),
             "scale": LEVEL_SCALES.get(a["field"])} for a in _STORE.get("axioms", [])]


# ---------- P3: 置信度刷新 ----------

def refresh_confidence(dry_run: bool = False, decay_base: float = 0.95,
                       deprecated_threshold: float = 0.30) -> Dict[str, Any]:
    """基于时间衰减 + 反馈准确率刷新所有公理置信度。

    公式: confidence_new = base_conf × (decay_base ^ days_since_last_hit) × accuracy
    accuracy = tp / (tp + fp + 1)
    """
    refreshed = []
    now = datetime.now(timezone.utc).isoformat()
    for ax in _STORE.get("axioms", []):
        # 首次刷新时记录 base_confidence
        if "base_confidence" not in ax:
            ax["base_confidence"] = ax.get("confidence", 0.85)
        base = ax["base_confidence"]
        stats = ax.get("stats", {})
        days = _days_since(stats.get("last_triggered"))
        tp = stats.get("true_positives", 0)
        fp = stats.get("false_positives", 0)
        if (tp + fp) > 0:
            accuracy = tp / (tp + fp + 1)
        elif stats.get("hits", 0) == 0:
            accuracy = 1.0  # 无触发且无反馈 = 中性
        else:
            accuracy = 1.0  # 有触发但无反馈 = 暂时中性
        new_conf = round(base * (decay_base ** days) * accuracy, 4)
        old_conf = ax.get("confidence", base)
        action = "kept"
        if new_conf < deprecated_threshold and ax.get("severity") != "deprecated":
            action = "deprecated"
            if not dry_run:
                ax["confidence"] = 0.0
                ax["severity"] = "deprecated"
        elif not dry_run:
            ax["confidence"] = new_conf
        refreshed.append({
            "rule_id": ax["id"], "old": old_conf, "new": new_conf if action != "deprecated" else 0.0,
            "days_since_hit": days, "accuracy": round(accuracy, 4), "action": action,
        })
    if not dry_run:
        _save_store(_STORE)
    return {"dry_run": dry_run, "refreshed": refreshed, "timestamp": now,
            "n_deprecated": sum(1 for r in refreshed if r["action"] == "deprecated"),
            "n_changed": sum(1 for r in refreshed if r["old"] != r["new"] and r["action"] != "deprecated")}
