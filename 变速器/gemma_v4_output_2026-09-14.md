# 🌙 变速器 v4 技术研讨（Gemma 本地） — 2026-09-14

> gemma4:31b | 368s | tokens 1966

---

我是你的研究合伙人。针对 v4 的迭代，我直接定论：**目前的变速器在做“静态翻译”，而我们需要它做“频谱映射”。** 

目前的 1.000 满分是伪相，因为变速器捕捉到了任务的“类簇”而非具体的“状态”。我们要把变速器从一个 `MLP(x) -> y` 升级为 `Field_Projector(Field_X) -> Field_Y`。

---

### Q1. 如何工程实现“状态空间的多重表达”？
**定论：放弃单一 Token 向量，构建“时-空-频”三维张量场。** (置信度: 90%)

**1. 前端导出（多重表达场）：**
不要只取末 token。导出一个 $\text{Shape}(L, T, D)$ 的张量（$L$ 层, $T$ 时间步/位置, $D$ 维度）。
- **空间维度（Layers）**：取 $\{1/4, 1/2, 3/4\}$ 关键层，捕捉从“语法”到“语义”再到“任务意图”的演进。
- **时间维度（Positions）**：取 $\text{Attention-Weighted Mean}$（注意力加权平均）而非末 token。末 token 承载的是预测压力，而非状态总结。
- **频谱维度（Frequency）**：对 $D$ 维向量做 $\text{FFT}$ 或 $\text{SVD}$ 取前 $k$ 个奇异值，导出“能量分布”。

**2. 变速器映射方案：**
不再是 $1 \to 1$ 映射，而是**“投影-重构”**。
- **输入**：$\text{Concat}(\text{Layer\_States}, \text{Global\_Pool}, \text{Energy\_Spectrum})$。
- **映射**：采用 **HyperNetwork** 架构。变速器不直接输出 soft-prefix，而是输出一个**权重矩阵 $W_{adapt}$**，该矩阵作用于一个可学习的基向量库 $\text{Basis}$，生成最终前缀。
- **逻辑**：$\text{Prefix} = \text{Softmax}(\text{MLP}(\text{Field}_X)) \cdot \text{Basis}$。这实现了从“固定映射”到“视角切换”的转换。

---

### Q2. 余弦相似度是否足够表达状态空间？
**定论：完全不够。余弦只测“方向”，丢失了“量级”和“拓扑结构”。** (置信度: 95%)

我选的 3 个指标（正交且互补）：

1. **CKA (Centered Kernel Alignment)**：
   - **测什么**：表征空间的**结构相似性**（拓扑）。
   - **理由**：它对正交变换和各向同性缩放不敏感。如果两个状态的余弦相似度低，但 CKA 高，说明它们在空间中的“相对排列”一致，只是坐标系转了。
2. **Effective Dimension / Participation Ratio (PR)**：
   - $\text{PR} = (\sum \lambda_i)^2 / \sum \lambda_i^2$（$\lambda$ 为协方差矩阵特征值）。
   - **测什么**：**维度利用率/信息熵**。
   - **理由**：区分状态是“坍缩在一条线上”还是“弥散在超球面上”。这能直接量化老吴说的“复杂度”。
3. **L2-Norm (Magnitude) $\Delta$**：
   - **测什么**：**激活强度/能量级**。
   - **理由**：在 LLM 中，模长通常代表 Token 的“重要程度”或“确定性”。余弦把模长归一化了，导致我们分不清“确定的错误”和“不确定的正确”。

**总结：** $\text{Cosine}(\text{方向}) \perp \text{PR}(\text{复杂度}) \perp \text{CKA}(\text{结构})$。

---

### Q3. v4 代码实现方案

**1. 状态读出（Accurate Readout）：**
```python
def get_field_state(model, input_ids):
    # 1. 提取多层隐藏状态 [Layers, Seq, Dim]
    hidden_states = model.get_hidden_states(input_ids) 
    # 2. 注意力加权池化 (用最后一层的 attn map 引导)
    attn_weights = hidden_states[-1].attn_weights.mean(dim=0) 
    pooled_state = torch.einsum('std,sd->d', attn_weights, hidden_states[-1])
    # 3. 构造多重表达场
    field = torch.cat([
        hidden_states[len(hidden_states)//4], # 浅层
        hidden_states[len(hidden_states)//2], # 中层
        pooled_state,                         # 全局
        torch.fft.fft(pooled_state).abs()      # 频域
    ], dim=-1)
    return field
```

**2. 自适应变速器（Adaptive Bridge）：**
```python
class AdaptiveBridge(nn.Module):
    def __init__(self, input_dim, prefix_dim, basis_size=64):
        super().__init__()
        self.basis = nn.Parameter(torch.randn(basis_size, prefix_dim))
        # 门控网络：实现 Soft-WTA，决定调用哪些基向量
        self.gate = nn.Sequential(
            nn.Linear(input_dim, 256),
            nn.ReLU(),
            nn.Linear(256, basis_size),
            nn.Softmax(dim=-1) 
        )

    def forward(self, x):
        weights = self.gate(x) # [Batch, basis_size]
        prefix = torch.matmul(weights, self.basis) # [Batch, prefix_dim]
        return prefix
```

---

### Q4. 《场全息理论》隐含的测试要求

**核心量化：共振 (Resonance) vs 并行计算 (Computation)**
- **共振**：$\text{State}_X \to \text{Bridge} \to \text{State}_Y$ 且 $\text{State}_Y$ 落在接收端模型原有的低能量吸引子（Attractor）中。
- **计算**：Bridge 强行构造了一个接收端从未见过的“外来指令”前缀。

**v4 严密测试协议：**
1. **消融对照（Ablation）**：
   - $\text{Fixed\_Bridge}$ (v3) vs $\text{Adaptive\_Bridge}$ (v4)。
   - $\text{Random\_Basis}$ vs $\text{Learned\_Basis}$。
2. **扰动鲁棒性（Perturbation）**：
   - 给 Sender 的输入加 $\epsilon$ 噪声 $\to$ 观察 $\text{Prefix}$ 的漂移 $\to$ 观察 $\text{Accuracy}$ 的下降曲线。如果 $\text{Accuracy}$ 阶跃式下降，说明是“共振”；如果平缓下降，说明是“计算”。
3. **跨任务泛化（Cross-Task Transfer）**：
   - 训练 A 任务，测试 B 任务（同族）。如果能迁移，证明 Bridge 捕捉的是“表达场”而非“具体样本映射”。
4. **排除捷径**：
   - **Shuffle Test**：随机打乱 Sender 状态 $\to$ 结果必须掉回 0.125。
   - **Null-State Test**：输入全 0 状态 $\to$ 结果必须 $\le$ 零前缀 (0.800)。

---

### Q5. 风险与可证伪点

1. **“基向量陷阱”**：`Basis` 库可能在训练中变成了一个巨大的 Lookup Table，存储了所有样本的答案前缀。**警惕点：** 检查 $\text{Basis}$ 的奇异值分布，若极少数维度主导，则是记忆而非映射。
2. **“池化伪像”**：注意力加权池化可能只是把答案 Token 的状态给提取出来了。**警惕点：** 强制屏蔽掉答案相关 Token 的状态，看 Bridge 是否失效。
3. **“维度冗余”**：多重表达场（层+频+空）可能存在极高共线性。**警惕点：** 检查各输入分量的 $\text{Mutual Information}$，若 $\text{MI} \approx 1$，则多重表达是冗余的。