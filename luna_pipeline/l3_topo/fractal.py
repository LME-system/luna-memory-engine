"""Hausdorff / 盒计数 分形维 (6/28 文档 `compute_fractal_dimension`)。

用于"系统复杂度评估"。归一化到单位立方体后按不同边长铺盒, 拟合
log(1/s) ~ log(N(s)) 的斜率即分形维。

⚠️ 局限: 点云点数少、维数高(768d)时, 盒计数对尺度极敏感、噪声大。
本实现只用计数随尺度变化的线性段, 结果仅作相对复杂度的粗略指标。
"""
from __future__ import annotations

from typing import Optional

import numpy as np


def box_counting_dimension(points, scales: Optional[np.ndarray] = None, n_scales: int = 20) -> float:
    arr = np.asarray(points, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.shape[0] < 4:
        return 0.0

    mn = arr.min(axis=0)
    span = np.clip(arr.max(axis=0) - mn, 1e-12, None)
    z = (arr - mn) / span                      # 单位立方体

    if scales is None:
        scales = np.logspace(0, -3, n_scales)  # 盒边长 1 → 1e-3

    n = arr.shape[0]
    counts = []
    for s in scales:
        nb = np.floor(z / s).astype(np.int64)
        counts.append(len(set(map(tuple, nb))))
    counts = np.asarray(counts, dtype=np.float64)
    log_c = np.log(counts)
    log_inv = np.log(1.0 / scales)

    # 有效区间: 计数既未塌到 1 (尺度太大), 也未进入饱和段 (尺度小于点间距,
    # 计数趋近 n 时斜率人为变平)。剔除饱和段后斜率才恢复真实维数。
    mask = (counts > 1) & (counts < 0.5 * n)
    if mask.sum() < 2:
        return 0.0

    slope = float(np.polyfit(log_inv[mask], log_c[mask], 1)[0])
    return max(0.0, slope)
