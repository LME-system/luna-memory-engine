#!/usr/bin/env python3
"""
Luna SGP - 联合早报新闻处理器 (Gemma 4 12B 版)
================================================

使用 Gemma 4 12B (7.6GB) 替代 31B，速度更快
"""

import json
import time
import requests
from datetime import datetime

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "gemma4:12b"  # 使用 12B 模型


def call_gemma(prompt: str, max_tokens: int = 2000) -> str:
    """调用 Gemma 4 12B"""
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
            timeout=120
        )
        
        if response.status_code == 200:
            return response.json().get("response", "")
        return f"Error: HTTP {response.status_code}"
    except Exception as e:
        return f"Error: {str(e)}"


def analyze_news(title: str, content: str) -> dict:
    """单层 Luna SGP 分析"""
    prompt = f"""你是一个战略分析专家，使用 Luna SGP 四层语义推理框架分析新闻。

标题: {title}
内容: {content[:1500]}

以 JSON 返回分析结果：
{{
    "L1": {{"entities": [{{"name": "实体", "type": "类型", "role": "角色"}}], "keywords": ["关键词"], "sentiment": "情感"}},
    "L2": {{"themes": ["主题"], "complexity": 7, "summary": "摘要"}},
    "L3": {{"relations": [{{"source": "A", "target": "B", "relation": "关系"}}], "causal_chains": [["因果链"]], "impacts": [{{"domain": "领域", "impact": "影响"}}]}},
    "L4": {{"complexity": "high/medium/low", "insights": ["洞察"], "investment": "投资含义", "variables": ["变量"], "actions": "建议"}}
}}

只返回 JSON。"""

    print("🌙 Luna SGP 分析中 (Gemma 4 12B)...")
    start = time.time()
    response = call_gemma(prompt, max_tokens=2000)
    elapsed = time.time() - start
    print(f"   耗时: {elapsed:.1f}s")
    
    try:
        json_start = response.find('{')
        json_end = response.rfind('}') + 1
        if json_start >= 0:
            result = json.loads(response[json_start:json_end])
            result["_time"] = f"{elapsed:.1f}s"
            return result
    except:
        pass
    
    return {"raw": response[:500], "_time": f"{elapsed:.1f}s"}


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
    print("🌙 Luna SGP v4.2.0 | Gemma 4 12B")
    print(f"时间: {datetime.now().strftime('%H:%M:%S')}")
    print("-"*60)
    
    result = analyze_news(NEWS["title"], NEWS["content"])
    
    # 打印结果
    print("\n📊 Luna SGP 分析报告")
    print("="*60)
    print(f"处理时间: {result.get('_time', 'N/A')}")
    
    l1 = result.get("L1", {})
    print(f"\n【L1 符号层】")
    print(f"  实体: {', '.join([e['name'] for e in l1.get('entities', [])[:3]])}")
    print(f"  关键词: {', '.join(l1.get('keywords', [])[:5])}")
    
    l2 = result.get("L2", {})
    print(f"\n【L2 几何层】")
    print(f"  主题: {', '.join(l2.get('themes', [])[:3])}")
    print(f"  复杂度: {l2.get('complexity', 'N/A')}/10")
    
    l3 = result.get("L3", {})
    print(f"\n【L3 拓扑层】")
    print(f"  关系: {len(l3.get('relations', []))}")
    print(f"  因果链: {len(l3.get('causal_chains', []))}")
    
    l4 = result.get("L4", {})
    print(f"\n【L4 编排层】")
    print(f"  定级: {l4.get('complexity', 'N/A')}")
    print(f"\n  核心洞察:")
    for i, ins in enumerate(l4.get("insights", [])[:3], 1):
        print(f"    {i}. {ins}")
    print(f"\n  投资含义: {l4.get('investment', 'N/A')}")
    
    print("\n" + "="*60)
    
    # 保存
    output = f"/Users/miaoliwang/.openclaw/workspace/luna_sgp_12b_{datetime.now().strftime('%H%M%S')}.json"
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"💾 已保存: {output}")
