#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mostik「桥」复现 (纯代码) — 按我们的理论框架设计
================================================
核心机制（对齐 Mostik 报道）:
  - sender(大) 只"读题"，产出隐藏状态, 不吐任何文字
  - 训练一座小桥(bridge) 把 sender 的隐藏状态映射成 receiver(小) 的 soft-prefix
  - receiver 负责全部生成; 两个模型参数完全冻结, 只有 bridge 训练
  - 对比: receiver 单独 / 文字接力 / 隐藏状态接力

按我们理论加的"可测量"部分:
  - L2几何层: 测 sender<->receiver 表征空间对齐 (线性 CKA + Procrustes R²) → 验证"存在可预测对齐基础"
  - 最优单位: 扫描 sender 取哪一层、receiver 注入哪一层 → 找 alignment 最优的"尺度"
  - 桥形态: 线性(低秩, ~Procrustes) vs MLP → 验证"共形/线性 vs 非线性"

用法:
  python3 mostik_bridge_repro.py --quick          # 冒烟测试
  python3 mostik_bridge_repro.py --steps 800      # 正式
"""
import os, sys, json, math, time, argparse, random
import numpy as np

def parse():
    p = argparse.ArgumentParser()
    p.add_argument("--sender", default="Qwen/Qwen2.5-1.5B-Instruct")
    p.add_argument("--receiver", default="Qwen/Qwen2.5-0.5B-Instruct")
    p.add_argument("--quick", action="store_true")
    p.add_argument("--n_train", type=int, default=1500)
    p.add_argument("--n_val", type=int, default=200)
    p.add_argument("--n_test", type=int, default=400)
    p.add_argument("--steps", type=int, default=900)
    p.add_argument("--bs", type=int, default=8)
    p.add_argument("--prefix_len", type=int, default=8)     # 桥产出多少个 soft 前缀
    p.add_argument("--send_layer", type=int, default=-1)     # sender 取哪层隐藏 (-1=最后)
    p.add_argument("--bridge", default="mlp", choices=["linear","mlp"])
    p.add_argument("--max_new", type=int, default=24)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", default="repro_result.json")
    a = p.parse_args()
    if a.quick:
        a.n_train, a.n_val, a.n_test, a.steps = 300, 40, 60, 120
    return a

# ---------------------------------------------------------------- 任务数据
def gen_data(n, rng):
    """两位/三位数加减 + 部分三目运算, 答案整数。sender易、receiver难，制造 gap。"""
    data = []
    for _ in range(n):
        k = rng.choice([2,2,2,3])
        if k == 2:
            a = rng.randint(11, 99); b = rng.randint(11, 99)
            op = rng.choice(["+", "-"])
            expr = f"{a} {op} {b}"
            ans = a + b if op == "+" else a - b
        else:
            a = rng.randint(11, 99); b = rng.randint(11, 99); c = rng.randint(11, 99)
            op1, op2 = rng.choice(["+","-"]), rng.choice(["+","-"])
            expr = f"{a} {op1} {b} {op2} {c}"
            v = a + b if op1 == "+" else a - b
            ans = v + c if op2 == "+" else v - c
        data.append({"q": f"计算: {expr} = ?", "a": str(ans)})
    return data

# ---------------------------------------------------------------- 工具
def pick_device():
    import torch
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")

def last_int(s):
    import re
    # 模型常复述题目("34 + 57 = 91")，答案在最后 → 取最后一个整数
    m = re.findall(r"-?\d+", s.replace(",", ""))
    return m[-1] if m else None

def exact_match(pred_text, gold):
    return last_int(pred_text) == gold

# ---------------------------------------------------------------- 主流程
def main():
    args = parse()
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    torch.manual_seed(args.seed); np.random.seed(args.seed); random.seed(args.seed)
    rng = random.Random(args.seed)
    dev = pick_device()
    print(f"device={dev} sender={args.sender} receiver={args.receiver}", flush=True)

    tok_s = AutoTokenizer.from_pretrained(args.sender)
    tok_r = AutoTokenizer.from_pretrained(args.receiver)
    model_s = AutoModelForCausalLM.from_pretrained(args.sender, torch_dtype=torch.float32).to(dev).eval()
    model_r = AutoModelForCausalLM.from_pretrained(args.receiver, torch_dtype=torch.float32).to(dev).eval()
    for p in model_s.parameters(): p.requires_grad_(False)
    for p in model_r.parameters(): p.requires_grad_(False)
    d_s = model_s.config.hidden_size
    d_r = model_r.config.hidden_size
    nL_s = model_s.config.num_hidden_layers
    nL_r = model_r.config.num_hidden_layers
    print(f"d_s={d_s} nL_s={nL_s} | d_r={d_r} nL_r={nL_r}", flush=True)

    data = gen_data(args.n_train + args.n_val + args.n_test, rng)
    train, val, test = data[:args.n_train], data[args.n_train:args.n_train+args.n_val], data[-args.n_test:]

    # ---- prompt 构造 (chat 模板)
    def prompt_text(tok, item, hint=None):
        u = item["q"] if hint is None else f"{item['q']}\n(参考: {hint})"
        return tok.apply_chat_template([{"role":"user","content":u}], tokenize=False, add_generation_prompt=True)

    # ============================================================ L2 几何: 对齐测量
    def collect_states(items, n=120):
        hs_s, hs_r = [], []
        with torch.no_grad():
            for it in items[:n]:
                ids = tok_s(prompt_text(tok_s, it), return_tensors="pt").to(dev)
                o = model_s(**ids, output_hidden_states=True)
                hs_s.append(torch.stack([h[0,-1,:] for h in o.hidden_states]).float().cpu())
                ids = tok_r(prompt_text(tok_r, it), return_tensors="pt").to(dev)
                o = model_r(**ids, output_hidden_states=True)
                hs_r.append(torch.stack([h[0,-1,:] for h in o.hidden_states]).float().cpu())
        return torch.stack(hs_s), torch.stack(hs_r)   # (n, L, d)
    n_geo = min(len(train), 600)   # 样本数须远大于维度, 否则 Procrustes R² 会虚高到 1.0
    print(f"测量表征空间几何对齐 (CKA + Procrustes, n={n_geo})...", flush=True)
    S, R = collect_states(train, n=n_geo)
    Sx = S - S.mean(0, keepdim=True); Rx = R - R.mean(0, keepdim=True)

    def cka(A, B):
        A = A - A.mean(0, keepdim=True); B = B - B.mean(0, keepdim=True)
        num = (A.T @ B).pow(2).sum()
        den = (A.T @ A).pow(2).sum() * (B.T @ B).pow(2).sum()
        return float(num / (den.sqrt() + 1e-12))

    def procrustes_r2(A, B, k=64):
        # 先 PCA 降到 k 维, 再拟合线性映射的 R^2 (避免 n<d 时过拟合虚高)
        k = min(k, A.shape[0]-1, A.shape[1], B.shape[1])
        def pca(X):
            Xc = X - X.mean(0, keepdim=True)
            U, S, V = torch.linalg.svd(Xc, full_matrices=False)
            return Xc @ V[:k].T, V[:k]
        A2, Va = pca(A); B2, _ = pca(B)
        A1 = torch.cat([A2, torch.ones(A2.shape[0],1)], 1)
        W = torch.linalg.lstsq(A1, B2).solution
        pred = A1 @ W
        ss_res = ((B2 - pred)**2).sum()
        ss_tot = ((B2 - B2.mean(0,keepdim=True))**2).sum()
        return float(1 - ss_res/(ss_tot+1e-12))

    align = {"cka": {}, "procrustes_r2": {}, "best": None}
    best = (-1, None)
    for ls in range(0, nL_s+1, max(1, nL_s//6)):
        for lr in range(0, nL_r+1, max(1, nL_r//6)):
            c = cka(Sx[:, ls, :], Rx[:, lr, :])
            align["cka"][f"{ls}->{lr}"] = round(c, 4)
            if c > best[0]: best = (c, (ls, lr))
    align["best"] = {"cka": round(best[0],4), "layers": best[1]}
    # Procrustes: 用 sender 最后层 -> receiver 最后层 (作为"既有对齐基础"基线)
    align["procrustes_r2"]["last->last"] = round(procrustes_r2(Sx[:,-1,:], Rx[:,-1,:]), 4)
    align["procrustes_r2"]["best_cka"] = round(procrustes_r2(Sx[:,best[1][0],:], Rx[:,best[1][1],:]), 4)
    print("  best CKA:", align["best"], "| Procrustes(last->last) R2:", align["procrustes_r2"]["last->last"], flush=True)

    # ============================================================ 桥
    class Bridge(torch.nn.Module):
        def __init__(self, kind, d_s, d_r, k, layers):
            super().__init__()
            self.k, self.d_r, self.layers = k, d_r, layers
            self.norm = torch.nn.LayerNorm(d_s)
            if kind == "linear":
                self.proj = torch.nn.Linear(d_s, k*d_r)
            else:
                self.proj = torch.nn.Sequential(
                    torch.nn.Linear(d_s, 512), torch.nn.GELU(),
                    torch.nn.Linear(512, 512), torch.nn.GELU(),
                    torch.nn.Linear(512, k*d_r))
            # 锚点: 用 receiver 的 embedding 统计初始化 (soft prompt 常规做法)
            emb = model_r.get_input_embeddings().weight.detach()
            self.anchor = torch.nn.Parameter(emb.mean(0).repeat(k,1).float(), requires_grad=True)
        def forward(self, h):          # h: (B, d_s)
            z = self.proj(self.norm(h)).view(h.shape[0], self.k, self.d_r)
            return z + self.anchor.unsqueeze(0)

    bridge = Bridge(args.bridge, d_s, d_r, args.prefix_len, None).to(dev)
    opt = torch.optim.AdamW(bridge.parameters(), lr=3e-4, weight_decay=0.0)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, args.steps)

    @torch.no_grad()
    def sender_vec(items):
        """sender 读题 → 隐藏向量 (B, d_s); 取指定层最后一 token"""
        out = []
        for it in items:
            ids = tok_s(prompt_text(tok_s, it), return_tensors="pt").to(dev)
            o = model_s(**ids, output_hidden_states=True)
            out.append(o.hidden_states[args.send_layer][0,-1,:])
        return torch.stack(out)   # (B, d_s)

    def build_batch(items, with_prefix=True):
        h = sender_vec(items)
        return h

    # ---- 训练
    print(f"训练桥 (kind={args.bridge}, steps={args.steps}, bs={args.bs})...", flush=True)
    t0 = time.time()
    for step in range(args.steps):
        batch = [rng.choice(train) for _ in range(args.bs)]
        hs = sender_vec(batch)                           # (B,d_s) no_grad
        pref = bridge(hs)                                # (B,k,d_r) grad
        # receiver 侧: [prefix | question+assistant]
        idss, masks, labs = [], [], []
        for it in batch:
            txt = prompt_text(tok_r, it)
            enc = tok_r(txt, return_tensors="pt")
            ans = tok_r(it["a"] + tok_r.eos_token, return_tensors="pt")
            q = enc.input_ids[0]; a = ans.input_ids[0]
            full = torch.cat([q, a])
            lab = torch.cat([torch.full_like(q, -100), a])
            idss.append(full); labs.append(lab)
        Lmax = max(t.shape[0] for t in idss) + args.prefix_len
        inp, att, lb = [], [], []
        emb_r = model_r.get_input_embeddings()
        loss = 0.0
        opt.zero_grad()
        # 逐样本 (简化, 避免 pad 复杂度)
        for i in range(len(batch)):
            ids = idss[i].to(dev); lab = labs[i].to(dev)
            qe = emb_r(ids).unsqueeze(0)                 # (1,T,d_r)
            x = torch.cat([pref[i:i+1], qe], dim=1)      # (1,k+T,d_r)
            l = torch.cat([torch.full((args.prefix_len,), -100, device=dev, dtype=torch.long), lab])
            am = torch.ones(x.shape[:2], device=dev)
            o = model_r(inputs_embeds=x, attention_mask=am, labels=l.unsqueeze(0))
            loss = loss + o.loss
        loss = loss / len(batch)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(bridge.parameters(), 1.0)
        opt.step(); sched.step()
        if step % 50 == 0 or step == args.steps-1:
            print(f"  step {step:4d} loss {loss.item():.4f} ({(time.time()-t0):.0f}s)", flush=True)
    print(f"训练完成 {time.time()-t0:.0f}s", flush=True)
    torch.save(bridge.state_dict(), "bridge.pt")

    # ---- 评估
    @torch.no_grad()
    def eval_receiver_alone(items):
        ok = 0
        for it in items:
            ids = tok_r(prompt_text(tok_r, it), return_tensors="pt").to(dev)
            g = model_r.generate(**ids, max_new_tokens=args.max_new, do_sample=False)
            txt = tok_r.decode(g[0, ids.input_ids.shape[1]:], skip_special_tokens=True)
            ok += exact_match(txt, it["a"])
        return ok / len(items)

    @torch.no_grad()
    def eval_text_relay(items):
        ok = 0
        for it in items:
            ids = tok_s(prompt_text(tok_s, it), return_tensors="pt").to(dev)
            g = model_s.generate(**ids, max_new_tokens=args.max_new, do_sample=False)
            hint = tok_s.decode(g[0, ids.input_ids.shape[1]:], skip_special_tokens=True)
            ids = tok_r(prompt_text(tok_r, it, hint=hint), return_tensors="pt").to(dev)
            g = model_r.generate(**ids, max_new_tokens=args.max_new, do_sample=False)
            txt = tok_r.decode(g[0, ids.input_ids.shape[1]:], skip_special_tokens=True)
            ok += exact_match(txt, it["a"])
        return ok / len(items)

    @torch.no_grad()
    def eval_hidden_relay(items):
        ok = 0
        for it in items:
            hs = sender_vec([it])
            pref = bridge(hs)                            # (1,k,d_r)
            enc = tok_r(prompt_text(tok_r, it), return_tensors="pt").to(dev)
            qe = model_r.get_input_embeddings()(enc.input_ids)
            x = torch.cat([pref, qe], dim=1)
            am = torch.ones(x.shape[:2], device=dev)
            g = model_r.generate(inputs_embeds=x, attention_mask=am,
                                 max_new_tokens=args.max_new, do_sample=False)
            txt = tok_r.decode(g[0], skip_special_tokens=True)
            ok += exact_match(txt, it["a"])
        return ok / len(items)

    print("评估中...", flush=True)
    res = {
        "receiver_alone": eval_receiver_alone(test),
        "text_relay": eval_text_relay(test),
        "hidden_relay(桥)": eval_hidden_relay(test),
    }
    # sender 单独 (上限参考)
    @torch.no_grad()
    def eval_sender_alone(items):
        ok=0
        for it in items:
            ids = tok_s(prompt_text(tok_s, it), return_tensors="pt").to(dev)
            g = model_s.generate(**ids, max_new_tokens=args.max_new, do_sample=False)
            txt = tok_s.decode(g[0, ids.input_ids.shape[1]:], skip_special_tokens=True)
            ok += exact_match(txt, it["a"])
        return ok/len(items)
    res["sender_alone"] = eval_sender_alone(test)

    out = {"config": vars(args), "geometry": align, "results": res,
           "gap_closed_vs_text": None}
    d = res["receiver_alone"]
    if abs(res["sender_alone"]-d) > 1e-6:
        out["gap_closed_vs_text"] = round((res["text_relay"]-d)/(res["sender_alone"]-d), 3)
        out["gap_closed_by_bridge"] = round((res["hidden_relay(桥)"]-d)/(res["sender_alone"]-d), 3)
    json.dump(out, open(args.out,"w"), ensure_ascii=False, indent=2)
    print("\n===== 结果 =====")
    for k,v in res.items(): print(f"  {k:22s}: {v:.3f}")
    print("gap closed (bridge):", out.get("gap_closed_by_bridge"))
    print("→", args.out)

if __name__ == "__main__":
    main()
