#!/usr/bin/env python3
"""
Luna SGP - 联合早报处理器 v2
使用 Gemma 4 12B
"""

import json
import time
import requests
from datetime import datetime

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma4:12b"

NEWS = {
    "title": "陈光炎：中国宏观政策已从'发展优先'转向'安全优先'",
    "content": """南洋理工大学经济学荣誉教授陈光炎表示，中国宏观政策已从"发展优先"转向"安全优先"，北京的优先事项不是推动增长，而是增强长期国家实力。

陈光炎指出，刺激措施"从未真正实施过"，北京优先追求的是长期国家实力，即增强中国与美国竞争的长期能力，并在未来二三十年维持这个大战略。

这一转变意味着：
1. 大规模财政刺激不太可能出台
2. 消费和就业不再是首要目标
3. 科技、能源、军工等战略领域将获得优先支持
4. 房地产和传统制造业将面临持续调整

分析人士认为，这种范式转变将对全球供应链、投资决策和地缘政治产生深远影响。投资者需要重新评估中国资产的配置逻辑，从"增长故事"转向"安全叙事"。"""
}


def call_gemma(prompt: str) -> dict:
    """调用 Gemma 4 12B"""
    resp = requests.post(OLLAMA_URL, json={
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"num_ctx": 4096, "temperature": 0.3, "num_predict": 1500}
    }, timeout=120)
    
    if resp.status_code == 200:
        return resp.json()
    return {"error": resp.status_code}


def main():
    print("🌙 Luna SGP v4.2.0 - 联合早报分析")
    print(f"模型: Gemma 4 12B | 时间: {datetime.now().strftime('%H:%M:%S')}")
    print("="*70)
    
    prompt = f"""你是一个战略分析专家。请分析以下新闻，使用 Luna SGP (Semantic Graph Processing) 四层语义推理框架。

【新闻标题】
{NEWS['title']}

【新闻内容】
{NEWS['content']}

请执行以下分析并以 JSON 格式返回：

{{
    "L1_symbolic": {{
        "entities": [{{"name": "实体名", "type": "PERSON/ORG/GPE", "role": "角色描述"}}],
        "keywords": ["关键词1", "关键词2", "关键词3"],
        "concepts": ["核心概念1", "概念2"],
        "sentiment": "positive/negative/neutral"
    }},
    "L2_geometric": {{
        "macro_themes": ["宏观主题1", "主题2", "主题3"],
        "complexity_score": 8,
        "semantic_summary": "50字以内的语义摘要"
    }},
    "L3_topological": {{
        "relations": [{{"source": "实体A", "target": "实体B", "relation": "影响/控制/竞争"}}],
        "causal_chains": [["原因", "过程", "结果"]],
        "systemic_impacts": [{{"domain": "领域", "impact": "影响描述", "severity": "high/medium/low"}}]
    }},
    "L4_orchestration": {{
        "complexity_level": "high/medium/low",
        "key_insights": ["核心洞察1", "洞察2", "洞察3", "洞察4"],
        "investment_implications": "投资含义简述",
        "critical_variables": ["关键变量1", "变量2", "变量3"],
        "recommended_actions": "建议行动"
    }}
}}

只返回 JSON，不要其他解释。"""

    print("\n🔄 执行 Luna SGP 四层推理...")
    start = time.time()
    result = call_gemma(prompt)
    elapsed = time.time() - start
    
    if "error" in result:
        print(f"❌ 错误: {result['error']}")
        return
    
    response_text = result.get("response", "")
    
    # 解析 JSON
    try:
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        data = json.loads(response_text[json_start:json_end])
    except:
        print("⚠️ JSON 解析失败，显示原始响应:")
        print(response_text[:500])
        return
    
    # 打印报告
    print(f"\n✅ 分析完成 (耗时: {elapsed:.1f}s)")
    print("\n" + "="*70)
    print("📊 Luna SGP (NeuroRAG) 分析报告")
    print("="*70)
    
    # L1
    l1 = data.get("L1_symbolic", {})
    print("\n【L1 符号层 - 实体与概念】")
    print(f"  关键实体:")
    for e in l1.get("entities", [])[:4]:
        print(f"    • {e.get('name', 'N/A')} ({e.get('type', 'N/A')}) - {e.get('role', '')}")
    print(f"  关键词: {', '.join(l1.get('keywords', [])[:6])}")
    print(f"  核心概念: {', '.join(l1.get('concepts', [])[:3])}")
    print(f"  情感倾向: {l1.get('sentiment', 'N/A')}")
    
    # L2
    l2 = data.get("L2_geometric", {})
    print("\n【L2 几何层 - 语义分析】")
    print(f"  宏观主题: {', '.join(l2.get('macro_themes', []))}")
    print(f"  复杂度评分: {l2.get('complexity_score', 'N/A')}/10")
    print(f"  语义摘要: {l2.get('semantic_summary', 'N/A')}")
    
    # L3
    l3 = data.get("L3_topological", {})
    print("\n【L3 拓扑层 - 系统影响】")
    print(f"  关系网络 ({len(l3.get('relations', []))} 条):")
    for r in l3.get("relations", [])[:3]:
        print(f"    • {r.get('source')} → {r.get('target')}: {r.get('relation')}")
    print(f"  因果链: {len(l3.get('causal_chains', []))} 条")
    print(f"  系统性影响:")
    for imp in l3.get("systemic_impacts", [])[:3]:
        print(f"    • {imp.get('domain')}: {imp.get('impact')} (严重度: {imp.get('severity')})")
    
    # L4
    l4 = data.get("L4_orchestration", {})
    print("\n【L4 编排层 - 综合洞察】")
    level = l4.get("complexity_level", "N/A")
    emoji = "🔴" if level == "high" else "🟡" if level == "medium" else "🟢"
    print(f"  复杂度定级: {emoji} {level.upper()}")
    print(f"\n  核心洞察:")
    for i, insight in enumerate(l4.get("key_insights", [])[:4], 1):
        print(f"    {i}. {insight}")
    print(f"\n  投资含义: {l4.get('investment_implications', 'N/A')}")
    print(f"\n  关键变量: {', '.join(l4.get('critical_variables', [])[:3])}")
    print(f"\n  建议行动: {l4.get('recommended_actions', 'N/A')}")
    
    print("\n" + "="*70)
    
    # 保存
    output_file = f"/Users/miaoliwang/.openclaw/workspace/luna_sgp_report_{datetime.now().strftime('%H%M%S')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 报告已保存: {output_file}")


if __name__ == "__main__":
    main()
