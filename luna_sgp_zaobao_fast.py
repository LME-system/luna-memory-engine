#!/usr/bin/env python3
"""
Luna SGP - 联合早报新闻处理器 (快速版)
=====================================

优化版本：单层调用，合并四层分析
大模型: Gemma 4 31B (本地 Ollama)
"""

import json
import time
import requests
from datetime import datetime

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "gemma4:31b"


def call_gemma(prompt: str, max_tokens: int = 2500) -> str:
    """调用 Gemma 4 31B"""
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_ctx": 4096,
                    "temperature": 0.4,
                    "num_predict": max_tokens
                }
            },
            timeout=180
        )
        
        if response.status_code == 200:
            return response.json().get("response", "")
        return f"Error: HTTP {response.status_code}"
    except Exception as e:
        return f"Error: {str(e)}"


def analyze_news(title: str, content: str) -> dict:
    """
    单层 Luna SGP 分析 - 合并四层推理
    """
    prompt = f"""你是一个战略分析专家，使用 Luna SGP (Semantic Graph Processing) 四层语义推理框架分析新闻。

【新闻标题】
{title}

【新闻内容】
{content[:1800]}

请执行以下四层分析，以 JSON 格式返回：

{{
    "L1_symbolic": {{
        "entities": [{{"name": "实体名", "type": "PERSON/ORG/GPE", "role": "角色"}}],
        "keywords": ["关键词1", "关键词2"],
        "concepts": ["核心概念"],
        "sentiment": "positive/negative/neutral"
    }},
    "L2_geometric": {{
        "macro_themes": ["宏观主题1", "主题2"],
        "complexity_score": 7,
        "information_density": 8,
        "semantic_summary": "50字以内语义摘要"
    }},
    "L3_topological": {{
        "relations": [{{"source": "A", "target": "B", "relation": "影响", "strength": 0.8}}],
        "causal_chains": [["原因", "过程", "结果"]],
        "systemic_impacts": [{{"domain": "领域", "impact": "影响", "severity": "high/medium/low"}}]
    }},
    "L4_orchestration": {{
        "complexity_level": "high/medium/low",
        "key_insights": ["洞察1", "洞察2", "洞察3"],
        "investment_implications": "投资含义",
        "critical_variables": ["关键变量1", "变量2"],
        "recommended_actions": "建议行动"
    }}
}}

只返回 JSON，不要其他解释。"""

    print("🌙 Luna SGP 分析中 (单层合并推理)...")
    start = time.time()
    response = call_gemma(prompt, max_tokens=2500)
    elapsed = time.time() - start
    
    # 解析 JSON
    try:
        json_start = response.find('{')
        json_end = response.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            result = json.loads(response[json_start:json_end])
            result["_processing_time"] = f"{elapsed:.1f}s"
            return result
    except Exception as e:
        print(f"解析错误: {e}")
    
    return {"raw": response, "_processing_time": f"{elapsed:.1f}s"}


def print_report(result: dict, title: str):
    """打印分析报告"""
    print("\n" + "="*70)
    print("📊 Luna SGP (NeuroRAG) 分析报告")
    print("="*70)
    print(f"标题: {title}")
    print(f"处理时间: {result.get('_processing_time', 'N/A')}")
    
    # L1
    l1 = result.get("L1_symbolic", {})
    print("\n【L1 符号层】")
    print(f"  实体: {', '.join([e['name'] for e in l1.get('entities', [])[:5]])}")
    print(f"  关键词: {', '.join(l1.get('keywords', [])[:8])}")
    print(f"  情感: {l1.get('sentiment', 'N/A')}")
    
    # L2
    l2 = result.get("L2_geometric", {})
    print("\n【L2 几何层】")
    print(f"  主题: {', '.join(l2.get('macro_themes', [])[:3])}")
    print(f"  复杂度: {l2.get('complexity_score', 'N/A')}/10")
    print(f"  摘要: {l2.get('semantic_summary', 'N/A')}")
    
    # L3
    l3 = result.get("L3_topological", {})
    print("\n【L3 拓扑层】")
    print(f"  关系数: {len(l3.get('relations', []))}")
    print(f"  因果链: {len(l3.get('causal_chains', []))}")
    impacts = l3.get("systemic_impacts", [])
    if impacts:
        print(f"  系统性影响:")
        for imp in impacts[:3]:
            print(f"    • {imp.get('domain', 'N/A')}: {imp.get('impact', 'N/A')}")
    
    # L4
    l4 = result.get("L4_orchestration", {})
    print("\n【L4 编排层】")
    print(f"  复杂度定级: {l4.get('complexity_level', 'N/A')}")
    print(f"\n  核心洞察:")
    for i, insight in enumerate(l4.get("key_insights", [])[:5], 1):
        print(f"    {i}. {insight}")
    
    print(f"\n  投资含义:")
    print(f"    {l4.get('investment_implications', 'N/A')}")
    
    print(f"\n  关键变量:")
    for var in l4.get("critical_variables", [])[:3]:
        print(f"    • {var}")
    
    print("\n" + "="*70)


# 示例新闻
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


if __name__ == "__main__":
    print("🌙 Luna SGP v4.2.0 - 联合早报新闻处理器 (快速版)")
    print(f"大模型: Gemma 4 31B | 时间: {datetime.now().strftime('%H:%M:%S')}")
    print("-"*70)
    
    result = analyze_news(NEWS["title"], NEWS["content"])
    print_report(result, NEWS["title"])
    
    # 保存
    output = f"~/.openclaw/workspace/luna_sgp_zaobao_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output.replace("~", "/Users/miaoliwang"), 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"💾 已保存: {output}")
