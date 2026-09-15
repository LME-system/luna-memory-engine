#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P1: CoT 状态桥 + 全对照矩阵。
- sender 先逐步算(CoT), 取"生成末位隐藏状态" → 桥 → receiver 前缀
- 对照: alone / bridge / text_relay / shuffle / constant_prefix / null
- 核心读数: content_dependence = acc(bridge) - acc(shuffle)
"""
import os, re, json, time, random, argparse, torch
os.environ.setdefault("HF_HUB_OFFLINE","1"); os.environ.setdefault("TRANSFORMERS_OFFLINE","1")
import sys; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from tasks_v5 import load, make_t1, last_int, qt

dev="mps" if torch.backends.mps.is_available() else "cpu"
M=load(dev); ms,mr,ts,tr=M["ms"],M["mr"],M["ts"],M["tr"]
ds,dr=ms.config.hidden_size,mr.config.hidden_size
print(f"d_s={ds} d_r={dr}",flush=True)

def cot(q): return q.replace("计算并直接输出最终数字（不要解释）","请逐步推理计算，最后一行只写：答案=<数字>")
def prompt_r(it): return cot(it["q"])
def ans_txt(it):  return f"答案={it['a']}"

rng=random.Random(11)
N_TRAIN,N_TEST,DIFF,CAP = 150,24,2,48
train=[make_t1(rng,DIFF) for _ in range(N_TRAIN)]
test =[make_t1(rng,DIFF) for _ in range(N_TEST)]

# ---------- 1. 预计算 sender 状态 + CoT 文本 ----------
@torch.no_grad()
def sender_run(it):
    """返回 (cot文本, 末位隐藏状态向量)"""
    ids=ts(qt(ts,prompt_r(it)),return_tensors="pt").to(dev)
    g=ms.generate(**ids,max_new_tokens=CAP,do_sample=False,pad_token_id=ts.eos_token_id)
    txt=ts.decode(g[0,ids.input_ids.shape[1]:],skip_special_tokens=True)
    full=torch.cat([ids.input_ids[0],g[0,ids.input_ids.shape[1]:]])
    H=ms(full.unsqueeze(0),output_hidden_states=True).hidden_states[-1][0,-1]
    return txt, H.float().cpu()

CACHE="p1_states.pt"
if os.path.exists(CACHE):
    print(f"载入状态缓存 {CACHE}",flush=True)
    c=torch.load(CACHE); tr_states,te_states=c["tr"],c["te"]
else:
    print("预计算 sender 状态(train)...",flush=True); t0=time.time()
    tr_states=[sender_run(it) for it in train]
    te_states=[sender_run(it) for it in test]
    torch.save({"tr":tr_states,"te":te_states},CACHE)
    print(f"  完成 {time.time()-t0:.0f}s (已缓存)",flush=True)

K=16
def emb_ids(ids): return mr.get_input_embeddings()(ids.to(dev))

class Bridge(torch.nn.Module):
    def __init__(s):
        super().__init__()
        s.norm=torch.nn.LayerNorm(ds)
        s.net=torch.nn.Sequential(torch.nn.Linear(ds,512),torch.nn.GELU(),torch.nn.Linear(512,K*dr))
        s.gate=torch.nn.Parameter(torch.tensor([0.0]))
        s.basis=torch.nn.Parameter(torch.randn(K,dr)*0.02)
    def forward(s,h):                     # h: (ds,)
        z=s.net(s.norm(h)).view(K,dr)
        g=s.gate.sigmoid()
        return ((1-g)*s.basis + g*z).unsqueeze(0)   # (1,K,dr)

class ConstPrefix(torch.nn.Module):
    def __init__(s):
        super().__init__(); s.p=torch.nn.Parameter(torch.randn(K,dr)*0.02)
    def forward(s,h): return s.p.unsqueeze(0)

def train_pref(model, states, steps=150, bs=4, tag=""):
    opt=torch.optim.AdamW(model.parameters(),lr=5e-4)
    sch=torch.optim.lr_scheduler.CosineAnnealingLR(opt,steps)
    for p in mr.parameters(): p.requires_grad_(False)
    print(f"训练 {tag}...",flush=True); t=time.time()
    for step in range(steps):
        idx=[rng.randrange(len(train)) for _ in range(bs)]
        loss=0.0
        for i in idx:
            it=train[i]; h=states[i][1].to(dev)
            pref=model(h)
            q=tr(qt(tr,prompt_r(it)),return_tensors="pt").input_ids[0]
            a=tr(ans_txt(it)+tr.eos_token,return_tensors="pt").input_ids[0]
            full=torch.cat([q,a]).to(dev); lab=torch.cat([torch.full_like(q,-100),a]).to(dev)
            x=torch.cat([pref,emb_ids(full.unsqueeze(0))],1)
            l=torch.cat([torch.full((K,),-100,device=dev,dtype=torch.long),lab]).unsqueeze(0)
            loss=loss+mr(inputs_embeds=x,attention_mask=torch.ones(x.shape[:2],device=dev),labels=l).loss
        (loss/bs).backward(); torch.nn.utils.clip_grad_norm_(model.parameters(),1.0); opt.step(); sch.step()
        if step%50==0 or step==steps-1: print(f"  {tag} step {step} loss {loss.item()/bs:.3f} ({time.time()-t:.0f}s)",flush=True)

bridge=Bridge().to(dev); const=ConstPrefix().to(dev)
train_pref(bridge, tr_states, tag="Bridge")
train_pref(const,  tr_states, tag="Const")

# ---------- 2. 评估 ----------
GEN_MAX=64
@torch.no_grad()
def rgen(x,mx=GEN_MAX):
    o=[]
    for _ in range(mx):
        nid=mr(inputs_embeds=x).logits[0,-1].argmax(-1); o.append(int(nid))
        if nid.item()==mr.config.eos_token_id: break
        x=torch.cat([x,emb_ids(nid.view(1,1))],1)
    return tr.decode(torch.tensor(o)) if o else ""

@torch.no_grad()
def acc(mode):
    ok=0; perm=list(range(len(test))); random.Random(7).shuffle(perm)
    for i,it in enumerate(test):
        ids=tr(qt(tr,prompt_r(it)),return_tensors="pt").to(dev)
        if mode=="alone":
            x=emb_ids(ids.input_ids)
        elif mode=="text_relay":
            hint=te_states[i][0]
            ids2=tr(qt(tr,prompt_r(it)+f"\n\n【上一步的计算参考】\n{hint}"),return_tensors="pt").to(dev)
            x=emb_ids(ids2.input_ids)
        else:
            if mode=="bridge":    p=bridge(te_states[i][1].to(dev))
            elif mode=="shuffle": p=bridge(te_states[perm[i]][1].to(dev))
            elif mode=="const":   p=const(te_states[i][1].to(dev))
            elif mode=="null":    p=torch.zeros(1,K,dr,device=dev)
            x=torch.cat([p,emb_ids(ids.input_ids)],1)
        ok+= last_int(rgen(x))==it["a"]
    return ok/len(test)

print("评估...",flush=True)
# sender 上界(用其 CoT 文本直接判)
sender_alone=sum(last_int(te_states[i][0])==test[i]["a"] for i in range(len(test)))/len(test)
res={}
for m in ["alone","bridge","text_relay","shuffle","const","null"]:
    res[m]=round(acc(m),3); print(f"  {m:11s}: {res[m]:.3f}",flush=True)

# ---------- 3. 几何/内容依赖 ----------
with torch.no_grad():
    P=torch.stack([bridge(te_states[i][1].to(dev)).view(-1).cpu() for i in range(len(test))])
Pn=torch.nn.functional.normalize(P,dim=1); C=Pn@Pn.T; n=len(test)
cos=float(C[~torch.eye(n,dtype=bool)].mean())
Fc=P-P.mean(0,keepdim=True); sv=torch.linalg.svdvals(Fc); ev=(sv**2)/n
PR=float((ev.sum()**2)/((ev**2).sum()+1e-12))
# 换状态前缀漂移
d=[]
with torch.no_grad():
    for i in range(len(test)):
        d.append((bridge(te_states[i][1].to(dev))-bridge(te_states[(i+1)%len(test)][1].to(dev))).norm().item())
out={"config":{"diff":DIFF,"n_train":N_TRAIN,"n_test":N_TEST,"K":K,"cap":CAP,"gen_max":GEN_MAX},
     "results":{"sender_alone":round(sender_alone,3),**res},
     "gap":round(sender_alone-res["alone"],3),
     "content_dependence(bridge-shuffle)":round(res["bridge"]-res["shuffle"],3),
     "metrics":{"cosine(前缀题间)":round(cos,4),"PR":round(PR,2),"前缀跨状态漂移":round(sum(d)/len(d),3)},
     "tokens":{"bridge前端token":0,"text_relay前端token":round(sum(len(te_states[i][0]) for i in range(len(test)))/len(test),1)}}
json.dump(out,open("p1_results.json","w"),ensure_ascii=False,indent=2)
print("\n===== P1 结果 (难度2) =====")
print(f"  sender_alone: {sender_alone:.3f}")
for k,v in res.items(): print(f"  {k:11s}: {v:.3f}")
print("  content_dependence =",out["content_dependence(bridge-shuffle)"])
print("  指标:",out["metrics"]); print("→ p1_results.json")
