# Luna SGP 激励/抑制模块架构设计

**日期**: 2026-08-28  
**版本**: v0.1.0  
**作者**: 阿月 + 老吴

---

## 核心概念

### 为什么需要激励/抑制？

当前的 Luna SGP 是一个**前馈系统**:
```
Input → L1 → L2 → L3 → Output
```

缺少:
1. **交互感知** - 不知道每次处理的效果如何
2. **自我评价** - 无法判断自己的表现
3. **递归改进** - 不能从历史中学习

激励/抑制模块填补这个空白，实现**元认知层**:
```
Input → L1 → L2 → L3 → Output
           ↓
    [激励/抑制引擎] ← 反馈
           ↓
    路径权重更新 → 下次优化
```

---

## 架构设计

### 1. 三层抽象

```
┌─────────────────────────────────────────────────────────────┐
│                    Meta-Cognition Layer                      │
│              (激励/抑制模块 - InhibitionEngine)               │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  交互感知    │  │  自我评价    │  │  递归改进    │         │
│  │ Perception  │  │ Evaluation  │  │  Learning   │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                    Layer 4 Orchestrator                      │
│                    (现有编排层)                               │
├─────────────────────────────────────────────────────────────┤
│  Input → Intent → L1 → [L2] → [L3] → Synthesis → Output    │
└─────────────────────────────────────────────────────────────┘
```

### 2. 核心组件

#### 2.1 CognitiveTrace (认知痕迹)

记录单次交互的完整信息:
- **各层贡献**: L1/L2/L3 的参与度
- **性能指标**: 延迟、token数、置信度
- **反馈信号**: 用户显式/隐式反馈
- **自我评价**: 内部一致性、新颖性

类比: 神经元的动作电位记录

#### 2.2 PathwayWeight (路径权重)

动态调节认知路径:
- **基础权重**: 路径的先天重要性
- **当前权重**: 经过激励/抑制调节后的有效权重
- **历史表现**: 成功率、调用次数
- **EI积累**: 激励/抑制的累积效应

类比: 神经突触的可塑性 (Hebbian Learning)

#### 2.3 SignalType (信号类型)

```python
class SignalType(Enum):
    EXCITATION = auto()   # 🟢 激励 - 强化路径
    INHIBITION = auto()   # 🔴 抑制 - 削弱路径
    NEUTRAL = auto()      # ⚪ 中性 - 观察记录
```

---

## 工作流程

### 标准处理流程

```
┌─────────┐     ┌──────────────┐     ┌─────────────┐
│  用户查询 │────→│ 选择最优路径  │────→│  执行处理   │
└─────────┘     └──────────────┘     └──────┬──────┘
                                            ↓
┌─────────┐     ┌──────────────┐     ┌─────────────┐
│ 应用信号  │←────│  自我评价    │←────│  感知交互   │
│(激励/抑制)│     └──────────────┘     └─────────────┘
└────┬────┘
     ↓
┌─────────────┐
│  更新路径权重  │
│ (递归改进)    │
└─────────────┘
```

### 详细步骤

1. **路径选择**
   ```python
   pathway = engine.select_optimal_pathway(query, complexity)
   # 基于历史表现选择权重最高的路径
   ```

2. **执行处理**
   ```python
   result = orchestrator.process(query, pathway)
   # 使用选定的路径执行 Luna SGP 处理
   ```

3. **交互感知**
   ```python
   trace = engine.perceive_interaction(
       query=query,
       l1_result=result.l1,
       l2_result=result.l2,
       l3_result=result.l3,
       latency_ms=latency
   )
   # 记录完整的认知痕迹
   ```

4. **自我评价**
   ```python
   evaluation = engine.self_evaluate(trace.trace_id)
   # 多维度评估: 效率、质量、适应性
   ```

5. **信号应用**
   ```python
   if evaluation.score > 0.7:
       engine.apply_signal(trace_id, EXCITATION, 0.2)
   elif evaluation.score < 0.4:
       engine.apply_signal(trace_id, INHIBITION, 0.15)
   # 根据评价应用激励或抑制
   ```

6. **递归改进**
   ```python
   pathway.current_weight = pathway.compute_effective_weight()
   # 更新路径权重，影响下次选择
   ```

---

## 激励机制详解

### 激励 (Excitation)

**触发条件**:
- 自我评分 > 0.7
- 用户显式好评
- 低延迟 + 高置信度

**效果**:
- 路径权重增加
- 该路径被优先选择
- 正向反馈循环

### 抑制 (Inhibition)

**触发条件**:
- 自我评分 < 0.4
- 用户显式差评
- 处理异常/超时

**效果**:
- 路径权重降低
- 该路径被避免
- 促使探索替代方案

### 时间衰减

防止"赢者通吃":
```python
decay_factor = max(0.5, 1.0 - decay_rate * days_since_use)
```

长期不用的路径会逐渐恢复，给予重新探索的机会。

---

## 与现有 Luna SGP 的集成

### 集成点

```python
# 现有代码
class LunaOrchestrator:
    def process(self, query: str) -> Dict:
        # ... 现有逻辑
        return result

# 新增适配器
class LunaSGPInhibitionAdapter:
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.engine = InhibitionEngine()
    
    def process_with_feedback(self, query: str):
        # 1. 选择路径
        pathway = self.engine.select_optimal_pathway(query)
        
        # 2. 执行处理
        result = self.orchestrator.process(query)
        
        # 3. 感知 & 评价 & 学习
        trace = self.engine.perceive_interaction(...)
        evaluation = self.engine.self_evaluate(trace.trace_id)
        self.engine.apply_signal(...)
        
        return result
```

### 使用示例

```python
from luna_layer4_orchestrator import LunaOrchestrator
from luna_sgp_inhibition_module import LunaSGPInhibitionAdapter

# 初始化
orchestrator = LunaOrchestrator()
adapter = LunaSGPInhibitionAdapter(orchestrator)

# 处理查询 (带激励/抑制)
result = adapter.process_with_feedback("分析这个拓扑结构")

# 用户反馈
adapter.provide_user_feedback(result["trace_id"], feedback=0.8, comment="很有用")

# 查看学习进展
report = adapter.get_learning_report()
print(report["improvement_trend"])  # "improving" | "stable" | "declining"
```

---

## 数据持久化

### 数据库 Schema

```sql
-- 认知痕迹表
CREATE TABLE cognitive_traces (
    trace_id TEXT PRIMARY KEY,
    timestamp REAL,
    query TEXT,
    l1_contribution REAL,
    l2_contribution REAL,
    l3_contribution REAL,
    latency_ms REAL,
    token_count INTEGER,
    confidence REAL,
    user_feedback REAL,
    implicit_feedback REAL,
    self_score REAL,
    coherence REAL,
    novelty REAL,
    tags TEXT,
    context_hash TEXT
);

-- 路径权重表
CREATE TABLE pathway_weights (
    pathway_id TEXT PRIMARY KEY,
    route TEXT,  -- JSON ["L1", "L2", "L3"]
    base_weight REAL,
    current_weight REAL,
    success_count INTEGER,
    failure_count INTEGER,
    total_invocations INTEGER,
    last_used REAL,
    decay_rate REAL,
    excitation_accumulator REAL,
    inhibition_accumulator REAL
);

-- 反馈事件表
CREATE TABLE feedback_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT,
    signal_type TEXT,  -- "EXCITATION" | "INHIBITION" | "NEUTRAL"
    magnitude REAL,
    timestamp REAL,
    reason TEXT
);
```

---

## 未来扩展

### 短期 (v0.2)
- [ ] 隐式反馈检测 (如用户是否追问)
- [ ] 路径探索奖励 (epsilon-greedy)
- [ ] 可视化仪表板

### 中期 (v0.5)
- [ ] 跨会话学习
- [ ] 多用户共享权重
- [ ] 对抗性抑制 (防止过拟合)

### 长期 (v1.0)
- [ ] 元学习 (学习如何学习)
- [ ] 情感感知集成
- [ ] 预测性路径选择

---

## 哲学思考

### 这与人类认知的类比

| 人类认知 | Luna SGP 激励/抑制 |
|---------|-------------------|
| 多巴胺奖励 | Excitation 信号 |
| 疼痛回避 | Inhibition 信号 |
| 突触可塑性 | PathwayWeight 更新 |
| 工作记忆 | recent_traces 缓存 |
| 长期记忆 | SQLite 持久化 |
| 元认知 | self_evaluate() |

### 关键洞察

> "智能不是静态的能力，而是动态的自我调节过程。"

激励/抑制模块让 Luna SGP 从**工具**进化为**学习者**:
- 不再只是执行预设逻辑
- 能够从每次交互中学习
- 形成独特的"认知风格"

---

## 文件清单

- `luna_sgp_inhibition_module.py` - 核心实现
- `luna_sgp_inhibition_architecture.md` - 本文档
- `~/.openclaw/luna_inhibition.db` - 数据存储

---

**下一步**: 将此模块集成到现有的 Luna Layer 4 编排器中，开始实际测试。
