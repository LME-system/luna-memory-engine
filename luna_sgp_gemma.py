#!/usr/bin/env python3
"""
Luna SGP Gemma 4 集成模块
自动加载配置并初始化 Gemma 4 引擎
"""

import sys
from pathlib import Path
from typing import Optional, Dict, Any

# 确保路径正确
workspace = Path.home() / ".openclaw/workspace"
sys.path.insert(0, str(workspace))

# 导入配置和引擎
from luna_sgp_config import MODEL_CONFIG, REASONING_TIERS, TASK_ROUTING
from gemma4_engine import Gemma4Engine, get_gemma_engine


class LunaSGPGemma:
    """Luna SGP + Gemma 4 集成控制器"""
    
    def __init__(self):
        self.config = MODEL_CONFIG
        self.tiers = REASONING_TIERS
        self.routing = TASK_ROUTING
        
        # 初始化引擎
        self.gemma = get_gemma_engine(self.config["gemma4"])
        self.gemma_available = self.gemma.is_available()
        
        if self.gemma_available:
            print("🌙 Luna SGP + Gemma 4 集成已就绪")
        else:
            print("⚠️ Gemma 4 不可用，将回退到 Kimi")
    
    def process(
        self,
        task_type: str,
        content: str,
        context: Optional[str] = None,
        force_engine: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        处理任务
        
        Args:
            task_type: 任务类型 (news_capture, news_analysis, chat_complex 等)
            content: 内容
            context: 上下文
            force_engine: 强制指定引擎
            
        Returns:
            处理结果
        """
        # 确定推理档位
        tier_name = self.routing.get(task_type, "medium")
        tier = self.tiers.get(tier_name, self.tiers["medium"])
        
        # 确定引擎
        engine_name = force_engine or tier["engine"]
        
        # 如果使用 Gemma 且可用
        if engine_name == "gemma4" and self.gemma_available:
            if task_type.startswith("news"):
                analysis_type = {"news_capture": "standard", "news_analysis": "deep", "news_deep_dive": "strategic"}.get(task_type, "standard")
                result = self.gemma.analyze_news(content, context, analysis_type)
            else:
                result = self.gemma.generate(
                    prompt=content,
                    max_tokens=tier["max_tokens"],
                    temperature=tier["temperature"]
                )
            
            result["engine"] = "gemma4"
            result["tier"] = tier_name
            return result
        
        # 回退到 Kimi (通过 OpenClaw)
        else:
            return {
                "status": "fallback",
                "engine": "kimi",
                "tier": tier_name,
                "message": "Gemma 4 不可用，请使用 OpenClaw 原生推理",
                "content": content
            }
    
    def get_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        return {
            "gemma4_available": self.gemma_available,
            "gemma4_stats": self.gemma.get_stats() if self.gemma_available else None,
            "default_engine": self.config["default_engine"],
            "fallback_engine": self.config["fallback_engine"]
        }


# 全局实例
_luna_sgp_instance = None


def get_luna_sgp() -> LunaSGPGemma:
    """获取 Luna SGP 实例（单例）"""
    global _luna_sgp_instance
    if _luna_sgp_instance is None:
        _luna_sgp_instance = LunaSGPGemma()
    return _luna_sgp_instance


# 便捷函数
def luna_analyze_news(news_text: str, context: Optional[str] = None, deep: bool = False) -> str:
    """分析新闻（便捷函数）"""
    luna = get_luna_sgp()
    task_type = "news_deep_dive" if deep else "news_analysis"
    result = luna.process(task_type, news_text, context)
    
    if result.get("status") == "success":
        return result.get("response", "")
    else:
        return f"[分析失败: {result.get('error', '未知错误')}]"


def luna_chat(content: str, context: Optional[str] = None) -> str:
    """对话（便捷函数）"""
    luna = get_luna_sgp()
    result = luna.process("chat_complex", content, context)
    
    if result.get("status") == "success":
        return result.get("response", "")
    else:
        return f"[处理失败: {result.get('error', '未知错误')}]"


if __name__ == "__main__":
    # 测试
    luna = get_luna_sgp()
    print(f"\n状态: {luna.get_status()}")
    
    if luna.gemma_available:
        print("\n测试新闻分析...")
        test_news = "美国财长贝森特宣布本周将对伊朗银行实施制裁。"
        result = luna.process("news_analysis", test_news)
        print(f"结果: {result.get('response', '')[:500]}...")
