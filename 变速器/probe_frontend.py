#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探针: 前端(sender 1.5B)在文字接力时到底吐了什么 —— 完整答案 or 半成品?
复用 v4.py 的任务生成器 make()。"""
import os, sys, torch
os.environ.setdefault("HF_HUB_OFFLINE","1"); os.environ.setdefault("TRANSFORMERS_OFFLINE","1")
sys.path.insert(0,".")
from v4 import make, last_int
import random
from transformers import AutoTokenizer, AutoModelForCausalLM

dev="mps" if torch.backends.mps.is_available() else "cpu"
S="Qwen/Qwen2.5-1.5B-Instruct"; R="Qwen/Qwen2.5-0.5B-Instruct"
ts=AutoTokenizer.from_pretrained(S); tr=AutoTokenizer.from_pretrained(R)
ms=AutoModelForCausalLM.from_pretrained(S,dtype=torch.float32).to(dev).eval()
mr=AutoModelForCausalLM.from_pretrained(R,dtype=torch.float32).to(dev).eval()

def qt(tok,txt): return tok.apply_chat_template([{"role":"user","content":txt}],tokenize=False,add_generation_prompt=True)

@torch.no_grad()
def gen(model,tok,txt,n=48):
    ids=tok(qt(tok,txt),return_tensors="pt").to(dev)
    g=model.generate(**ids,max_new_tokens=n,do_sample=False,
                     pad_token_id=tok.eos_token_id)
    return tok.decode(g[0,ids.input_ids.shape[1]:],skip_special_tokens=True)

rng=random.Random(7)
samples=[make(rng,4) for _ in range(5)]
print("="*70)
for i,it in enumerate(samples):
    print(f"\n【样本{i}】题: {it['q'].splitlines()[0]}")
    print(f"  正文: {it['q'].splitlines()[-1][:90]}...")
    print(f"  ✅正解 = {it['a']}")
    # A) 直接问(只答数字) —— 对标 text_relay 的用法
    oA=gen(ms,ts,it["q"],16).strip().replace("\n"," ")
    print(f"  [A 前端·只答数字 16tok] 「{oA}」  取末整数={last_int(oA)}")
    # B) 放开长度, 看它是不是在"边想边算"
    oB=gen(ms,ts,it["q"],48).strip().replace("\n"," ")
    print(f"  [B 前端·放宽48tok ] 「{oB[:160]}」")
    # C) 要求写推理过程 —— 看"算一半"的证据
    oC=gen(ms,ts,it["q"]+"\n请先写出你的推理过程。",48).strip().replace("\n"," ")
    print(f"  [C 前端·要求推理 ] 「{oC[:160]}」")
    # D) 小模型单独
    oD=gen(mr,tr,it["q"],16).strip().replace("\n"," ")
    print(f"  [D 小模型单独    ] 「{oD}」  取末整数={last_int(oD)}")
print("\n"+"="*70)
