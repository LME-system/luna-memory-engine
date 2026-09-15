#!/usr/bin/env python3
"""Luna SGP 输出 → gemma4:31b 研究合伙人 (本地/Ollama, chat+think=false)
用法: python3 gemma_research_snn.py <luna_sgp.md> <out.md>
"""
import json, sys, time, urllib.request
from datetime import datetime

INP = sys.argv[1] if len(sys.argv) > 1 else "luna_sgp_snn_arch_2026-09-15.md"
OUT = sys.argv[2] if len(sys.argv) > 2 else "gemma_research_snn_2026-09-15.md"
MODEL = "gemma4:31b"

SYSTEM = """你是 Luna SGP 的分析引擎，同时是本课题的研究合伙人。专长：神经形态计算硬件、数字电路/NoC 架构、SNN 学习规则、信息论、可解释性。
规则：
- 第一人称，敢定论，标注置信度；不复述材料，只做串联、升维、下判断。
- 不仅分析，还要**动手参与设计**：给出电路级/协议级的可行方案、模块接口、伪码或关键设计参数，指出风险与可证伪点。
- 明确区分"能立刻造/写进代码的" 与 "待证假设"。
- 中文输出，密度高。"""

def gen(prompt, num_predict=4500, temperature=0.6, retries=2, num_ctx=32768):
    payload={"model":MODEL,"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],
             "stream":False,"think":False,
             "options":{"num_predict":num_predict,"temperature":temperature,"num_ctx":num_ctx}}
    for i in range(retries+1):
        try:
            req=urllib.request.Request("http://localhost:11434/api/chat",
                data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req, timeout=3600) as r:
                d=json.loads(r.read().decode())
            return d.get("message",{}).get("content",""), d.get("eval_count",0), d.get("done_reason")
        except Exception as e:
            print(f"  重试{i+1}: {e}", flush=True); time.sleep(3)
    return "",0,"error"

def main():
    src=open(INP,encoding="utf-8").read()
    prompt=f"""================ 阿月的 Luna SGP 分析全文 ================
{src}
========================================================

请作为研究合伙人输出两部分：

【第一部分】对你（gemma）这份 Luna SGP 的批判性升维：逐层 L1→L2→L3→L4，指出哪条判断被高估/低估，补上更锋利的量或反例。结尾：统一主矛盾、非线性触发点、被滥用的说法、追踪变量表、整体置信度。

【第二部分】研究合伙人交付（要具体、可执行）：
1. 把"多时间尺度阈值子阵列 + 稀疏数据面 + 弥漫控制面 + 软编码总线"落成**电路/协议级设计**：阈值类如何设定时间常数 τ、tag/码如何编、广播如何调制、匹配如何保持稀疏；给出关键参数与量级。
2. **最小可证伪实验**：设计一个能区分"真神经形态(记忆=动力学)"与"普通数字加速器(记忆=存储)"的实验，给出判据、阈值、预期曲线形状。
3. 标注每条是【能立刻造/写进代码】还是【待证假设】。

禁止复述材料原文，只做升维、定论与工程设计。"""
    print(f"[{datetime.now():%H:%M:%S}] gemma4:31b 研究推理开始...", flush=True)
    t0=time.time(); text,tokens,reason=gen(prompt); dt=time.time()-t0
    print(f"[{datetime.now():%H:%M:%S}] 完成 {dt:.1f}s tokens={tokens} reason={reason}", flush=True)
    hdr=(f"# 🌙 Luna SGP × 研究合伙人（Gemma 本地） — 事件相机×SNN架构\n\n"
         f"> 引擎: {MODEL} (本地/Ollama, chat+think=false) | {datetime.now():%Y-%m-%d %H:%M} CST\n"
         f"> 耗时 {dt:.0f}s | tokens {tokens} | 输入: {INP}\n\n---\n\n")
    open(OUT,"w",encoding="utf-8").write(hdr+text)
    print("✅ →",OUT); print("\n--- 预览 ---\n"+text[:1500])

if __name__=="__main__": main()
