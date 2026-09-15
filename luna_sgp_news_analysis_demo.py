#!/usr/bin/env python3
"""
Luna SGP 全球资讯处理演示
==========================

模拟 Luna SGP 如何处理和分析全球新闻资讯
展示激励/抑制模块的实际应用

Author: 阿月
Date: 2026-08-28
"""

import sys
sys.path.insert(0, '/Users/miaoliwang/.openclaw/workspace')

from luna_sgp_inhibition_module import InhibitionEngine, SignalType
import time
import random


def simulate_news_fetch():
    """模拟获取全球新闻"""
    
    news_items = [
        {
            "id": "news_001",
            "headline": "Norway's King Harald V dies at 89, son becomes King Haakon VIII",
            "category": "politics",
            "region": "europe",
            "source": "AP News",
            "timestamp": time.time(),
            "complexity": 1,  # 中等复杂度
            "entities": ["Norway", "King Harald V", "King Haakon VIII", "monarchy"]
        },
        {
            "id": "news_002", 
            "headline": "Death toll rises in Nepal-China border disaster as lake poses new flood threat",
            "category": "disaster",
            "region": "asia",
            "source": "AP News",
            "timestamp": time.time(),
            "complexity": 2,  # 高复杂度 - 涉及地缘政治+环境
            "entities": ["Nepal", "China", "Tibet", "glacier", "flood", "climate"]
        },
        {
            "id": "news_003",
            "headline": "White House construction contributed to radio problems that let Trump copter come close to jet",
            "category": "security",
            "region": "us",
            "source": "AP News", 
            "timestamp": time.time(),
            "complexity": 1,
            "entities": ["White House", "Trump", "Marine One", "NTSB", "aviation"]
        },
        {
            "id": "news_004",
            "headline": "ICE officer's release from Texas jail opens new front in escalating fight over extradition",
            "category": "legal",
            "region": "us",
            "source": "AP News",
            "timestamp": time.time(),
            "complexity": 2,
            "entities": ["ICE", "Texas", "Minnesota", "extradition", "immigration"]
        },
        {
            "id": "news_005",
            "headline": "Tropical Storms Karina and Lowell form in Pacific as Dolly churns in Atlantic",
            "category": "weather",
            "region": "global",
            "source": "AP News",
            "timestamp": time.time(),
            "complexity": 0,  # 低复杂度
            "entities": ["tropical storm", "Karina", "Lowell", "Dolly", "hurricane"]
        }
    ]
    
    return news_items


def luna_sgp_analyze(news_item: dict, engine: InhibitionEngine) -> dict:
    """
    Luna SGP 分析单条新闻
    
    展示四层架构如何处理资讯
    """
    print(f"\n{'='*60}")
    print(f"📰 分析新闻: {news_item['headline'][:50]}...")
    print(f"{'='*60}")
    
    # L1: 符号层 - 实体提取与分类
    print("\n🔍 L1 (符号层): 实体提取")
    l1_result = {
        "entities": news_item["entities"],
        "category": news_item["category"],
        "region": news_item["region"],
        "contribution": 0.3
    }
    print(f"   实体: {', '.join(news_item['entities'])}")
    print(f"   分类: {news_item['category']} | 区域: {news_item['region']}")
    
    # L2: 几何层 - 语义相似度与重要性评估
    print("\n📐 L2 (几何层): 重要性投影")
    
    # 基于复杂度计算重要性向量
    importance_factors = {
        "complexity": news_item["complexity"] / 2.0,  # 0-1
        "regional_relevance": 0.7 if news_item["region"] in ["asia", "us", "europe"] else 0.4,
        "category_priority": 0.8 if news_item["category"] in ["politics", "security", "disaster"] else 0.5
    }
    
    importance_vector = sum(importance_factors.values()) / len(importance_factors)
    
    l2_result = {
        "importance_vector": importance_vector,
        "factors": importance_factors,
        "contribution": 0.4
    }
    print(f"   重要性评分: {importance_vector:.2f}")
    print(f"   因素: 复杂度={importance_factors['complexity']:.2f}, "
          f"区域相关={importance_factors['regional_relevance']:.2f}, "
          f"类别优先={importance_factors['category_priority']:.2f}")
    
    # L3: 拓扑层 - 关系网络与模式识别
    print("\n🌀 L3 (拓扑层): 关系拓扑分析")
    
    # 检测模式
    patterns = []
    if news_item["category"] == "disaster" and "climate" in news_item["entities"]:
        patterns.append("climate_disaster_pattern")
    if news_item["category"] == "politics" and "monarchy" in news_item["entities"]:
        patterns.append("political_succession_pattern")
    if news_item["category"] == "security":
        patterns.append("security_incident_pattern")
    
    l3_result = {
        "patterns": patterns,
        "criticality": "high" if importance_vector > 0.7 else "medium" if importance_vector > 0.5 else "low",
        "contribution": 0.3
    }
    print(f"   检测模式: {patterns}")
    print(f"   紧急程度: {l3_result['criticality']}")
    
    # L4: 编排层 - 综合决策
    print("\n🎯 L4 (编排层): 综合决策")
    
    # 决定是否深入分析
    should_deep_analyze = importance_vector > 0.6 or len(patterns) > 0
    
    l4_decision = {
        "action": "deep_analyze" if should_deep_analyze else "brief_summary",
        "priority": l3_result["criticality"],
        "layers_used": ["L1", "L2", "L3"] if should_deep_analyze else ["L1", "L2"]
    }
    print(f"   决策: {l4_decision['action']}")
    print(f"   优先级: {l4_decision['priority']}")
    print(f"   使用层: {', '.join(l4_decision['layers_used'])}")
    
    # 记录认知痕迹 (激励/抑制模块)
    print("\n🧠 记录认知痕迹...")
    
    latency_ms = random.randint(100, 500)  # 模拟处理延迟
    
    trace = engine.perceive_interaction(
        query=news_item["headline"],
        l1_result=l1_result,
        l2_result=l2_result,
        l3_result=l3_result,
        latency_ms=latency_ms,
        confidence=importance_vector,
        tags=[news_item["category"], news_item["region"]]
    )
    
    print(f"   Trace ID: {trace.trace_id}")
    print(f"   自我评分: {trace.self_score:.2f}")
    print(f"   一致性: {trace.coherence:.2f}")
    
    # 自我评价
    evaluation = engine.self_evaluate(trace.trace_id)
    print(f"\n📊 自我评价:")
    print(f"   总体评分: {evaluation['overall_score']:.2f}")
    print(f"   建议: {evaluation['recommendations']}")
    
    # 应用激励/抑制
    if evaluation["overall_score"] > 0.7:
        signal_result = engine.apply_signal(
            trace.trace_id,
            SignalType.EXCITATION,
            magnitude=0.2,
            reason=f"High-quality analysis of {news_item['category']} news"
        )
        print(f"\n🟢 应用激励: {signal_result['pathway_id']} (新权重: {signal_result['new_weight']:.2f})")
    elif evaluation["overall_score"] < 0.4:
        signal_result = engine.apply_signal(
            trace.trace_id,
            SignalType.INHIBITION,
            magnitude=0.15,
            reason="Low-quality analysis"
        )
        print(f"\n🔴 应用抑制: {signal_result['pathway_id']} (新权重: {signal_result['new_weight']:.2f})")
    
    return {
        "news_id": news_item["id"],
        "trace_id": trace.trace_id,
        "importance": importance_vector,
        "decision": l4_decision,
        "evaluation": evaluation
    }


def generate_digest(results: list, engine: InhibitionEngine) -> str:
    """生成资讯摘要"""
    
    print("\n" + "="*60)
    print("📋 LUNA SGP 全球资讯摘要")
    print("="*60)
    
    # 分类统计
    high_priority = [r for r in results if r["decision"]["priority"] == "high"]
    medium_priority = [r for r in results if r["decision"]["priority"] == "medium"]
    low_priority = [r for r in results if r["decision"]["priority"] == "low"]
    
    digest = f"""
分析完成: {len(results)} 条新闻

🔴 高优先级 ({len(high_priority)}):
"""
    for r in high_priority:
        digest += f"   • {r['news_id']} - 重要性: {r['importance']:.2f}\n"
    
    digest += f"""
🟡 中优先级 ({len(medium_priority)}):
"""
    for r in medium_priority:
        digest += f"   • {r['news_id']} - 重要性: {r['importance']:.2f}\n"
    
    digest += f"""
🟢 低优先级 ({len(low_priority)}):
"""
    for r in low_priority:
        digest += f"   • {r['news_id']} - 重要性: {r['importance']:.2f}\n"
    
    # 学习总结
    learning = engine.get_learning_summary()
    digest += f"""

📈 学习状态:
   平均自我评分: {learning['overall_metrics']['avg_self_score']:.3f}
   平均延迟: {learning['overall_metrics']['avg_latency_ms']:.1f}ms
   趋势: {learning['improvement_trend']}
"""
    
    return digest


def main():
    print("="*60)
    print("🌙 Luna SGP 全球资讯处理演示")
    print("="*60)
    print("\n初始化激励/抑制引擎...")
    
    # 初始化引擎
    engine = InhibitionEngine()
    
    # 获取新闻
    print("\n📡 获取全球新闻...")
    news_items = simulate_news_fetch()
    print(f"获取到 {len(news_items)} 条新闻")
    
    # 分析每条新闻
    results = []
    for news in news_items:
        result = luna_sgp_analyze(news, engine)
        results.append(result)
        time.sleep(0.5)  # 模拟处理间隔
    
    # 生成摘要
    digest = generate_digest(results, engine)
    print(digest)
    
    # 路径权重状态
    print("\n" + "="*60)
    print("🛤️  路径权重状态")
    print("="*60)
    
    for pathway_id, stats in engine.get_learning_summary()["pathway_performance"].items():
        print(f"   {pathway_id}: 权重={stats['current_weight']:.2f}, "
              f"成功率={stats['success_rate']:.1%}, 使用={stats['total_uses']}次")
    
    print("\n" + "="*60)
    print("✅ 演示完成")
    print("="*60)


if __name__ == "__main__":
    main()
