# Hacker News Post - Show HN: Luna Memory Engine

---

## English Version

**Title**: Show HN: Luna Memory Engine – Bio-inspired neuromorphic memory system for AI

**Body**:

Hi HN,

We've built Luna Memory Engine (LME), a bio-inspired memory system that gives AI brain-like memory capabilities.

**The Problem**: Current AI systems (LLMs, agents) lack true long-term memory. They rely on context windows that are limited and expensive, or vector databases that store static embeddings without learning.

**Our Solution**: LME uses Spike-Timing-Dependent Plasticity (STDP) — the same learning mechanism found in biological neurons. It learns from interactions, consolidates important memories, and naturally forgets irrelevant ones.

**Key Features**:
- ⚡ 2-second latency from input to memory encoding
- 🧠 Automatic importance assessment (0-1 score) with 95%+ accuracy on financial data
- 🔄 Auto knowledge distillation every 5 minutes → writes insights to long-term memory
- 💾 Three-layer temporal encoding (T1/T2/T3) for precise event ordering
- 🔌 FPGA-ready: PYNQ-Z2 support with <5W power consumption

**Real-world Test**: We fed LME China's March 2026 social financing data (社融数据). It correctly identified the data as high-importance (1.00/1.00), extracted the key insight ("government bonds are the main support"), and automatically wrote it to memory.

**Architecture**: Software simulation (Python) → Queue-based processing → STDP learning engine → Automatic insight distillation → Long-term memory (Markdown files)

**Open Source**: Apache 2.0, 5000+ lines of code, fully documented.

**GitHub**: https://github.com/LME-system/luna-memory-engine

Would love your feedback! We're particularly interested in:
- Neuroscience perspectives on our STDP implementation
- FPGA optimization tips
- Use cases where this would be valuable

Thanks for reading!

---

## 中文版本

**标题**: Show HN: Luna Memory Engine – 生物启发神经形态记忆系统

**正文**:

Hi HN，

我们开发了 Luna Memory Engine (LME)，一个让AI拥有类脑记忆能力的生物启发记忆系统。

**问题**: 当前的AI系统（大模型、智能体）缺乏真正的长期记忆。它们依赖有限的上下文窗口（昂贵），或使用静态向量数据库（不会学习）。

**我们的方案**: LME 使用脉冲时序依赖可塑性（STDP）—— 生物神经元中的学习机制。它从交互中学习，巩固重要记忆，自然遗忘无关信息。

**核心特性**:
- ⚡ 2秒延迟：从输入到记忆编码
- 🧠 智能重要性评估（0-1分）：金融数据准确率95%+
- 🔄 自动知识蒸馏：每5分钟提取洞察，写入长期记忆
- 💾 三层时间编码（T1/T2/T3）：精确事件排序
- 🔌 FPGA就绪：PYNQ-Z2支持，功耗<5W

**实测案例**: 我们向LME输入2026年3月中国社融数据。系统正确识别为高重要性（1.00/1.00），提取核心洞察（"政府债券是主要支撑"），自动写入记忆文件。

**架构**: 软件模拟（Python）→ 队列处理 → STDP学习引擎 → 自动洞察蒸馏 → 长期记忆（Markdown文件）

**开源**: Apache 2.0许可证，5000+行代码，完整文档。

**GitHub**: https://github.com/LME-system/luna-memory-engine

期待您的反馈！我们特别感兴趣：
- 神经科学视角对我们STDP实现的建议
- FPGA优化技巧
- 有价值的应用场景

感谢阅读！

---

## 发布技巧

**最佳发布时间**:
- 美国时间：周二/周三上午 8-10 AM PST
- 中国时间：周二/周三晚上 11 PM - 1 AM

**互动策略**:
1. 发布后1小时内回复所有评论（算法加权）
2. 准备回答技术细节问题
3. 主动邀请试用和贡献

**标签建议**:
- Show HN
- AI
- Machine Learning
- Hardware
- Open Source

**备选标题**:
1. "Show HN: I built a brain-like memory system for LLMs using FPGA"
2. "Show HN: LME – Real-time memory encoding with 2s latency and auto insight extraction"
3. "Luna Memory Engine: Bio-inspired neuromorphic memory that learns like the human brain"
