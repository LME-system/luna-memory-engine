#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P1 诊断: receiver 在 alone / text_relay / bridge 下到底吐了什么"""
import os, random, torch
os.environ.setdefault("HF_HUB_OFFLINE","1"); os.environ.setdefault("TRANSFORMERS_OFFLINE","1")
import sys; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from tasks_v5 import load, make_t1, last_int, qt
dev="mps" if torch.backends.mps.is_available() else "cpu"
M=load(dev); ms,mr,ts,tr=M["ms"],M["mr"],M["ts"],M["tr"]
dr=mr.config.hidden_size; K=16
def cot(q): return q.replace("计算并直接输出最终数字（不要解释）","请逐步推理计算，最后一行只写：答案=<数字>")
rng=random.Random(11)
train=[make_t1(rng,2) for _ in range(150)]; test=[make_t1(rng,2) for _ in range(24)]
c=torch.load("p1_states.pt"); te=c["te"]
def emb(ids): return mr.get_input_embeddings()(ids.to(dev))
@torch.no_grad()
def rgen(x,mx=64):
    o=[]
    for _ in range(mx):
        nid=mr(inputs_embeds=x).logits[0,-1].argmax(-1); o.append(int(nid))
        if nid.item()==mr.config.eos_token_id: break
        x=torch.cat([x,emb(nid.view(1,1))],1)
    return tr.decode(torch.tensor(o)) if o else ""
print("="*72)
for i in range(6):
    it=test[i]; hint=te[i][0].strip().replace("\n"," ")
    ids=tr(qt(tr,cot(it["q"])),return_tensors="pt").to(dev)
    oA=rgen(emb(ids.input_ids)).strip().replace("\n"," ")
    ids2=tr(qt(tr,cot(it["q"])+f"\n\n【上一步的计算参考】\n{hint}"),return_tensors="pt").to(dev)
    oT=rgen(emb(ids2.input_ids)).strip().replace("\n"," ")
    print(f"\n[{i}] 正解={it['a']}")
    print(f"   sender CoT: 「{hint[:120]}」→{last_int(hint)}")
    print(f"   alone     : 「{oA[:120]}」→{last_int(oA)}")
    print(f"   text_relay: 「{oT[:120]}」→{last_int(oT)}")
