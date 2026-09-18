"""P1 验收脚本 — 光智科技案例 (来自 6/28 文档的回归案例)。

用法: .venv/bin/python l1_graph/ingest.py
跑完打印: 图规模 / 触发公理 / 从事实到公理的路径。
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import axioms as AX
from graph_client import GraphClient

BUNDLE = {
    "entities": [
        {"id": "e:guangzhi", "name": "光智科技", "type": "Company"},
        {"id": "e:xianrui", "name": "先锐科技", "type": "Company"},
        {"id": "e:zhushihui", "name": "朱世会", "type": "Person", "props": {"role": "Controller"}},
    ],
    "facts": [
        {"id": "f:acq", "content": "光智科技出资3亿收购先锐科技", "strength": 0.9,
         "confidence": 0.9, "source": "doc"},
        {"id": "f:premium", "content": "标的净资产仅4251万 → 溢价率≈7.1x", "strength": 0.95,
         "confidence": 0.9, "source": "doc"},
    ],
    "relations": [
        {"src": "e:guangzhi", "rel": "ACQUIRES", "dst": "e:xianrui",
         "props": {"amount": "3亿", "premium_ratio": 7.1}},
        {"src": "e:zhushihui", "rel": "CONTROLS", "dst": "e:guangzhi",
         "props": {"confidence": 0.99}},
        {"src": "f:acq", "rel": "MENTIONS", "dst": "e:guangzhi"},
        {"src": "f:acq", "rel": "MENTIONS", "dst": "e:xianrui"},
    ],
}


def main():
    gc = GraphClient()
    gc.verify()
    gc.init_schema()
    for r in AX.all_axioms():
        gc.upsert_rule(r)
    print("ingest:", gc.ingest_bundle(BUNDLE))

    # 公理检查
    facts_for_axioms = [
        {"premium_ratio": 7.1},
        {"control_confidence": 0.99},
    ]
    triggered = AX.check_axiom(facts_for_axioms)
    print("\n触发公理:")
    for t in triggered:
        print(f"  [{t['rule_id']}] {t['name']} → {t['conclusion']}  (conf {t['confidence']})")
        gc.link_fact_rule("f:premium", t["rule_id"])

    # 路径验证: 事实 → 公理
    path = gc.query(
        "MATCH p=(f:Fact)-[:TRIGGERS]->(r:Rule) "
        "RETURN f.id AS fact, r.id AS rule, r.conclusion AS conclusion"
    )
    print("\n图路径 (Fact)-[:TRIGGERS]->(Rule):")
    for row in path:
        print(" ", row)

    print("\n图规模:", gc.stats())
    gc.close()


if __name__ == "__main__":
    main()
