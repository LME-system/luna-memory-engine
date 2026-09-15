#!/usr/bin/env python3
"""Luna SGP 四层分析 - 本地 Gemma4:31b 引擎 (chat API + think:false)
修复: gemma4 是 thinking 模型, /api/generate 只返回 content 而思维全在 thinking 通道 → 空输出。
改用 /api/chat 且 think=false, 直接拿最终 content。
"""
import json
import sys
import time
import urllib.request
from datetime import datetime

CAPTURE = sys.argv[1] if len(sys.argv) > 1 else "news_capture_2026-09-13.md"
OUT = sys.argv[2] if len(sys.argv) > 2 else "luna_sgp_gemma_2026-09-13.md"
MODEL = "gemma4:31b"

SYSTEM = """你是 Luna SGP (Semantic Graph Processing) 分析引擎，运行在本地。
对全球资讯做四层语义推理：

- L1 符号层 (Symbolic): 提取核心事实、实体、数字、5W1H、信号强度(🔴重大/🟡关注/🟢常态)
- L2 几何层 (Geometric): 识别向量/方向/速度/加速度——趋势往哪走、斜率多大、是否拐点
- L3 拓扑层 (Topological): 找关联结构——哪些事件连成网、跨市场/跨地缘耦合、反馈回路
- L4 编排层 (Orchestration): 综合判断——主矛盾、非线性触发点、定价是否错误、战略含义与追踪变量

风格：锐利、密度高、敢于下判断、标注置信度。避免空话。"""


def gen(prompt, num_predict=3000, temperature=0.7, retries=2, num_ctx=32768):
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
            msg = d.get("message", {})
            return msg.get("content", ""), d.get("eval_count", 0), d.get("done_reason")
        except Exception as e:
            print(f"  重试 {i+1}: {e}", flush=True)
            time.sleep(3)
    return "", 0, "error"


def main():
    with open(CAPTURE, encoding="utf-8") as f:
        news = f.read()

    prompt = f"""================ 资讯原文 ================
{news}
========================================

请按 L1→L2→L3→L4 四层框架输出完整分析报告。结尾给出：主矛盾、非线性触发点、定价错误、追踪变量、整体置信度。"""

    print(f"[{datetime.now():%H:%M:%S}] 开始 gemma4:31b 推理 (chat/think=false)...", flush=True)
    t0 = time.time()
    text, tokens, reason = gen(prompt)
    dt = time.time() - t0
    print(f"[{datetime.now():%H:%M:%S}] 完成 {dt:.1f}s | tokens={tokens} | reason={reason}", flush=True)

    header = (
        f"# 🌙 Luna SGP 分析报告 — {datetime.now():%Y-%m-%d}\n\n"
        f"> 引擎: {MODEL} (本地/Ollama, chat+think=false) | 生成: {datetime.now():%Y-%m-%d %H:%M} CST\n"
        f"> 耗时: {dt:.0f}s | 输出 token: {tokens} | 输入: {CAPTURE}\n\n---\n\n"
    )
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(header + text)
    print(f"✅ 已保存 → {OUT}")
    print("\n--- 输出预览 ---")
    print(text[:1200])


if __name__ == "__main__":
    main()
