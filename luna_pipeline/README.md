# Luna SGP — Symbolic-Geometric Pipeline (真实现)

按老吴 2026-06-28 架构文档实现，**不是 prompt wrapper**。
参考：`memory/2026-06-28_symbolic_geometric_pipeline.md`、`memory/2026-06-28_luna_architecture_decisions.md`

## 目标架构（四层，微服务）

```
                     API Gateway
                          │
     ┌────────────────────┼────────────────────┐
     ▼                    ▼                    ▼
Graph-Service(:8001)  Geo-Service(:8002)  Mind-Service(:8003)
  Neo4j + Cypher        PyTorch + geoopt     LangGraph
  专家规则(公理)         Poincaré/动态维度     编排 + LLM 综合
     └────────────────────┼────────────────────┘
                 Shared Storage (Redis/SQLite)
```

## 四层定义（严格按文档，杜绝"修辞化"）

| 层 | 文档定义 | 真实现要素 | 对应目录 |
|---|---|---|---|
| **L1 符号层** | 结构化知识图谱 + 专家规则 | Neo4j 图、Cypher、公理(约束节点) | `l1_graph/` |
| **L2 几何层** | 表征投影 / 动态流形空间 | 嵌入(nomic-embed)→Poincaré/欧氏、测地线、同构检测、冲突升维 | `l2_geo/` |
| **L3 拓扑层** | 拓扑分析 | 持续同调(空洞)、Mapper、Hausdorff 分形维、临界转变 | `l3_topo/` |
| **L4 编排层** | 神经符号控制器 | LangGraph 状态机，决定何时调 L2/L3 | `l4_mind/` |

## 实施顺序（架构决策文档：渐进演进, L1→L4→L2→L3）

- [x] **P0 基础设施**：Neo4j(Docker) + Redis + 项目骨架 `✅ 2026-09-17`
- [x] **P1 L1**：Graph-Service；图模型 + AX 公理编码 + 方向保真比较 `✅ 2026-09-17 / 09-18`
  - `docker compose up -d` → luna-neo4j(:7474/:7687) + luna-redis(:6379)
  - `l1_graph/`：models / axioms / graph_client / service(:8001) / ingest
  - 验收：光智科技案例 → AX-002 高溢价 + AX-001 控制权 触发，(Fact)-[:TRIGGERS]->(Rule) 路径可查
  - 接口 /health /ingest /query /check_axiom /verify /stats 全通
  - ⚠️ 注：v4.0 的 CPR/MCMC 代码在仓里已不存在（luna_v4 空），图模型按 6/28 文档重建
- [x] **P2 L4**：LangGraph 编排骨架 `✅ 2026-09-17`
  - `l4_mind/orchestrator.py`：StateGraph `extract→symbolic→route→(geometry→topology→upscale?)→verify→synthesize`
  - 条件边：公理 conf≥0.9 走快速路径(直答)；否则进 L2/L3 增强；拓扑临界→upscale
  - `l4_mind/service.py`(:8003)：/health /orchestrate /extract /synthesize
  - L2/L3 未就绪时优雅降级 (not_ready/skipped)，不阻断链路
  - 验收：光智案例 trace=extract→symbolic[AX-002]→geometry:not_ready→topology:skipped→verify→synthesize ✓
  - ✅ 2026-09-18 修复 extract 公理字段映射（BoE 通胀案例现已触发 AX-004）：
    - **单一真源**：`axioms.axiom_field_spec()` 动态生成 extract prompt 的字段清单，prompt 与公理不再脱节
    - **方向保真**：事实值支持 `{"value":X,"cmp":"gt|gte|lt|lte"}`，"高于4%" 不再退化成"等于4"；`_cmp` 改为区间相交（边界安全）
    - **结构化输出**：ollama `format` JSON schema 约束外层结构；温度 0
    - 回归：`l1_graph/test_axioms.py` 全过（含方向保真）；`/orchestrate` BoE 案例 trace 出现 `symbolic:rules=['AX-004']`
- [x] **P3 L2**：Geo-Service(:8002) —— nomic-embed(768d) → Dual-Embedding(欧氏余弦 + Poincaré expmap0) + 测地线 + 形状同构 + 冲突升维 `✅ 2026-09-18`
  - `l2_geo/`：embedding.py / manifold.py / service.py，独立 venv `.venv_geo`(geoopt 0.5.1 + torch 2.8)
  - 接口 /health /project /analogy /upscale /embed 全通；与 L4 打通(geometry:ok)
  - **修 bug #1（半径退化）**：旧 `to_poincare` 把每行归一化再乘同一 scale=0.5 → 所有点同半径(0.4621)，双曲只剩方向、丢了层级。改为 centroid-depth proxy：半径 = 离全局质心的角距离(越特异越靠边界)。⚠️ 仍是无监督代理，非 Nickel&Kiela 黎曼学习嵌入，待接 L1 图结构后升级
  - **修 bug #2（prompt 炸裂）**：L4 synthesize 原样把 L2 结果(含 768d embedding + 测地线矩阵)塞进 LLM prompt → 30k+ tokens、prompt 处理 >6min 卡死。加 `_slim_geo()` 剔除重型数组
  - ⚠️ 待办：中心化方向用质心差会更严谨；depth 对语义接近的文本区分度低
- [x] **P4 L3**：Topo-Service(:8004) —— 持续同调(空洞/连通分量) + 临界转变 + Hausdorff 分形维 `✅ 2026-09-18`
  - `l3_topo/`：topology.py(持久同调/监控器) / fractal.py(盒计数) / service.py / test_l3.py
  - 库：**giotto-tda 0.6.2**（独立 venv `.venv_topo`，numpy<2 —— 方案 A，忠于文档）
  - 接口 /health /analyze /fractal /history /reset
  - 回归测试：圆环→1洞、三环→3洞、两分离簇→2分量、分形维(线≈1/面≈2)、临界转变(0→3洞触发) 全过
  - **踩坑**：gtda 持续图三元组是 `[birth, death, dimension]`（非文档字面的 [dim,...]）；`reduced_homology=False` 才有 H0 本质类（否则分量恒少1）；盒计数须剔除饱和段(计数<n/2)；history 跨不同点数快照比较会产生假"临界转变"→ 加可比性护栏
- [~] **P5**：全链路压测（光智科技案例回归）
  - 2026-09-18 首跑(L3 未建)：HTTP 200，130s
  - 2026-09-18 集成跑(L3 接入)：HTTP 200，**48s**；trace: extract:ok → symbolic:[AX-002] → geometry:ok → **topology:ok** → verify:done → synthesize:done
  - L3 结果：comp=3, holes=0, conflict=False；输出"高度疑似利益输送" conf 0.92
  - 端到端延迟瓶颈 = gemma4:31b 两次调用（extract+synthesize），本地 ~7-8 tok/s

## 启动

```bash
bash luna_pipeline/run_services.sh   # 起 L1(:8001)/L2(:8002)/L4(:8003)，含健康检查
```

## 硬约束（架构决策文档已定）

- **TDA 异步**：L3 开销大，只在"睡眠周期"跑，不进推理路径
- **Dual-Embedding**：欧氏(检索) + Poincaré(结构) 并存，避免维度坍缩
- **Constrained Decoding**：公理作为 prompt hard constraint

## 环境（2026-09-17 实测）

- Python 3.9.6 (系统) | numpy 2.0.2 | torch 2.8.0 | networkx 3.2.1 | sklearn 1.6.1
- Docker ✅（无容器运行）| neo4j ❌（待容器化）
- 缺：geoopt / umap-learn / fastapi / redis / langgraph / giotto-tda
- ⚠️ **giotto-tda 与 numpy 2.0 不兼容** → L3 用 `gudhi` 或独立 venv 锁 numpy<2
- ⚠️ GPU 争用：gemma4:31b/Qwen 与嵌入计算不可同时重载（9/9 结论）
