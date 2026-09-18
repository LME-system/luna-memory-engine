"""L1 公理比较逻辑回归测试 (含方向保真)。
跑: ../.venv/bin/python test_axioms.py  (cwd=l1_graph)
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import axioms as AX

CASES = [
    ("premium_ratio", 7.1, ["AX-002"]),
    ("core_inflation_yoy", 4.5, ["AX-004"]),
    ("core_inflation_yoy", 4.0, []),                                # 恰等于阈值, gt 不触发
    ("core_inflation_yoy", {"value": 4.0, "cmp": "gt"}, ["AX-004"]),  # "高于4%" 触发
    ("core_inflation_yoy", {"value": 4.0, "cmp": "lt"}, []),          # "低于4%" 不触发
    ("premium_ratio", {"value": 5, "cmp": "gt"}, ["AX-002"]),
    ("liquidity_support", False, ["AX-003"]),
    ("liquidity_support", True, []),
    ("control_confidence", 0.99, ["AX-001"]),
    ("control_confidence", 0.5, []),
]


def main():
    ok = True
    for field, val, exp in CASES:
        got = [t["rule_id"] for t in AX.check_axiom([{field: val}])]
        good = got == exp
        ok &= good
        print(f"{'PASS' if good else 'FAIL'} {field}={val!r} → {got} (期望{exp})")
    print("\n==>", "ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
