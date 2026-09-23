#!/usr/bin/env python3
"""
Luna SGP × Jev 并联桥接器
零额外依赖（仅 requests），Jev 作为结构化校验/增强层并联接入 L1/L2

调用链：
    单条快讯
        ├──→ DeepSeek Flash / Gemma → LLM 文本分析（现有流程）
        │
        ├──→ Jev → 6 个并行结构化判断（本文件）
        │
        └──→ fuse_l2() → 融合节点（含 confidence / conflict_flags）
"""

import os
import json
import requests
from typing import Dict, Any, Optional

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
# 优先从 .env 文件读取，其次环境变量
_ENV_PATH = os.path.join(os.path.expanduser("~"), ".openclaw", ".env")
TYPESAFE_API_KEY = ""
if os.path.exists(_ENV_PATH):
    with open(_ENV_PATH) as f:
        for line in f:
            if line.startswith("TYPESAFE_API_KEY="):
                TYPESAFE_API_KEY = line.split("=", 1)[1].strip()
                break
if not TYPESAFE_API_KEY:
    TYPESAFE_API_KEY = os.environ.get("TYPESAFE_API_KEY", "")
TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-latest"

# ---------------------------------------------------------------------------
# 阈值外置 (问题6): 读 luna_jev_config.json，缺省回落硬编码原值
# ---------------------------------------------------------------------------
_DEFAULT_CONFIG = {
    "JEV_CONFIDENCE_LOW": 0.60,          # 低于此值，该维度以 LLM 为准
    "JEV_CONFIDENCE_HIGH": 0.85,         # 高于此值，一致时触发升权
    "BOOST_DELTA": 0.08,                 # 升权幅度
    "NONLINEAR_FLAG_THRESHOLD": 0.60,    # nonlinear noul 概率 flag 阈值
    "NOUL_THRESHOLD": 0.70,              # 一般 noul 维度判定阈值
    "MONETARY_RATE_RELAXED_THRESHOLD": 0.20,  # event_type=monetary 时涉利率补偿阈值
    "LLM_CLASSIFY_MIN_CONF": 0.60,       # LLM classify 侧参与冲突判定的最低置信
    "SENTIMENT_CONFLICT_GAP": 1,         # 情绪冲突允差级数
}

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "luna_jev_config.json")


def load_jev_config(path: Optional[str] = None) -> Dict[str, Any]:
    """读外置阈值配置；文件缺失/损坏/缺键时逐键回落默认值。"""
    cfg = dict(_DEFAULT_CONFIG)
    try:
        with open(path or _CONFIG_PATH) as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            for k in _DEFAULT_CONFIG:
                v = loaded.get(k)
                if v is not None:
                    cfg[k] = v
    except Exception:
        pass
    return cfg


JEV_CONFIG = load_jev_config()
JEV_CONFIDENCE_LOW = JEV_CONFIG["JEV_CONFIDENCE_LOW"]
JEV_CONFIDENCE_HIGH = JEV_CONFIG["JEV_CONFIDENCE_HIGH"]
BOOST_DELTA = JEV_CONFIG["BOOST_DELTA"]
NONLINEAR_FLAG_THRESHOLD = JEV_CONFIG["NONLINEAR_FLAG_THRESHOLD"]
NOUL_THRESHOLD = JEV_CONFIG["NOUL_THRESHOLD"]
MONETARY_RATE_RELAXED_THRESHOLD = JEV_CONFIG["MONETARY_RATE_RELAXED_THRESHOLD"]
LLM_CLASSIFY_MIN_CONF = JEV_CONFIG["LLM_CLASSIFY_MIN_CONF"]
SENTIMENT_CONFLICT_GAP = JEV_CONFIG["SENTIMENT_CONFLICT_GAP"]

# Jev choice / score 枚举（与 classify 严格对齐，单一真源）
EVENT_TYPES = ["monetary", "fiscal", "geopolitical", "tech_regulation", "market_structure", "other"]
SENTIMENT_LEGEND = [
    "极度恐慌/崩溃性抛售", "恐慌/避险情绪升温", "偏空/谨慎/担忧",
    "中性/观望/信息混杂", "偏多/乐观/信心恢复", "狂热/过度乐观/FOMO",
]
CERTAINTY_LEGEND = [
    "纯传闻/市场猜测/无可靠来源", "弱信号/非官方渠道/分析师推测",
    "部分确认/有来源但未官宣", "即将官宣/已确定时间或已泄露",
    "已官宣、已执行或已落地",
]

# ---------------------------------------------------------------------------
# Jev 调用
# ---------------------------------------------------------------------------

def jev_judge(news_text: str, title: str = "", api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    对单条快讯并行发起 6 个 Jev 判断。

    Args:
        news_text: 快讯正文
        title: 标题（可选，会拼接进 state）
        api_key: 可选，默认读环境变量 TYPESAFE_API_KEY

    Returns:
        dict: {"answers": {...}, "model": "jev-latest", "usage": {...}}
              或 {"error": str}
    """
    key = api_key or TYPESAFE_API_KEY
    if not key:
        return {"error": "TYPESAFE_API_KEY not set"}

    state = news_text
    if title:
        state = f"标题：{title}\n正文：{news_text}"

    payload = {
        "model": JEV_MODEL,
        "state": state,
        "questions": {
            "event_type": {
                "type": "choice",
                "instructions": "该快讯属于哪种宏观/政策事件类型？",
                "criteria": {
                    "monetary": "货币政策（利率、QE/QT、央行动作、流动性）",
                    "fiscal": "财政政策（赤字、税收、政府支出、债务）",
                    "geopolitical": "地缘冲突、国际关系、制裁、外交博弈",
                    "tech_regulation": "科技监管、AI 政策、数据安全、半导体管制",
                    "market_structure": "市场结构变化（ETF、流动性、交易机制、衍生品）",
                    "other": "其他或无法归类",
                },
            },
            "involves_rate": {
                "type": "noul",
                "instructions": "该快讯是否涉及利率变动（含预期、市场押注、点阵图、实际变动）？",
                "criteria": {
                    "true": "明确涉及利率、降息、加息、点阵图、利差",
                    "false": "完全不涉及利率相关议题",
                },
            },
            "involves_ai": {
                "type": "noul",
                "instructions": "该快讯是否涉及 AI 产业、AI 安全叙事、算力管制、模型监管？",
                "criteria": {
                    "true": "涉及 AI 技术、AI 公司、AI 政策、AI 安全风险",
                    "false": "不涉及 AI 相关议题",
                },
            },
            "policy_certainty": {
                "type": "score",
                "instructions": "该事件的政策/信息确定性如何？",
                "criteria": [
                    "纯传闻/市场猜测/无可靠来源",
                    "弱信号/非官方渠道/分析师推测",
                    "部分确认/有来源但未官宣",
                    "即将官宣/已确定时间或已泄露",
                    "已官宣、已执行或已落地",
                ],
            },
            "sentiment": {
                "type": "score",
                "instructions": "该快讯反映的市场情绪极性？",
                "criteria": [
                    "极度恐慌/崩溃性抛售",
                    "恐慌/避险情绪升温",
                    "偏空/谨慎/担忧",
                    "中性/观望/信息混杂",
                    "偏多/乐观/信心恢复",
                    "狂热/过度乐观/FOMO",
                ],
            },
            "nonlinear": {
                "type": "noul",
                "instructions": "该快讯是否呈现非线性特征（突变、超预期、反直觉、叙事反转、与主流预期背离、隐性结构暴露）？",
                "criteria": {
                    "true": "事件打破既有叙事、超预期、反直觉、引发范式转移",
                    "false": "符合线性预期、属于常规波动",
                },
            },
        },
    }

    try:
        resp = requests.post(
            TYPESAFE_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# 融合层
# ---------------------------------------------------------------------------

def _llm_classify_confidence(llm_result: Dict[str, Any]) -> float:
    """LLM classify 侧的置信度。

    注：classify() 只输出 event_type/sentiment_score/certainty_hint 三个键，不含 confidence，
    因此 LLM 侧置信度取 classify.confidence（若上游补写）否则整体置信度，最后回落 0.75。
    """
    cls = llm_result.get("classify") or {}
    if isinstance(cls, dict) and cls.get("confidence") is not None:
        return float(cls["confidence"])
    try:
        return float(llm_result.get("confidence", 0.75))
    except (TypeError, ValueError):
        return 0.75


def _llm_theme_to_event_type(llm_themes: list) -> Optional[str]:
    """将 LLM themes 粗糙映射到 Jev event_type。

    降级为 fallback：仅当 llm_result 不含结构化 classify.event_type 时才使用。
    """
    theme_text = " ".join(llm_themes).lower()
    mapping = {
        "monetary": ["利率", "央行", "fed", "降息", "加息", "qe", "qt", "流动性", "货币政策"],
        "fiscal": ["财政", "赤字", "税收", "政府支出", "债务", "基建"],
        "geopolitical": ["地缘", "冲突", "制裁", "外交", "战争", "中美", "中俄", "台海"],
        "tech_regulation": ["ai", "科技", "监管", "半导体", "芯片", "数据安全", "算力"],
        "market_structure": ["etf", "流动性", "交易", "衍生品", "市场结构"],
    }
    for etype, keywords in mapping.items():
        if any(k in theme_text for k in keywords):
            return etype
    return None


def _llm_sentiment_to_score(sentiment: str) -> int:
    """LLM sentiment → Jev sentiment score 索引（0~5）。"""
    s = sentiment.lower()
    if "panic" in s or "极度恐慌" in s or "crash" in s:
        return 0
    if "panic" in s or "恐慌" in s or "fear" in s:
        return 1
    if "negative" in s or "偏空" in s or "bear" in s or "cautious" in s:
        return 2
    if "neutral" in s or "中性" in s or "mixed" in s:
        return 3
    if "positive" in s or "偏多" in s or "bull" in s or "optimistic" in s:
        return 4
    if "euphoria" in s or "狂热" in s or "fomo" in s:
        return 5
    return 3  # 默认中性


def fuse_l2(llm_result: Dict[str, Any], jev_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 LLM 文本分析结果与 Jev 结构化判断融合为统一 L2 节点。

    融合策略：
        1. 一致 → 升权（confidence + BOOST_DELTA，上限 0.99）
        2. 冲突 → 标记 conflict_flag，供 L3 特别关注
        3. Jev 独有维度（policy_certainty, nonlinear）直接注入
        4. Jev confidence < JEV_CONFIDENCE_LOW → 降级，以 LLM 为准
    """
    if "error" in jev_result:
        # Jev 调用失败，回退到纯 LLM
        return {
            **llm_result,
            "jev_status": "failed",
            "jev_error": jev_result["error"],
            "confidence": llm_result.get("confidence", 0.75),
            "conflict_flags": [],
        }

    answers = jev_result.get("answers", {})
    fused = dict(llm_result)  # 深拷贝基础
    fused["jev_judgments"] = {
        k: {kk: vv for kk, vv in v.items() if kk != "distribution"}  # 去掉冗长分布
        for k, v in answers.items()
    }
    fused["jev_status"] = "ok"

    conflict_flags = []
    base_confidence = llm_result.get("confidence", 0.75)

    # ------------------------
    # 1. event_type ↔ themes 冲突检测
    # ------------------------
    jev_event = answers.get("event_type", {})
    jev_event_choice = jev_event.get("choice")
    jev_event_conf = jev_event.get("confidence", 0.0)

    # 问题2: 优先消费结构化 classify；关键词启发式仅作 fallback
    cls = llm_result.get("classify")
    if not isinstance(cls, dict):
        cls = {}
    if cls:
        fused["llm_classify"] = cls

    if cls.get("event_type") in EVENT_TYPES:
        llm_event_guess = cls["event_type"]
        llm_event_source = "classify"
    else:
        llm_event_guess = _llm_theme_to_event_type(llm_result.get("themes", []))
        llm_event_source = "heuristic" if llm_event_guess else None
    llm_event_conf = _llm_classify_confidence(llm_result)

    if jev_event_choice and llm_event_guess:
        if jev_event_choice == llm_event_guess:
            if jev_event_conf >= JEV_CONFIDENCE_HIGH:
                base_confidence = min(0.99, base_confidence + BOOST_DELTA)
        else:
            # 冲突: 双方 confidence 都 >= 低阈值
            if jev_event_conf >= JEV_CONFIDENCE_LOW and llm_event_conf >= LLM_CLASSIFY_MIN_CONF:
                conflict_flags.append({
                    "dimension": "event_type",
                    "llm": llm_event_guess,
                    "llm_source": llm_event_source,
                    "llm_confidence": round(llm_event_conf, 3),
                    "jev": jev_event_choice,
                    "jev_confidence": jev_event_conf,
                })

    # ------------------------
    # 2. sentiment ↔ sentiment 冲突检测
    # ------------------------
    jev_sent = answers.get("sentiment", {})
    jev_sent_score = int(jev_sent.get("score", 3))
    jev_sent_conf = jev_sent.get("confidence", 0.0)

    if isinstance(cls.get("sentiment_score"), int):
        llm_sent = max(0, min(5, cls["sentiment_score"]))
        llm_sent_source = "classify"
    else:
        llm_sent = _llm_sentiment_to_score(llm_result.get("sentiment", "neutral"))
        llm_sent_source = "heuristic"
    llm_sent_conf = _llm_classify_confidence(llm_result)

    # 允许差 SENTIMENT_CONFLICT_GAP 级（评分尺度不同）
    if abs(jev_sent_score - llm_sent) <= SENTIMENT_CONFLICT_GAP:
        if jev_sent_conf >= JEV_CONFIDENCE_HIGH:
            base_confidence = min(0.99, base_confidence + BOOST_DELTA)
    else:
        if jev_sent_conf >= JEV_CONFIDENCE_LOW and llm_sent_conf >= LLM_CLASSIFY_MIN_CONF:
            conflict_flags.append({
                "dimension": "sentiment",
                "llm_score": llm_sent,
                "llm_source": llm_sent_source,
                "llm_confidence": round(llm_sent_conf, 3),
                "jev_score": jev_sent_score,
                "jev_confidence": jev_sent_conf,
            })

    # ------------------------
    # 3. involves_rate / involves_ai —— Jev 独有校验
    # ------------------------
    for dim in ["involves_rate", "involves_ai"]:
        jv = answers.get(dim, {})
        prob = jv.get("noul", 0.5)
        conf = jv.get("confidence", 1.0)
        if conf >= JEV_CONFIDENCE_LOW:
            # 优化1: event_type=monetary 时涉利率阈值补偿
            if dim == "involves_rate":
                et_monetary = (answers.get("event_type", {}).get("choice") == "monetary")
                flag = prob > NOUL_THRESHOLD or (prob > MONETARY_RATE_RELAXED_THRESHOLD and et_monetary)
            else:
                flag = prob > NOUL_THRESHOLD
            fused[f"jev_{dim}"] = {
                "probability": prob,
                "confidence": conf,
                "flag": flag,
            }

    # ------------------------
    # 4. policy_certainty —— Jev 独有，直接注入
    # ------------------------
    pc = answers.get("policy_certainty", {})
    if pc.get("confidence", 0) >= JEV_CONFIDENCE_LOW:
        pc_idx = max(0, min(4, int(pc.get("score", 2) or 2)))   # score 是 float，必须 int() 后索引
        fused["policy_certainty"] = {
            "score": pc.get("score"),          # 0~4 (float)
            "confidence": pc.get("confidence"),
            "level": CERTAINTY_LEGEND[pc_idx],
        }

    # ------------------------
    # 5. nonlinear —— 最关键：L3 回路入口标记
    # ------------------------
    nl = answers.get("nonlinear", {})
    nl_prob = nl.get("noul", 0.0)
    nl_conf = nl.get("confidence", 1.0)
    if nl_conf >= JEV_CONFIDENCE_LOW:
        fused["nonlinear_signal"] = {
            "probability": nl_prob,
            "confidence": nl_conf,
            "flag": nl_prob > NONLINEAR_FLAG_THRESHOLD,
        }
        if nl_prob > NONLINEAR_FLAG_THRESHOLD:
            base_confidence = min(0.99, base_confidence + BOOST_DELTA / 2)
            fused["l3_priority"] = "high"

    # ------------------------
    # 6. 情绪 × 确定性 交叉标记（优化3）
    # ------------------------
    if "policy_certainty" in fused and (cls or "sentiment" in llm_result):
        pc_score = max(0, min(4, int(pc.get("score", 2) or 2)))
        cross_flags = []
        if llm_sent <= 1 and pc_score >= 4:
            cross_flags.append("black_swan_confirmed")  # 恐慌 + 已官宣 = 黑天鹅确认
        if llm_sent >= 5 and pc_score <= 1:
            cross_flags.append("bubble_narrative")      # 狂热 + 纯传闻 = 泡沫叙事
        if cross_flags:
            fused["cross_signals"] = cross_flags
            base_confidence = min(0.99, base_confidence + BOOST_DELTA / 2)

    # ------------------------
    # 收尾
    # ------------------------
    fused["confidence"] = round(base_confidence, 3)
    fused["conflict_flags"] = conflict_flags

    return fused


# ---------------------------------------------------------------------------
# 问题1: Jev 信号下推到 L3 / L4
# ---------------------------------------------------------------------------

def apply_to_l3_l4(fused: Dict[str, Any], l3_body: Dict[str, Any]) -> Dict[str, Any]:
    """当 nonlinear flag=True 时，把 Jev 信号下推到 L3 请求体/结果。

    Args:
        fused: fuse_l2() 输出（含 nonlinear_signal）
        l3_body: L3 请求体（{"points": [...]}）或 L3 结果 dict

    Returns:
        dict: 注入后的副本；nonlinear flag 不成立时原样返回副本
              - l3_priority: "high"
              - jev_nonlinear_prior: Jev nonlinear noul 概率（供后续消费）
    """
    body = dict(l3_body) if isinstance(l3_body, dict) else {}
    sig = fused.get("nonlinear_signal") or {}
    if sig.get("flag"):
        body["l3_priority"] = "high"
        body["jev_nonlinear_prior"] = sig.get("probability")
        body["jev_nonlinear_confidence"] = sig.get("confidence")
    return body


def jev_summary(fused: Dict[str, Any]) -> Dict[str, Any]:
    """从融合结果抽取结构化判断摘要，供 L4 synthesize 的 state["jev"] 使用。"""
    jj = fused.get("jev_judgments") or {}
    et = (jj.get("event_type") or {})
    return {
        "status": fused.get("jev_status", "unknown"),
        "confidence": fused.get("confidence"),
        "event_type": et.get("choice"),
        "event_type_confidence": et.get("confidence"),
        "sentiment_score": (jj.get("sentiment") or {}).get("score"),
        "policy_certainty": fused.get("policy_certainty"),
        "involves_rate": fused.get("jev_involves_rate"),
        "involves_ai": fused.get("jev_involves_ai"),
        "nonlinear_signal": fused.get("nonlinear_signal"),
        "conflict_flags": fused.get("conflict_flags", []),
        "cross_signals": fused.get("cross_signals", []),
    }


# ---------------------------------------------------------------------------
# 便捷封装：单条快讯完整处理
# ---------------------------------------------------------------------------

def process_single(news_text: str, title: str = "", llm_result: Optional[Dict] = None,
                   api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    端到端处理单条快讯：
        1. 调用 Jev
        2. 若提供 llm_result，执行融合
        3. 返回统一 L2 节点

    若 llm_result 为 None，仅返回 Jev 原始结果（方便测试）。
    """
    jev = jev_judge(news_text, title=title, api_key=api_key)

    if llm_result is None:
        return {
            "jev_raw": jev,
            "note": "未提供 LLM 结果，返回 Jev 原始输出",
        }

    return fuse_l2(llm_result, jev)


# ---------------------------------------------------------------------------
# 测试 / 示例
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # 示例快讯
    demo_news = "美联储降息25基点，市场反应超预期，科技股大涨"
    demo_title = "美联储意外降息"

    # 模拟的 LLM 输出（实际接入时替换为真实 LLM 结果）
    demo_llm = {
        "entities": ["美联储", "科技股"],
        "keywords": ["降息", "超预期"],
        "themes": ["货币政策", "市场反应"],
        "sentiment": "positive",
        "insights": ["降息刺激风险偏好", "科技股受益"],
        "investment": "看好科技股",
        "confidence": 0.78,
    }

    print("=" * 60)
    print("Luna SGP × Jev 桥接器 测试")
    print("=" * 60)
    print(f"快讯：{demo_title}")
    print(f"正文：{demo_news}")
    print()

    result = process_single(demo_news, title=demo_title, llm_result=demo_llm)

    if "error" in result:
        print(f"❌ 错误：{result['error']}")
        sys.exit(1)

    print("📊 融合结果")
    print("-" * 60)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("-" * 60)

    # 简要解读
    print("\n🔍 关键信号")
    if result.get("conflict_flags"):
        print(f"  ⚠️  冲突标记：{len(result['conflict_flags'])} 处")
        for cf in result["conflict_flags"]:
            print(f"      - {cf['dimension']}: LLM={cf.get('llm') or cf.get('llm_score')} vs Jev={cf.get('jev') or cf.get('jev_score')}")
    else:
        print("  ✅ 无冲突")

    if result.get("nonlinear_signal", {}).get("flag"):
        print(f"  🚨 非线性信号：概率 {result['nonlinear_signal']['probability']:.2f}（L3 高优先级）")
    else:
        print("  ➖ 无非线性信号")

    print(f"\n  综合置信度：{result['confidence']}")
    print(f"  Jev 状态：{result.get('jev_status')}")
