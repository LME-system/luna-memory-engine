#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporal Echo Test on 变速器
判据: 准确率随"桥与问题之间的时间间隔 g"如何衰减 —— 阶跃(存储) vs 指数(动力学)。
条件:
  text   : 值留在正文, g 句干扰插在正文与问题之间  → 参照(变压器/存储预期应为平台)
  bridge : 值从正文抹掉, 只能经桥的前缀到达, g 句干扰插在前缀与正文之间 → 被测
  shuffle/null : 否决性对照
"""
import os, re, json, time, random, math, torch
os.environ.setdefault("HF_HUB_OFFLINE","1"); os.environ.setdefault("TRANSFORMERS_OFFLINE","1")
import sys; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from tasks_v5 import load, qt, last_int

dev="mps" if torch.backends.mps.is_available() else "cpu"
M=load(dev); ms,mr,ts,tr=M["ms"],M["mr"],M["ts"],M["tr"]
ds,dr=ms.config.hidden_size,mr.config.hidden_size
K=16
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

rng=random.Random(21)
N_TRAIN,N_TEST=140,20
train=[make(rng) for _ in range(N_TRAIN)]; test=[make(rng) for _ in range(N_TEST)]
GAPS=[0,1,2,4,8]

# ---- sender 状态(全信息 prefill 末位) ----
@torch.no_grad()
def sstate(it):
    ids=ts(qt(ts,it["q"]),return_tensors="pt").to(dev)
    H=ms(**ids,output_hidden_states=True).hidden_states[-1][0,-1]
    return H.float().cpu()
CACHE="echo_states.pt"
if os.path.exists(CACHE):
    c=torch.load(CACHE); trS,teS=c["tr"],c["te"]; print("载入 echo_states 缓存",flush=True)
else:
    print("预计算 sender 状态...",flush=True); t0=time.time()
    trS=[sstate(it) for it in train]; teS=[sstate(it) for it in test]
    torch.save({"tr":trS,"te":teS},CACHE); print(f"  {time.time()-t0:.0f}s",flush=True)

def emb(ids): return mr.get_input_embeddings()(ids.to(dev))
class Bridge(torch.nn.Module):
    def __init__(s):
        super().__init__(); s.norm=torch.nn.LayerNorm(ds)
        s.net=torch.nn.Sequential(torch.nn.Linear(ds,512),torch.nn.GELU(),torch.nn.Linear(512,K*dr))
        s.gate=torch.nn.Parameter(torch.tensor([0.0])); s.basis=torch.nn.Parameter(torch.randn(K,dr)*0.02)
    def forward(s,h):
        z=s.net(s.norm(h)).view(K,dr); g=s.gate.sigmoid()
        return ((1-g)*s.basis+g*z).unsqueeze(0)
brid=Bridge().to(dev)
opt=torch.optim.AdamW(brid.parameters(),lr=5e-4)
for p in mr.parameters(): p.requires_grad_(False)
print("训练桥...",flush=True); t0=time.time()
for step in range(160):
    idx=[rng.randrange(N_TRAIN) for _ in range(4)]; loss=0.0
    for i in idx:
        it=train[i]; pref=brid(trS[i].to(dev))
        q=tr(qt(tr,it["qr"]),return_tensors="pt").input_ids[0]
        a=tr("答案="+it["a"]+tr.eos_token,return_tensors="pt").input_ids[0]
        full=torch.cat([q,a]).to(dev); lab=torch.cat([torch.full_like(q,-100),a]).to(dev)
        x=torch.cat([pref,emb(full.unsqueeze(0))],1)
        l=torch.cat([torch.full((K,),-100,device=dev,dtype=torch.long),lab]).unsqueeze(0)
        loss=loss+mr(inputs_embeds=x,attention_mask=torch.ones(x.shape[:2],device=dev),labels=l).loss
    (loss/4).backward(); torch.nn.utils.clip_grad_norm_(brid.parameters(),1.0); opt.step()
    if step%40==0: print(f"  step {step} loss {loss.item()/4:.3f} ({time.time()-t0:.0f}s)",flush=True)

@torch.no_grad()
def rgen(x,mx=24):
    o=[]
    for _ in range(mx):
        nid=mr(inputs_embeds=x).logits[0,-1].argmax(-1); o.append(int(nid))
        if nid.item()==mr.config.eos_token_id: break
        x=torch.cat([x,emb(nid.view(1,1))],1)
    return tr.decode(torch.tensor(o)) if o else ""
def gap_emb(g,rng): 
    if g==0: return None
    ids=tr(gap(rng,g),return_tensors="pt").input_ids.to(dev)
    return emb(ids)

@torch.no_grad()
def acc(mode,g):
    ok=0; grng=random.Random(99+g)
    perm=list(range(len(test))); random.Random(5).shuffle(perm)
    for i,it in enumerate(test):
        if mode=="text":
            gp=gap(grng,g)
            qq=it["q"]+("\n"+gp if g>0 else "")     # 值仍在正文, g句干扰在正文与答案之间
            x=emb(tr(qt(tr,qq),return_tensors="pt").to(dev).input_ids)
        else:
            pre=emb(tr(qt(tr,it["qr"]),return_tensors="pt").to(dev).input_ids)
            gE=gap_emb(g,grng)
            if mode=="bridge": p=brid(teS[i].to(dev))
            elif mode=="shuffle": p=brid(teS[perm[i]].to(dev))
            elif mode=="null": p=torch.zeros(1,K,dr,device=dev)
            parts=[p]+([gE] if gE is not None else [])+[pre]
            x=torch.cat(parts,1)
        ok+= last_int(rgen(x))==it["a"]
    return ok/len(test)

print("评估(各 g)...",flush=True)
res={}
for mode in ["text","bridge","shuffle","null"]:
    res[mode]={}
    for g in GAPS:
        res[mode][g]=round(acc(mode,g),3)
    print(f"  {mode:8s}: "+" ".join(f"g{g}:{res[mode][g]:.2f}" for g in GAPS),flush=True)

# 拟合: 阶跃 vs 指数
def fit_exp(gaps,ys):
    best=None
    for b in [x/20 for x in range(1,200)]:
        # y = c*exp(-g/b): 线性回归 log y vs g
        ss=0
        for g,y in zip(gaps,ys):
            pred=ys[0]*math.exp(-g/b); ss+=(y-pred)**2
        if best is None or ss<best[0]: best=(ss,b)
    return best
def fit_step(gaps,ys):
    # 阶跃: 前段常数=ys[0], 后段0; 找最佳断点
    best=None
    for k in range(1,len(gaps)):
        pred=[ys[0]]*k+[0]*(len(gaps)-k); ss=sum((y-p)**2 for y,p in zip(ys,pred))
        if best is None or ss<best[0]: best=(ss,k)
    return best
out={"config":{"n_train":N_TRAIN,"n_test":N_TEST,"gaps":GAPS},"results":res}
for mode in ["text","bridge"]:
    ys=[res[mode][g] for g in GAPS]
    ss_e,b=fit_exp(GAPS,ys); ss_s,k=fit_step(GAPS,ys)
    verdict="动力学(指数)" if ss_e<ss_s else "存储(阶跃)"
    out[mode+"_fit"]={"exp_ss":round(ss_e,4),"exp_tau":b,"step_ss":round(ss_s,4),"step_k":k,"verdict":verdict}
    print(f"  [{mode}] 指数SS={ss_e:.3f} vs 阶跃SS={ss_s:.3f} → {verdict}",flush=True)
json.dump(out,open("echo_results.json","w"),ensure_ascii=False,indent=2)
print("→ echo_results.json")
