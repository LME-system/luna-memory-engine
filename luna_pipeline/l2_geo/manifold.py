"""L2 几何层 — 动态流形空间 (真数学, 对齐 6/28 文档)

- Dual-Embedding: 欧氏(快速检索) + Poincaré(双曲结构推理)
- 图节点 → 几何坐标; 边 → 测地线 (Geodesic)
- geometric_analogy: 区域形状同构检测
- 冲突 → 动态升维 (upscale)
"""
from __future__ import annotations
import numpy as np
import torch
from geoopt import PoincareBall

BALL = PoincareBall()
EPS = 1e-5


# ---------- 欧氏侧 ----------
def _norm(mat: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(mat, axis=1, keepdims=True)
    return mat / np.clip(n, EPS, None)


def euclidean_similarity(mat: np.ndarray) -> np.ndarray:
    """余弦相似度矩阵。"""
    m = _norm(mat)
    return m @ m.T


def neighbors(mat: np.ndarray, k: int = 5):
    """返回每个点的 top-k 近邻索引(不含自身)。"""
    sim = euclidean_similarity(mat)
    np.fill_diagonal(sim, -np.inf)
    idx = np.argsort(-sim, axis=1)[:, :k]
    return idx, sim


# ---------- 双曲侧 (Poincaré) ----------
def to_poincare(mat: np.ndarray, scale: float = 0.9, min_r: float = 0.15):
    """把欧氏向量投到 Poincaré 球 (半径编码层级/特异度)。

    修复旧实现退化 bug: 旧版对每行做单位归一化再乘同一 scale=0.5, 导致所有点落
    在同一半径(0.4621)的球面上 —— 双曲空间只剩"方向", 丢了"层级半径", 与文档
    "Poincaré 适合层级关系"的初衷冲突。

    现方案 (centroid-depth proxy):
      - 方向 = 单位化语义方向 v
      - 半径 = 离全局质心(典型语义)的角距离 → 越远半径越大(靠边界=越特异/层级越深),
        越近越靠原点(越泛化)
      - min_r 兜底避免塌缩到原点

    ⚠️ 这是无监督代理, 非 Nickel&Kiela(2017) 的黎曼学习嵌入。后续接入 L1 图结构
    后应换成真正的层级学习 (Riemannian SGD on Poincaré ball)。
    """
    v = _norm(mat)                                       # 单位方向
    centroid = _norm(v.mean(axis=0, keepdims=True))      # 典型语义方向
    cos = np.clip((v * centroid).sum(axis=1), -1.0, 1.0)
    depth = (1.0 - cos) / 2.0                            # 0(典型) .. 1(特异)
    radius = min_r + (scale - min_r) * depth             # 半径各异
    t = v * radius[:, None]
    return BALL.expmap0(torch.tensor(t, dtype=torch.float64))


def geodesic_matrix(points: torch.Tensor) -> np.ndarray:
    """两两测地线距离矩阵。"""
    n = points.shape[0]
    d = np.zeros((n, n))
    for i in range(n):
        di = BALL.dist(points[i].unsqueeze(0), points).squeeze(0).detach().numpy()
        d[i] = di
    return d


# ---------- 形状同构 (analogy) ----------
def region_descriptor(geo: np.ndarray, i: int, k: int) -> np.ndarray:
    """点 i 的局部形状 = 到最近 k 点的测地距离向量(排序并归一化)。"""
    d = geo[i].copy()
    d[i] = np.inf
    kk = min(k, len(d) - 1)
    v = np.sort(d)[:kk]
    v = v / np.clip(v.max(), EPS, None)
    return v


def find_analogy(geo: np.ndarray, i: int, j: int, k: int = 5):
    a = region_descriptor(geo, i, k)
    b = region_descriptor(geo, j, k)
    L = min(len(a), len(b))
    cos = float(np.dot(a[:L], b[:L]) / (np.linalg.norm(a[:L]) * np.linalg.norm(b[:L]) + EPS))
    return {"similarity": round(cos, 4), "isomorphism": cos > 0.9}


# ---------- 动态维度 ----------
def dynamic_dim(mat: np.ndarray, target_var: float = 0.9, base: int = 64, cap: int = 512):
    """按目标解释方差确定所需维度。冲突(需升维)时返回更大维度。"""
    x = mat - mat.mean(axis=0, keepdims=True)
    # SVD 方差谱
    _, s, _ = np.linalg.svd(x, full_matrices=False)
    var = (s ** 2) / np.sum(s ** 2)
    cum = np.cumsum(var)
    need = int(np.searchsorted(cum, target_var) + 1)
    dim = min(max(base, need), cap)
    return dim, float(cum[min(need, len(cum)) - 1]), need


def detect_conflict(mat: np.ndarray, geo: np.ndarray) -> dict:
    """冲突定义: 点塌缩(测地距离过小) 或 必要维度显著超出 base。"""
    dim, var, need = dynamic_dim(mat)
    off = geo[np.triu_indices_from(geo, 1)] if geo.shape[0] > 1 else np.array([])
    min_d = float(off.min()) if off.size else 0.0
    collapsed = min_d < 0.05
    return {"collapsed": collapsed, "min_geodesic": round(min_d, 4),
            "need_dim": need, "needed_var": round(var, 4)}


# ---------- 顶层: 投影 ----------
def project(labels, texts, k: int = 5):
    from embedding import embed
    vecs = np.array(embed(texts), dtype=np.float64)
    eu = _norm(vecs)
    poi = to_poincare(vecs)
    geo = geodesic_matrix(poi)
    idx, sim = neighbors(vecs, k=min(k, len(texts) - 1) if len(texts) > 1 else 0)

    neigh = []
    for i, lab in enumerate(labels):
        ns = [{"label": labels[j], "cosine": round(float(sim[i, j]), 4),
               "geodesic": round(float(geo[i, j]), 4)} for j in (idx[i] if len(idx) else [])]
        neigh.append({"label": lab, "neighbors": ns})

    dim, var, need = dynamic_dim(vecs)
    conflict = detect_conflict(vecs, geo)
    return {
        "status": "ok", "space": "dual(euclidean+poincare)",
        "dimension": dim, "base_var": round(var, 4), "need_dim": need,
        "conflict": conflict,
        "points": [{"label": labels[i],
                    "poincare_norm": round(float(torch.linalg.norm(poi[i])), 4)} for i in range(len(labels))],
        "neighbors": neigh,
        "geodesic": np.round(geo, 4).tolist(),
        "embedding": eu.tolist(),   # 欧氏侧 (768d) — 供 L3/检索
    }


def analogy_between(labels, texts, a: str, b: str, k: int = 5):
    from embedding import embed
    vecs = np.array(embed(texts), dtype=np.float64)
    poi = to_poincare(vecs)
    geo = geodesic_matrix(poi)
    i, j = labels.index(a), labels.index(b)
    return find_analogy(geo, i, j, k)


def upscale(labels, texts, target: float = 0.95):
    from embedding import embed
    vecs = np.array(embed(texts), dtype=np.float64)
    base = dynamic_dim(vecs)[0]
    dim, var, need = dynamic_dim(vecs, target_var=target)
    return {"base_dim": base, "upscaled_dim": dim, "achieved_var": round(var, 4), "need": need}
