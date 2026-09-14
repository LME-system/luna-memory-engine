#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 0 门槛测试 v2：找"对小模型真难、对大模型不难"的文字处理拐点。
任务：带干扰的长文属性提取（难度=干扰属性数）
修：主语名字一致
"""
import os, re, random
os.environ.setdefault("HF_HUB_OFFLINE","1"); os.environ.setdefault("TRANSFORMERS_OFFLINE","1")
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
dev = "mps" if torch.backends.mps.is_available() else "cpu"
MODELS = {"1.5B":"Qwen/Qwen2.5-1.5B-Instruct", "0.5B":"Qwen/Qwen2.5-0.5B-Instruct"}

ATTRS = [
    ("入职年份", "他于{y}年加入公司", lambda r: r.randint(1998,2020)),
    ("月薪",     "他的月薪是{y}元",   lambda r: r.randint(8000,40000)),
    ("年龄",     "他今年{y}岁",       lambda r: r.randint(25,58)),
    ("工位号",   "他的工位是{y}号",   lambda r: r.randint(100,999)),
    ("项目数",   "他负责过{y}个项目", lambda r: r.randint(2,40)),
    ("存款",     "他有{y}元存款",     lambda r: r.randint(10000,900000)),
]
FILLER = ["这家公司位于南方一座安静的沿海城市。","团队最近搬进了新的办公楼，采光很好。",
          "公司每年秋天都会组织一次团建活动。","食堂最近新增了几个档口，很受欢迎。",
          "附近新开了一家书店，午休时同事们常去。"]

def make(rng, n_extra_attr, n_filler=2):
    """n_extra_attr = 干扰属性句数 (0..5); 目标属性随机"""
    body = rng.choice(["李明","王芳","张伟","刘洋"])
    order = rng.sample(ATTRS, len(ATTRS))          # 6 个属性打乱
    target = order[0]
    words = {name: gen(rng) for name,tmpl,gen in ATTRS}
    vals = {name: words[name] for name,_,_ in ATTRS}
    sents = []
    # 目标句 + n_extra_attr 个干扰属性句
    sents.append(target[1].format(y=vals[target[0]]))
    for name, tmpl, _ in order[1:1+n_extra_attr]:
        sents.append(tmpl.format(y=vals[name]))
    sents += [rng.choice(FILLER) for _ in range(n_filler)]
    rng.shuffle(sents)
    passage = f"{body}是一名软件工程师。" + "".join(sents)
    q = f"阅读下面这段话，只回答一个数字：{body}的{target[0]}是多少？\n\n{passage}"
    return {"q": q, "a": str(vals[target[0]]), "nattr": n_extra_attr}

def last_int(s):
    m = re.findall(r"-?\d+", s.replace(",", ""))
    return m[-1] if m else None

def main():
    tok={};mod={}
    for k,n in MODELS.items():
        tok[k]=AutoTokenizer.from_pretrained(n);mod[k]=AutoModelForCausalLM.from_pretrained(n,dtype=torch.float32).to(dev).eval()
    def ask(k,q,nmax=10):
        t=tok[k];m=mod[k]
        ids=t(t.apply_chat_template([{"role":"user","content":q}],tokenize=False,add_generation_prompt=True),return_tensors="pt").to(dev)
        g=m.generate(**ids,max_new_tokens=nmax,do_sample=False)
        return t.decode(g[0,ids.input_ids.shape[1]:],skip_special_tokens=True)
    rng=random.Random(2026)
    print(f"device={dev}  | 任务: 带干扰长文属性提取")
    print(f"{'干扰属性数':<10}{'1.5B':<8}{'0.5B':<8}{'gap':<8}")
    for na in [0,1,2,3,4,5]:
        items=[make(rng,na) for _ in range(24)]
        acc={k:0 for k in MODELS}
        for it in items:
            for k in MODELS:
                acc[k]+= (last_int(ask(k,it["q"]))==it["a"])
        print(f"{na:<11}{acc['1.5B']/24:<9.2f}{acc['0.5B']/24:<9.2f}{(acc['1.5B']-acc['0.5B'])/24:+.2f}")
    it=make(rng,3)
    print("\n示例 gold=",it["a"],"\n 1.5B:",repr(ask("1.5B",it["q"])),"\n 0.5B:",repr(ask("0.5B",it["q"])))

if __name__=="__main__": main()
