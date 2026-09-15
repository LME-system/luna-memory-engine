# 🌙 Luna SGP × 研究合伙人（Gemma 本地） — 事件相机×SNN架构

> 引擎: gemma4:31b (本地/Ollama, chat+think=false) | 2026-09-15 22:06 CST
> 耗时 278s | tokens 1756 | 输入: luna_sgp_snn_arch_2026-09-15.md

---

我是 Luna SGP 的分析引擎。这份分析报告在架构构想上极具前瞻性，但在**工程闭环**和**动力学稳定性**上过于乐观。它把“结构同构”当成了“功能实现”，忽略了异步系统中最致命的**时钟漂移（Jitter）与因果律失效**。

---

### 【第一部分】批判性升维：L1 $\rightarrow$ L4

**L1 符号层：低估了“异步仲裁”的成本**
*   **批判**：将 AER 视为简单的“压力后移”太轻巧。在数字实现中，异步事件流的**仲裁（Arbitration）**是 O(N) 甚至 O(N log N) 的延迟。当场景动态度增加，仲裁延迟会变成一个动态的、不可预测的 $\tau_{delay}$，直接污染 SNN 的时间尺度 $\tau$。
*   **锋利量**：$\text{Effective } \tau = \tau_{nominal} + \text{Arbitration\_Latency}(\text{Event\_Rate})$。当事件率 $\lambda > \text{Threshold}$，系统动力学将从“神经形态”退化为“排队论”。

**L2 几何层：高估了“时间尺度分离”的鲁棒性**
*   **批判**：认为 $\tau$ 谱能直接构成记忆。事实上，若没有**负反馈（Inhibition）**，多 $\tau$ 阵列极易陷入“正反馈雪崩”或“全静默”。
*   **反例**：一个纯粹的 $\tau$ 谱阵列在面对高频噪声时，慢类子阵列会迅速积分饱和，导致记忆被噪声“冲刷”掉，而非巩固。

**L3 拓扑层：低估了“弥漫控制面”的量化噪声**
*   **批判**：将“弥漫信号”等同于“带标签广播”太理想化。在数字电路中，全局广播意味着巨大的扇出（Fan-out）和电容负载，会导致严重的功耗峰值和时钟偏移。
*   **升维**：弥漫面不应是“总线”，而应是**“低频分段式配置总线”**。

**L4 编排层：主矛盾偏移**
*   **批判**：主矛盾不在于“连接自由度 vs 总线带宽”，而在于**“局部动力学稳定性 vs 全局一致性”**。
*   **非线性触发点**：当 $\tau_{slow} / \tau_{fast} > 10^2$ 且 $\text{Sparsity} < 1\%$ 时，系统才真正具备“状态空间记忆”能力，否则只是个带延迟的滤波器。

| 维度 | 统一主矛盾 | 非线性触发点 | 被滥用的说法 | 追踪变量 | 置信度 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **定论** | 异步仲裁延迟 $\leftrightarrow$ 神经动力学精度 | $\tau$ 谱跨度 $\ge 2$ 个数量级 | "SNN 大模型" | $\text{Jitter} / \tau_{fast}$ | 65% |

---

### 【第二部分】研究合伙人交付：电路与协议设计

#### 1. 架构实现方案：$\text{SGP-Core}$

**A. 多 $\tau$ 子阵列实现 (Leakage-based $\tau$)**
*   **电路级**：不使用乘法器，使用**移位寄存器 + 计数器**实现 $\text{LIF}$ 的漏电。
*   **参数设定**：
    *   $\tau_{fast}$ (瞬时响应): $1\text{ms} \sim 10\text{ms}$ $\rightarrow$ 计数器每 $10\mu\text{s}$ 减 1。
    *   $\tau_{slow}$ (状态记忆): $100\text{ms} \sim 1\text{s}$ $\rightarrow$ 计数器每 $1\text{ms}$ 减 1。
*   **阈值类**：采用**等差阶梯阈值** $\theta_i = \theta_0 + i \cdot \Delta\theta$。
*   【能立刻造】

**B. 软编码总线与 Tag 协议 (AER-Ext)**
*   **协议格式**：`[Priority(2b) | Type_Tag(3b) | Address(13b) | Timestamp(10b)]`
    *   `Type_Tag`: 区分 `001: Fast_SNN`, `010: Slow_SNN`, `100: Diffuse_Ctrl`。
*   **匹配稀疏化**：在 NoC 路由节点引入 **Bloom Filter**。只有当 `Address` 命中本地子阵列的连接表时，才触发 SRAM 读写。
*   【能立刻造】

**C. 弥漫控制面 (Global Modulation Plane)**
*   **机制**：采用**异步广播总线 (Asynchronous Broadcast Bus)**，不触发神经元发放，而是直接修改子阵列的 $\theta_{offset}$ 或 $\tau_{scale}$。
*   **调制方式**：$\theta_{eff} = \theta_{base} + \text{Global\_Modulator\_Value}$。
*   【待证假设】：全局广播的电容负载是否会导致时延抖动超过 $\tau_{fast}$ 的 10%。

#### 2. 最小可证伪实验：$\text{Temporal Echo Test}$

**实验设计**：
输入一个具有特定时间间隔 $\Delta t$ 的脉冲序列 $S = \{t_1, t_2, \dots, t_n\}$，其中 $\Delta t$ 逐渐增加。

*   **普通数字加速器 (Memory=Storage)**：
    *   表现：只要 $\Delta t < \text{Buffer\_Size}$，输出结果恒定。
    *   曲线：阶梯状（全对 $\rightarrow$ 全错）。
*   **真神经形态 (Memory=Dynamics)**：
    *   表现：输出结果随 $\Delta t$ 连续衰减。当 $\Delta t \approx \tau_{slow}$ 时，出现一个临界点（相变），系统失去对序列的整合能力。
    *   曲线：指数衰减状 $\text{Accuracy} \propto e^{-\Delta t / \tau}$。

**判据与阈值**：
*   **判据**：计算 $\frac{\partial \text{Accuracy}}{\partial \Delta t}$。
*   **阈值**：若相关系数 $R^2(\text{Accuracy}, e^{-\Delta t / \tau}) > 0.9$，则证明记忆是由动力学（$\tau$）而非存储空间决定的。
*   【能立刻造】

#### 3. 交付清单总结

| 模块/方案 | 状态 | 关键风险 |
| :--- | :--- | :--- |
| **移位寄存器 $\tau$ 实现** | 【能立刻造】 | 精度受限于计数器位数 |
| **AER-Ext 协议 + Bloom Filter** | 【能立刻造】 | 碰撞率导致误触发 $\rightarrow$ 能效下降 |
| **$\theta_{offset}$ 全局调制电路** | 【待证假设】 | 物理布线导致的信号同步问题 |
| **$\tau$ 谱跨度 $\ge 100\times$** | 【待证假设】 | 慢类神经元是否会被快类神经元的噪声淹没 |
| **Temporal Echo 实验** | 【能立刻造】 | 需精确控制输入脉冲的 $\mu\text{s}$ 级时延 |