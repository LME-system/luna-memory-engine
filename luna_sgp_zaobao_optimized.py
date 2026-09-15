#!/usr/bin/env python3
"""
Luna SGP - 联合早报处理器 (优化版)
使用 Gemma 4 12B，上下文窗口 2048
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
    """调用 Gemma 4 12B - 优化参数"""
    resp = requests.post(OLLAMA_URL, json={
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_ctx": 2048,  # 从 4096 降到 2048
            "temperature": 0.3,
            "num_predict": 1000  # 减少生成长度
        }
    }, timeout=120)  # 2分钟超时
    
    if resp.status_code == 200:
        return resp.json()
    return {"error": resp.status_code}


def main():
    print("🌙 Luna SGP v4.2.0 - 联合早报分析 (优化版)")
    print(f"模型: Gemma 4 12B | 上下文: 2048 | 时间: {datetime.now().strftime('%H:%M:%S')}")
    print("="*70)
    
    prompt = f"""分析新闻，输出JSON：

标题：{NEWS['title']}
内容：{NEWS['content'][:500]}

输出：
{{
"entities": [{{"name": "实体", "type": "类型", "role": "角色"}}],
"keywords": ["关键词1", "关键词2"],
"themes": ["主题1", "主题2"],
"sentiment": "情感",
"complexity": 7,
"insights": ["洞察1", "洞察2", "洞察3"],
"investment": "投资含义"
}}"""

    print("\n🔄 执行 Luna SGP 分析...")
    print("(上下文 2048，预计 30-50 秒)\n")
    
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
        print("⚠️ 解析失败，显示原始响应:")
        print(response_text[:600])
        return
    
    # 打印报告
    print(f"✅ 完成 (耗时: {elapsed:.1f}s)")
    print("\n" + "="*70)
    print("📊 Luna SGP (NeuroRAG) 分析报告")
    print("="*70)
    
    print(f"\n【L1 符号层】")
    print(f"  实体: {', '.join([e['name'] for e in data.get('entities', [])[:3]])}")
    print(f"  关键词: {', '.join(data.get('keywords', [])[:5])}")
    print(f"  情感: {data.get('sentiment', 'N/A')}")
    
    print(f"\n【L2 几何层】")
    print(f"  主题: {', '.join(data.get('themes', [])[:3])}")
    print(f"  复杂度: {data.get('complexity', 'N/A')}/10")
    
    print(f"\n【L4 编排层】")
    print(f"  核心洞察:")
    for i, ins in enumerate(data.get('insights', [])[:3], 1):
        print(f"    {i}. {ins}")
    print(f"\n  投资含义: {data.get('investment', 'N/A')}")
    
    print("\n" + "="*70)
    
    # 保存
    output = f"/Users/miaoliwang/.openclaw/workspace/luna_sgp_2048_{datetime.now().strftime('%H%M%S')}.json"
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 已保存: {output}")
    
    # 显示性能对比
    print(f"\n📈 性能对比:")
    print(f"  上下文 4096: ~50-60 秒")
    print(f"  上下文 2048: {elapsed:.1f} 秒")
    if elapsed < 50:
        print(f"  ⚡ 提速: {((50-elapsed)/50*100):.0f}%")


if __name__ == "__main__":
    main()
