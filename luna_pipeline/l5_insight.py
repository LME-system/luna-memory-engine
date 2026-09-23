#!/usr/bin/env python3
"""Luna SGP L5 · 全局洞察层（结构模式 v6）

职责：把一批已跑完 L1–L4 的条目，读成「结构」而不是「标签」。
  - 机器侧（不调 LLM）：批内两两共享实体 → 候选超边；跨日 → 记忆图邻居 → 候选超边。
  - LLM 侧：候选链（带真实 id / 真实共享实体）+ 各条 conclusion → 一段 narrative + chains + obstacles。
  - 硬校验：id 必须真实存在、shared 必须是成员的**真实**共同实体（不一致以真实交集覆盖）、
    evidence_ids 必须非空且真实；narrative 一旦出现规则编号（AX-0NN）或规则库增补口径 → 整体 rejected。

CLI（可只重跑 L5、不重跑批，便于换模型试验）：
  python3 luna_pipeline/l5_insight.py <items.json> <out.md|-> [--provider X] [--model Y]
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from l4_mind.llm_client import chat

DEFAULT_TOP_N = 12
DEFAULT_MAX_ITEMS = 40          # 喂给 LLM 的条目上限（防止超长 prompt）
CONC_CHARS = 400                # 每条 conclusion 进 prompt 的截断长度

# narrative 违规判定：规则编号 / 规则库增补口径
AX_RE = re.compile(r"AX-\d{3}")
FORBIDDEN_PHRASES = ("公理库缺口", "候选公理")


# ---------------------------------------------------------------- 工具

def _parse_json(raw: str) -> dict:
    """容错 JSON 解析（去 ``` 包裹 / 取最外层大括号）。解析失败返回 {}。"""
    if not isinstance(raw, str):
        return {}
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) else {}
    except Exception:
        i, j = raw.find("{"), raw.rfind("}")
        if 0 <= i < j:
            try:
                d = json.loads(raw[i:j + 1])
                return d if isinstance(d, dict) else {}
            except Exception:
                pass
    return {}


def entities_of(item: dict) -> list:
    """条目的真实实体列表（去空、去重、保序）。"""
    out, seen = [], set()
    for e in (item.get("entities") or []):
        s = str(e).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


# 缺失分类：文本内缺失 / 情境性缺失（说了但没落纸）/ 未定
ABSENCE_OK = ("textual", "situational", "unspecified")
ABSENCE_LABEL = {
    "textual": "[文本内缺失]",
    "situational": "[情境性缺失]",
    "unspecified": "",
}

# situational 的两条授权依据：处境码本 / 文本内自述线索（cue，须能在该条目可见文本里逐字找到）
BASIS_OK = ("codebook", "textual")
BASIS_LABEL = {
    "codebook": "[情境性缺失·处境码本]",
    "textual": "[情境性缺失·文本内线索]",
}
CUE_MIN_CHARS = 6                    # 引文式 cue 归一化后至少这么长，防「不宜」这类短串碰巧命中
CUE_OBS_MIN_TOKENS = 3               # 观察式 cue 至少与可见文本共享这么多二元片段（中文 bigram）
CUE_KIND_LABEL = {
    "quote": "[情境性缺失·文本内线索]",
    "observation": "[情境性缺失·文本内观察]",
}
EXCERPT_CHARS = 600                  # 条目原文摘要进 prompt / 供 cue 验证的字数上限


def situation_of(item: dict) -> dict:
    """条目的「说话人处境」块（没有则空 dict）。"""
    s = item.get("situation") if isinstance(item, dict) else None
    return s if isinstance(s, dict) else {}


def situation_brief(item: dict) -> str:
    """说话人处境 → 一行紧凑文本（位置/场合/在场/源型/约束），无处境返回 ""。"""
    s = situation_of(item)
    if not s:
        return ""
    parts = []
    for key, label in (("role", "位置"), ("venue", "场合"),
                       ("audience", "在场"), ("source_type", "源型")):
        v = str(s.get(key) or "").strip()
        if v:
            parts.append(f"{label}={v}")
    c = s.get("constraints")
    if isinstance(c, (list, tuple)):
        c = "；".join(str(x).strip() for x in c if str(x).strip())
    c = str(c or "").strip()
    if c:
        parts.append(f"约束={c}")
    return " | ".join(parts)


def _norm_text(s) -> str:
    """归一化：去所有空白。用于 cue 的逐字比对（排版换行不应导致比对失败）。"""
    return re.sub(r"\s+", "", str(s or ""))


def visible_text(item: dict) -> str:
    """L5 能看到的该条目文本（题 + 结论 + 原文摘要）。cue 只能引这里出现过的内容。"""
    return _norm_text(" ".join([str(item.get("title") or ""),
                                str(item.get("conclusion") or ""),
                                str(item.get("text_excerpt") or "")]))


def _content_tokens(s: str) -> set:
    """内容片段：中文二元组 + 长度≥3 的拉丁词—— 给观察式 cue 做重叠度检查。

    用二元组而非整段：中文连续段整段比对要求逐字全同，等于只认引文，观察式线索永远
    不能命中（实测踩过）。"""
    t = set()
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", str(s or "")):
        t.update(run[i:i + 2] for i in range(len(run) - 1))
    t.update(w.lower() for w in re.findall(r"[A-Za-z]{3,}", str(s or "")))
    return t


def _cue_strict() -> bool:
    """LUNA_L5_CUE_STRICT=1 → 只认引文式 cue（逐字命中），观察式线索不授权。"""
    return str(os.getenv("LUNA_L5_CUE_STRICT", "")).strip().lower() in ("1", "true", "yes", "on")


def _top_n() -> int:
    try:
        return max(1, int(os.getenv("LUNA_L5_TOP_N", str(DEFAULT_TOP_N))))
    except (TypeError, ValueError):
        return DEFAULT_TOP_N


def _max_items() -> int:
    try:
        return max(1, int(os.getenv("LUNA_L5_MAX_ITEMS", str(DEFAULT_MAX_ITEMS))))
    except (TypeError, ValueError):
        return DEFAULT_MAX_ITEMS


# ---------------------------------------------------------------- B1 机器侧候选超边

def mine_candidates(items: list, memory_store=None, top_n: int = None) -> list:
    """挖掘候选超边（不调 LLM）。

    批内：两两条目共享 ≥1 实体即候选，shared = 真实共享实体，weight = Jaccard。
    跨日：对每条用记忆图的 graph_neighbors_by_entities 取真实历史邻居，scope=memory。
    按 weight 降序取 top-N。
    """
    top_n = top_n or _top_n()
    ents = {}
    for it in items:
        iid = str(it.get("id"))
        if iid:
            ents[iid] = set(entities_of(it))

    cands = []
    ids = list(ents.keys())
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            shared = ents[a] & ents[b]
            if not shared:
                continue
            union = ents[a] | ents[b]
            cands.append({
                "scope": "batch",
                "members": [a, b],
                "shared": sorted(shared),
                "weight": round(len(shared) / max(len(union), 1), 4),
            })

    if memory_store is not None:
        for it in items:
            iid = str(it.get("id"))
            cur = entities_of(it)
            if not iid or not cur:
                continue
            try:
                nbrs = memory_store.graph_neighbors_by_entities(cur, k=3, exclude_id=iid)
            except Exception:
                nbrs = []
            for nb in (nbrs or []):
                nid = str(nb.get("id"))
                shared = sorted(str(x) for x in (nb.get("edge_shared") or []))
                if not nid or not shared:
                    continue
                cands.append({
                    "scope": "memory",
                    "members": [iid, nid],
                    "shared": shared,
                    "weight": round(float(nb.get("edge_weight") or 0.0), 4),
                })

    cands.sort(key=lambda c: (-c["weight"], -len(c["shared"]), c["scope"], c["members"]))
    return cands[:top_n]


# ---------------------------------------------------------------- B2 LLM 侧

L5_SYSTEM = """你是 Luna SGP 的全局洞察层（结构模式 v6）。你只读结构：角色、超边、障碍。

【口径】
1. 用「角色 / 超边 / 绑定」的语言说话。一条超边是若干角色同时成立的关系
   （例如 提取方—被提取方—通道—受益方），它不是一个标签，也不是一根轴上的一个刻度。
2. 连贯书面中文，成段陈述。不要列点、不要小标题、不要堆英文术语、不要复述输入。
3. 只判读「结构是否在场 / 偏移在哪个角色上 / 哪个角色缺席」，不做道德评判，不预测价格与涨跌。
4. 禁止讨论规则编号、禁止讨论规则库的缺口、禁止提出任何新规则的增补建议。
   你的产出是结构判读，不是规则提案。
5. 硬要求：chains 与 obstacles 里出现的**每一个条目 id 与每一个实体名，必须逐字来自**
   下面给出的「本批条目」与「候选链」；不得发明 id、不得改写实体、不得用「上述」「所有条目」等
   泛指代替真实 id。候选链为空时，chains 必须返回空数组。
6. 条目若带「处境」（说话人位置 / 场合 / 在场 / 源型 / 约束），把它当作接收端码本的一部分：
   处境显示这是公开论坛的圆桌实录、有监管官员在场、或只是媒体二次摘要时，某个角色的缺席
   更可能是**情境性缺失**——发言人说了，但没落在这份材料里（被提问框窄化、被编辑剪掉、
   不方便写下来），而不是结构上真的缺席。反过来，处境是专题发言稿 / 专访时，文本内确实没有
   就更接近真实的结构缺席。不要因处境宽松就放弃判读，只须把缺席的性质标清楚。
7. absence 填 situational 必须有依据，两条路任选其一；两条都不成立就只能填 textual 或 unspecified：
   (a) 处境码本：条目带「处境」行，且处境里的位置 / 场合 / 在场 / 约束能指出该角色为何
       在文本外仍成立；
   (b) 文本内线索：条目没有「处境」行，但题目 / 结论 / 原文摘要本身透露出说话人只讲了一部分——
       典型形态：① 主持人交代「每人只问一个问题」/ 提问范围被限定；② 说话人自述「不宜置评 /
       不便直说 / 只谈技术层面 / 这不是我该说的」；③ 答问只覆盖被问到的议题，自己的核心判断
       整段不在文中。此时必须把那段**原文照抄**（含标点）放进 cue —— 这是这条依据的唯一凭证，
       代码会拿它与该条目的可见文本逐字 / 片段比对；编造或转述的 cue 一律不予授权，该障碍降级为未定。
       没有这样的文字依据时，只能填 textual 或 unspecified。
   两条都成立时优先走 (a)、cue 留空。文本内线索判不准就不填——宁可标未定。
   cue 只能引自该条目题目或结论里真实出现过的片段；代码会逐字比对，编造的 cue 一律不予授权。

【narrative】一段成篇的结构判读：这一批条目共同在场的是什么结构；跨条目或跨日读出了什么一致、
什么冲突；偏移出现在哪个角色上。只写结构，不写规则。

【chains】从候选链里挑真正有结构意义的（不必全用），每条：
  members: 该链的条目 id 列表（逐字来自候选链）
  shared: 这些条目共同在场的实体（逐字来自候选链，且必须真是成员共同拥有的）
  reading: 这条链读出了什么，一到三句。

【obstacles】结构本该出现却没有出现的障碍点，每条：
  where: 障碍发生在哪个角色或环节
  roles_before: 障碍之前的角色配置
  roles_after: 障碍之后的角色配置
  evidence_ids: 支撑该障碍的条目 id（至少一个，逐字来自上面的清单）
  absence: 缺失性质，三选一逐字填：
    "textual"     —— 这份文本里确实没有该角色（结构上缺席）；
    "situational" —— 处境码本或文本内线索表明该角色在文本外已（或可能已）绑定，
                      只是没落在这份材料里；
    "unspecified" —— 判不准。
  cue: 仅当走上面 7(b) 文本内线索时填，照抄该条目题目 / 结论 / 原文摘要里出现过的文字；
       否则留空。cue 里不要写自己的推论或评价。

只输出 JSON，不要任何额外文字。"""

L5_FORMAT = {
    "type": "object",
    "properties": {
        "narrative": {"type": "string"},
        "chains": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "members": {"type": "array", "items": {"type": "string"}},
                    "shared": {"type": "array", "items": {"type": "string"}},
                    "reading": {"type": "string"},
                },
                "required": ["members", "shared"],
            },
        },
        "obstacles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "where": {"type": "string"},
                    "roles_before": {"type": "string"},
                    "roles_after": {"type": "string"},
                    "absence": {"type": "string", "enum": list(ABSENCE_OK)},
                    "cue": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["where", "evidence_ids"],
            },
        },
    },
    "required": ["narrative"],
}


def build_user_prompt(items: list, candidates: list) -> str:
    """把条目摘要（带真实 id / 实体）与候选链喂给 LLM。"""
    lines = ["【本批条目】格式: - id | 时间 | 标题"]
    for it in items[:_max_items()]:
        iid = str(it.get("id"))
        ents = entities_of(it)[:20]
        concl = (it.get("conclusion") or "").strip().replace("\n", " ")
        if len(concl) > CONC_CHARS:
            concl = concl[:CONC_CHARS] + "…"
        l3 = it.get("l3") or {}
        l3s = l3.get("status") if isinstance(l3, dict) else str(l3)
        jv = it.get("jev")
        jvs = ""
        if isinstance(jv, dict):
            jvs = f"{jv.get('status')}|conflict={jv.get('conflict_flags')}|nonlinear={jv.get('nonlinear')}"
        lines.append(f"- {iid} | {it.get('time','')} | {it.get('title','')}")
        sb = situation_brief(it)
        if sb:
            lines.append(f"    处境: {sb}")
        lines.append(f"    实体: {', '.join(ents)}")
        lines.append(f"    L3: {l3s} | Jev: {jvs}")
        lines.append(f"    结论: {concl}")
        ex = str(it.get("text_excerpt") or "").strip().replace("\n", " ")
        if ex:
            if len(ex) > EXCERPT_CHARS:
                ex = ex[:EXCERPT_CHARS] + "…"
            lines.append(f"    原文: {ex}")

    lines.append("")
    lines.append("【候选链】（members / shared 均为真实 id 与真实共享实体；scope=batch 为批内，memory 为跨日历史邻居）")
    if not candidates:
        lines.append("（无候选链）")
    else:
        for i, c in enumerate(candidates, 1):
            lines.append(f"{i}. [{c['scope']}] members={c['members']} "
                         f"shared={c['shared']} weight={c['weight']}")
    lines.append("")
    lines.append("请按 system 规定的 JSON 结构只输出 JSON。")
    return "\n".join(lines)


# ---------------------------------------------------------------- B3 硬校验

def entity_map(items: list, memory_store=None) -> dict:
    """id → 真实实体集合（本批 ∪ 记忆库）。"""
    m = {}
    for it in items:
        iid = str(it.get("id"))
        if iid:
            m[iid] = set(entities_of(it))
    if memory_store is not None:
        for rec in (getattr(memory_store, "_meta", None) or []):
            rid = str(rec.get("id"))
            if rid and rid not in m:
                m[rid] = set(str(e) for e in (rec.get("entities") or []))
        g = getattr(memory_store, "_graph", None)
        if g is not None:
            try:
                for nid, data in g.nodes(data=True):
                    sid = str(nid)
                    if sid not in m:
                        m[sid] = set(str(e) for e in (data.get("entities") or []))
            except Exception:
                pass
    return m


def validate_llm_output(raw: dict, emap: dict, situation_ids=None, texts=None) -> dict:
    """纯函数硬校验（不依赖网络/LLM）。返回 {status, narrative, chains, obstacles, dropped, gated}。

    absence=situational 是关于文本外世界的判断，须有依据，两条路任选其一：
      (a) 处境码本：evidence 里至少一个条目带「说话人处境」（situation_ids）；
      (b) 文本内线索：障碍带 cue，且该 cue 能在任一 evidence 条目的可见文本里得到验证
          （texts: id → 可见文本）——逐字命中（quote），或与其内容片段重叠足够
          （observation，LUNA_L5_CUE_STRICT=1 时不认）。
    两条都不成立 → 降级为 unspecified（计 gated）——**不清洗掉障碍**。
    situation_ids=None 表示旧调用，完全不门控。
    """
    valid_ids = set(emap.keys())
    dropped = []
    narrative = raw.get("narrative") if isinstance(raw, dict) else ""
    narrative = narrative.strip() if isinstance(narrative, str) else ""

    # 4) narrative 违规 → 整体 rejected
    if AX_RE.search(narrative) or any(p in narrative for p in FORBIDDEN_PHRASES):
        return {
            "status": "rejected",
            "reason": "narrative 出现规则编号或规则库增补口径",
            "narrative": narrative,
            "gated": 0,
            "chains": [],
            "obstacles": [],
            "dropped": [],
        }

    # 1) + 2) chains
    chains = []
    for c in (raw.get("chains") or []):
        if not isinstance(c, dict):
            dropped.append({"type": "chain", "reason": "非对象", "value": c})
            continue
        members = [str(x) for x in (c.get("members") or []) if str(x)]
        if not members:
            dropped.append({"type": "chain", "reason": "members 为空", "value": c})
            continue
        unknown = [x for x in members if x not in valid_ids]
        if unknown:                                   # 1) 未知 id → 丢该链
            dropped.append({"type": "chain", "reason": f"含未知 id: {unknown}", "value": c})
            continue
        real_shared = None
        for mid in members:
            s = set(emap.get(mid) or set())
            real_shared = s if real_shared is None else (real_shared & s)
        real_shared = real_shared or set()
        if not real_shared:                            # 2) 交集为空 → 丢该链
            dropped.append({"type": "chain", "reason": "成员无真实共同实体", "value": c})
            continue
        chains.append({
            "members": members,
            "shared": sorted(real_shared),             # 2) 一律以真实交集覆盖
            "reading": (c.get("reading") or "").strip() if isinstance(c.get("reading"), str) else "",
        })

    # 3) obstacles
    obstacles = []
    for o in (raw.get("obstacles") or []):
        if not isinstance(o, dict):
            dropped.append({"type": "obstacle", "reason": "非对象", "value": o})
            continue
        eids = [str(x) for x in (o.get("evidence_ids") or []) if str(x)]
        bad = [x for x in eids if x not in valid_ids]
        if not eids or bad:                            # 3) 空或非真实 → 丢该障碍
            dropped.append({
                "type": "obstacle",
                "reason": f"evidence_ids 含未知 id: {bad}" if bad else "evidence_ids 为空",
                "value": o,
            })
            continue
        absence = str(o.get("absence") or "").strip().lower()
        if absence not in ABSENCE_OK:                   # 缺省/非法 → unspecified，不清洗掉该障碍
            absence = "unspecified"
        cue = (o.get("cue") or "").strip() if isinstance(o.get("cue"), str) else ""
        basis, cue_kind, gated = "", "", False
        if absence == "situational" and situation_ids is not None:
            if set(eids) & set(situation_ids):           # (a) 处境码本授权
                basis = "codebook"
            elif cue and texts is not None:              # (b) 文本内线索授权（须可验）
                c = _norm_text(cue)
                if len(c) >= CUE_MIN_CHARS and any(
                        c in _norm_text(texts.get(e, "")) for e in eids):
                    basis, cue_kind = "textual", "quote"          # 引文式：逐字命中
                elif not _cue_strict() and sum(
                        len(_content_tokens(cue) & _content_tokens(texts.get(e, "")))
                        for e in eids) >= CUE_OBS_MIN_TOKENS:
                    basis, cue_kind = "textual", "observation"    # 观察式：与可见文本有足够重叠
            if not basis:                                # 依据不成立 → 降级未定（不丢障碍）
                absence, gated = "unspecified", True
        obstacles.append({
            "where": (o.get("where") or "").strip() if isinstance(o.get("where"), str) else "",
            "roles_before": (o.get("roles_before") or "").strip() if isinstance(o.get("roles_before"), str) else "",
            "roles_after": (o.get("roles_after") or "").strip() if isinstance(o.get("roles_after"), str) else "",
            "absence": absence,
            "basis": basis,
            "cue": cue,
            "cue_kind": cue_kind,
            "gated": gated,
            "evidence_ids": eids,
        })

    # 5) 皆空 → empty（合法结果）
    if not chains and not obstacles:
        return {
            "status": "empty",
            "narrative": narrative or "本轮结构不在场",
            "chains": [],
            "obstacles": [],
            "dropped": dropped,
            "gated": 0,
        }
    return {"status": "ok", "narrative": narrative, "chains": chains,
            "obstacles": obstacles, "dropped": dropped,
            "gated": sum(1 for o in obstacles if o.get("gated"))}


# ---------------------------------------------------------------- 入口

def build_insight(items: list, memory_store=None, provider: str = None, model: str = None) -> dict:
    """L5 主入口：机器侧候选 → LLM 判读 → 硬校验。"""
    p = (provider or os.getenv("LUNA_L5_PROVIDER") or os.getenv("LUNA_LLM_PROVIDER") or "ollama").strip().lower()
    items = [it for it in (items or []) if isinstance(it, dict)]

    candidates = mine_candidates(items, memory_store)
    emap = entity_map(items, memory_store)
    sit_ids = {str(it.get("id")) for it in items if situation_of(it)}
    texts = {str(it.get("id")): visible_text(it) for it in items if str(it.get("id"))}
    out = {
        "status": "empty",
        "narrative": "本轮结构不在场",
        "chains": [],
        "obstacles": [],
        "dropped": [],
        "gated": 0,
        "candidates_n": len(candidates),
        "model": {"provider": p, "model": model},
    }
    if not items:
        return out

    user = build_user_prompt(items, candidates)
    raw = {}
    for _ in range(2):                                  # 空/坏返回 → 重试一次
        try:
            txt = chat(L5_SYSTEM, user, num_predict=2500, temperature=0.35,
                       timeout=900, fmt=L5_FORMAT, provider=p, model=model)
        except Exception:
            continue
        raw = _parse_json(txt)
        if raw.get("narrative") or raw.get("chains") or raw.get("obstacles"):
            break

    res = validate_llm_output(raw, emap, situation_ids=sit_ids, texts=texts)
    out.update(res)
    out["candidates_n"] = len(candidates)
    out["model"] = {"provider": p, "model": model}
    return out


def render_md(insight: dict) -> str:
    """L5 结果 → md 段落（run_batch 与 CLI 共用同一渲染）。"""
    L = ["## 全局洞察（L5 · 结构模式 v6）", ""]
    st = insight.get("status")
    L.append(f"- 状态: {st} | 候选链: {insight.get('candidates_n', 0)} | "
             f"结构链: {len(insight.get('chains') or [])} | "
             f"障碍: {len(insight.get('obstacles') or [])} | "
             f"丢弃: {len(insight.get('dropped') or [])}")
    if st == "rejected":
        L.append(f"- 原因: {insight.get('reason', '')}（不产出结构判读）")
        return "\n".join(L) + "\n"
    obs_all = insight.get("obstacles") or []
    if obs_all:
        cnt = {k: 0 for k in ABSENCE_OK}
        basis_cnt = {k: 0 for k in BASIS_OK}
        for o in obs_all:
            k = o.get("absence") or "unspecified"
            cnt[k if k in cnt else "unspecified"] += 1
            b = o.get("basis") or ""
            if k == "situational" and b in basis_cnt:
                basis_cnt[b] += 1
        L.append(f"- 缺失分类: 文本内 {cnt['textual']} | 情境性 {cnt['situational']}"
                 f"（处境码本 {basis_cnt['codebook']} / 文本内线索 {basis_cnt['textual']}）"
                 f" | 未定 {cnt['unspecified']}")
        n_gated = int(insight.get("gated") or 0)
        if n_gated:
            L.append(f"- 无依据降级: {n_gated} 条 situational → 未定"
                     f"（处境码本与文本内线索都不成立，不解码）")
    nar = (insight.get("narrative") or "").strip()
    if nar:
        L += ["", nar]
    chains = insight.get("chains") or []
    if chains:
        L += ["", "**结构链**", ""]
        for c in chains:
            L.append(f"- `{' + '.join(c.get('members', []))}`"
                     f"（共享: {'、'.join(c.get('shared', []))}）— {c.get('reading', '')}")
    obs = insight.get("obstacles") or []
    if obs:
        L += ["", "**障碍**", ""]
        for o in obs:
            if o.get("absence") == "situational":
                tag = ""
                if o.get("basis") == "textual":
                    tag = CUE_KIND_LABEL.get(o.get("cue_kind") or "", "")
                tag = tag or BASIS_LABEL.get(o.get("basis") or "", "") or ABSENCE_LABEL["situational"]
            else:
                tag = ABSENCE_LABEL.get(o.get("absence") or "unspecified", "")
            line = (f"- {tag}{o.get('where','')}：{o.get('roles_before','')} → {o.get('roles_after','')}")
            if o.get("cue"):
                line += f"（线索: “{o['cue']}”）"
            L.append(line + f"（证据: {', '.join(o.get('evidence_ids', []))}）")
    return "\n".join(L) + "\n"


def load_items(path: str) -> list:
    """读 items.json：接受裸数组，或 run_batch 写的 {"count":n,"items":[...]}。"""
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    if isinstance(d, dict):
        d = d.get("items") or []
    return [x for x in (d or []) if isinstance(x, dict)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Luna SGP L5 全局洞察（可单独重跑）")
    ap.add_argument("items", help="items.json（run_batch 产出的 <out>.items.json）")
    ap.add_argument("out", help="输出 md 路径，或 - 表示 stdout")
    ap.add_argument("--provider", default=None)
    ap.add_argument("--model", default=None)
    a = ap.parse_args(argv)

    items = load_items(a.items)
    mem = None
    try:
        from memory_store import MemoryStore
        with contextlib.redirect_stdout(sys.stderr):   # 记忆库加载日志别污染 md 的 stdout
            mem = MemoryStore(dim=768)
    except Exception as e:                    # 记忆库不可用 → 降级为纯批内挖掘
        print(f"[l5] memory store unavailable: {type(e).__name__}: {e}", file=sys.stderr)

    ins = build_insight(items, mem, provider=a.provider, model=a.model)
    md = render_md(ins)
    if a.out in ("-", ""):
        sys.stdout.write(md)
    else:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(md)
    print(json.dumps({
        "status": ins["status"], "candidates_n": ins["candidates_n"],
        "chains": len(ins["chains"]), "obstacles": len(ins["obstacles"]),
        "dropped": len(ins["dropped"]), "model": ins["model"],
    }, ensure_ascii=False), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
