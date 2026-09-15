from gemma4_engine import get_gemma_engine

engine = get_gemma_engine()
print(f"Gemma 4 可用: {engine.is_available()}")

# 简单测试
result = engine.generate(
    prompt="分析：美国ADP就业3.7万人创新低。请用中文回复'分析完成'",
    max_tokens=50,
    temperature=0.5
)
print(f"状态: {result['status']}")
print(f"响应: {result['response']}")
print(f"耗时: {result['time']:.1f}s")
