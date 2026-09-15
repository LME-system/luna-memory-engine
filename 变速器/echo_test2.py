#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporal Echo Test v2 —— 四选一(只输出字母A/B/C/D)，让桥能承载。
数据生成与 v1 完全一致(rng=21)，复用 echo_states.pt。
"""
import os, json, time, random, math, torch
os.environ.setdefault("HF_HUB_OFFLINE","1"); os.environ.setdefault("TRANSFORMERS_OFFLINE","1")
import sys; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from tasks_v5 import load, qt, last_int

dev="mps" if torch.backends.mps.is_available() else "cpu"
M=load(dev); ms,mr,ts,tr=M["ms"],M["mr"],M["ts"],M["tr"]
ds,dr=ms.config.hidden_size,mr.config.hidden_size
K=16; LETTERS=["A","B","C","D"]
FILL=["这家公司位于南方一座安静的沿海城市。","团队最近搬进了新的办公楼，采光很好。",
      "食堂最近新增了几个档口，很受欢迎。","附近新开了一家书店，午休时同事们常去。",
      "公司每年秋天都会组织一次团建活动。","走廊尽头的绿植长势不错。"]
OTHER=[("年龄","他今年{y}岁",lambda r:r.randint(25,60)),("工位号","他的工位是{y}号",lambda r:r.randint(10,99)),
       ("项目数","他负责过{y}个项目",lambda r:r.randint(10,99)),("楼层","他在{y}楼办公",lambda r:r.randint(10,99)),
       ("成员数","他团队有{y}人",lambda r:r.randint(10,99))]

def make(rng):
    name=rng.choice(["李明","王芳","张伟","刘洋"]); V=rng.randint(10000,999999)
    tgt=f"他的存款是{V}元"
    sents=[tgt]+[t.format(y=g(rng)) for _,t,g in rng.sample(OTHER,4)]+[rng.choice(FILL) for _ in range(2)]
    rng.shuffle(sents); passage=f"{name}是一名软件工程师。"+"".join(sents)
    q=f"阅读下面这段话，回答问题：{name}的存款是多少？只回答一个数字。\n\n{passage}"
    red=q.replace(tgt,"他的存款是【未知】元")
    return {"q":q,"qr":red,"a":str(V),"tgt":tgt}
def gap(rng,g): return "".join(rng.choice(FILL) for _ in range(g))

# ---- 与 v1 一致的数据(rng=21) ----
rng=random.Random(21); N_TRAIN,N_TEST=140,20
train=[make(rng) for _ in range(N_TRAIN)]; test=[make(rng) for _ in range(N_TEST)]
GAPS=[0,1,2,4,8]
# ---- 选项(独立 rng) ----
orr=random.Random(77)
def opts(it):
    V=int(it["a"]); c=[V]
    while len(c)<4:
        x=random.Random(orr.randrange(1<<30)).randint(10000,999999)
        if x not in c: c.append(x)
    orr.shuffle(c); ci=c.index(V); it=dict(it); it["opts"]=c; it["letter"]=LETTERS[ci]; return it
train=[opts(it) for it in train]; test=[opts(it) for it in test]
teS=torch.load("echo_states.pt")["te"]; trS=torch.load("echo_states.pt")["tr"]
print(f"数据/状态就绪 train={len(train)} test={len(test)}",flush=True)

def emb(ids): return mr.get_input_embeddings()(ids.to(dev))
class Bridge(torch.nn.Module):
    def __init__(s):
        super().__init__(); s.norm=torch.nn.LayerNorm(ds)
        s.net=torch.nn.Sequential(torch.nn.Linear(ds,512),torch.nn.GELU(),torch.nn.Linear(512,K*dr))
        s.gate=torch.nn.Parameter(torch.tensor([0.0])); s.basis=torch.nn.Parameter(torch.randn(K,dr)*0.02)
    def forward(s,h):
        z=s.net(s.norm(h)).view(K,dr); g=s.gate.sigmoid()
        return ((1-g)*s.basis+g*z).unsqueeze(0)
brid=Bridge().to(dev); opt=torch.optim.AdamW(brid.parameters(),lr=5e-4)
for p in mr.parameters(): p.requires_grad_(False)

def mc_prompt(it,redacted=True,grng=None,g=0):
    body=it["qr"] if redacted else it["q"]
    o=it["opts"]; optline=" ".join(f"{L}){v}" for L,v in zip(LETTERS,o))
    base=body.split("\n\n",1)
    head=f"阅读下面这段话，从选项中选择一个数字回答，只回答一个字母。\n\n{base[1] if len(base)>1 else ''}"
    return head+f"\n\n选项：{optline}\n答案："

print("训练桥...",flush=True); t0=time.time()
for step in range(200):
    idx=[rng.randrange(N_TRAIN) for _ in range(4)]; loss=0.0
    for i in idx:
        it=train[i]; pref=brid(trS[i].to(dev))
        q=tr(qt(tr,mc_prompt(it)),return_tensors="pt").input_ids[0]
        a=tr(it["letter"]+tr.eos_token,return_tensors="pt").input_ids[0]
        full=torch.cat([q,a]).to(dev); lab=torch.cat([torch.full_like(q,-100),a]).to(dev)
        x=torch.cat([pref,emb(full.unsqueeze(0))],1)
        l=torch.cat([torch.full((K,),-100,device=dev,dtype=torch.long),lab]).unsqueeze(0)
        loss=loss+mr(inputs_embeds=x,attention_mask=torch.ones(x.shape[:2],device=dev),labels=l).loss
    (loss/4).backward(); torch.nn.utils.clip_grad_norm_(brid.parameters(),1.0); opt.step()
    if step%40==0: print(f"  step {step} loss {loss.item()/4:.3f} ({time.time()-t0:.0f}s)",flush=True)

@torch.no_grad()
def pick(x):
    nid=mr(inputs_embeds=x).logits[0,-1].argmax(-1)
    return tr.decode(nid.view(1)).strip()[:1].upper()

@torch.no_grad()
def acc(mode,g):
    ok=0; grng=random.Random(99+g); perm=list(range(len(test))); random.Random(5).shuffle(perm)
    for i,it in enumerate(test):
        if mode=="text":
            gp=gap(grng,g); body=it["q"]+("\n"+gp if g>0 else "")
            o=it["opts"]; optline=" ".join(f"{L}){v}" for L,v in zip(LETTERS,o))
            txt=f"阅读下面这段话，从选项中选择一个数字回答，只回答一个字母。\n\n{body.split(chr(10)+chr(10),1)[1]}\n\n选项：{optline}\n答案："
            x=emb(tr(qt(tr,txt),return_tensors="pt").to(dev).input_ids)
        else:
            pre=emb(tr(qt(tr,mc_prompt(it)),return_tensors="pt").to(dev).input_ids)
            gE=emb(tr(gap(grng,g),return_tensors="pt").input_ids.to(dev)) if g>0 else None
            if mode=="bridge": p=brid(teS[i].to(dev))
            elif mode=="shuffle": p=brid(teS[perm[i]].to(dev))
            elif mode=="null": p=torch.zeros(1,K,dr,device=dev)
            x=torch.cat([p]+([gE] if gE is not None else [])+[pre],1)
        ok+= pick(x)==it["letter"]
    return ok/len(test)

print("评估...",flush=True); res={}
for mode in ["text","bridge","shuffle","null"]:
    res[mode]={g:round(acc(mode,g),3) for g in GAPS}
    print(f"  {mode:8s}: "+" ".join(f"g{g}:{res[mode][g]:.2f}" for g in GAPS),flush=True)
def fit_exp(gs,ys):
    best=None
    for b in [x/10 for x in range(1,500)]:
        ss=sum((y-ys[0]*math.exp(-g/b))**2 for g,y in zip(gs,ys))
        if best is None or ss<best[0]: best=(ss,b)
    return best
def fit_step(gs,ys):
    best=None
    for k in range(1,len(gs)):
        pred=[ys[0]]*k+[0]*(len(gs)-k); ss=sum((y-p)**2 for y,p in zip(ys,pred))
        if best is None or ss<best[0]: best=(ss,k)
    return best
out={"gaps":GAPS,"results":res}
for m in ["text","bridge"]:
    ys=[res[m][g] for g in GAPS]; se,b=fit_exp(GAPS,ys); ss,k=fit_step(GAPS,ys)
    v="动力学(指数)" if se<ss else "存储(阶跃)"
    out[m+"_fit"]={"exp_ss":round(se,4),"exp_tau":b,"step_ss":round(ss,4),"step_k":k,"verdict":v}
    print(f"  [{m}] 指数SS={se:.4f} vs 阶跃SS={ss:.4f} → {v}",flush=True)
json.dump(out,open("echo_results2.json","w"),ensure_ascii=False,indent=2); print("→ echo_results2.json")
