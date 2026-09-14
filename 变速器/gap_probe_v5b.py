#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0b: 修正造题 bug 后重探 gap。
修正: ①操作数同量级小值(10-99),不用"年份" ②T2只用+/-避免优先级 ③sender/receiver 都放开生成
"""
import os, re, random, json, torch
os.environ.setdefault("HF_HUB_OFFLINE","1"); os.environ.setdefault("TRANSFORMERS_OFFLINE","1")
from transformers import AutoTokenizer, AutoModelForCausalLM

dev="mps" if torch.backends.mps.is_available() else "cpu"
ts=AutoTokenizer.from_pretrained("Qwen/Qwen2.5-1.5B-Instruct")
tr=AutoTokenizer.from_pretrained("Qwen/Qwen2.5-0.5B-Instruct")
ms=AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-1.5B-Instruct",dtype=torch.float32).to(dev).eval()
mr=AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-0.5B-Instruct",dtype=torch.float32).to(dev).eval()

def qt(tok,txt): return tok.apply_chat_template([{"role":"user","content":txt}],tokenize=False,add_generation_prompt=True)
@torch.no_grad()
def gen(model,tok,txt,n=64):
    ids=tok(qt(tok,txt),return_tensors="pt").to(dev)
    g=model.generate(**ids,max_new_tokens=n,do_sample=False,pad_token_id=tok.eos_token_id)
    return tok.decode(g[0,ids.input_ids.shape[1]:],skip_special_tokens=True)
def last_int(s):
    m=re.findall(r"-?\d+",str(s).replace(",","")); return m[-1] if m else None

T1=[("工位号","他的工位是{y}号"),("项目数","他负责过{y}个项目"),("楼层","他在{y}楼办公"),
    ("编号","他的编号是{y}"),("年龄","他今年{y}岁"),("成员数","他团队有{y}人")]
FILL=["这家公司位于南方一座安静的沿海城市。","团队最近搬进了新的办公楼，采光很好。",
      "食堂最近新增了几个档口，很受欢迎。","附近新开了一家书店，午休时同事们常去。"]
def make_t1(rng,n_op=2):
    body=rng.choice(["李明","王芳","张伟","刘洋"]); order=rng.sample(T1,len(T1))
    v={n:rng.randint(10,99) for n,_ in T1}
    s=[t.format(y=v[n]) for n,t in order]+[rng.choice(FILL) for _ in range(2)]
    rng.shuffle(s); passage=f"{body}是一名软件工程师。"+"".join(s)
    picked=rng.sample([n for n,_ in T1],n_op)
    expr=f"{body}的{picked[0]}"; ans=v[picked[0]]
    for n in picked[1:]:
        op=rng.choice(["+","-"]); expr+=f"{op}{body}的{n}"; ans=ans+v[n] if op=="+" else ans-v[n]
    q=f"阅读下面这段话，计算并直接输出最终数字（不要解释）：{expr}等于多少？\n\n{passage}"
    return {"q":q,"a":str(ans),"diff":n_op}

def make_t2(rng,n_step=3):
    a=rng.randint(10,60); expr=f"{a}"
    for _ in range(n_step):
        op=rng.choice(["+","-"]); b=rng.randint(2,30); expr+=f" {op} {b}"
        a=a+b if op=="+" else a-b
    q=f"从左往右依次计算，直接输出最终数字（不要解释）：{expr} = ?"
    return {"q":q,"a":str(a),"diff":n_step}

rng=random.Random(0); NT=12
rep={}
for name,mk,diffs in [("T1多跳检索+运算",make_t1,[1,2,3]),("T2链式+/-",make_t2,[2,3,4])]:
    print(f"\n### {name}"); rep[name]={}
    for d in diffs:
        its=[mk(rng,d) for _ in range(NT)]
        aS=sum(last_int(gen(ms,ts,it["q"]))==it["a"] for it in its)/NT
        aR=sum(last_int(gen(mr,tr,it["q"]))==it["a"] for it in its)/NT
        rep[name][d]={"sender":round(aS,2),"receiver":round(aR,2),"gap":round(aS-aR,2)}
        print(f"  难度={d}: sender {aS:.2f} | receiver {aR:.2f} | gap {aS-aR:+.2f}")
        if d==diffs[0]:
            for it in its[:2]: print(f"     e.g. {it['q'].splitlines()[0][:30]}.. 正解={it['a']} S「{gen(ms,ts,it['q'],40).strip()[:60]}」R「{gen(mr,tr,it['q'],40).strip()[:40]}」")
json.dump(rep,open("gap_probe_v5b.json","w"),ensure_ascii=False,indent=2)
print("\n→ gap_probe_v5b.json")
