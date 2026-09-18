"""L3 拓扑层 — 持续同调 / 空洞检测 / 临界转变 / 连通分量
对齐 6/28 文档 `TopologicalMonitor`。

库: giotto-tda (VietorisRipsPersistence)。
giotto-tda 与 numpy>=2 不兼容 → 本层跑在独立 venv `.venv_topo` (numpy<2),
契合文档"TDA 异步 / 睡眠周期执行, 不进推理路径"的设定。

融合点 (文档原文):
  拓扑空洞 → 逻辑矛盾/信息缺失
  临界转变 → 触发专家系统预警
  分形维度 → 系统复杂度评估
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

try:
    from gtda.homology import VietorisRipsPersistence
    _HAS_GTDA = True
except Exception:  # pragma: no cover
    _HAS_GTDA = False

MAX_POINTS = int(os.getenv("L3_MAX_POINTS", "200"))
DEFAULT_HISTORY = os.path.join(os.path.dirname(__file__), "..", "data", "l3_history.jsonl")
HISTORY_FILE = os.getenv("L3_HISTORY", DEFAULT_HISTORY)


# ---------------------------------------------------------------- 工具

def as_matrix(points) -> np.ndarray:
    """接受 [[...]] 或 {"points"/"embedding": [...]}, 统一成 (n, d)。"""
    if isinstance(points, dict):
        points = points.get("points") or points.get("embedding") or []
    arr = np.asarray(points, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.size == 0:
        arr = arr.reshape(0, 0)
    return arr


def subsample(arr: np.ndarray, max_points: int = MAX_POINTS, seed: int = 0) -> np.ndarray:
    """点云过大时确定性下采样 (VR 复杂度 O(n^2))。"""
    n = arr.shape[0]
    if n <= max_points:
        return arr
    rng = np.random.default_rng(seed)
    idx = np.sort(rng.choice(n, size=max_points, replace=False))
    return arr[idx]


# ---------------------------------------------------------------- 持续同调

def persistent_homology(points, maxdim: int = 1):
    """Vietoris-Rips 持续同调 → 每个同调维的持续图 [birth, death]。

    返回 (arr, diagrams, meta)；diagrams[k] = [[birth, death], ...]。
    无 giotto-tda 时退化为单链聚类 (只出 H0)。
    """
    arr = subsample(as_matrix(points))
    n = arr.shape[0]
    diagrams: List[List[List[float]]] = [[] for _ in range(maxdim + 1)]
    if n < 2:
        return arr, diagrams, {"backend": "none", "n_points": n, "dim": int(arr.shape[1]) if arr.ndim == 2 else 0}

    if _HAS_GTDA:
        # reduced_homology=False: 保留 H0 本质类(死期=inf), 否则连通分量恒少 1
        vr = VietorisRipsPersistence(homology_dimensions=list(range(maxdim + 1)),
                                     n_jobs=-1, reduced_homology=False)
        dg = vr.fit_transform([arr])[0]            # (n_features, 3): [birth, death, dimension]
        for row in dg:
            b, d, q = float(row[0]), float(row[1]), int(round(row[2]))
            # 仅 b<d 有意义; b==d 是 padding (gtda transform docstring)
            if b < d and 0 <= q <= maxdim:
                diagrams[q].append([b, d])
        backend = "giotto-tda/VietorisRips"
    else:  # 退化: H0 = 单链聚类合并距离
        from scipy.sparse.csgraph import minimum_spanning_tree
        from scipy.spatial.distance import pdist, squareform
        dm = squareform(pdist(arr))
        mst = minimum_spanning_tree(dm).toarray()
        for w in np.sort(mst[mst > 0]):
            diagrams[0].append([0.0, float(w)])
        diagrams[0].append([0.0, float("inf")])
        backend = "fallback(single-linkage)"

    from scipy.spatial.distance import pdist
    diameter = float(np.max(pdist(arr))) if n >= 2 else 0.0
    return arr, diagrams, {"backend": backend, "n_points": n, "dim": int(arr.shape[1]),
                           "diameter": round(diameter, 6)}


def significant_holes(diagram_h1, rel: float = 0.4, floor: float = 0.0):
    """显著 H1 空洞: 持续度 >= max(floor, rel * 最大持续度)。

    floor 一般传 0.05*点云直径, 作为噪声底 (小样本均匀点云会产生微小伪空洞)。
    """
    finite = [d - b for b, d in diagram_h1 if np.isfinite(d)]
    holes: List[Dict[str, float]] = []
    if not finite:
        return holes, 0.0
    thr = max(float(floor), rel * max(finite))
    for b, d in diagram_h1:
        if np.isfinite(d) and (d - b) >= thr:
            holes.append({"birth": round(b, 4), "death": round(d, 4),
                          "persistence": round(d - b, 4), "midpoint": round((b + d) / 2, 4)})
    holes.sort(key=lambda h: -h["persistence"])
    return holes, round(thr, 4)


def count_components(diagram_h0, ref: Optional[float] = None, rel: float = 0.25) -> int:
    """连通分量(知识簇)数 = 尺度 eps 处仍存活的 H0 类数。

    eps = rel * ref, ref 为点云直径 (max pairwise distance)。
    用直径而非"最大有限 death"作参照: 均匀环/流形的 H0 合并距离彼此接近,
    "半个最大 death"会误判成几十个分量。
    """
    if not diagram_h0:
        return 0
    if ref is None:
        deaths = [d for _, d in diagram_h0 if np.isfinite(d)]
        ref = max(deaths) if deaths else 0.0
    eps = rel * ref
    return int(sum(1 for _, d in diagram_h0 if (not np.isfinite(d)) or d > eps))


# ---------------------------------------------------------------- 监控器

class TopologicalMonitor:
    """对齐文档: history + detect_critical_transition。"""

    def __init__(self, history_file: Optional[str] = HISTORY_FILE, max_history: int = 200):
        self.history_file = history_file
        self.max_history = max_history
        self.history: List[Dict[str, Any]] = []

    def analyze(self, points, maxdim: int = 1, rel: float = 0.4) -> Dict[str, Any]:
        import fractal as _F  # 同目录 (service 已把本目录加入 sys.path)
        arr, diagrams, meta = persistent_homology(points, maxdim=maxdim)
        d0 = diagrams[0] if diagrams else []
        d1 = diagrams[1] if len(diagrams) > 1 else []
        dia = meta.get("diameter") or 0.0
        holes, thr = significant_holes(d1, rel=rel, floor=0.05 * dia)
        comp = count_components(d0, ref=dia)

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "n_points": meta["n_points"],
            "diameter": meta.get("diameter"),
            "components": comp,
            "num_holes": len(holes),
            "holes": holes,
            "hole_threshold": thr,
        }
        # 盒计数在点数过少(<8)时无意义 (计数区间不足), 不记录, 避免污染临界转变
        if meta["n_points"] >= 8:
            entry["fractal_dimension"] = round(_F.box_counting_dimension(arr), 4)

        self.history.append(entry)
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
        self._persist(entry)

        ct = self.detect_critical_transition()
        return {
            "status": "ok",
            **entry,
            "critical_transition": ct,
            "has_conflict": bool(len(holes) or ct),
            "backend": meta["backend"],
            "persistence": {
                "H0": [[round(b, 4), (round(d, 4) if np.isfinite(d) else None)] for b, d in d0],
                "H1": [[round(b, 4), round(d, 4)] for b, d in d1 if np.isfinite(d)],
            },
        }

    def detect_critical_transition(self, delta_threshold: int = 2, frac_threshold: float = 0.5):
        """文档: 空洞数突变(>2) → 预警；另加分形维突变。

        只在相邻两次快照可比(点数同量级, 0.5x ~ 2x)时比较, 否则返回 None ——
        否则不同实体集的快照互相比较会产出假"剧变"。
        """
        if len(self.history) < 2:
            return None
        cur, prev = self.history[-1], self.history[-2]
        n_cur, n_prev = cur.get("n_points", 0), prev.get("n_points", 0)
        if not (n_prev and 0.5 <= n_cur / n_prev <= 2.0):
            return None  # 无可比基线 (点数差异过大)
        dh = cur["num_holes"] - prev["num_holes"]
        alert = None
        if abs(dh) > delta_threshold:
            alert = {"alert": "拓扑结构剧变", "type": "critical_transition",
                     "holes_delta": dh, "from": prev["num_holes"], "to": cur["num_holes"]}
        fdc, fdp = cur.get("fractal_dimension"), prev.get("fractal_dimension")
        if fdc is not None and fdp is not None and abs(fdc - fdp) > frac_threshold:
            alert = alert or {"alert": "分形维突变", "type": "critical_transition",
                              "fractal_delta": round(fdc - fdp, 4),
                              "from": fdp, "to": fdc}
        return alert

    def reset(self):
        self.history = []

    def _persist(self, entry: Dict[str, Any]):
        """落盘 (睡眠周期异步可达)。失败不阻断。"""
        try:
            path = os.path.abspath(self.history_file)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass


MONITOR = TopologicalMonitor()
