#!/usr/bin/env python3
"""
Gemma 审阅脚本 - Luna SGP 激励/抑制模块
=========================================

由于 Gemma 4 存在 thinking 模式问题，此脚本使用 num_predict >= 50 来确保响应。

使用方法:
    python3 gemma_review_inhibition.py

输出:
    gemma_inhibition_review_report.txt
"""

import requests
import json
import time
from pathlib import Path


def read_file(filepath: str) -> str:
    """读取文件内容"""
    with open(filepath, 'r') as f:
        return f.read()


def call_gemma(prompt: str, num_predict: int = 1000) -> str:
    """调用 Gemma 4"""
    url = "http://localhost:11434/api/generate"
    
    data = {
        "model": "gemma4:31b",
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": num_predict,
            "temperature": 0.3
        }
    }
    
    try:
        response = requests.post(url, json=data, timeout=300)
        result = response.json()
        return result.get("response", "")
    except Exception as e:
        return f"Error: {str(e)}"


def main():
    print("=" * 60)
    print("Gemma 审阅: Luna SGP 激励/抑制模块")
    print("=" * 60)
    
    # 读取源代码
    code_file = Path.home() / ".openclaw/workspace/luna_sgp_inhibition_module.py"
    arch_file = Path.home() / ".openclaw/workspace/luna_sgp_inhibition_architecture.md"
    
    print(f"\n1. 读取源代码...")
    code = read_file(str(code_file))
    arch = read_file(str(arch_file))
    
    print(f"   代码长度: {len(code)} 字符")
    print(f"   文档长度: {len(arch)} 字符")
    
    # 构建审阅提示
    print(f"\n2. 构建审阅提示...")
    
    review_prompt = f"""You are Gemma, an AI Systems Architect. Please review the following Luna SGP Inhibition/Excitation Module.

## Design Summary

The module adds meta-cognition to a 4-layer cognitive architecture:
- L1: Symbolic layer
- L2: Geometric layer  
- L3: Topological layer
- L4: Orchestration layer

New Meta-Cognition Layer provides:
1. Interaction Perception - records cognitive traces
2. Self-Evaluation - multi-dimensional scoring
3. Recursive Improvement - excitation/inhibition signals

## Core Components

- CognitiveTrace: records single interaction
- PathwayWeight: dynamic pathway weight management
- InhibitionEngine: core engine
- LunaSGPInhibitionAdapter: integration with L4

## Signal Types

- EXCITATION: positive feedback, strengthen pathway
- INHIBITION: negative feedback, weaken pathway
- NEUTRAL: observation only

## Learning Mechanism

Hebbian-like weight update:
- score > 0.7 → EXCITATION → weight increases
- score < 0.4 → INHIBITION → weight decreases
- time decay prevents "winner-takes-all"

## Architecture Position

Meta-Cognition Layer (NEW)
    ↕
Layer 4 Orchestrator (existing)
    ↕
L1/L2/L3

## Questions

1. Is Hebbian-like learning sufficient or need RL (PPO/DQN)?
2. Are 3 signal types enough or need finer granularity?
3. Is simple exponential time decay appropriate?
4. Risks of positive feedback loops causing pathway monopoly?
5. Is "L1->L2->L3" string ID scalable for dynamic paths?
6. Is Adapter pattern elegant or need tighter integration?
7. What critical features are missing for v0.1?

## Code Structure

The implementation includes:
- InhibitionEngine class (core logic)
- CognitiveTrace dataclass (interaction records)
- PathwayWeight dataclass (pathway management)
- LunaSGPInhibitionAdapter class (L4 integration)
- SQLite persistence layer

Please provide:
1. Overall assessment (PASS / NEEDS_REVISION / MAJOR_REVISION)
2. Critical issues (if any)
3. Answers to the 7 questions above
4. Specific code improvement suggestions
5. Priority-ranked action items

Be thorough but constructive.
"""
    
    print(f"   提示长度: {len(review_prompt)} 字符")
    
    # 调用 Gemma
    print(f"\n3. 调用 Gemma 4 (预计需要 2-3 分钟)...")
    start_time = time.time()
    
    response = call_gemma(review_prompt, num_predict=1500)
    
    elapsed = time.time() - start_time
    print(f"   耗时: {elapsed:.1f} 秒")
    print(f"   响应长度: {len(response)} 字符")
    
    # 保存报告
    print(f"\n4. 保存审阅报告...")
    report_file = Path.home() / ".openclaw/workspace/gemma_inhibition_review_report.txt"
    
    report_content = f"""# Gemma 审阅报告: Luna SGP 激励/抑制模块

**审阅时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}
**Gemma 模型**: gemma4:31b
**响应长度**: {len(response)} 字符
**审阅耗时**: {elapsed:.1f} 秒

---

## Gemma 的审阅意见

{response if response else "(Gemma 返回了空响应 - 可能需要增加 num_predict)"}

---

## 原始提示

```
{review_prompt}
```

---

*报告生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}*
"""
    
    with open(report_file, 'w') as f:
        f.write(report_content)
    
    print(f"   报告已保存: {report_file}")
    
    # 显示摘要
    print(f"\n5. 审阅摘要:")
    print(f"   {'='*50}")
    if response:
        # 显示前 500 字符
        preview = response[:500].replace('\n', ' ')
        print(f"   {preview}...")
    else:
        print("   (空响应 - Gemma 4 可能需要更多 token 预算)")
    print(f"   {'='*50}")
    
    print(f"\n" + "=" * 60)
    print("审阅完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
