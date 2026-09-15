# Luna SGP Configuration - Gemma 4 Engine
# 日期: 2026-09-02
# 用途: 指定 Gemma 4 (31B) 作为 Luna SGP 本地推理引擎

# 模型配置
MODEL_CONFIG = {
    "default_engine": "gemma4",  # 默认使用 Gemma 4 本地模型
    "fallback_engine": "kimi",   # 回退到 Kimi (仅在 Gemma 不可用时)
    
    # Gemma 4 配置
    "gemma4": {
        "model_name": "gemma4:31b",
        "api_url": "http://localhost:11434/api/generate",
        "api_type": "ollama",
        "context_window": 131072,  # 128K context
        "max_tokens": 8192,
        "temperature": 0.7,
        "timeout": 300,
        "description": "本地 Gemma 4 (31B) - Luna SGP 主引擎"
    },
    
    # Kimi 配置 (仅作为回退)
    "kimi": {
        "model_name": "moonshot/kimi-k2.6",
        "api_type": "openclaw",
        "context_window": 256000,
        "max_tokens": 4096,
        "temperature": 0.7,
        "description": "Kimi k2.6 - 云端回退引擎 (避免敏感内容触发)"
    }
}

# Luna SGP 推理档位映射
REASONING_TIERS = {
    "low": {
        "engine": "gemma4",
        "max_tokens": 2048,
        "temperature": 0.5,
        "description": "快速响应 - 日常对话、简单任务"
    },
    "medium": {
        "engine": "gemma4", 
        "max_tokens": 4096,
        "temperature": 0.7,
        "description": "标准推理 - 一般分析、资讯处理"
    },
    "high": {
        "engine": "gemma4",
        "max_tokens": 8192,
        "temperature": 0.7,
        "description": "深度分析 - 复杂推理、报告生成"
    },
    "max": {
        "engine": "gemma4",
        "max_tokens": 8192,
        "temperature": 0.8,
        "description": "完整 Luna SGP - 四层语义推理 (L1→L2→L3→L4)"
    }
}

# 任务类型 → 推理档位映射
TASK_ROUTING = {
    # 资讯捕获与摘要
    "news_capture": "medium",
    "news_analysis": "high",
    "news_deep_dive": "max",
    
    # 记忆处理
    "memory_store": "low",
    "memory_recall": "medium",
    "memory_consolidation": "high",
    
    # 对话
    "chat_simple": "low",
    "chat_complex": "medium",
    "chat_strategic": "high",
    
    # 代码/技术
    "code_generation": "high",
    "code_review": "medium",
    "technical_analysis": "high"
}

# 敏感内容处理
SENSITIVE_CONTENT = {
    "use_local_engine": True,  # 涉及敏感政治/地缘内容时使用本地模型
    "auto_detect": True,
    "keywords": [
        "政治", "领导人", "政权", "制裁", "战争", "军事",
        "political", "sanctions", "regime", "conflict"
    ]
}

# 健康检查配置
HEALTH_CHECK = {
    "gemma4_url": "http://localhost:11434/api/tags",
    "check_interval": 300,  # 5分钟
    "auto_restart": False
}
