#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""6 样本快速验证：前端状态空间差异大 + 接收端极难
6 个任务族(各不同) → sender 状态彼此分开; 且 0.5B 难
对照: alone / q+bridge / q+bridge_shuffle(错配)
"""
import os, re, random, json, time
os.environ.setdefault("HF_HUB_OFFLINE","1"); os.environ.setdefault("TRANSFORMERS_OFFLINE","1")
import torch
dev="mps" if torch.backends.mps.is_available() else "cpu"
SEND="Qwen/Qwen2.5-1.5B-Instruct"; RECV="Qwen/Qwen2.5-0.5B-Instruct"
NAMES=["李明","王芳","张伟","刘洋","陈静","赵磊"]
K=16; RANK=128; STEPS=200; NTRAIN=600

# ---------------- 6 个任务族 (答案均为纯数字) ----------------
def f_age(r):
    a=r.randint(30,55); d=r.randint(22,30); n=r.choice(NAMES)
    return (f"{n}今年{a}岁，{n}的儿子比{n}小{d}岁。{n}的儿子今年多少岁？只答数字。", str(a-d))
def f_salary(r):
    a=r.randint(15000,40000); d=r.randint(2000,8000); n1,n2=r.sample(NAMES,2)
    return (f"{n1}的月薪是{a}元，{n2}的月薪比{n1}少{d}元。{n2}的月薪是多少元？只答数字。", str(a-d))
def f_sum(r):
    vals=[r.randint(11,99) for _ in range(3)]; n=r.choice(NAMES)
    return (f"{n}负责过{vals[0]}个项目，另一位同事负责过{vals[1]}个项目，第三位负责过{vals[2]}个项目。这三个人负责的项目一共多少个？只答数字。", str(sum(vals)))
def f_mult(r):
    k=r.randint(3,7); m=r.randint(2000,9000); n=r.choice(NAMES)
    return (f"{n}的存款是同事的{k}倍，同事有{m}元存款。{n}有多少元存款？只答数字。", str(k*m))
def f_find(r):
    n=r.choice(NAMES); y=r.randint(1998,2016); w=r.randint(100,999); p=r.randint(8000,30000)
    s=[f"{n}于{y}年加入公司。",f"{n}的工位是{w}号。",f"{n}的月薪是{p}元。","公司在南方一座安静的城市，团队最近搬了新办公室。"]
    r.shuffle(s)
    return (f"阅读这段话，只回答一个数字：{n}的工位是多少号？\n"+"".join(s), str(w))
def f_years(r):
    y=r.randint(2000,2018); n=r.choice(NAMES)
    return (f"{n}在{y}年入职，现在是2026年。{n}已经工作了多少年？只答数字。", str(2026-y))

FAMS=[f_age,f_salary,f_sum,f_mult,f_find,f_years]

def last_int(s):
    m=re.findall(r"-?\d+",s.replace(",",""))
    return m[-1] if m else None

def main():
    from transformers import AutoTokenizer,AutoModelForCausalLM
    torch.manual_seed(0); rng=random.Random(7)
    ts=AutoTokenizer.from_pretrained(SEND); tr=AutoTokenizer.from_pretrained(RECV)
    ms=AutoModelForCausalLM.from_pretrained(SEND,dtype=torch.float32).to(dev).eval()
    mr=AutoModelForCausalLM.from_pretrained(RECV,dtype=torch.float32).to(dev).eval()
    for p in ms.parameters(): p.requires_grad_(False)
    for p in mr.parameters(): p.requires_grad_(False)
    ds,dr=ms.config.hidden_size,mr.config.hidden_size; emb=emb_r=mr.get_input_embeddings()
    def qt(tok,txt): return tok.apply_chat_template([{"role":"user","content":txt}],tokenize=False,add_generation_prompt=True)
    # 训练集: 6 族混合
    train=[]
    for i in range(NTRAIN): train.append(FAMS[i%6](rng))
    # 6 个测试样本: 每族 1 个 (固定 seed 生成)
    test=[FAMS[i](random.Random(100+i)) for i in range(6)]

    class Bridge(torch.nn.Module):
        def __init__(s):
            super().__init__(); s.ln=torch.nn.LayerNorm(ds); s.dr=dr
            s.down=torch.nn.Linear(ds,RANK); s.up=torch.nn.Linear(RANK,K*dr)
            s.anchor=torch.nn.Parameter(emb.weight.detach().mean(0).repeat(K,1).float())
        def forward(s,h):
            return s.up(torch.nn.functional.gelu(s.down(s.ln(h)))).view(h.shape[0],K,s.dr)+s.anchor.unsqueeze(0)
    bridge=Bridge().to(dev); opt=torch.optim.AdamW(bridge.parameters(),lr=5e-4)
    sch=torch.optim.lr_scheduler.CosineAnnealingLR(opt,STEPS)
    @torch.no_grad()
    def svec(txts):
        out=[]
        for t in txts:
            ids=ts(qt(ts,t),return_tensors="pt").to(dev)
            out.append(ms(**ids,output_hidden_states=True).hidden_states[-1][0,-1,:])
        return torch.stack(out)
    print(f"device={dev} 训练桥 ({STEPS}步, {NTRAIN}样本)...",flush=True); t0=time.time()
    for step in range(STEPS):
        batch=[rng.choice(train) for _ in range(4)]
        pref=bridge(svec([b[0] for b in batch])); opt.zero_grad(); loss=0.0
        for i,(q,a) in enumerate(batch):
            enc=tr(qt(tr,q),return_tensors="pt"); qq=enc.input_ids[0]
            ans=tr(a+tr.eos_token,return_tensors="pt").input_ids[0]
            full=torch.cat([qq,ans]); lab=torch.cat([torch.full_like(qq,-100),ans]).to(dev)
            x=torch.cat([pref[i:i+1],emb(full.to(dev)).unsqueeze(0)],1)
            l=torch.cat([torch.full((K,),-100,device=dev,dtype=torch.long),lab]).unsqueeze(0)
            loss=loss+mr(inputs_embeds=x,attention_mask=torch.ones(x.shape[:2],device=dev),labels=l).loss
        (loss/4).backward(); torch.nn.utils.clip_grad_norm_(bridge.parameters(),1.0); opt.step(); sch.step()
        if step%50==0 or step==STEPS-1: print(f"  step {step} loss {loss.item()/4:.3f} ({time.time()-t0:.0f}s)",flush=True)

    @torch.no_grad()
    def gen(x,mx=12):
        o=[]
        for _ in range(mx):
            nid=mr(inputs_embeds=x).logits[0,-1].argmax(-1); o.append(int(nid))
            if nid.item()==mr.config.eos_token_id: break
            x=torch.cat([x,emb(nid.view(1,1))],1)
        return tr.decode(torch.tensor(o)) if o else ""

    T=[t[0] for t in test]; A=[t[1] for t in test]
    S=svec(T)                                    # (6,ds)
    P=bridge(S)                                  # (6,K,dr)
    # 状态多样性
    Sn=torch.nn.functional.normalize(S,dim=1); C=Sn@Sn.T
    off=C[~torch.eye(6,dtype=bool)]
    print(f"\n6样本 sender状态 题间余弦: 均值={off.mean():.4f} 最小={off.min():.4f} 最大={off.max():.4f}")
    Pn=torch.nn.functional.normalize(P.reshape(6,-1),dim=1); Cp=Pn@Pn.T
    offp=Cp[~torch.eye(6,dtype=bool)]
    print(f"6样本 桥输出prefix 题间余弦: 均值={offp.mean():.4f} 最小={offp.min():.4f}")
    print(f"\n{'族':<8}{'gold':<8}{'sender':<10}{'alone':<10}{'q+bridge':<10}{'shuffle':<10}")
    perm=[5,4,3,2,1,0]  # 错配: 反序映射
    ok_s=ok_a=ok_b=ok_h=0
    for i in range(6):
        ids=ts(qt(ts,T[i]),return_tensors="pt").to(dev)
        g=ms.generate(**ids,max_new_tokens=12,do_sample=False); o_s=ts.decode(g[0,ids.input_ids.shape[1]:],skip_special_tokens=True)
        enc=tr(qt(tr,T[i]),return_tensors="pt").to(dev)
        o_a=gen(emb(enc.input_ids))
        o_b=gen(torch.cat([P[i:i+1],emb(enc.input_ids)],1))
        o_h=gen(torch.cat([P[perm[i]:perm[i]+1],emb(enc.input_ids)],1))
        ok_s+=last_int(o_s)==A[i]; ok_a+=last_int(o_a)==A[i]; ok_b+=last_int(o_b)==A[i]; ok_h+=last_int(o_h)==A[i]
        print(f"F{i+1:<7}{A[i]:<8}{('✓' if last_int(o_s)==A[i] else '✗')+o_s[:6]:<10}"
              f"{('✓' if last_int(o_a)==A[i] else '✗')+o_a[:6]:<10}"
              f"{('✓' if last_int(o_b)==A[i] else '✗')+o_b[:6]:<10}"
              f"{('✓' if last_int(o_h)==A[i] else '✗')+o_h[:6]:<10}")
    print(f"\n合计 (n=6): sender {ok_s}/6 | alone {ok_a}/6 | q+bridge {ok_b}/6 | shuffle {ok_h}/6")
    json.dump({"sender":ok_s,"alone":ok_a,"q_bridge":ok_b,"shuffle":ok_h,
               "state_cos":round(float(off.mean()),4),"prefix_cos":round(float(offp.mean()),4)},
              open("v3_6.json","w"),ensure_ascii=False,indent=2)

if __name__=="__main__": main()
