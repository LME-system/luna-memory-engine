"""L3 拓扑层回归测试 (已知形状 → 已知拓扑)。

跑: .venv_topo/bin/python l3_topo/test_l3.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import topology as T
import fractal as F


def _circle(cx, cy, r, n=40):
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.c_[cx + r * np.cos(th), cy + r * np.sin(th)]


def main():
    rng = np.random.default_rng(0)
    cases = []
    # 圆环: 1 分量, 1 个 H1 空洞
    cases.append(("圆环", _circle(0, 0, 1), dict(components=1, num_holes=1)))
    # 三环: 3 分量, 3 个 H1 空洞
    tri = np.vstack([_circle(cx, cy, 0.5) for cx, cy in [(0, 0), (5, 0), (2.5, 4)]])
    cases.append(("三环", tri, dict(components=3, num_holes=3)))
    # 两分离簇: 2 分量, 无空洞
    c1 = rng.normal([0, 0], 0.05, size=(20, 2)); c2 = rng.normal([3, 0], 0.05, size=(20, 2))
    cases.append(("两分离簇", np.r_[c1, c2], dict(components=2, num_holes=0)))

    ok = True
    for name, pts, exp in cases:
        m = T.TopologicalMonitor(history_file="/tmp/l3_test_hist.jsonl"); m.reset()
        r = m.analyze(pts)
        good = all(r[k] == v for k, v in exp.items())
        ok &= good
        print(f"{'PASS' if good else 'FAIL'} {name}: comp={r['components']} holes={r['num_holes']} "
              f"frac={r.get('fractal_dimension')} 期望={exp}")

    # 分形维: 线≈1, 面≈2
    line = np.c_[np.linspace(0, 1, 5000), np.zeros(5000)]
    sq = rng.uniform(0, 1, size=(30000, 2))
    d_line, d_sq = F.box_counting_dimension(line), F.box_counting_dimension(sq)
    g1 = d_line < 1.3; g2 = d_sq > 1.5
    ok &= g1 and g2
    print(f"{'PASS' if g1 else 'FAIL'} 分形维 线={d_line:.3f} (期望≈1)")
    print(f"{'PASS' if g2 else 'FAIL'} 分形维 面={d_sq:.3f} (期望≈2)")

    # 临界转变: 0洞 → 3洞 (delta=3 > 2), 两次快照点数需同量级
    tri40 = np.vstack([_circle(cx, cy, 0.5, n=13) for cx, cy in [(0, 0), (5, 0), (2.5, 4)]])
    m = T.TopologicalMonitor(history_file="/tmp/l3_test_hist.jsonl"); m.reset()
    m.analyze(np.r_[c1, c2]); m.analyze(tri40)
    ct = m.detect_critical_transition()
    g3 = ct is not None and ct.get("holes_delta") == 3
    ok &= g3
    print(f"{'PASS' if g3 else 'FAIL'} 临界转变 0→3洞: {ct}")

    print("\n==>", "ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
