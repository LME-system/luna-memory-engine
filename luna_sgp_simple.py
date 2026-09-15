#!/usr/bin/env python3
"""
Luna SGP - 简化版联合早报处理器
使用 Gemma 4 12B，单次调用，简化输出
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

这一转变意味着大规模财政刺激不太可能出台，消费和就业不再是首要目标，科技、能源、军工等战略领域将获得优先支持。"""
}


def analyze():
    print("🌙 Luna SGP 简化版 | Gemma 4 12B")
    print(f"时间: {datetime.now().strftime('%H:%M:%S')}")
    print("-"*60)
    
    prompt = f"""分析新闻，输出JSON：
标题：{NEWS['title']}
内容：{NEWS['content'][:500]}

输出格式：
{{
"entities": ["实体1", "实体2"],
"keywords": ["关键词1", "关键词2"],
"themes": ["主题1", "主题2"],
"sentiment": "positive/negative/neutral",
"insights": ["洞察1", "洞察2", "洞察3"],
"investment": "投资含义"
}}"""

    print("🔄 调用 Gemma 4 12B...")
    start = time.time()
    
    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"num_ctx": 2048, "temperature": 0.3, "num_predict": 800}
        }, timeout=90)
        
        elapsed = time.time() - start
        
        if resp.status_code == 200:
            text = resp.json().get("response", "")
            # 提取 JSON
            jstart = text.find('{')
            jend = text.rfind('}') + 1
            if jstart >= 0:
                result = json.loads(text[jstart:jend])
                print(f"\n✅ 完成 ({elapsed:.1f}s)\n")
                
                print("📊 Luna SGP 分析结果")
                print("="*60)
                print(f"实体: {', '.join(result.get('entities', [])[:5])}")
                print(f"关键词: {', '.join(result.get('keywords', [])[:6])}")
                print(f"主题: {', '.join(result.get('themes', [])[:3])}")
                print(f"情感: {result.get('sentiment', 'N/A')}")
                print(f"\n核心洞察:")
                for i, ins in enumerate(result.get('insights', [])[:3], 1):
                    print(f"  {i}. {ins}")
                print(f"\n投资含义: {result.get('investment', 'N/A')}")
                print("="*60)
                return
        
        print(f"⚠️  错误: {resp.status_code}")
        
    except Exception as e:
        print(f"❌ 异常: {e}")


if __name__ == "__main__":
    analyze()
