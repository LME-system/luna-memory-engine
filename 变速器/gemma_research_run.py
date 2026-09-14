#!/usr/bin/env python3
"""Luna SGP + 研究合伙人 (本地 gemma4:31b, chat/think=false)"""
import json, sys, time, urllib.request
from datetime import datetime

INP = sys.argv[1]
OUT = sys.argv[2]
MODEL = "gemma4:31b"

SYSTEM = """你是 Luna SGP 分析引擎，同时是本课题的研究合伙人。你的专长是：语义几何、统计物理(RG/共形/SLE)、信息论、可解释性、PyTorch 工程。

规则：
- 第一人称，敢定论，标注置信度；禁止复述材料，只做串联、升维、下判断。
- 你不仅分析，还要**动手参与代码工程**：给出可执行的数学形式、模块接口、伪码或关键代码片段，并指出风险与可证伪点。
- 区分"能立刻写进代码的"与"待证假设"。
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
    prompt=f"""================ 交流全文 ================
{src}
==========================================

请输出两部分：
【第一部分】Luna SGP 四层升维研判（L1符号→L2几何→L3拓扑→L4编排，结尾：统一主矛盾、非线性触发点、定价/认知错误、追踪变量、置信度）。
【第二部分】研究合伙人交付：对 mostik_bridge_repro.py 的批判 + 你负责模块的**具体代码/伪码**（桥的数学形式、注入位置、层/单位选择实验、如何测共形、评估口径），并标注 能立刻写/待证假设。"""
    print(f"[{datetime.now():%H:%M:%S}] gemma4:31b 研究推理开始...", flush=True)
    t0=time.time(); text,tokens,reason=gen(prompt); dt=time.time()-t0
    print(f"[{datetime.now():%H:%M:%S}] 完成 {dt:.1f}s tokens={tokens} reason={reason}", flush=True)
    hdr=(f"# 🌙 Luna SGP × 研究合伙人（Gemma 本地） — 2026-09-14\n\n"
         f"> 引擎: {MODEL} (本地/Ollama, chat+think=false) | {datetime.now():%Y-%m-%d %H:%M} CST\n"
         f"> 耗时 {dt:.0f}s | tokens {tokens}\n\n---\n\n")
    open(OUT,"w",encoding="utf-8").write(hdr+text)
    print("✅ →",OUT); print(text[:1500])

if __name__=="__main__": main()
