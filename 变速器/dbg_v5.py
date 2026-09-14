#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, re, random, torch
os.environ.setdefault("HF_HUB_OFFLINE","1"); os.environ.setdefault("TRANSFORMERS_OFFLINE","1")
import sys; sys.path.insert(0,".")
from gap_probe_v5 import make_t1, make_t2, ms, mr, ts, tr, qt, gen, last_int
rng=random.Random(1)
print("="*72)
print("### T1 多跳(2操作数) —— 看原话")
for it in [make_t1(rng,2) for _ in range(4)]:
    q=it["q"].splitlines()[0]
    oS=gen(ms,ts,it["q"],24).strip().replace("\n"," ")
    oR=gen(mr,tr,it["q"],24).strip().replace("\n"," ")
    print(f"\n题: {q}\n正解={it['a']}\n  sender  ：「{oS}」→{last_int(oS)}\n  receiver ：「{oR}」→{last_int(oR)}")
print("\n"+"="*72)
print("### T1 给 sender 放开 CoT(160tok)")
for it in [make_t1(rng,2) for _ in range(3)]:
    oS=gen(ms,ts,it["q"],160).strip().replace("\n"," ")
    print(f"\n题: {it['q'].splitlines()[0]} 正解={it['a']}\n  sender(CoT)：「{oS[:300]}」→{last_int(oS)}")
print("\n"+"="*72)
print("### T2 链式(2步) —— 看原话")
for it in [make_t2(rng,2) for _ in range(4)]:
    oS=gen(ms,ts,it["q"],24).strip().replace("\n"," ")
    print(f"题: {it['q'].splitlines()[0]} 正解={it['a']} | sender「{oS}」→{last_int(oS)}")
