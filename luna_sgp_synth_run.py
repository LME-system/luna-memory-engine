#!/usr/bin/env python3
"""Luna SGP 合成分析 - 把多份分析串成统一结构 (本地 gemma4:31b)"""
import json
import sys
import time
import urllib.request
from datetime import datetime

INPUT = sys.argv[1] if len(sys.argv) > 1 else "luna_sgp_input_synthesis_2026-09-12.md"
OUT = sys.argv[2] if len(sys.argv) > 2 else "luna_sgp_gemma_synthesis_2026-09-12.md"
MODEL = "gemma4:31b"

SYSTEM = """你是 Luna SGP 合成引擎。给你三份已完成的独立分析（宏观市场 / 中国算力与地缘 / AI 科研伦理）。
你的任务不是复述，而是【串联】——找出它们背后的同一套底层结构。

要求输出：
- L1 符号层：提取三份材料各自的「关键实体/事件」，并标注哪些是跨材料共同出现的
- L2 几何层：三条趋势向量的方向/斜率对比，找出共同加速的变量
- L3 拓扑层：画出跨材料的耦合网络与反馈回路（谁驱动谁、哪条回路闭合）
- L4 编排层：把三件事收敛到 1-2 个「统一主矛盾」和 1 个「统一底层变量」
- 最后给出：统一触发点、统一定价错误、跨域追踪变量表、整体置信度

风格：锐利、密度高、敢定论、承认不确定性。禁止复述材料原文，只做串联与升维。"""


def gen(prompt, num_predict=4000, temperature=0.7, num_ctx=32768, retries=2):
    # gemma4 是 thinking 模型 → 必须用 chat + think:false, 否则 content 为空
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "think": False,
        "options": {"num_predict": num_predict, "temperature": temperature, "num_ctx": num_ctx},
    }
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(
                "http://localhost:11434/api/chat",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=1800) as r:
                d = json.loads(r.read().decode())
            return d.get("message", {}).get("content", ""), d.get("eval_count", 0), d.get("done_reason")
        except Exception as e:
            print(f"  重试 {i+1}: {e}", flush=True)
            time.sleep(3)
    return "", 0, "error"


def main():
    with open(INPUT, encoding="utf-8") as f:
        material = f.read()

    prompt = f"""三份分析材料如下：

================ 三份分析材料 ================
{material}
=============================================

请把这三份分析【串成一个统一结构】，按 L1→L2→L3→L4→统一结论 输出。"""

    print(f"[{datetime.now():%H:%M:%S}] 开始 gemma4:31b 合成推理 (chat/think=false)...", flush=True)
    t0 = time.time()
    text, tokens, reason = gen(prompt)
    dt = time.time() - t0
    print(f"[{datetime.now():%H:%M:%S}] 完成 {dt:.1f}s | tokens={tokens} | reason={reason}", flush=True)

    header = (
        f"# Luna SGP 合成报告 — 2026-09-13 全景串联\n\n"
        f"> 引擎: {MODEL} (本地/Ollama, chat+think=false) | 生成: {datetime.now():%Y-%m-%d %H:%M} CST\n"
        f"> 耗时: {dt:.0f}s | 输出 token: {tokens} | 串联: 早间全球快讯 + Anthropic 威胁情报 + Amodei《Pace the Frontier》\n\n---\n\n"
    )
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(header + text)
    print(f"✅ 已保存 → {OUT}")
    print("\n--- 预览 ---")
    print(text[:1200])


if __name__ == "__main__":
    main()
