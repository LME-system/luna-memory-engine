import os,random
os.environ.setdefault("HF_HUB_OFFLINE","1");os.environ.setdefault("TRANSFORMERS_OFFLINE","1")
import torch
from transformers import AutoTokenizer,AutoModelForCausalLM
dev="mps"
ATTRS=[("入职年份","他于{y}年加入公司",lambda r:r.randint(1998,2020)),("月薪","他的月薪是{y}元",lambda r:r.randint(8000,40000)),
       ("年龄","他今年{y}岁",lambda r:r.randint(25,58)),("工位号","他的工位是{y}号",lambda r:r.randint(100,999)),
       ("项目数","他负责过{y}个项目",lambda r:r.randint(2,40)),("存款","他有{y}元存款",lambda r:r.randint(10000,900000))]
FILL=["这家公司位于南方一座安静的沿海城市。","团队最近搬进了新的办公楼，采光很好。","公司每年秋天都会组织一次团建活动。"]
def make(rng,na=4):
    body=rng.choice(["李明","王芳","张伟","刘洋"]);o=rng.sample(ATTRS,6);t=o[0]
    v={n:g(rng) for n,tm,g in ATTRS}
    s=[t[1].format(y=v[t[0]])]+[tm.format(y=v[n]) for n,tm,_ in o[1:1+na]]+[rng.choice(FILL) for _ in range(2)]
    rng.shuffle(s);p=f"{body}是一名软件工程师。"+"".join(s)
    return {"q":f"阅读下面这段话，只回答一个数字：{body}的{t[0]}是多少？\n\n{p}","a":str(v[t[0]])}
ts=AutoTokenizer.from_pretrained("Qwen/Qwen2.5-1.5B-Instruct")
ms=AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-1.5B-Instruct",dtype=torch.float32).to(dev).eval()
sd=torch.load("/Users/miaoliwang/.openclaw/workspace/mostik_bridge/bridge_v2.pt",map_location=dev)
class Bridge(torch.nn.Module):
    def __init__(s,k=16,ds=1536,dr=896,rank=128):
        super().__init__();s.k=k;s.dr=dr;s.ln=torch.nn.LayerNorm(ds)
        s.down=torch.nn.Linear(ds,rank);s.up=torch.nn.Linear(rank,k*dr)
        s.anchor=torch.nn.Parameter(torch.zeros(k,dr))
    def forward(s,h):
        z=s.up(torch.nn.functional.gelu(s.down(s.ln(h)))).view(h.shape[0],s.k,s.dr)
        return z+s.anchor.unsqueeze(0)
b=Bridge().to(dev);b.load_state_dict(sd);b.eval()
def qt(it): return ts.apply_chat_template([{"role":"user","content":it["q"]}],tokenize=False,add_generation_prompt=True)
rng=random.Random(0);items=[make(rng) for _ in range(40)]
with torch.no_grad():
    Hs=[]
    for it in items:
        ids=ts(qt(it),return_tensors="pt").to(dev)
        Hs.append(ms(**ids,output_hidden_states=True).hidden_states[-1][0,-1,:])
    H=torch.stack(Hs); P=b(H).reshape(40,-1)
def cos(X,name):
    Xn=torch.nn.functional.normalize(X,dim=1);S=Xn@Xn.T;n=len(X)
    off=S[~torch.eye(n,dtype=bool)]
    print(f"{name:20s} 题间余弦 均值={off.mean():.4f} 最小={off.min():.4f}")
cos(H,"sender状态(输入)")
cos(P,"桥输出prefix")
# 桥输出对输入变化的敏感度: 用同题 vs 错配题, 输出差多少
import itertools
d_same=[];d_shuf=[]
for i in range(40):
    j=(i+7)%40
    d_same.append((P[i]-P[i]).norm())
    d_shuf.append((P[i]-P[j]).norm())
print(f"桥输出||P_i-P_j(错配)|| 均值={torch.stack(d_shuf).mean():.4f} | ||P_i|| 均值={P.norm(dim=1).mean():.4f}")
print(f"→ 错配造成的输出变化占自身模长的比例: {torch.stack(d_shuf).mean()/P.norm(dim=1).mean():.4f}")
