#!/usr/bin/env python3
"""
Yuehen LME Integration - 月魂 + LME 集成模块

职责：
- 对接月魂记忆系统（MEMORY.md / memory/*.md）
- 对接 LME 神经形态记忆引擎
- 处理对话并提取重要信息
- 双向同步：文件记忆 ↔ LME 神经元记忆
"""

import os
import sys
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# 导入记忆同步模块
sys.path.insert(0, '/Users/miaoliwang/.openclaw/workspace')
from memory_sync import MemorySync

# 导入 LME 驱动
sys.path.insert(0, '/Users/miaoliwang/.openclaw/workspace/lme/software')
from lme_driver import LMESimulator
from luna_memory_system import LunaMemorySystem


class YuehenLMEIntegration:
    """
    月魂 + LME 集成系统
    
    实现：
    1. 对话处理 → 重要性评估 → LME 记忆编码
    2. 知识蒸馏 → 提取洞察 → 写入 MEMORY.md
    3. 双向同步 → 文件记忆 ↔ 神经元记忆
    """
    
    def __init__(self, pynq_ip: str = None, enable_lme: bool = True):
        """
        初始化集成系统
        
        Args:
            pynq_ip: PYNQ-Z2 板子的 IP 地址（如果有硬件）
            enable_lme: 是否启用 LME（软件模拟模式）
        """
        self.workspace = Path("/Users/miaoliwang/.openclaw/workspace")
        self.memory_file = self.workspace / "MEMORY.md"
        self.memory_dir = self.workspace / "memory"
        
        # 初始化记忆同步器
        self.memory_sync = MemorySync(str(self.workspace))
        
        # 初始化 LME（软件模拟模式）
        self.lme = None
        if enable_lme:
            try:
                self.lme = LMESimulator()
                print("✅ LME 软件模拟器初始化成功")
            except Exception as e:
                print(f"⚠️ LME 初始化失败: {e}")
        
        # 初始化月魂记忆系统（可选，失败不阻塞）
        self.luna_memory = None
        try:
            # LunaMemorySystem 可能需要特定配置，暂时禁用
            # self.luna_memory = LunaMemorySystem()
            # print("✅ 月魂记忆系统初始化成功")
            print("ℹ️ 月魂记忆系统初始化跳过（使用基础模式）")
        except Exception as e:
            print(f"⚠️ 月魂记忆系统初始化失败: {e}")
        
        # 重要信息缓冲区（待写入 MEMORY.md）
        self.important_buffer = []
        
        print("✅ 月魂 + LME 集成系统初始化完成")
    
    def process_dialogue(self, speaker: str, content: str, context: str = "") -> Dict[str, Any]:
        """
        处理对话，提取重要信息并编码到 LME
        
        Args:
            speaker: 说话者（user/assistant）
            content: 对话内容
            context: 上下文
            
        Returns:
            处理结果（重要性评分、LME 神经元 ID 等）
        """
        result = {
            'importance': 0.0,
            'lme_neuron': None,
            'memory_updated': False,
            'extracted_insights': []
        }
        
        # 1. 重要性评估
        importance = self._assess_importance(speaker, content, context)
        result['importance'] = importance
        
        # 2. 如果重要性高，编码到 LME
        if importance > 0.6 and self.lme:
            try:
                neuron_id = self._encode_to_lme(speaker, content, importance)
                result['lme_neuron'] = neuron_id
            except Exception as e:
                print(f"   LME 编码失败: {e}")
        
        # 3. 提取洞察
        insights = self._extract_insights(content)
        result['extracted_insights'] = insights
        
        # 4. 如果非常重要，加入缓冲区待写入 MEMORY.md
        if importance > 0.8 or insights:
            self.important_buffer.append({
                'timestamp': datetime.now().isoformat(),
                'speaker': speaker,
                'content': content[:200],  # 限制长度
                'importance': importance,
                'insights': insights
            })
            result['memory_updated'] = True
        
        return result
    
    def _assess_importance(self, speaker: str, content: str, context: str) -> float:
        """
        评估对话内容的重要性（0-1）
        
        基于：
        - 关键词匹配（项目、决策、突破、问题等）
        - 内容长度和结构
        - 上下文相关性
        """
        importance = 0.5  # 基础分
        
        # 关键词加分
        high_value_keywords = [
            '项目', '架构', '设计', '决策', '突破', '重大', '关键',
            '问题', 'bug', '错误', '失败', '教训', '洞察',
            '完成', '发布', '上线', '成功', '实现',
            '记住', '记录', '更新', '修改'
        ]
        
        for keyword in high_value_keywords:
            if keyword in content:
                importance += 0.1
        
        # 金融/经济数据关键词（高价值）
        finance_keywords = [
            '社融', 'M2', 'M1', '贷款', '债券', '融资', '万亿元', 
            '同比增长', '余额', '增量', '利率', '外汇储备'
        ]
        for keyword in finance_keywords:
            if keyword in content:
                importance += 0.15  # 金融数据重要性更高
        
        # 长度适中加分（太短没内容，太长可能是闲聊）
        content_len = len(content)
        if 50 < content_len < 500:
            importance += 0.1
        elif content_len >= 500:  # 长内容通常有信息量
            importance += 0.15
        
        # 包含代码、命令、路径加分
        if any(pattern in content for pattern in ['`', '/', 'def ', 'class ', 'import ']):
            importance += 0.1
        
        # 用户明确指示记录
        if any(phrase in content for phrase in ['记住', '记录下来', '写到', '更新']):
            importance += 0.2
        
        # 包含具体数字/数据加分
        if re.search(r'\d+\.?\d*\s*(万亿|亿|万|%|个百分点)', content):
            importance += 0.1
        
        return min(importance, 1.0)
    
    def _encode_to_lme(self, speaker: str, content: str, importance: float) -> str:
        """
        将对话编码到 LME 神经元
        
        Returns:
            神经元 ID
        """
        if not self.lme:
            return None
        
        # 生成事件数据
        event_data = {
            'type': 'dialogue',
            'speaker': speaker,
            'content_hash': hash(content) % 10000,
            'importance': importance,
            'timestamp': datetime.now().isoformat()
        }
        
        # 发送到 LME（简化处理）
        try:
            # 这里可以调用 LME 的事件编码功能
            neuron_id = f"neuron_{datetime.now().strftime('%H%M%S')}_{hash(content) % 1000}"
            return neuron_id
        except Exception as e:
            print(f"   LME 编码错误: {e}")
            return None
    
    def _extract_insights(self, content: str) -> List[str]:
        """
        从内容中提取洞察/教训/决策点
        """
        insights = []
        
        # 模式 1: "关键是..." / "核心洞察..."
        patterns = [
            r'关键是[：:](.+?)(?:\n|$)',
            r'核心洞察[：:](.+?)(?:\n|$)',
            r'重要[的是][：:](.+?)(?:\n|$)',
            r'决定[：:](.+?)(?:\n|$)',
            r'教训[：:](.+?)(?:\n|$)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, content)
            insights.extend([m.strip() for m in matches if len(m.strip()) > 10])
        
        # 模式 2: 包含 "应该"、"需要"、"必须" 的句子（决策点）
        decision_pattern = r'[^。]*?(?:应该|需要|必须|建议)[^。]*。'
        decisions = re.findall(decision_pattern, content)
        insights.extend([d.strip() for d in decisions if len(d.strip()) > 15])
        
        return insights[:3]  # 限制数量
    
    def run_distillation(self) -> Dict[str, Any]:
        """
        运行知识蒸馏，将缓冲区内容写入 MEMORY.md
        
        Returns:
            蒸馏报告
        """
        report = {
            'changes_detected': len(self.important_buffer),
            'knowledge_extracted': 0,
            'memories_updated': 0
        }
        
        if not self.important_buffer:
            return report
        
        # 1. 聚合洞察
        all_insights = []
        for item in self.important_buffer:
            all_insights.extend(item.get('insights', []))
        
        report['knowledge_extracted'] = len(all_insights)
        
        # 2. 写入 MEMORY.md（追加到重要事件部分）
        if all_insights:
            self._append_to_memory_md(all_insights)
            report['memories_updated'] = len(all_insights)
        
        # 3. 清空缓冲区
        self.important_buffer = []
        
        return report
    
    def _append_to_memory_md(self, insights: List[str]):
        """
        将洞察追加到 MEMORY.md
        """
        if not self.memory_file.exists():
            print(f"   错误: {self.memory_file} 不存在")
            return
        
        # 读取现有内容
        with open(self.memory_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 生成新内容
        date_str = datetime.now().strftime('%Y-%m-%d')
        new_section = f"\n\n## {date_str} — 自动提取的洞察\n\n"
        for insight in insights:
            new_section += f"- {insight}\n"
        
        # 找到合适的位置插入（在 "重要事件" 部分之后）
        # 简化处理：追加到文件末尾
        with open(self.memory_file, 'a', encoding='utf-8') as f:
            f.write(new_section)
        
        print(f"   已追加 {len(insights)} 条洞察到 MEMORY.md")
    
    def sync_to_memory_files(self) -> Dict[str, Any]:
        """
        将 LME 记忆同步到文件系统
        
        Returns:
            同步统计
        """
        stats = {
            'lme_memories': 0,
            'files_updated': 0
        }
        
        # 这里可以实现从 LME 读取记忆并写入日文件
        # 简化版本：直接调用 memory_sync 的功能
        
        return stats
    
    def close(self):
        """
        关闭集成系统，保存未写入的数据
        """
        print("🔄 关闭集成系统...")
        
        # 运行最后一次蒸馏
        if self.important_buffer:
            report = self.run_distillation()
            print(f"   最后蒸馏: {report}")
        
        # 关闭 LME
        if self.lme:
            # self.lme.close()
            pass
        
        print("✅ 集成系统已关闭")


# 测试函数
if __name__ == "__main__":
    print("🧪 测试 Yuehen LME Integration")
    print("=" * 50)
    
    # 创建集成系统（软件模拟模式）
    integration = YuehenLMEIntegration(enable_lme=True)
    
    # 测试对话处理
    print("\n📝 测试对话处理:")
    
    test_dialogues = [
        ("user", "今天天气不错", ""),
        ("user", "LME 项目完成了重大突破，需要记录下来", ""),
        ("user", "关键是：索引和学习是一回事，这是核心洞察", ""),
    ]
    
    for speaker, content, context in test_dialogues:
        result = integration.process_dialogue(speaker, content, context)
        print(f"\n  内容: {content[:30]}...")
        print(f"  重要性: {result['importance']:.2f}")
        print(f"  洞察: {result['extracted_insights']}")
        print(f"  记忆更新: {result['memory_updated']}")
    
    # 测试知识蒸馏
    print("\n🔬 测试知识蒸馏:")
    report = integration.run_distillation()
    print(f"  变化检测: {report['changes_detected']}")
    print(f"  知识提取: {report['knowledge_extracted']}")
    print(f"  记忆更新: {report['memories_updated']}")
    
    # 关闭
    integration.close()
    
    print("\n✅ 测试完成")
