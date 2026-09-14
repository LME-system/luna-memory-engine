#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0d: 放开 CoT 指令, 测真实能力差。"""
import json, random, torch
from tasks_v5 import load, gen, make_t1, last_int
M=load(); ms,mr,ts,tr=M["ms"],M["mr"],M["ts"],M["tr"]
def cot(q): return q.replace("计算并直接输出最终数字（不要解释）","请逐步推理计算，最后一行只写：答案=<数字>")
rng=random.Random(5); NT=8; CAP=200
rep={}
for d in [1,2,3]:
    its=[make_t1(rng,d) for _ in range(NT)]
    aS=sum(last_int(gen(ms,ts,cot(it["q"]),CAP))==it["a"] for it in its)/NT
    aR=sum(last_int(gen(mr,tr,cot(it["q"]),CAP))==it["a"] for it in its)/NT
    rep[d]={"sender":round(aS,2),"receiver":round(aR,2),"gap":round(aS-aR,2)}
    print(f"T1 难度={d}: sender {aS:.2f} | receiver {aR:.2f} | gap {aS-aR:+.2f}")
    if d==2:
        for it in its[:4]:
            oS=gen(ms,ts,cot(it["q"]),CAP).strip().replace("\n"," ")
            oR=gen(mr,tr,cot(it["q"]),CAP).strip().replace("\n"," ")
            print(f"    正解={it['a']}\n      S「{oS[-90:]}」→{last_int(oS)}\n      R「{oR[-70:]}」→{last_int(oR)}")
json.dump(rep,open("gap_probe_v5d.json","w"),ensure_ascii=False,indent=2)
print("→ gap_probe_v5d.json")
