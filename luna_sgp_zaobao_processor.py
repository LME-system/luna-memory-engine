#!/usr/bin/env python3
"""
Luna SGP - 联合早报新闻处理器
=============================

使用 Luna SGP 四层语义推理系统处理联合早报新闻
- L1 符号层: 实体提取、关键词识别
- L2 几何层: 向量嵌入、语义相似度
- L3 拓扑层: 关系图谱、因果链
- L4 编排层: 动态规划、策略选择

大模型: Gemma 4 31B (本地 Ollama)
"""

import json
import time
import requests
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

# =============================================================================
# 配置
# =============================================================================
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "gemma4:31b"

# =============================================================================
# 数据结构
# =============================================================================

@dataclass
class SGPAnalysisResult:
    """Luna SGP 分析结果"""
    # L1: 符号层
    entities: List[Dict[str, Any]] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    concepts: List[str] = field(default_factory=list)
    
    # L2: 几何层
    semantic_embedding: Optional[List[float]] = None
    similarity_scores: Dict[str, float] = field(default_factory=dict)
    
    # L3: 拓扑层
    relations: List[Dict[str, Any]] = field(default_factory=list)
    causal_chains: List[List[str]] = field(default_factory=list)
    
    # L4: 编排层
    complexity: int = 0  # 0=低, 1=中, 2=高
    routing_decision: str = ""
    final_insight: str = ""
    
    # 元数据
    processing_time_ms: float = 0.0
    timestamp: str = ""


# =============================================================================
# Gemma 调用封装
# =============================================================================

def call_gemma(prompt: str, max_tokens: int = 2000, temperature: float = 0.7) -> str:
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
                    "temperature": temperature,
                    "num_predict": max_tokens
                }
            },
            timeout=120
        )
        
        if response.status_code == 200:
            result = response.json()
            return result.get("response", "")
        else:
            return f"Error: HTTP {response.status_code}"
    except Exception as e:
        return f"Error: {str(e)}"


# =============================================================================
# L1: 符号层 - 实体与概念提取
# =============================================================================

def layer1_symbolic_analysis(news_text: str, title: str) -> Dict[str, Any]:
    """
    L1 符号层分析
    - 提取命名实体（人名、机构、地点）
    - 识别关键词
    - 提取核心概念
    """
    prompt = f"""你是一个专业的信息提取专家。请分析以下新闻内容，提取关键信息。

【新闻标题】
{title}

【新闻内容】
{news_text[:2000]}

请提取以下信息，以 JSON 格式返回：
{{
    "entities": [
        {{"name": "实体名称", "type": "PERSON/ORG/LOCATION/GPE", "role": "角色描述"}}
    ],
    "keywords": ["关键词1", "关键词2", ...],
    "concepts": ["核心概念1", "核心概念2", ...],
    "sentiment": "positive/negative/neutral",
    "topic": "主要话题"
}}

只返回 JSON，不要其他解释。"""

    response = call_gemma(prompt, max_tokens=1500, temperature=0.3)
    
    # 尝试解析 JSON
    try:
        # 提取 JSON 部分
        json_start = response.find('{')
        json_end = response.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            json_str = response[json_start:json_end]
            return json.loads(json_str)
    except:
        pass
    
    # 如果解析失败，返回原始响应
    return {
        "raw_response": response,
        "entities": [],
        "keywords": [],
        "concepts": []
    }


# =============================================================================
# L2: 几何层 - 语义嵌入与相似度
# =============================================================================

def layer2_geometric_analysis(news_text: str, l1_result: Dict) -> Dict[str, Any]:
    """
    L2 几何层分析
    - 生成语义摘要
    - 评估与历史话题的相似度
    - 识别语义聚类
    """
    keywords = ", ".join(l1_result.get("keywords", [])[:10])
    
    prompt = f"""你是一个语义分析专家。请分析以下新闻的语义特征。

【新闻内容摘要】
{news_text[:1500]}

【已提取关键词】
{keywords}

请分析：
1. 这篇新闻与哪些宏观主题最相关？（如：中美关系、科技竞争、能源安全、货币政策等）
2. 语义复杂度评分（1-10）
3. 信息密度评分（1-10）
4. 与以下历史话题的关联度（0-1）：
   - 中美贸易战
   - 科技脱钩
   - 能源转型
   - 货币政策
   - 地缘政治

以 JSON 格式返回：
{{
    "macro_themes": ["主题1", "主题2"],
    "complexity_score": 7,
    "information_density": 8,
    "historical_similarity": {{
        "trade_war": 0.6,
        "tech_decoupling": 0.4,
        "energy_transition": 0.3,
        "monetary_policy": 0.5,
        "geopolitics": 0.7
    }},
    "semantic_summary": "50字以内的语义摘要"
}}

只返回 JSON。"""

    response = call_gemma(prompt, max_tokens=1000, temperature=0.3)
    
    try:
        json_start = response.find('{')
        json_end = response.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            return json.loads(response[json_start:json_end])
    except:
        pass
    
    return {"raw_response": response}


# =============================================================================
# L3: 拓扑层 - 关系网络与因果链
# =============================================================================

def layer3_topological_analysis(news_text: str, l1_result: Dict, l2_result: Dict) -> Dict[str, Any]:
    """
    L3 拓扑层分析
    - 构建实体关系网络
    - 识别因果链
    - 检测系统性影响
    """
    entities = l1_result.get("entities", [])
    themes = l2_result.get("macro_themes", [])
    
    prompt = f"""你是一个系统思维分析专家。请分析以下新闻的系统性影响。

【新闻内容】
{news_text[:1500]}

【关键实体】
{json.dumps(entities, ensure_ascii=False, indent=2)}

【宏观主题】
{json.dumps(themes, ensure_ascii=False)}

请分析：
1. 实体之间的关系网络（谁影响谁）
2. 因果链条（事件A → 事件B → 结果C）
3. 系统性影响（对哪些领域/市场/国家有影响）
4. 潜在的二阶效应（连锁反应）

以 JSON 格式返回：
{{
    "relations": [
        {{"source": "实体A", "target": "实体B", "relation": "影响/控制/竞争", "strength": 0.8}}
    ],
    "causal_chains": [
        ["事件1", "事件2", "结果"]
    ],
    "systemic_impacts": [
        {{"domain": "领域", "impact": "影响描述", "severity": "high/medium/low"}}
    ],
    "second_order_effects": ["效应1", "效应2"]
}}

只返回 JSON。"""

    response = call_gemma(prompt, max_tokens=1500, temperature=0.4)
    
    try:
        json_start = response.find('{')
        json_end = response.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            return json.loads(response[json_start:json_end])
    except:
        pass
    
    return {"raw_response": response}


# =============================================================================
# L4: 编排层 - 综合决策与洞察生成
# =============================================================================

def layer4_orchestration(news_text: str, title: str, 
                         l1_result: Dict, l2_result: Dict, l3_result: Dict) -> Dict[str, Any]:
    """
    L4 编排层
    - 综合各层分析结果
    - 生成最终洞察
    - 决定输出策略
    """
    
    # 计算复杂度
    complexity = l2_result.get("complexity_score", 5)
    if complexity >= 7:
        complexity_level = 2  # 高
    elif complexity >= 4:
        complexity_level = 1  # 中
    else:
        complexity_level = 0  # 低
    
    prompt = f"""你是一个战略分析专家。请基于以下多层分析结果，生成综合洞察。

【原始新闻】
标题: {title}
内容: {news_text[:1000]}

【L1 符号层 - 实体与概念】
- 实体: {json.dumps(l1_result.get("entities", []), ensure_ascii=False)}
- 关键词: {l1_result.get("keywords", [])}
- 概念: {l1_result.get("concepts", [])}
- 情感: {l1_result.get("sentiment", "neutral")}

【L2 几何层 - 语义分析】
- 宏观主题: {l2_result.get("macro_themes", [])}
- 复杂度: {complexity}/10
- 历史相似度: {json.dumps(l2_result.get("historical_similarity", {}), ensure_ascii=False)}
- 语义摘要: {l2_result.get("semantic_summary", "")}

【L3 拓扑层 - 系统影响】
- 关系网络: {len(l3_result.get("relations", []))} 条关系
- 因果链: {len(l3_result.get("causal_chains", []))} 条
- 系统性影响: {json.dumps(l3_result.get("systemic_impacts", [])[:3], ensure_ascii=False)}

请生成：
1. 核心洞察（3-5条，每条配证据）
2. 投资含义（如果有）
3. 需要关注的关键变量
4. 建议的后续行动

以结构化文本返回，使用 Markdown 格式。"""

    final_insight = call_gemma(prompt, max_tokens=2000, temperature=0.5)
    
    return {
        "complexity": complexity_level,
        "routing_decision": "full_pipeline" if complexity_level >= 1 else "fast_track",
        "final_insight": final_insight
    }


# =============================================================================
# 主处理流程
# =============================================================================

def process_zaobao_news(title: str, news_text: str) -> SGPAnalysisResult:
    """
    使用 Luna SGP 处理联合早报新闻
    """
    start_time = time.time()
    result = SGPAnalysisResult()
    result.timestamp = datetime.now().isoformat()
    
    print(f"\n{'='*60}")
    print(f"🌙 Luna SGP 新闻分析")
    print(f"{'='*60}")
    print(f"标题: {title[:80]}...")
    print(f"内容长度: {len(news_text)} 字符")
    print(f"\n开始四层语义推理...\n")
    
    # L1: 符号层
    print("🔹 L1 符号层: 实体提取与概念识别...")
    l1_start = time.time()
    l1_result = layer1_symbolic_analysis(news_text, title)
    result.entities = l1_result.get("entities", [])
    result.keywords = l1_result.get("keywords", [])
    result.concepts = l1_result.get("concepts", [])
    print(f"   ✓ 提取 {len(result.entities)} 个实体, {len(result.keywords)} 个关键词")
    print(f"   ⏱️  {(time.time() - l1_start):.1f}s")
    
    # L2: 几何层
    print("\n🔹 L2 几何层: 语义嵌入与相似度分析...")
    l2_start = time.time()
    l2_result = layer2_geometric_analysis(news_text, l1_result)
    print(f"   ✓ 复杂度评分: {l2_result.get('complexity_score', 'N/A')}/10")
    print(f"   ✓ 相关主题: {', '.join(l2_result.get('macro_themes', [])[:3])}")
    print(f"   ⏱️  {(time.time() - l2_start):.1f}s")
    
    # L3: 拓扑层
    print("\n🔹 L3 拓扑层: 关系网络与因果链...")
    l3_start = time.time()
    l3_result = layer3_topological_analysis(news_text, l1_result, l2_result)
    result.relations = l3_result.get("relations", [])
    result.causal_chains = l3_result.get("causal_chains", [])
    print(f"   ✓ 识别 {len(result.relations)} 个关系, {len(result.causal_chains)} 条因果链")
    print(f"   ⏱️  {(time.time() - l3_start):.1f}s")
    
    # L4: 编排层
    print("\n🔹 L4 编排层: 综合洞察生成...")
    l4_start = time.time()
    l4_result = layer4_orchestration(news_text, title, l1_result, l2_result, l3_result)
    result.complexity = l4_result.get("complexity", 0)
    result.routing_decision = l4_result.get("routing_decision", "")
    result.final_insight = l4_result.get("final_insight", "")
    print(f"   ✓ 复杂度定级: {'高' if result.complexity == 2 else '中' if result.complexity == 1 else '低'}")
    print(f"   ✓ 路由决策: {result.routing_decision}")
    print(f"   ⏱️  {(time.time() - l4_start):.1f}s")
    
    # 完成
    result.processing_time_ms = (time.time() - start_time) * 1000
    print(f"\n{'='*60}")
    print(f"✅ 分析完成 | 总耗时: {result.processing_time_ms/1000:.1f}s")
    print(f"{'='*60}\n")
    
    return result


def print_sgp_report(result: SGPAnalysisResult):
    """打印 Luna SGP 分析报告"""
    print("\n" + "="*60)
    print("📊 Luna SGP (NeuroRAG) 分析报告")
    print("="*60)
    
    print("\n【L1 符号层 - 实体与概念】")
    print(f"关键实体:")
    for entity in result.entities[:5]:
        print(f"  • {entity.get('name', 'N/A')} ({entity.get('type', 'N/A')}) - {entity.get('role', '')}")
    
    print(f"\n关键词: {', '.join(result.keywords[:10])}")
    print(f"核心概念: {', '.join(result.concepts[:5])}")
    
    print("\n【L3 拓扑层 - 关系网络】")
    print(f"关系数量: {len(result.relations)}")
    for rel in result.relations[:3]:
        print(f"  • {rel.get('source')} → {rel.get('target')}: {rel.get('relation')}")
    
    print(f"\n因果链数量: {len(result.causal_chains)}")
    
    print("\n【L4 编排层 - 综合洞察】")
    print(f"复杂度定级: {'🔴 高' if result.complexity == 2 else '🟡 中' if result.complexity == 1 else '🟢 低'}")
    print(f"路由策略: {result.routing_decision}")
    
    print("\n" + "-"*60)
    print("📝 核心洞察:")
    print("-"*60)
    print(result.final_insight)
    
    print("\n" + "="*60)


# =============================================================================
# 示例新闻（联合早报风格）
# =============================================================================

SAMPLE_NEWS = {
    "title": "陈光炎：中国宏观政策已从'发展优先'转向'安全优先'",
    "content": """
南洋理工大学经济学荣誉教授陈光炎表示，中国宏观政策已从"发展优先"转向"安全优先"，
北京的优先事项不是推动增长，而是增强长期国家实力。

陈光炎指出，这些措施"从未真正实施过"，北京优先追求的是长期国家实力，
即增强中国与美国竞争的长期能力，并在未来二三十年维持这个大战略。

这一转变意味着：
1. 大规模财政刺激不太可能出台
2. 消费和就业不再是首要目标
3. 科技、能源、军工等战略领域将获得优先支持
4. 房地产和传统制造业将面临持续调整

分析人士认为，这种范式转变将对全球供应链、投资决策和地缘政治产生深远影响。
投资者需要重新评估中国资产的配置逻辑，从"增长故事"转向"安全叙事"。
"""
}


# =============================================================================
# 主入口
# =============================================================================

if __name__ == "__main__":
    print("🌙 Luna SGP v4.2.0 - 联合早报新闻处理器")
    print(f"大模型: Gemma 4 31B (本地 Ollama)")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 处理示例新闻
    result = process_zaobao_news(SAMPLE_NEWS["title"], SAMPLE_NEWS["content"])
    
    # 打印报告
    print_sgp_report(result)
    
    # 保存结果
    output_file = f"/Users/miaoliwang/.openclaw/workspace/luna_sgp_zaobao_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "timestamp": result.timestamp,
            "processing_time_ms": result.processing_time_ms,
            "entities": result.entities,
            "keywords": result.keywords,
            "concepts": result.concepts,
            "relations": result.relations,
            "causal_chains": result.causal_chains,
            "complexity": result.complexity,
            "routing_decision": result.routing_decision,
            "final_insight": result.final_insight
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 报告已保存: {output_file}")
