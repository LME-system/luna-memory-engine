#!/usr/bin/env python3
"""
Luna SGP - 测试总结与优化建议
使用 Gemma 4 31B 分析本次测试
"""

import json
import time
import requests
from datetime import datetime

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma4:31b"

def call_gemma(prompt: str, max_tokens: int = 2000) -> str:
    """调用 Gemma 4 31B"""
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
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


def main():
    print("🌙 Luna SGP - 测试总结与优化分析")
    print(f"模型: Gemma 4 31B | 时间: {datetime.now().strftime('%H:%M:%S')}")
    print("="*70)
    
    # 测试数据摘要
    test_summary = """
本次测试数据：
1. 模型尝试：Gemma 4 31B (19GB) - 首次成功，后续超时
2. 模型尝试：Gemma 4 12B (7.6GB) - 返回空响应，正在重新下载
3. 上下文测试：4096 → 2048 → 1024，响应仍被截断或为空
4. 处理时间：31B 约 50-60 秒，12B 约 30-40 秒（但输出异常）
5. 提示策略：JSON 格式要求导致模型困惑，纯文本效果更好
6. 调用方式：API 调用不稳定，命令行 ollama run 更可靠
"""
    
    prompt = f"""你是一个系统优化专家。请基于以下测试数据，分析本地大模型部署的问题，并提出优化建议。

{test_summary}

请从以下维度分析：
1. 模型选择策略（大小 vs 速度 vs 稳定性）
2. 提示工程优化（如何避免 JSON 解析失败）
3. 调用方式优化（API vs 命令行）
4. 上下文窗口优化（4096/2048/1024 的选择）
5. 超时与重试机制设计
6. 备选方案（云端 API 的集成策略）

以结构化方式输出分析结果和建议。"""

    print("\n🔄 调用 Gemma 4 31B 进行分析...")
    print("(预计 60-90 秒)\n")
    
    start = time.time()
    response = call_gemma(prompt, max_tokens=2000)
    elapsed = time.time() - start
    
    print(f"✅ 分析完成 (耗时: {elapsed:.1f}s)")
    print("\n" + "="*70)
    print("📊 Luna SGP 测试总结与优化建议")
    print("="*70)
    print(response)
    print("\n" + "="*70)
    
    # 保存结果
    output = f"/Users/miaoliwang/.openclaw/workspace/luna_sgp_test_summary_{datetime.now().strftime('%H%M%S')}.txt"
    with open(output, 'w', encoding='utf-8') as f:
        f.write("Luna SGP 测试总结与优化建议\n")
        f.write("="*70 + "\n")
        f.write(f"模型: Gemma 4 31B\n")
        f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"耗时: {elapsed:.1f}s\n\n")
        f.write(response)
    
    print(f"💾 已保存: {output}")


if __name__ == "__main__":
    main()
