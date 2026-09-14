#!/usr/bin/env python3
"""变速器 v4 技术研讨 — 本地 Gemma4:31b (chat/think=false)"""
import json, sys, time, urllib.request
from datetime import datetime
INP, OUT = sys.argv[1], sys.argv[2]
MODEL="gemma4:31b"
SYSTEM="""你是本课题(变速器/桥)的研究合伙人。专长：表征几何、统计物理(RG/共形)、信息论、可解释性、PyTorch工程、认知架构。
规则：第一人称，敢定论，标注置信度；禁止复述，只做串联、升维、给可执行方案；区分"能立刻写进代码的"与"待证假设"；中文，密度高。"""
def gen(prompt,np_=4500,temp=0.55,retries=2,ctx=32768):
    payload={"model":MODEL,"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],
             "stream":False,"think":False,"options":{"num_predict":np_,"temperature":temp,"num_ctx":ctx}}
    for i in range(retries+1):
        try:
            req=urllib.request.Request("http://localhost:11434/api/chat",data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req,timeout=3600) as r: d=json.loads(r.read().decode())
            return d.get("message",{}).get("content",""),d.get("eval_count",0),d.get("done_reason")
        except Exception as e:
            print(f"  重试{i+1}: {e}",flush=True); time.sleep(3)
    return "",0,"error"
def main():
    src=open(INP,encoding="utf-8").read()
    prompt=f"================ 研讨材料 ================\n{src}\n========================================\n\n请按 Q1→Q5 逐条输出。重点在 Q1(多重表达如何工程实现) 与 Q2(≤3个指标的选择与论证)。"
    print(f"[{datetime.now():%H:%M:%S}] gemma4:31b v4研讨开始...",flush=True)
    t0=time.time(); text,tok,rs=gen(prompt); dt=time.time()-t0
    print(f"[{datetime.now():%H:%M:%S}] 完成 {dt:.0f}s tokens={tok} {rs}",flush=True)
    hdr=f"# 🌙 变速器 v4 技术研讨（Gemma 本地） — 2026-09-14\n\n> {MODEL} | {dt:.0f}s | tokens {tok}\n\n---\n\n"
    open(OUT,"w",encoding="utf-8").write(hdr+text); print("✅ →",OUT); print(text[:1200])
if __name__=="__main__": main()
