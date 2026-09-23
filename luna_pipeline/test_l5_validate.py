#!/usr/bin/env python3
"""L5 硬校验 / 候选挖掘 对抗测试（纯离线，不调 LLM/网络）。

对 validate_llm_output 与 mine_candidates 喂入「好/坏」两类输入，
证明守卫真的会拦，而不是永远放行。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from l5_insight import (
    entities_of, mine_candidates, entity_map, validate_llm_output,
    build_user_prompt, _parse_json, situation_brief, situation_of,
    render_md, ABSENCE_OK, BASIS_OK, CUE_MIN_CHARS, visible_text,
)

PASS, FAIL = [], []

def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  :: {detail}" if detail and not cond else ""))

ITEMS = [
    {"id": "A", "title": "t-A", "entities": ["中国", "俄罗斯", "普京"]},
    {"id": "B", "title": "t-B", "entities": ["中国", "俄罗斯", "特朗普"]},
    {"id": "C", "title": "t-C", "entities": ["埃塞俄比亚", "TPLF"]},
    {"id": "D", "title": "t-D", "entities": ["中国"]},
    {"id": "E", "title": "t-E", "entities": ["埃塞俄比亚", "TPLF", "格塔丘"]},
]
EMAP = entity_map(ITEMS, None)

print("=" * 70)
print("A. entities_of")
check("去空/去重/保序", entities_of({"entities": [" x ", "x", "", "y"]}) == ["x", "y"])
check("无 entities 键 → 空", entities_of({}) == [])

print("=" * 70)
print("B. mine_candidates（批内，无记忆库）")
cands = mine_candidates(ITEMS, None, top_n=20)
pair_ab = [c for c in cands if c["members"] == ["A", "B"]]
pair_ce = [c for c in cands if c["members"] == ["C", "E"]]
check("A-B 共享 中国+俄罗斯", bool(pair_ab) and set(pair_ab[0]["shared"]) == {"中国", "俄罗斯"})
check("C-E 共享 埃塞俄比亚+TPLF", bool(pair_ce) and set(pair_ce[0]["shared"]) == {"埃塞俄比亚", "TPLF"})
check("A-C 无共享 → 不成链", not [c for c in cands if c["members"] == ["A", "C"]])
check("D 只与中国共享 → A-D 成链", bool([c for c in cands if c["members"] == ["A", "D"]]))
check("weight 降序", all(cands[i]["weight"] >= cands[i+1]["weight"] for i in range(len(cands)-1)))
check("scope 全为 batch", all(c["scope"] == "batch" for c in cands))

print("=" * 70)
print("C. entity_map")
check("含全部批内 id", set(EMAP.keys()) == {"A", "B", "C", "D", "E"})
check("A 实体正确", EMAP["A"] == {"中国", "俄罗斯", "普京"})

print("=" * 70)
print("D. validate_llm_output — 正向")
good = {
    "narrative": "这一批的共现结构是……",
    "chains": [{"members": ["A", "B"], "shared": ["俄罗斯", "中国"],
                "reading": "同一组角色跨条共现。"}],
    "obstacles": [{"where": "确认方", "roles_before": "两造就位",
                   "roles_after": "仍缺第三方", "evidence_ids": ["C"]}],
}
r = validate_llm_output(good, EMAP)
check("合法输出 → status=ok", r["status"] == "ok", r)
check("合法输出 chains=1", len(r["chains"]) == 1)
check("合法输出 obstacles=1", len(r["obstacles"]) == 1)
check("shared 被真实交集覆盖(A∩B)", set(r["chains"][0]["shared"]) == {"中国", "俄罗斯"})

print("=" * 70)
print("E. validate_llm_output — 守卫（喂坏数据，必须拦）")
# E1 伪造 member id
bad1 = {"narrative": "n", "chains": [{"members": ["A", "ZZZ"], "shared": ["中国"]}]}
r1 = validate_llm_output(bad1, EMAP)
check("E1 伪造 id → 丢链", r1["status"] == "empty" and len(r1["dropped"]) == 1, r1)

# E2 真 id 但无真实共同实体
bad2 = {"narrative": "n", "chains": [{"members": ["A", "C"], "shared": ["中国"]}]}
r2 = validate_llm_output(bad2, EMAP)
check("E2 无真实共同实体 → 丢链", r2["status"] == "empty" and len(r2["dropped"]) == 1, r2)

# E3 obstacles 伪造 evidence
bad3 = {"narrative": "n", "obstacles": [{"where": "w", "evidence_ids": ["NOPE"]}]}
r3 = validate_llm_output(bad3, EMAP)
check("E3 伪造 evidence → 丢障碍", r3["status"] == "empty" and len(r3["dropped"]) == 1, r3)

# E4 obstacles 空 evidence
bad4 = {"narrative": "n", "obstacles": [{"where": "w", "evidence_ids": []}]}
r4 = validate_llm_output(bad4, EMAP)
check("E4 空 evidence → 丢障碍", r4["status"] == "empty" and len(r4["dropped"]) == 1, r4)

# E5 narrative 含规则编号 → 整体 rejected
bad5 = {"narrative": "命中 AX-019 所示结构", "chains": [{"members": ["A", "B"]}]}
r5 = validate_llm_output(bad5, EMAP)
check("E5 narrative 含 AX-01N → rejected", r5["status"] == "rejected", r5)

# E6 narrative 含「公理库缺口」
bad6 = {"narrative": "此处暴露公理库缺口", "chains": [{"members": ["A", "B"]}]}
r6 = validate_llm_output(bad6, EMAP)
check("E6 narrative 含增补口径 → rejected", r6["status"] == "rejected", r6)

# E7 皆空 → empty（合法结果）
r7 = validate_llm_output({"narrative": "", "chains": [], "obstacles": []}, EMAP)
check("E7 皆空 → empty", r7["status"] == "empty")

# E8 混入：一条坏链 + 一条好链 → 只留好链
mixed = {"narrative": "n",
         "chains": [{"members": ["A", "ZZZ"], "shared": ["中国"]},
                    {"members": ["C", "E"], "shared": ["X"]}],
         "obstacles": []}
r8 = validate_llm_output(mixed, EMAP)
check("E8 混入 → 坏者丢、好者留", r8["status"] == "ok" and len(r8["chains"]) == 1
      and set(r8["chains"][0]["shared"]) == {"埃塞俄比亚", "TPLF"} and len(r8["dropped"]) == 1, r8)

print("=" * 70)
print("F. _parse_json 容错")
check("```json 包裹", _parse_json('```json\n{"a":1}\n```') == {"a": 1})
check("前后噪声", _parse_json('blah {"a":2} tail') == {"a": 2})
check("坏输入 → {}", _parse_json("not json") == {})

print("=" * 70)
print("G. build_user_prompt")
p = build_user_prompt(ITEMS, cands)
check("含真实 id", "A |" in p or "- A " in p)
check("含候选链段", "【候选链】" in p)
check("无候选链时给占位", "（无候选链）" in build_user_prompt(ITEMS, []))

print("=" * 70)
print("H. 说话人处境 / 缺失分类")
SIT_ITEM = {
    "id": "A", "title": "t-A", "entities": ["中国"],
    "situation": {"role": "外资行首席经济学家", "venue": "公开论坛·圆桌实录",
                  "audience": "监管官员在场", "source_type": "实录",
                  "constraints": ["不宜直接点名现行政策"]},
}
check("situation_brief 拼接全字段",
      situation_brief(SIT_ITEM) == "位置=外资行首席经济学家 | 场合=公开论坛·圆桌实录 | "
                                   "在场=监管官员在场 | 源型=实录 | 约束=不宜直接点名现行政策",
      situation_brief(SIT_ITEM))
check("无 situation → 空串", situation_brief({"id": "X"}) == "")
check("situation 非 dict → 空串", situation_brief({"situation": "oops"}) == "")
check("situation_of 缺省 → {}", situation_of({"id": "X"}) == {})
check("build_user_prompt 带出处境",
      "处境: 位置=外资行首席经济学家" in build_user_prompt([SIT_ITEM], []))
check("无条件 prompt 不含处境行", "处境: " not in build_user_prompt(ITEMS, []))


def _ob(a):
    o = {"where": "受益方", "evidence_ids": ["A"]}
    if a is not None:
        o["absence"] = a
    return o

for tag in ("situational", "textual"):
    rr = validate_llm_output({"narrative": "n", "obstacles": [_ob(tag)]}, EMAP)
    check(f"absence={tag} 保留", rr["status"] == "ok" and rr["obstacles"][0]["absence"] == tag, rr)
rr = validate_llm_output({"narrative": "n", "obstacles": [_ob("bogus")]}, EMAP)
check("absence 非法 → unspecified（不丢障碍）",
      rr["status"] == "ok" and rr["obstacles"][0]["absence"] == "unspecified", rr)
rr = validate_llm_output({"narrative": "n", "obstacles": [_ob(None)]}, EMAP)
check("absence 缺失 → unspecified（不丢障碍）",
      rr["status"] == "ok" and rr["obstacles"][0]["absence"] == "unspecified", rr)

# 门控：absence=situational 须有依据 —— (a) 处境码本 或 (b) 文本内线索（cue 须逐字可验）
rr = validate_llm_output({"narrative": "n", "obstacles": [_ob("situational")]}, EMAP,
                         situation_ids=set())
check("无任何依据（无处境、无 cue）→ situational 降级 unspecified（不丢障碍）",
      rr["status"] == "ok" and rr["obstacles"][0]["absence"] == "unspecified"
      and rr["gated"] == 1, rr)
rr = validate_llm_output({"narrative": "n", "obstacles": [_ob("situational")]}, EMAP,
                         situation_ids={"A"})
check("有处境依据 → situational 保留，basis=codebook",
      rr["obstacles"][0]["absence"] == "situational" and rr["gated"] == 0
      and rr["obstacles"][0]["basis"] == "codebook", rr)
rr = validate_llm_output({"narrative": "n", "obstacles": [_ob("textual")]}, EMAP,
                         situation_ids=set())
check("门控不动 textual", rr["obstacles"][0]["absence"] == "textual", rr)
rr = validate_llm_output({"narrative": "n", "obstacles": [_ob("situational")]}, EMAP)
check("未传 situation_ids → 不门控（旧调用兼容）",
      rr["obstacles"][0]["absence"] == "situational", rr)

# (b) 文本内线索：cue 逐字引自该条目可见文本
CUE_ITEM = {"id": "A", "title": "实录", "entities": ["中国"],
            "conclusion": "以我的身份，不方便点评现行财政政策，只说技术问题。"}
CUE_TEXTS = {"A": visible_text(CUE_ITEM)}

def _obs(a, cue=None, eid="A"):
    o = {"where": "受益方", "evidence_ids": [eid]}
    if a is not None:
        o["absence"] = a
    if cue is not None:
        o["cue"] = cue
    return o

rr = validate_llm_output(
    {"narrative": "n", "obstacles": [_obs("situational", "不方便点评现行财政政策")]}, EMAP,
    situation_ids=set(), texts=CUE_TEXTS)
check("文本内线索可逐字验证 → situational 保留，basis=textual",
      rr["obstacles"][0]["absence"] == "situational" and rr["gated"] == 0
      and rr["obstacles"][0]["basis"] == "textual", rr)
rr = validate_llm_output(
    {"narrative": "n", "obstacles": [_obs("situational", "他不愿多谈是因为外资行身份")]}, EMAP,
    situation_ids=set(), texts=CUE_TEXTS)
check(" cue 编造（文本里找不到）→ 降级 unspecified 并计 gated",
      rr["obstacles"][0]["absence"] == "unspecified" and rr["gated"] == 1, rr)
rr = validate_llm_output(
    {"narrative": "n", "obstacles": [_obs("situational", "不宜")]}, EMAP,
    situation_ids=set(), texts=CUE_TEXTS)
check(f"cue 短于 {CUE_MIN_CHARS} 字 → 不予授权",
      rr["obstacles"][0]["absence"] == "unspecified" and rr["gated"] == 1, rr)
rr = validate_llm_output(
    {"narrative": "n", "obstacles": [_obs("situational", "不方便点评现行财政政策")]}, EMAP,
    situation_ids={"A"}, texts=CUE_TEXTS)
check("两条依据都在 → 优先处境码本（basis=codebook）",
      rr["obstacles"][0]["basis"] == "codebook", rr)
rr = validate_llm_output(
    {"narrative": "n", "obstacles": [_obs("situational", "不方便点评现行财政政策")]}, EMAP,
    situation_ids=set(), texts={"B": "别家文本"})
check("cue 只在 cited 条目的文本里找（换 id 不认）",
      rr["obstacles"][0]["absence"] == "unspecified" and rr["gated"] == 1, rr)
rr = validate_llm_output(
    {"narrative": "n", "obstacles": [_obs("situational", "不方便点评现行财政政策")]}, EMAP,
    situation_ids=set())
check("无 texts（旧调用）→ 线索无法验证，降级",
      rr["obstacles"][0]["absence"] == "unspecified" and rr["gated"] == 1, rr)
check("visible_text 含标题与结论", "实录" in CUE_TEXTS["A"] and "不方便点评" in CUE_TEXTS["A"])

# 观察式线索：非逐字，但与可见文本共享足够内容片段
rr = validate_llm_output(
    {"narrative": "n", "obstacles": [_obs("situational", "说话人自述身份不便点评财政政策")]}, EMAP,
    situation_ids=set(), texts=CUE_TEXTS)
check("观察式线索（片段重叠）→ situational 保留，cue_kind=observation",
      rr["obstacles"][0]["absence"] == "situational"
      and rr["obstacles"][0]["cue_kind"] == "observation", rr)
rr = validate_llm_output(
    {"narrative": "n", "obstacles": [_obs("situational", "他可能在担心监管压力而选择回避话题")]}, EMAP,
    situation_ids=set(), texts=CUE_TEXTS)
check("观察式线索与文本零重叠 → 降级",
      rr["obstacles"][0]["absence"] == "unspecified" and rr["gated"] == 1, rr)
os.environ["LUNA_L5_CUE_STRICT"] = "1"
rr = validate_llm_output(
    {"narrative": "n", "obstacles": [_obs("situational", "说话人自述身份不便点评财政政策")]}, EMAP,
    situation_ids=set(), texts=CUE_TEXTS)
check("LUNA_L5_CUE_STRICT=1 → 观察式不授权",
      rr["obstacles"][0]["absence"] == "unspecified" and rr["gated"] == 1, rr)
rr = validate_llm_output(
    {"narrative": "n", "obstacles": [_obs("situational", "不方便点评现行财政政策")]}, EMAP,
    situation_ids=set(), texts=CUE_TEXTS)
check("LUNA_L5_CUE_STRICT=1 → 引文式仍授权",
      rr["obstacles"][0]["absence"] == "situational", rr)
del os.environ["LUNA_L5_CUE_STRICT"]

# 原文摘要（text_excerpt）：进 prompt，且进 cue 验证语料
EX_ITEM = {"id": "A", "title": "实录", "entities": ["中国"],
           "text_excerpt": "主持人：今天我们只谈两个问题，一是资产价格，二是货币政策。"}
check("prompt 带原文摘要行", "原文: 主持人：今天我们只谈两个问题" in build_user_prompt([EX_ITEM], []))
check("visible_text 含原文摘要", "主持人" in visible_text(EX_ITEM))
rr = validate_llm_output(
    {"narrative": "n", "obstacles": [_obs("situational", "只谈两个问题")]}, EMAP,
    situation_ids=set(), texts={"A": visible_text(EX_ITEM)})
check("cue 可引自原文摘要", rr["obstacles"][0]["absence"] == "situational"
      and rr["obstacles"][0]["cue_kind"] == "quote", rr)
GATED_MD = render_md({"status": "ok", "candidates_n": 0, "chains": [], "dropped": [],
                      "gated": 2,
                      "obstacles": [{"where": "受益方", "roles_before": "a",
                                     "roles_after": "b", "absence": "unspecified",
                                     "evidence_ids": ["A"]}]})
check("渲染出无依据降级行", "无依据降级: 2" in GATED_MD, GATED_MD)

MD = render_md({"status": "ok", "candidates_n": 0, "chains": [], "dropped": [],
                "obstacles": [{"where": "受益方", "roles_before": "a", "roles_after": "b",
                                "absence": "situational", "basis": "textual",
                                "cue": "不方便点评现行财政政策", "evidence_ids": ["A"]}]})
check("render 含缺失分类行（带依据拆分）",
      "缺失分类: 文本内 0 | 情境性 1（处境码本 0 / 文本内线索 1） | 未定 0" in MD, MD)
check("render 含文本内线索标签与原文",
      "[情境性缺失·文本内线索]" in MD and "线索: “不方便点评现行财政政策”" in MD, MD)
MD2 = render_md({"status": "ok", "candidates_n": 0, "chains": [], "dropped": [],
                 "obstacles": [{"where": "受益方", "absence": "situational",
                                 "basis": "codebook", "evidence_ids": ["A"]}]})
check("render 含处境码本标签", "[情境性缺失·处境码本]" in MD2, MD2)
check("render 含文本内观察标签",
      "[情境性缺失·文本内观察]" in render_md(
          {"status": "ok", "candidates_n": 0, "chains": [], "dropped": [],
           "obstacles": [{"where": "受益方", "absence": "situational", "basis": "textual",
                           "cue_kind": "observation", "cue": "只谈两个问题",
                           "evidence_ids": ["A"]}]}))
MD3 = render_md({"status": "ok", "candidates_n": 0, "chains": [], "dropped": [],
                 "obstacles": [{"where": "受益方", "absence": "situational",
                                 "evidence_ids": ["A"]}]})
check("无 basis（旧调用）→ 回退为 [情境性缺失]", "[情境性缺失]（证据" in MD3 or "[情境性缺失]受益方" in MD3, MD3)
check("ABSENCE_OK 三值", set(ABSENCE_OK) == {"textual", "situational", "unspecified"})
check("BASIS_OK 两值", set(BASIS_OK) == {"codebook", "textual"})

print("=" * 70)
print(f"结果: PASS={len(PASS)}  FAIL={len(FAIL)}")
if FAIL:
    print("失败项:")
    for f in FAIL:
        print("  -", f)
sys.exit(1 if FAIL else 0)
