#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""变速器 v4 — 多重表达场 + 自适应基向量桥
设计依据: 《场全息理论》§4.2 Bridge Network + 本地Gemma4:31b 技术研讨
- 状态读出(准确测量): 多层(1/4,1/2,1) + 学习式注意力池化(自适应) + 频谱能量
- 自适应桥: 基向量库 Basis + 门控 Soft-WTA  → Prefix = softmax(gate(field)) · Basis
- 三指标: Cosine(方向) ⊥ PR(有效维度/复杂度) ⊥ CKA(结构)  (+L2)
- 测试: alone / q+bridge / shuffle / null / random_basis ; 前端token计量
"""
import os, re, random, json, time, argparse
os.environ.setdefault("HF_HUB_OFFLINE","1"); os.environ.setdefault("TRANSFORMERS_OFFLINE","1")
import torch

def parse():
    p=argparse.ArgumentParser()
    p.add_argument("--sender",default="Qwen/Qwen2.5-1.5B-Instruct")
    p.add_argument("--receiver",default="Qwen/Qwen2.5-0.5B-Instruct")
    p.add_argument("--n_attr",type=int,default=4)
    p.add_argument("--n_train",type=int,default=1500)
    p.add_argument("--n_test",type=int,default=40)
    p.add_argument("--steps",type=int,default=350)
    p.add_argument("--bs",type=int,default=4)
    p.add_argument("--k",type=int,default=16)          # soft-prefix 长度
    p.add_argument("--basis",type=int,default=64)      # 基向量库大小
    p.add_argument("--quick",action="store_true")
    p.add_argument("--out",default="v4.json")
    a=p.parse_args()
    if a.quick: a.n_train,a.n_test,a.steps=300,20,80
    return a

ATTRS=[("入职年份","他于{y}年加入公司",lambda r:r.randint(1998,2020)),("月薪","他的月薪是{y}元",lambda r:r.randint(8000,40000)),
       ("年龄","他今年{y}岁",lambda r:r.randint(25,58)),("工位号","他的工位是{y}号",lambda r:r.randint(100,999)),
       ("项目数","他负责过{y}个项目",lambda r:r.randint(2,40)),("存款","他有{y}元存款",lambda r:r.randint(10000,900000))]
FILL=["这家公司位于南方一座安静的沿海城市。","团队最近搬进了新的办公楼，采光很好。",
      "公司每年秋天都会组织一次团建活动。","食堂最近新增了几个档口，很受欢迎。","附近新开了一家书店，午休时同事们常去。"]
def make(rng,na=4):
    body=rng.choice(["李明","王芳","张伟","刘洋"]);o=rng.sample(ATTRS,6);t=o[0]
    v={n:g(rng) for n,tm,g in ATTRS}
    s=[t[1].format(y=v[t[0]])]+[tm.format(y=v[n]) for n,tm,_ in o[1:1+na]]+[rng.choice(FILL) for _ in range(2)]
    rng.shuffle(s);p=f"{body}是一名软件工程师。"+"".join(s)
    return {"q":f"阅读下面这段话，只回答一个数字：{body}的{t[0]}是多少？\n\n{p}","a":str(v[t[0]])}
def last_int(s):
    m=re.findall(r"-?\d+",s.replace(",",""))
    return m[-1] if m else None

def main():
    a=parse()
    from transformers import AutoTokenizer,AutoModelForCausalLM
    torch.manual_seed(0); rng=random.Random(0)
    dev="mps" if torch.backends.mps.is_available() else "cpu"
    print(f"device={dev} 难度={a.n_attr} | v4 多重表达场+自适应基桥",flush=True)
    ts=AutoTokenizer.from_pretrained(a.sender); tr=AutoTokenizer.from_pretrained(a.receiver)
    ms=AutoModelForCausalLM.from_pretrained(a.sender,dtype=torch.float32).to(dev).eval()
    mr=AutoModelForCausalLM.from_pretrained(a.receiver,dtype=torch.float32).to(dev).eval()
    for p in ms.parameters(): p.requires_grad_(False)
    for p in mr.parameters(): p.requires_grad_(False)
    ds,dr=ms.config.hidden_size,mr.config.hidden_size; nL=ms.config.num_hidden_layers
    emb=mr.get_input_embeddings()
    LAYERS=[nL//4, nL//2, nL]                          # 空: 浅/中/深 (1/4,1/2,1)
    print(f"d_s={ds} d_r={dr} nL={nL} 读出层={LAYERS}",flush=True)

    data=[make(rng,a.n_attr) for _ in range(a.n_train+a.n_test)]
    train,test=data[:a.n_train],data[-a.n_test:]
    def qt(tok,txt): return tok.apply_chat_template([{"role":"user","content":txt}],tokenize=False,add_generation_prompt=True)

    # ---------- 状态读出: 多层 + 学习式注意力池化 + 频谱 ----------
    @torch.no_grad()
    def raw_states(txts):
        """返回 [(3,T,ds)] 各层 prompt-token 隐藏状态 (T 可变)"""
        out=[]
        for t in txts:
            ids=ts(qt(ts,t),return_tensors="pt").to(dev)
            H=ms(**ids,output_hidden_states=True).hidden_states
            out.append(torch.stack([H[l][0] for l in LAYERS]))   # (3,T,ds)
        return out

    class Readout(torch.nn.Module):
        """学习式注意力池化(自适应测量) + 频谱"""
        def __init__(s):
            super().__init__(); s.q=torch.nn.Parameter(torch.randn(ds)/ds**0.5)
            s.scale=torch.nn.Parameter(torch.ones(3))
        def forward(s, H):                       # H: (3,T,ds)
            sc=(H@s.q)/ds**0.5*s.scale.view(3,1) # (3,T)
            w=torch.softmax(sc,-1)               # 层内位置注意力
            pooled=(w.unsqueeze(-1)*H).sum(1)    # (3,ds)
            spec=torch.fft.rfft(pooled,dim=-1).abs()[:, :64]   # 频: 能量谱
            return torch.cat([pooled.reshape(-1), spec.reshape(-1)])   # field

    field_dim=None
    class V4(torch.nn.Module):
        """自适应基桥: Prefix = softmax(gate(field)) · Basis"""
        def __init__(s, fdim):
            super().__init__(); s.readout=Readout()
            s.basis=torch.nn.Parameter(torch.randn(a.basis, a.k*dr)*0.02)
            s.gate=torch.nn.Sequential(torch.nn.Linear(fdim,256),torch.nn.GELU(),torch.nn.Linear(256,a.basis))
        def field(s,H): return s.readout(H)
        def forward(s,H):
            f=s.field(H); w=torch.softmax(s.gate(f),-1)          # Soft-WTA 门控
            return (w.unsqueeze(1)*s.basis.unsqueeze(0)).sum(1).view(a.k,dr).unsqueeze(0)
    model=V4(3*ds+64*3).to(dev)
    opt=torch.optim.AdamW(model.parameters(),lr=5e-4)
    sch=torch.optim.lr_scheduler.CosineAnnealingLR(opt,a.steps)

    print("训练 v4...",flush=True); t0=time.time()
    for step in range(a.steps):
        batch=[rng.choice(train) for _ in range(a.bs)]
        Hs=raw_states([b["q"] for b in batch])
        pref=torch.cat([model(H) for H in Hs],0)
        opt.zero_grad(); loss=0.0
        for i,it in enumerate(batch):
            enc=tr(qt(tr,it["q"]),return_tensors="pt"); qq=enc.input_ids[0]
            ans=tr(it["a"]+tr.eos_token,return_tensors="pt").input_ids[0]
            full=torch.cat([qq,ans]); lab=torch.cat([torch.full_like(qq,-100),ans]).to(dev)
            x=torch.cat([pref[i:i+1],emb(full.to(dev)).unsqueeze(0)],1)
            l=torch.cat([torch.full((a.k,),-100,device=dev,dtype=torch.long),lab]).unsqueeze(0)
            loss=loss+mr(inputs_embeds=x,attention_mask=torch.ones(x.shape[:2],device=dev),labels=l).loss
        (loss/len(batch)).backward(); torch.nn.utils.clip_grad_norm_(model.parameters(),1.0); opt.step(); sch.step()
        if step%50==0 or step==a.steps-1: print(f"  step {step} loss {loss.item()/len(batch):.3f} ({time.time()-t0:.0f}s)",flush=True)
    torch.save(model.state_dict(), "v4_bridge.pt")

    @torch.no_grad()
    def gen(x,mx=10):
        o=[]
        for _ in range(mx):
            nid=mr(inputs_embeds=x).logits[0,-1].argmax(-1); o.append(int(nid))
            if nid.item()==mr.config.eos_token_id: break
            x=torch.cat([x,emb(nid.view(1,1))],1)
        return tr.decode(torch.tensor(o)) if o else ""
    @torch.no_grad()
    def acc(mode):
        ok=0; okgen=0
        perm=list(range(len(test))); random.Random(1).shuffle(perm)
        for i,it in enumerate(test):
            enc=tr(qt(tr,it["q"]),return_tensors="pt").to(dev)
            if mode=="alone":
                x=emb(enc.input_ids)
            else:
                H=raw_states([it["q"]])[0]
                if mode=="bridge":  p=model(H)
                elif mode=="shuffle":
                    Hj=raw_states([test[perm[i]]["q"]])[0]; p=model(Hj)
                elif mode=="null":   p=model(torch.zeros_like(H))
                elif mode=="random": p=torch.randn(1,a.k,dr,device=dev)*0.02
                x=torch.cat([p,emb(enc.input_ids)],1)
            ok+= last_int(gen(x))==it["a"]
        return ok/len(test)

    # ---- 三指标: Cosine / PR / CKA (在 sender 多重表达场上) ----
    with torch.no_grad():
        F=torch.stack([model.field(raw_states([it["q"]])[0]) for it in test]).cpu()   # (n, fdim) CPU(for eigvalsh)
    Fn=torch.nn.functional.normalize(F,dim=1); C=Fn@Fn.T; n=len(test)
    cos_mean=float(C[~torch.eye(n,dtype=bool)].mean())
    Fc=F-F.mean(0,keepdim=True); cov=Fc.T@Fc/n
    ev=torch.linalg.eigvalsh(cov).clamp(min=0); PR=float((ev.sum()**2)/((ev**2).sum()+1e-12))
    def cka(A,B):
        A=A-A.mean(0,keepdim=True); B=B-B.mean(0,keepdim=True)
        return float(((A.T@B)**2).sum()/(((A.T@A)**2).sum()*((B.T@B)**2).sum()).sqrt())
    # 用两半样本算 CKA(自结构一致性)
    Fa,Fb=F[:n//2],F[n//2:]
    cka_v=cka(Fa[:len(Fb)],Fb)
    norm_mean=float(F.norm(dim=1).mean())

    print("评估...",flush=True)
    res={"alone":acc("alone"),"q+bridge":acc("bridge"),"shuffle":acc("shuffle"),
         "null":acc("null"),"random":acc("random")}
    M={"cosine(方向)":round(cos_mean,4),"PR(有效维度)":round(PR,2),"CKA(结构)":round(cka_v,4),"L2(能量)":round(norm_mean,2)}
    # 前端 token 计量
    tok={"bridge(前端生成token/题)":0,"text_relay(前端生成token/题)":None}
    @torch.no_grad()
    def text_relay_tokens():
        tot=0; ok=0
        for it in test[:12]:
            ids=ts(qt(ts,it["q"]),return_tensors="pt").to(dev)
            g=ms.generate(**ids,max_new_tokens=12,do_sample=False)
            nt=g.shape[1]-ids.input_ids.shape[1]; tot+=nt
            hint=ts.decode(g[0,ids.input_ids.shape[1]:],skip_special_tokens=True)
            e2=tr(qt(tr,it["q"]+f"\n(参考:{hint})"),return_tensors="pt").to(dev)
            gg=mr.generate(**e2,max_new_tokens=10,do_sample=False)
            ok+= last_int(tr.decode(gg[0,e2.input_ids.shape[1]:],skip_special_tokens=True))==it["a"]
        return tot/12, ok/12
    tm,tok_relay=text_relay_tokens(); tok["text_relay(前端生成token/题)"]=round(tm,1)
    out={"config":vars(a),"results":res,"metrics":M,"tokens":tok}
    json.dump(out,open(a.out,"w"),ensure_ascii=False,indent=2)
    print("\n===== v4 结果 =====")
    for k,v in res.items(): print(f"  {k:12s}: {v:.3f}")
    print("  指标:",M); print("  前端token:",tok)
    print("→",a.out)

if __name__=="__main__": main()
