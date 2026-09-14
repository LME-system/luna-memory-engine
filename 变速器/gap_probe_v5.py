#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0: 任务候选 gap 探针 —— 只测 sender/receiver 能力差, 不训桥。
选出让 1.5B≫0.5B 的任务+难度。"""
import os, re, random, json, torch, time
os.environ.setdefault("HF_HUB_OFFLINE","1"); os.environ.setdefault("TRANSFORMERS_OFFLINE","1")
from transformers import AutoTokenizer, AutoModelForCausalLM

dev="mps" if torch.backends.mps.is_available() else "cpu"
S="Qwen/Qwen2.5-1.5B-Instruct"; R="Qwen/Qwen2.5-0.5B-Instruct"
ts=AutoTokenizer.from_pretrained(S); tr=AutoTokenizer.from_pretrained(R)
ms=AutoModelForCausalLM.from_pretrained(S,dtype=torch.float32).to(dev).eval()
mr=AutoModelForCausalLM.from_pretrained(R,dtype=torch.float32).to(dev).eval()

def qt(tok,txt): return tok.apply_chat_template([{"role":"user","content":txt}],tokenize=False,add_generation_prompt=True)
@torch.no_grad()
def gen(model,tok,txt,n=16):
    ids=tok(qt(tok,txt),return_tensors="pt").to(dev)
    g=model.generate(**ids,max_new_tokens=n,do_sample=False,pad_token_id=tok.eos_token_id)
    return tok.decode(g[0,ids.input_ids.shape[1]:],skip_special_tokens=True)
def last_int(s):
    m=re.findall(r"-?\d+",str(s).replace(",","")); return m[-1] if m else None

# ---------------- T1: 多跳检索+运算 ----------------
T1_ATTRS=[("入职年份",lambda r:r.randint(1998,2015)),("年龄",lambda r:r.randint(25,60)),
          ("工位号",lambda r:r.randint(10,99)),("项目数",lambda r:r.randint(10,99)),
          ("楼层",lambda r:r.randint(10,99)),("编号",lambda r:r.randint(10,99))]
T1_TMPL={"入职年份":"他于{y}年加入公司","年龄":"他今年{y}岁","工位号":"他的工位是{y}号",
         "项目数":"他负责过{y}个项目","楼层":"他在{y}楼办公","编号":"他的编号是{y}"}
FILL=["这家公司位于南方一座安静的沿海城市。","团队最近搬进了新的办公楼，采光很好。",
      "食堂最近新增了几个档口，很受欢迎。","附近新开了一家书店，午休时同事们常去。"]
def make_t1(rng,n_op=2):
    body=rng.choice(["李明","王芳","张伟","刘洋"])
    order=rng.sample(T1_ATTRS,len(T1_ATTRS)); v={n:g(rng) for n,g in T1_ATTRS}
    s=[T1_TMPL[n].format(y=v[n]) for n,_ in order]+[rng.choice(FILL) for _ in range(2)]
    rng.shuffle(s); passage=f"{body}是一名软件工程师。"+"".join(s)
    picked=rng.sample([n for n,_ in T1_ATTRS],n_op)
    if n_op==1:
        expr=f"{body}的{picked[0]}"; ans=v[picked[0]]
    else:
        expr=f"{body}的{picked[0]}"; ans=v[picked[0]]
        for i,n in enumerate(picked[1:]):
            op=rng.choice(["+","-"])
            expr+=f"{op}{body}的{n}"; ans=ans+v[n] if op=="+" else ans-v[n]
    q=f"阅读下面这段话，计算并只回答一个数字：{expr}等于多少？\n\n{passage}"
    return {"q":q,"a":str(ans),"diff":n_op}

# ---------------- T2: 链式运算 ----------------
def make_t2(rng,n_step=3):
    a=rng.randint(2,9); expr=f"{a}"
    for _ in range(n_step):
        op=rng.choice(["+","-","×"]); b=rng.randint(2,9)
        expr+=f" {op} {b}"; a=a+b if op=="+" else (a-b if op=="-" else a*b)
    q=f"计算并只回答一个数字：{expr} = ?"
    return {"q":q,"a":str(a),"diff":n_step}

rng=random.Random(0)
NTEST=12
print("="*72)
report={}
for name,mk,diffs in [("T1多跳检索+运算",make_t1,[1,2,3]),
                      ("T2链式运算",      make_t2,[2,3,4])]:
    print(f"\n### {name}")
    report[name]={}
    for d in diffs:
        items=[mk(rng,d) for _ in range(NTEST)]
        accS=sum(last_int(gen(ms,ts,it["q"]))==it["a"] for it in items)/NTEST
        accR=sum(last_int(gen(mr,tr,it["q"]))==it["a"] for it in items)/NTEST
        report[name][d]={"sender":round(accS,3),"receiver":round(accR,3),"gap":round(accS-accR,3)}
        print(f"  难度={d}: sender {accS:.2f} | receiver {accR:.2f} | gap {accS-accR:+.2f}")
json.dump(report,open("gap_probe_v5.json","w"),ensure_ascii=False,indent=2)
print("\n→ gap_probe_v5.json")
