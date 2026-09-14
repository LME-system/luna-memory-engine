#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""变速器 对照实验：随机前缀基线 + 答案数值留出
对照:
  q+bridge        : 训练好的变速器 + 正确 sender 状态 (主结果)
  q+bridge_shuffle: 错配 sender 状态 (用别的题的隐藏状态) → 必须是"这道题"的状态才有效
  q+random        : 随机噪声前缀 (同形状/同量级)
  q+zero          : 零前缀
  alone           : 不给前缀
  sender          : 大模型上限
留出: test 的答案数值在 train 中未出现 (排除记忆)
"""
import os, re, random, json, time, argparse
os.environ.setdefault("HF_HUB_OFFLINE","1"); os.environ.setdefault("TRANSFORMERS_OFFLINE","1")
import torch

def parse():
    p=argparse.ArgumentParser()
    p.add_argument("--sender",default="Qwen/Qwen2.5-1.5B-Instruct")
    p.add_argument("--receiver",default="Qwen/Qwen2.5-0.5B-Instruct")
    p.add_argument("--n_attr",type=int,default=4)
    p.add_argument("--n_train",type=int,default=1200)
    p.add_argument("--n_test",type=int,default=40)
    p.add_argument("--steps",type=int,default=300)
    p.add_argument("--bs",type=int,default=4)
    p.add_argument("--k",type=int,default=16)
    p.add_argument("--rank",type=int,default=128)
    p.add_argument("--out",default="control.json")
    return p.parse_args()

ATTRS=[("入职年份","他于{y}年加入公司",lambda r:r.randint(1998,2020)),
       ("月薪","他的月薪是{y}元",lambda r:r.randint(8000,40000)),
       ("年龄","他今年{y}岁",lambda r:r.randint(25,58)),
       ("工位号","他的工位是{y}号",lambda r:r.randint(100,999)),
       ("项目数","他负责过{y}个项目",lambda r:r.randint(2,40)),
       ("存款","他有{y}元存款",lambda r:r.randint(10000,900000))]
FILLER=["这家公司位于南方一座安静的沿海城市。","团队最近搬进了新的办公楼，采光很好。",
        "公司每年秋天都会组织一次团建活动。","食堂最近新增了几个档口，很受欢迎。",
        "附近新开了一家书店，午休时同事们常去。"]

def make(rng,n_attr,n_filler=2):
    body=rng.choice(["李明","王芳","张伟","刘洋"])
    order=rng.sample(ATTRS,len(ATTRS)); target=order[0]
    vals={name:gen(rng) for name,tmpl,gen in ATTRS}
    sents=[target[1].format(y=vals[target[0]])]
    for name,tmpl,_ in order[1:1+n_attr]: sents.append(tmpl.format(y=vals[name]))
    sents+=[rng.choice(FILLER) for _ in range(n_filler)]
    rng.shuffle(sents)
    passage=f"{body}是一名软件工程师。"+"".join(sents)
    q=f"阅读下面这段话，只回答一个数字：{body}的{target[0]}是多少？\n\n{passage}"
    return {"q":q,"a":str(vals[target[0]])}

def last_int(s):
    m=re.findall(r"-?\d+",s.replace(",",""))
    return m[-1] if m else None

def main():
    a=parse()
    from transformers import AutoTokenizer,AutoModelForCausalLM
    torch.manual_seed(0); random.seed(0)
    dev="mps" if torch.backends.mps.is_available() else "cpu"
    rng=random.Random(0)
    print(f"device={dev} 难度={a.n_attr} 留出=答案数值",flush=True)
    ts=AutoTokenizer.from_pretrained(a.sender); tr=AutoTokenizer.from_pretrained(a.receiver)
    ms=AutoModelForCausalLM.from_pretrained(a.sender,dtype=torch.float32).to(dev).eval()
    mr=AutoModelForCausalLM.from_pretrained(a.receiver,dtype=torch.float32).to(dev).eval()
    for p in ms.parameters(): p.requires_grad_(False)
    for p in mr.parameters(): p.requires_grad_(False)
    ds,dr=ms.config.hidden_size,mr.config.hidden_size
    emb_r=mr.get_input_embeddings()

    train=[make(rng,a.n_attr) for _ in range(a.n_train)]
    train_vals={it["a"] for it in train}
    test=[]
    tries=0
    while len(test)<a.n_test and tries<200000:
        tries+=1; it=make(rng,a.n_attr)
        if it["a"] not in train_vals: test.append(it)   # 答案数值留出
    overlap=sum(1 for it in test if it["a"] in train_vals)
    print(f"train={len(train)} test={len(test)} 答案重叠={overlap}",flush=True)

    def qtext(tok,it): return tok.apply_chat_template([{"role":"user","content":it["q"]}],tokenize=False,add_generation_prompt=True)

    class Bridge(torch.nn.Module):
        def __init__(s):
            super().__init__(); s.k=a.k; s.dr=dr
            s.ln=torch.nn.LayerNorm(ds); s.down=torch.nn.Linear(ds,a.rank); s.up=torch.nn.Linear(a.rank,a.k*dr)
            s.anchor=torch.nn.Parameter(emb_r.weight.detach().mean(0).repeat(a.k,1).float())
        def forward(s,h):
            z=s.up(torch.nn.functional.gelu(s.down(s.ln(h)))).view(h.shape[0],s.k,s.dr)
            return z+s.anchor.unsqueeze(0)
    bridge=Bridge().to(dev)
    opt=torch.optim.AdamW(bridge.parameters(),lr=5e-4)
    sch=torch.optim.lr_scheduler.CosineAnnealingLR(opt,a.steps)

    @torch.no_grad()
    def svec(items):
        out=[]
        for it in items:
            ids=ts(qtext(ts,it),return_tensors="pt").to(dev)
            out.append(ms(**ids,output_hidden_states=True).hidden_states[-1][0,-1,:])
        return torch.stack(out)

    print("训练...",flush=True); t0=time.time()
    for step in range(a.steps):
        batch=[rng.choice(train) for _ in range(a.bs)]
        pref=bridge(svec(batch)); opt.zero_grad(); loss=0.0
        for i,it in enumerate(batch):
            enc=tr(qtext(tr,it),return_tensors="pt"); q=enc.input_ids[0]
            ans=tr(it["a"]+tr.eos_token,return_tensors="pt").input_ids[0]
            full=torch.cat([q,ans]); lab=torch.cat([torch.full_like(q,-100),ans]).to(dev)
            x=torch.cat([pref[i:i+1],emb_r(full.to(dev)).unsqueeze(0)],1)
            l=torch.cat([torch.full((a.k,),-100,device=dev,dtype=torch.long),lab]).unsqueeze(0)
            am=torch.ones(x.shape[:2],device=dev)
            loss=loss+mr(inputs_embeds=x,attention_mask=am,labels=l).loss
        (loss/len(batch)).backward(); torch.nn.utils.clip_grad_norm_(bridge.parameters(),1.0)
        opt.step(); sch.step()
        if step%50==0 or step==a.steps-1: print(f"  step {step} loss {loss.item()/len(batch):.3f} ({time.time()-t0:.0f}s)",flush=True)

    @torch.no_grad()
    def gen_embeds(x,max_new=10):
        out=[]
        for _ in range(max_new):
            nid=mr(inputs_embeds=x).logits[0,-1].argmax(-1); out.append(int(nid))
            if nid.item()==mr.config.eos_token_id: break
            x=torch.cat([x,emb_r(nid.view(1,1))],1)
        return tr.decode(torch.tensor(out)) if out else ""

    Sall=svec(test)                       # 预先算好全部 sender 状态
    perm=list(range(len(test))); random.Random(1).shuffle(perm)
    def prefix_for(it_i, mode):
        if mode=="bridge":  return bridge(Sall[it_i:it_i+1])
        if mode=="shuffle": return bridge(Sall[perm[it_i]:perm[it_i]+1])   # 错配
        if mode=="random":  return torch.randn(1,a.k,dr,device=dev)*float(Sall.std())
        if mode=="zero":    return torch.zeros(1,a.k,dr,device=dev)
    def eval_mode(mode, with_q=True):
        ok=0
        for i,it in enumerate(test):
            enc=tr(qtext(tr,it),return_tensors="pt").to(dev)
            x=torch.cat([prefix_for(i,mode),emb_r(enc.input_ids)],1) if mode!="alone" else emb_r(enc.input_ids)
            ok+= last_int(gen_embeds(x))==it["a"]
        return ok/len(test)
    @torch.no_grad()
    def acc_sender():
        ok=0
        for it in test:
            ids=ts(qtext(ts,it),return_tensors="pt").to(dev)
            g=ms.generate(**ids,max_new_tokens=10,do_sample=False)
            ok+= last_int(ts.decode(g[0,ids.input_ids.shape[1]:],skip_special_tokens=True))==it["a"]
        return ok/len(test)

    print("评估...",flush=True)
    res={"sender(上限)":acc_sender(),"alone":eval_mode("alone"),
         "q+bridge":eval_mode("bridge"),"q+bridge_shuffle(错配)":eval_mode("shuffle"),
         "q+random":eval_mode("random"),"q+zero":eval_mode("zero")}
    json.dump(res,open(a.out,"w"),ensure_ascii=False,indent=2)
    print("\n===== 结果 =====")
    for k,v in res.items(): print(f"  {k:26s}: {v:.3f}")
    print("→",a.out)

if __name__=="__main__": main()
