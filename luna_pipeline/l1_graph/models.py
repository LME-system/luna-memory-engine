"""L1 符号层 — 数据模型 (对齐 JSON-LD reasoning_state.schema.json)"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class Entity:
    id: str
    name: str
    type: str                      # Company / Person / Country / Commodity / Asset ...
    props: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Fact:
    id: str
    content: str
    strength: float = 0.5          # 信号强度 0..1
    confidence: float = 0.8
    source: Optional[str] = None
    ts: Optional[str] = None


@dataclass
class Relation:
    src: str                       # entity/fact id
    rel: str                       # ACQUIRES / CONTROLS / CAUSES / TRIGGERS ...
    dst: str
    props: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Rule:
    """公理 = 图中的约束节点"""
    id: str
    name: str
    field: str                     # 作用对象字段
    op: str                        # gt / gte / lt / lte / eq / in / is_false
    threshold: Any = None
    conclusion: str = ""
    severity: str = "medium"       # low / medium / high
    confidence: float = 0.85

    def to_props(self) -> Dict[str, Any]:
        d = asdict(self)
        return d
