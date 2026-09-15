#!/usr/bin/env python3
"""Luna SGP 四层分析 — 技术命题版 (本地 gemma4:31b, chat + think:false)
用法: python3 luna_sgp_gemma_tech.py <input.md> <output.md>
"""
import json, sys, time, urllib.request
from datetime import datetime

IN  = sys.argv[1] if len(sys.argv) > 1 else "luna_sgp_tech_input_event_camera_2026-09-15.md"
OUT = sys.argv[2] if len(sys.argv) > 2 else "luna_sgp_gemma_event_camera_2026-09-15.md"
MODEL = "gemma4:31b"

SYSTEM = """你是 Luna SGP (Semantic Graph Processing) 分析引擎，运行在本地。对象是【技术命题】而非新闻。
请对该命题做四层语义推理：

- L1 符号层 (Symbolic): 拆解命题中的核心概念/术语/前置事实，指出哪些是已被工程验证的、哪些是宣称/假设。
- L2 几何层 (Geometric): 把命题里的关键变量看成向量——算力/带宽/功耗/精度/时延/可扩展性，走向与约束在哪、有无拐点。
- L3 拓扑层 (Topological): 找结构关系——组件如何耦合、信息/能量如何流动、闭环反馈在哪、瓶颈在哪个节点。
- L4 编排层 (Orchestration): 综合裁决——命题成立需要哪些必要条件、哪里会断、"大模型形态"这类说法是否被滥用、给出可证伪的判据与追踪变量。

风格：锐利、密度高、敢下判断、区分"能做到/理论上可/营销话术"，标注置信度。避免空话。"""


def gen(prompt, num_predict=3000, temperature=0.7, retries=2, num_ctx=32768):
    payload = {"model": MODEL,
               "messages": [{"role": "system", "content": SYSTEM},
                            {"role": "user", "content": prompt}],
               "stream": False, "think": False,
               "options": {"num_predict": num_predict, "temperature": temperature, "num_ctx": num_ctx}}
    for i in range(retries + 1):
        try:
            req = urllib.request.Request("http://localhost:11434/api/chat",
                data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=1800) as r:
                d = json.loads(r.read().decode())
            m = d.get("message", {})
            return m.get("content", ""), d.get("eval_count", 0), d.get("done_reason")
        except Exception as e:
            print(f"  重试 {i+1}: {e}", flush=True); time.sleep(3)
    return "", 0, "error"


def main():
    with open(IN, encoding="utf-8") as f:
        topic = f.read()
    prompt = f"""================ 待分析命题 ================
{topic}
==========================================

请按 L1→L2→L3→L4 四层框架输出完整分析。结尾给出：命题裁定（成立/有条件成立/不成立）、必要条件清单、非线性触发点、被滥用的说法、可证伪判据、追踪变量、整体置信度。"""
    print(f"[{datetime.now():%H:%M:%S}] gemma4:31b 技术命题推理...", flush=True)
    t0 = time.time()
    text, tokens, reason = gen(prompt)
    dt = time.time() - t0
    print(f"[{datetime.now():%H:%M:%S}] 完成 {dt:.1f}s | tokens={tokens} | reason={reason}", flush=True)
    header = (f"# 🌙 Luna SGP 技术命题分析 — 事件相机 × 数字神经突触阵列 × SNN\n\n"
              f"> 引擎: {MODEL} (本地/Ollama, chat+think=false) | 生成: {datetime.now():%Y-%m-%d %H:%M} CST\n"
              f"> 耗时: {dt:.0f}s | 输出 token: {tokens} | 输入: {IN}\n\n---\n\n")
    open(OUT, "w", encoding="utf-8").write(header + text)
    print(f"✅ → {OUT}\n\n--- 预览 ---\n{text[:1500]}")


if __name__ == "__main__":
    main()
