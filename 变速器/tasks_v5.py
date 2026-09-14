#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""共享: 任务生成器 + 模型加载(惰性)。被各探针/评估脚本 import。"""
import os, re, random, torch
os.environ.setdefault("HF_HUB_OFFLINE","1"); os.environ.setdefault("TRANSFORMERS_OFFLINE","1")

HERE=os.path.dirname(os.path.abspath(__file__))
S_MODEL="Qwen/Qwen2.5-1.5B-Instruct"; R_MODEL="Qwen/Qwen2.5-0.5B-Instruct"
_models={}
def load(dev=None):
    if _models: return _models
    from transformers import AutoTokenizer, AutoModelForCausalLM
    dev=dev or ("mps" if torch.backends.mps.is_available() else "cpu")
    ts=AutoTokenizer.from_pretrained(S_MODEL); tr=AutoTokenizer.from_pretrained(R_MODEL)
    ms=AutoModelForCausalLM.from_pretrained(S_MODEL,dtype=torch.float32).to(dev).eval()
    mr=AutoModelForCausalLM.from_pretrained(R_MODEL,dtype=torch.float32).to(dev).eval()
    _models.update(dev=dev,ts=ts,tr=tr,ms=ms,mr=mr); return _models

def qt(tok,txt): return tok.apply_chat_template([{"role":"user","content":txt}],tokenize=False,add_generation_prompt=True)
def last_int(s):
    m=re.findall(r"-?\d+",str(s).replace(",","")); return m[-1] if m else None

_T1=[("工位号","他的工位是{y}号"),("项目数","他负责过{y}个项目"),("楼层","他在{y}楼办公"),
     ("编号","他的编号是{y}"),("年龄","他今年{y}岁"),("成员数","他团队有{y}人")]
_FILL=["这家公司位于南方一座安静的沿海城市。","团队最近搬进了新的办公楼，采光很好。",
       "食堂最近新增了几个档口，很受欢迎。","附近新开了一家书店，午休时同事们常去。"]
def make_t1(rng,n_op=2):
    body=rng.choice(["李明","王芳","张伟","刘洋"]); order=rng.sample(_T1,len(_T1))
    v={n:rng.randint(10,99) for n,_ in _T1}
    s=[t.format(y=v[n]) for n,t in order]+[rng.choice(_FILL) for _ in range(2)]
    rng.shuffle(s); passage=f"{body}是一名软件工程师。"+"".join(s)
    picked=rng.sample([n for n,_ in _T1],n_op)
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

@torch.no_grad()
def gen(model,tok,txt,n=64,prompt_suffix=None):
    ids=tok(qt(tok,txt),return_tensors="pt").to(_models["dev"])
    g=model.generate(**ids,max_new_tokens=n,do_sample=False,pad_token_id=tok.eos_token_id)
    return tok.decode(g[0,ids.input_ids.shape[1]:],skip_special_tokens=True)
