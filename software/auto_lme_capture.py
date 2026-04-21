#!/usr/bin/env python3
"""
Auto LME Capture - 自动 LME 捕获触发器

使用方式：在每次对话处理时调用 auto_capture()
"""

import sys
sys.path.insert(0, '/Users/miaoliwang/.openclaw/workspace')

from openclaw_lme_bridge import capture_to_lme


def auto_capture_user_input(content: str, context: str = "") -> bool:
    """
    自动捕获用户输入到 LME
    
    调用时机：收到用户消息时
    """
    try:
        return capture_to_lme('user', content, context)
    except Exception as e:
        print(f"[LME Capture Error] {e}")
        return False


def auto_capture_assistant_response(content: str, context: str = "") -> bool:
    """
    自动捕获助手回复到 LME
    
    调用时机：生成回复后
    """
    try:
        return capture_to_lme('assistant', content, context)
    except Exception as e:
        print(f"[LME Capture Error] {e}")
        return False


# 测试
if __name__ == "__main__":
    print("🧪 测试自动 LME 捕获")
    
    # 模拟用户输入（金融数据）
    test_content = """一、社会融资规模存量同比增长7.9%
    
初步统计，2026年3月末社会融资规模存量为456.46万亿元，同比增长7.9%。
其中，对实体经济发放的人民币贷款余额277.3万亿元，同比增长5.8%；
政府债券余额98.47万亿元，同比增长15.9%。"""
    
    result = auto_capture_user_input(test_content, "金融统计数据")
    print(f"捕获结果: {result}")
