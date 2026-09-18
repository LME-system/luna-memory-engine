"""L1 Graph-Service — Neo4j 连接层 + 构图/查询。

图模型 (Entity-Relation-Attribute, 对齐 6/28 决策4):
  (:Entity {id,name,type})          实体
  (:Fact   {id,content,strength,confidence,source,ts})  事实
  (:Rule   {id,name,...})           公理(约束节点)
  关系: ACQUIRES / CONTROLS / CAUSES{strength,confidence,sign} / TRIGGERS / MENTIONS
"""
from __future__ import annotations
import os
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase

URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
AUTH = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASS", "luna_sgp_local"))

SCHEMA = [
    "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT fact_id IF NOT EXISTS FOR (f:Fact) REQUIRE f.id IS UNIQUE",
    "CREATE CONSTRAINT rule_id IF NOT EXISTS FOR (r:Rule) REQUIRE r.id IS UNIQUE",
    "CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)",
]


class GraphClient:
    def __init__(self, uri: str = URI, auth=AUTH):
        self._d = GraphDatabase.driver(uri, auth=auth)

    def close(self):
        self._d.close()

    def verify(self):
        self._d.verify_connectivity()
        return True

    def init_schema(self):
        with self._d.session() as s:
            for stmt in SCHEMA:
                s.run(stmt)
        return len(SCHEMA)

    # ---------- 写入 ----------
    def upsert_entity(self, e: Dict[str, Any]):
        with self._d.session() as s:
            s.run(
                "MERGE (n:Entity {id:$id}) SET n.name=$name, n.type=$type, n += $props",
                id=e["id"], name=e["name"], type=e.get("type", "Unknown"),
                props=e.get("props", {}),
            )

    def upsert_fact(self, f: Dict[str, Any]):
        with self._d.session() as s:
            s.run(
                "MERGE (n:Fact {id:$id}) SET n.content=$content, n.strength=$strength, "
                "n.confidence=$confidence, n.source=$source, n.ts=$ts",
                id=f["id"], content=f.get("content", ""), strength=f.get("strength", 0.5),
                confidence=f.get("confidence", 0.8), source=f.get("source"),
                ts=f.get("ts"),
            )

    def upsert_rule(self, r: Dict[str, Any]):
        with self._d.session() as s:
            s.run(
                "MERGE (n:Rule {id:$id}) SET n += $props",
                id=r["id"], props={k: v for k, v in r.items() if k != "id"},
            )

    def add_relation(self, src: str, rel: str, dst: str, props: Optional[dict] = None):
        props = props or {}
        rel = "".join(c for c in rel.upper() if c.isalnum() or c == "_")
        q = (
            f"MATCH (a) WHERE a.id=$src MATCH (b) WHERE b.id=$dst "
            f"MERGE (a)-[r:{rel}]->(b) SET r += $props"
        )
        with self._d.session() as s:
            s.run(q, src=src, dst=dst, props=props)

    def link_fact_rule(self, fact_id: str, rule_id: str):
        with self._d.session() as s:
            s.run(
                "MATCH (f:Fact {id:$f}) MATCH (r:Rule {id:$r}) MERGE (f)-[:TRIGGERS]->(r)",
                f=fact_id, r=rule_id,
            )

    # ---------- 查询 ----------
    def query(self, cypher: str, params: Optional[dict] = None) -> List[Dict[str, Any]]:
        with self._d.session() as s:
            return [dict(rec) for rec in s.run(cypher, params or {})]

    def stats(self) -> Dict[str, int]:
        out = {}
        for label in ("Entity", "Fact", "Rule"):
            with self._d.session() as s:
                out[label] = s.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()["c"]
        return out

    def ingest_bundle(self, bundle: Dict[str, Any]) -> Dict[str, int]:
        for e in bundle.get("entities", []):
            self.upsert_entity(e)
        for f in bundle.get("facts", []):
            self.upsert_fact(f)
        for r in bundle.get("rules", []):
            self.upsert_rule(r)
        n_rel = 0
        for rel in bundle.get("relations", []):
            self.add_relation(rel["src"], rel["rel"], rel["dst"], rel.get("props"))
            n_rel += 1
        return {
            "entities": len(bundle.get("entities", [])),
            "facts": len(bundle.get("facts", [])),
            "rules": len(bundle.get("rules", [])),
            "relations": n_rel,
        }
