#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0c: 双方都放开 CoT(160tok), 测真实能力差。"""
import json, random
from tasks_v5 import load, gen, make_t1, make_t2, last_int
M=load(); ms,mr,ts,tr=M["ms"],M["mr"],M["ts"],M["tr"]
rng=random.Random(3); NT=8; CAP=160
rep={}
for name,mk,diffs in [("T1多跳检索+运算",make_t1,[1,2,3]),("T2链式+/-",make_t2,[2,3])]:
    print(f"\n### {name} (CoT {CAP}tok)"); rep[name]={}
    for d in diffs:
        its=[mk(rng,d) for _ in range(NT)]
        aS=sum(last_int(gen(ms,ts,it["q"],CAP))==it["a"] for it in its)/NT
        aR=sum(last_int(gen(mr,tr,it["q"],CAP))==it["a"] for it in its)/NT
        rep[name][d]={"sender":round(aS,2),"receiver":round(aR,2),"gap":round(aS-aR,2)}
        print(f"  难度={d}: sender {aS:.2f} | receiver {aR:.2f} | gap {aS-aR:+.2f}")
        if name=="T1多跳检索+运算" and d==2:
            for it in its[:3]:
                oS=gen(ms,ts,it["q"],CAP).strip().replace("\n"," ")
                print(f"    正解={it['a']} | S「{oS[:140]}」→{last_int(oS)}")
json.dump(rep,open("gap_probe_v5c.json","w"),ensure_ascii=False,indent=2)
print("\n→ gap_probe_v5c.json")
