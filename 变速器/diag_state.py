#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诊断: sender 状态在题目间到底有没有差异?
若"最后一token状态"在所有题间近乎相同 → shuffle 对照无效(我的结论站不住)
"""
import os, random, re
os.environ.setdefault("HF_HUB_OFFLINE","1"); os.environ.setdefault("TRANSFORMERS_OFFLINE","1")
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
dev="mps" if torch.backends.mps.is_available() else "cpu"
ATTRS=[("入职年份","他于{y}年加入公司",lambda r:r.randint(1998,2020)),("月薪","他的月薪是{y}元",lambda r:r.randint(8000,40000)),
       ("年龄","他今年{y}岁",lambda r:r.randint(25,58)),("工位号","他的工位是{y}号",lambda r:r.randint(100,999)),
       ("项目数","他负责过{y}个项目",lambda r:r.randint(2,40)),("存款","他有{y}元存款",lambda r:r.randint(10000,900000))]
FILL=["这家公司位于南方一座安静的沿海城市。","团队最近搬进了新的办公楼，采光很好。","公司每年秋天都会组织一次团建活动。"]
def make(rng,na=4):
    body=rng.choice(["李明","王芳","张伟","刘洋"]);order=rng.sample(ATTRS,6);t=order[0]
    v={n:g(rng) for n,tm,g in ATTRS}
    s=[t[1].format(y=v[t[0]])]+[tm.format(y=v[n]) for n,tm,_ in order[1:1+na]]+[rng.choice(FILL) for _ in range(2)]
    rng.shuffle(s);p=f"{body}是一名软件工程师。"+"".join(s)
    return {"q":f"阅读下面这段话，只回答一个数字：{body}的{t[0]}是多少？\n\n{p}","a":str(v[t[0]])}
ts=AutoTokenizer.from_pretrained("Qwen/Qwen2.5-1.5B-Instruct")
ms=AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-1.5B-Instruct",dtype=torch.float32).to(dev).eval()
rng=random.Random(0); items=[make(rng) for _ in range(40)]
def qt(it): return ts.apply_chat_template([{"role":"user","content":it["q"]}],tokenize=False,add_generation_prompt=True)
last=[]; mean=[]; ansref=[]
with torch.no_grad():
    for it in items:
        ids=ts(qt(it),return_tensors="pt").to(dev)
        H=ms(**ids,output_hidden_states=True).hidden_states[-1][0]   # (T,d)
        last.append(H[-1]); mean.append(H.mean(0))
        # 参考: 把 gold 答案接上, 取答案第一个token位置的隐藏状态(含答案内容)
        ids2=ts(qt(it)+it["a"],return_tensors="pt").to(dev)
        H2=ms(**ids2,output_hidden_states=True).hidden_states[-1][0]
        ansref.append(H2[len(ids.input_ids[0])-1])   # 答案前一位置
last=torch.stack(last); mean=torch.stack(mean); ansref=torch.stack(ansref)
def cosstats(X,name):
    Xn=torch.nn.functional.normalize(X,dim=1)
    S=Xn@Xn.T; n=S.shape[0]; off=S[~torch.eye(n,dtype=bool)]
    print(f"{name:26s} 余弦相似度: 均值={off.mean():.4f} 最小={off.min():.4f} 最大={off.max():.4f} | 不同题间= {1-off.mean():.4f}")
cosstats(last,   "最后一token(我用的)")
cosstats(mean,   "题干token平均(内容承载?)")
cosstats(ansref, "答案前位置(含答案)")
# 输出多样性: 两两 L2 距离 vs 组内方差
def dist(X,name):
    D=torch.cdist(X,X); n=X.shape[0]; off=D[~torch.eye(n,dtype=bool)]
    print(f"{name:26s} L2距离 均值={off.mean():.3f} | 向量模长均值={X.norm(dim=1).mean():.3f}")
dist(last,"最后一token"); dist(mean,"题干平均"); dist(ansref,"答案前")
