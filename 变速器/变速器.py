#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mostik「桥」复现 v2 — 修正测试设计
任务: 带干扰的长文属性提取 (对小模型真难, 对大模型不难)
消融: alone / 题+桥 / 桥only(因果铁证)
桥  : gemma版 (LayerNorm→低秩MLP→gate) + 尺度归一(治生成失配)
"""
import os, re, random, json, time, argparse
os.environ.setdefault("HF_HUB_OFFLINE","1"); os.environ.setdefault("TRANSFORMERS_OFFLINE","1")
import torch

def parse():
    p=argparse.ArgumentParser()
    p.add_argument("--sender",default="Qwen/Qwen2.5-1.5B-Instruct")
    p.add_argument("--receiver",default="Qwen/Qwen2.5-0.5B-Instruct")
    p.add_argument("--n_attr",type=int,default=4)     # 干扰属性数 (=难度)
    p.add_argument("--n_train",type=int,default=1500)
    p.add_argument("--n_test",type=int,default=120)
    p.add_argument("--steps",type=int,default=400)
    p.add_argument("--bs",type=int,default=4)
    p.add_argument("--k",type=int,default=8)
    p.add_argument("--rank",type=int,default=128)
    p.add_argument("--quick",action="store_true")
    p.add_argument("--out",default="v2.json")
    a=p.parse_args()
    if a.quick: a.n_train,a.n_test,a.steps=200,30,60
    return a

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
    return {"q":q,"a":str(vals[target[0]]),"body":body}

def last_int(s):
    m=re.findall(r"-?\d+",s.replace(",",""))
    return m[-1] if m else None

def main():
    a=parse()
    from transformers import AutoTokenizer,AutoModelForCausalLM
    torch.manual_seed(0);random.seed(0)
    dev="mps" if torch.backends.mps.is_available() else "cpu"
    rng=random.Random(0)
    print(f"device={dev} 难度(干扰属性)={a.n_attr}",flush=True)
    ts=AutoTokenizer.from_pretrained(a.sender);tr=AutoTokenizer.from_pretrained(a.receiver)
    ms=AutoModelForCausalLM.from_pretrained(a.sender,dtype=torch.float32).to(dev).eval()
    mr=AutoModelForCausalLM.from_pretrained(a.receiver,dtype=torch.float32).to(dev).eval()
    for p in ms.parameters(): p.requires_grad_(False)
    for p in mr.parameters(): p.requires_grad_(False)
    ds,dr=ms.config.hidden_size,mr.config.hidden_size
    emb_r=mr.get_input_embeddings()
    emb_std=float(emb_r.weight.detach().float().std())
    print(f"d_s={ds} d_r={dr} emb_std={emb_std:.4f}",flush=True)

    data=[make(rng,a.n_attr) for _ in range(a.n_train+a.n_test)]
    train,test=data[:a.n_train],data[-a.n_test:]

    def qtext(tok,it): return tok.apply_chat_template([{"role":"user","content":it["q"]}],tokenize=False,add_generation_prompt=True)

    # ---- gemma 版桥: LN -> 低秩 MLP -> gate; 输出归一化到 embedding 尺度
    class Bridge(torch.nn.Module):
        def __init__(s,ds,dr,k,rank):
            super().__init__(); s.k,s.dr=k,dr
            s.ln=torch.nn.LayerNorm(ds)
            s.down=torch.nn.Linear(ds,rank); s.up=torch.nn.Linear(rank,k*dr)
            # 锚点: receiver embedding 均值 (soft-prompt 常规)
            s.anchor=torch.nn.Parameter(emb_r.weight.detach().mean(0).repeat(k,1).float())
            s.emb_std=emb_std
        def forward(s,h):
            z=s.up(torch.nn.functional.gelu(s.down(s.ln(h)))).view(h.shape[0],s.k,s.dr)
            return z + s.anchor.unsqueeze(0)             # 标准 soft-prompt
    bridge=Bridge(ds,dr,a.k,a.rank).to(dev)
    opt=torch.optim.AdamW(bridge.parameters(),lr=5e-4,weight_decay=0.0)
    sch=torch.optim.lr_scheduler.CosineAnnealingLR(opt,a.steps)

    @torch.no_grad()
    def svec(items):
        out=[]
        for it in items:
            ids=ts(qtext(ts,it),return_tensors="pt").to(dev)
            o=ms(**ids,output_hidden_states=True)
            out.append(o.hidden_states[-1][0,-1,:])
        return torch.stack(out)

    print("训练桥...",flush=True); t0=time.time()
    for step in range(a.steps):
        batch=[rng.choice(train) for _ in range(a.bs)]
        h=svec(batch); pref=bridge(h)
        opt.zero_grad(); loss=0.0
        for i in range(len(batch)):
            it=batch[i]
            enc=tr(qtext(tr,it),return_tensors="pt")
            q=enc.input_ids[0]
            ans=tr(it["a"]+tr.eos_token,return_tensors="pt").input_ids[0]
            full=torch.cat([q,ans]); lab=torch.cat([torch.full_like(q,-100),ans]).to(dev)
            qe=emb_r(full.to(dev)).unsqueeze(0)
            x=torch.cat([pref[i:i+1],qe],1)
            l=torch.cat([torch.full((a.k,),-100,device=dev,dtype=torch.long),lab]).unsqueeze(0)
            am=torch.ones(x.shape[:2],device=dev)
            loss=loss+mr(inputs_embeds=x,attention_mask=am,labels=l).loss
        (loss/len(batch)).backward()
        torch.nn.utils.clip_grad_norm_(bridge.parameters(),1.0)
        opt.step(); sch.step()
        if step%50==0 or step==a.steps-1:
            print(f"  step {step} loss {loss.item()/len(batch):.3f} ({time.time()-t0:.0f}s)",flush=True)
    torch.save(bridge.state_dict(),"bridge_v2.pt")

    # ---- 手写贪心生成 (绕开 generate(inputs_embeds=...) 返回空的 bug)
    @torch.no_grad()
    def gen_embeds(x, max_new=10):
        out=[]
        for _ in range(max_new):
            o=mr(inputs_embeds=x)
            nid=o.logits[0,-1].argmax(-1)
            out.append(int(nid))
            if nid.item()==mr.config.eos_token_id: break
            x=torch.cat([x,emb_r(nid.view(1,1))],1)
        return tr.decode(torch.tensor(out)) if out else ""

    # ---- 评估
    @torch.no_grad()
    def acc_alone(items):
        ok=0
        for it in items:
            ids=tr(qtext(tr,it),return_tensors="pt").to(dev)
            g=mr.generate(**ids,max_new_tokens=10,do_sample=False)
            ok+= last_int(tr.decode(g[0,ids.input_ids.shape[1]:],skip_special_tokens=True))==it["a"]
        return ok/len(items)
    @torch.no_grad()
    def acc_q_bridge(items):
        ok=0
        for it in items:
            pref=bridge(svec([it]))
            enc=tr(qtext(tr,it),return_tensors="pt").to(dev)
            x=torch.cat([pref,emb_r(enc.input_ids)],1)
            ok+= last_int(gen_embeds(x))==it["a"]
        return ok/len(items)
    @torch.no_grad()
    def acc_bridge_only(items):
        """因果铁证: 只给桥前缀, 不给题目"""
        ok=0
        for it in items:
            pref=bridge(svec([it]))
            ok+= last_int(gen_embeds(pref))==it["a"]
        return ok/len(items)
    @torch.no_grad()
    def acc_sender(items):
        ok=0
        for it in items:
            ids=ts(qtext(ts,it),return_tensors="pt").to(dev)
            g=ms.generate(**ids,max_new_tokens=10,do_sample=False)
            ok+= last_int(ts.decode(g[0,ids.input_ids.shape[1]:],skip_special_tokens=True))==it["a"]
        return ok/len(items)

    print("评估...",flush=True)
    res={"sender(上限)":acc_sender(test),"receiver_alone":acc_alone(test),
         "q+bridge":acc_q_bridge(test),"bridge_only(铁证)":acc_bridge_only(test)}
    d=res["receiver_alone"]; up=res["sender(上限)"]
    out={"config":vars(a),"results":res,"gap":up-d,
         "gap_closed_q_bridge":round((res["q+bridge"]-d)/(up-d),3) if up>d else None,
         "gap_closed_bridge_only":round((res["bridge_only(铁证)"]-d)/(up-d),3) if up>d else None}
    json.dump(out,open(a.out,"w"),ensure_ascii=False,indent=2)
    print("\n===== 结果 =====")
    for k,v in res.items(): print(f"  {k:22s}: {v:.3f}")
    print(f"  gap={out['gap']:+.3f} | gap_closed(q+bridge)={out['gap_closed_q_bridge']} | gap_closed(bridge_only)={out['gap_closed_bridge_only']}")
    print("→",a.out)

if __name__=="__main__": main()
