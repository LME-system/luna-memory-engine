#!/usr/bin/env python3
"""
OpenClaw LME Bridge - OpenClaw 与 LME 守护进程的实时桥接

职责：
- 拦截 OpenClaw 对话
- 自动写入 LME 队列
- 实现对话内容的实时记忆捕获

集成方式：
1. 作为 OpenClaw 的钩子（hook）
2. 或作为独立服务监听对话日志
"""

import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path


class OpenClawLMEBridge:
    """
    OpenClaw ↔ LME 桥接器
    
    实现对话的自动捕获和转发
    """
    
    def __init__(self):
        self.workspace = Path("/Users/miaoliwang/.openclaw/workspace")
        self.queue_dir = Path("~/.openclaw/yuehen_queue").expanduser()
        self.log_dir = Path("~/.openclaw/logs").expanduser()
        
        # 确保队列目录存在
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"🌉 OpenClaw LME Bridge 初始化")
        print(f"   队列目录: {self.queue_dir}")
    
    def capture_dialogue(self, speaker: str, content: str, context: str = "", 
                         importance_hint: float = None) -> bool:
        """
        捕获对话并写入 LME 队列
        
        Args:
            speaker: 说话者（user/assistant）
            content: 对话内容
            context: 上下文/话题
            importance_hint: 重要性提示（可选，0-1）
            
        Returns:
            是否成功写入
        """
        try:
            # 构建队列文件
            timestamp = int(time.time())
            queue_file = self.queue_dir / f"dialogue_{timestamp}.json"
            
            # 构建数据
            data = {
                'speaker': speaker,
                'content': content,
                'context': context,
                'timestamp': datetime.now().isoformat(),
                'source': 'openclaw_bridge',
            }
            
            if importance_hint is not None:
                data['importance_hint'] = importance_hint
            
            # 写入文件
            queue_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            
            print(f"📝 对话已捕获 → LME队列: {queue_file.name}")
            return True
            
        except Exception as e:
            print(f"❌ 捕获失败: {e}")
            return False
    
    def capture_user_input(self, content: str, context: str = "", 
                           auto_importance: bool = True) -> bool:
        """
        捕获用户输入
        
        Args:
            content: 内容
            context: 上下文
            auto_importance: 是否自动评估重要性提示
        """
        importance_hint = None
        if auto_importance:
            importance_hint = self._assess_importance_hint(content)
        
        return self.capture_dialogue('user', content, context, importance_hint)
    
    def _assess_importance_hint(self, content: str) -> float:
        """
        预评估内容重要性，给守护进程提示
        """
        importance = 0.5
        
        # 金融/经济数据加分
        if any(kw in content for kw in ['社融', 'M2', '贷款', '债券', '融资', '万亿元', '同比增长']):
            importance += 0.2
        
        # 项目/技术/架构关键词加分
        if any(kw in content for kw in ['项目', '架构', '设计', '实现', '突破']):
            importance += 0.15
        
        # 长内容加分（有信息量）
        if len(content) > 500:
            importance += 0.1
        
        return min(importance, 0.95)  # 最高0.95，留给守护进程判断空间
    
    def capture_assistant_response(self, content: str, context: str = "") -> bool:
        """
        捕获助手回复
        """
        return self.capture_dialogue('assistant', content, context)
    
    def capture_full_exchange(self, user_input: str, assistant_response: str, 
                              context: str = "") -> bool:
        """
        捕获完整对话交换（用户输入 + 助手回复）
        """
        # 合并为一条记录
        combined_content = f"用户: {user_input[:200]}\n助手: {assistant_response[:200]}"
        return self.capture_dialogue('exchange', combined_content, context)


# 全局桥接实例（单例模式）
_bridge_instance = None

def get_bridge() -> OpenClawLMEBridge:
    """获取全局桥接实例"""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = OpenClawLMEBridge()
    return _bridge_instance


def capture_to_lme(speaker: str, content: str, context: str = "") -> bool:
    """
    便捷函数：捕获对话到 LME
    
    使用方式：
        from openclaw_lme_bridge import capture_to_lme
        capture_to_lme('user', '用户输入内容', '金融数据')
    """
    bridge = get_bridge()
    return bridge.capture_dialogue(speaker, content, context)


# 测试
if __name__ == "__main__":
    print("🧪 测试 OpenClaw LME Bridge")
    print("=" * 50)
    
    bridge = OpenClawLMEBridge()
    
    # 测试用户输入
    bridge.capture_user_input(
        "一、社会融资规模存量同比增长7.9%...",
        "金融统计数据"
    )
    
    # 测试助手回复
    bridge.capture_assistant_response(
        "收到！这是2026年3月/一季度的金融统计数据...",
        "金融数据分析"
    )
    
    print("\n✅ 测试完成")
    print(f"请检查队列目录: {bridge.queue_dir}")
