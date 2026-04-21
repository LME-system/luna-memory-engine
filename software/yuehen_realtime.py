#!/usr/bin/env python3
"""
月痕实时记忆系统 - 动态评估优化层 (Yuehen-RT)

在月痕基础能力之上，实现:
1. 对话实时捕获
2. 重要性动态评估
3. 触发式自动存储
4. 上下文感知回忆

设计原则: 结合已有记忆，动态评估优化
作者: 阿月
日期: 2026-03-28
"""

import json
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque
import hashlib
import re

# 导入月痕基础
from luna_memory_system import LunaMemorySystem, LunaEmbedder


@dataclass
class DialogueTurn:
    """对话轮次"""
    turn_id: str
    speaker: str  # 'user' or 'assistant'
    content: str
    timestamp: datetime
    embedding: Optional[np.ndarray] = None
    importance: float = 0.0  # 动态评估的重要性
    stored: bool = False  # 是否已存入月痕
    
    def to_dict(self) -> dict:
        return {
            'turn_id': self.turn_id,
            'speaker': self.speaker,
            'content': self.content,
            'timestamp': self.timestamp.isoformat(),
            'importance': self.importance,
            'stored': self.stored
        }


@dataclass
class ContextWindow:
    """上下文窗口 - 滑动窗口管理对话历史"""
    max_turns: int = 10
    turns: deque = field(default_factory=lambda: deque(maxlen=10))
    
    def add(self, turn: DialogueTurn):
        self.turns.append(turn)
    
    def get_recent(self, n: int = 5) -> List[DialogueTurn]:
        return list(self.turns)[-n:]
    
    def get_summary(self) -> str:
        """生成上下文摘要"""
        recent = self.get_recent(3)
        return " | ".join([f"{t.speaker}:{t.content[:50]}..." for t in recent])


class ImportanceEvaluator:
    """重要性评估器 - 动态判断内容是否值得记忆"""
    
    def __init__(self, memory_system: LunaMemorySystem):
        self.memory = memory_system
        self.embedder = LunaEmbedder()
        
        # 重要性触发词
        self.high_importance_keywords = [
            '决定', '确定', '完成', '实现', '设计', '架构', '突破',
            '重要', '关键', '核心', '必须', '一定', '永远',
            '命名', '创建', '启动', '开始', '结束', '完成',
            '错误', '问题', '失败', '教训', '注意', '警告',
        ]
        
        self.medium_importance_keywords = [
            '讨论', '考虑', '计划', '准备', '尝试', '测试',
            '优化', '改进', '调整', '修改', '更新', '升级',
            '建议', '想法', '思路', '方案', '策略', '方法',
        ]
    
    def evaluate(self, turn: DialogueTurn, context: ContextWindow) -> float:
        """
        评估对话轮次的重要性 (0-1)
        
        综合因素:
        1. 关键词匹配
        2. 与已有记忆的关联度 (新颖性)
        3. 对话上下文连贯性
        4. 信息密度
        """
        scores = []
        
        # 1. 关键词匹配 (0-0.4)
        keyword_score = self._keyword_score(turn.content)
        scores.append(('keyword', keyword_score, 0.4))
        
        # 2. 新颖性 - 与已有记忆的差异度 (0-0.3)
        novelty_score = self._novelty_score(turn)
        scores.append(('novelty', novelty_score, 0.3))
        
        # 3. 上下文连贯性 (0-0.2)
        coherence_score = self._coherence_score(turn, context)
        scores.append(('coherence', coherence_score, 0.2))
        
        # 4. 信息密度 (0-0.1)
        density_score = self._density_score(turn.content)
        scores.append(('density', density_score, 0.1))
        
        # 加权求和
        total = sum(score * weight for _, score, weight in scores)
        
        # 记录评估详情
        turn.importance = min(1.0, max(0.0, total))
        
        return turn.importance
    
    def _keyword_score(self, content: str) -> float:
        """关键词匹配分数"""
        content_lower = content.lower()
        
        high_matches = sum(1 for kw in self.high_importance_keywords if kw in content_lower)
        medium_matches = sum(1 for kw in self.medium_importance_keywords if kw in content_lower)
        
        score = high_matches * 0.15 + medium_matches * 0.05
        return min(0.4, score)
    
    def _novelty_score(self, turn: DialogueTurn) -> float:
        """新颖性分数 - 与已有记忆的差异"""
        if not self.memory.network.nodes:
            return 0.3  # 无记忆时，默认中等新颖
        
        # 编码当前内容
        if turn.embedding is None:
            turn.embedding = self.embedder.encode(turn.content)
        
        # 计算与最近记忆的相似度
        max_sim = 0
        for node in list(self.memory.network.nodes.values())[-20:]:  # 最近20条
            sim = float(np.dot(turn.embedding, node.embedding))
            max_sim = max(max_sim, sim)
        
        # 相似度越低，新颖性越高
        novelty = 1 - max_sim
        return min(0.3, novelty * 0.3)
    
    def _coherence_score(self, turn: DialogueTurn, context: ContextWindow) -> float:
        """上下文连贯性分数"""
        recent = context.get_recent(3)
        if not recent or turn.speaker != 'user':
            return 0.1
        
        # 用户连续提问通常更重要
        user_turns = [t for t in recent if t.speaker == 'user']
        if len(user_turns) >= 2:
            return 0.2
        
        return 0.1
    
    def _density_score(self, content: str) -> float:
        """信息密度分数"""
        # 基于长度和标点密度
        if len(content) < 20:
            return 0.05
        
        # 计算实体密度 (简单版本)
        entities = len(re.findall(r'[A-Z][a-z]+|[\u4e00-\u9fff]{2,}', content))
        density = min(1.0, entities / max(1, len(content) / 20))
        
        return density * 0.1


class TriggerDetector:
    """触发检测器 - 识别存储触发点"""
    
    def __init__(self):
        # 显式触发词
        self.explicit_triggers = [
            '记住', '记下来', '保存', '存储', '记录',
            '记住这个', '保存一下', '记一下',
        ]
        
        # 隐式触发模式
        self.implicit_patterns = [
            r'我们.*决定.*',  # 我们决定...
            r'.*命名为.*',    # ...命名为...
            r'.*完成了.*',    # ...完成了...
            r'.*确定.*',      # ...确定...
            r'以后.*',        # 以后...
            r'下次.*',        # 下次...
        ]
        
        # 结束标记
        self.conclusion_markers = [
            '总结一下', '结论是', '最终', '总之', '所以',
        ]
    
    def check_trigger(self, turn: DialogueTurn, importance: float) -> Tuple[bool, str]:
        """
        检查是否触发存储
        
        Returns:
            (是否触发, 触发原因)
        """
        content = turn.content.lower()
        
        # 1. 显式触发 (最高优先级)
        for trigger in self.explicit_triggers:
            if trigger in content:
                return True, f"显式触发: '{trigger}'"
        
        # 2. 隐式模式匹配
        for pattern in self.implicit_patterns:
            if re.search(pattern, content):
                return True, f"隐式模式: '{pattern}'"
        
        # 3. 结论标记
        for marker in self.conclusion_markers:
            if marker in content:
                return True, f"结论标记: '{marker}'"
        
        # 4. 重要性阈值触发
        if importance > 0.6:
            return True, f"重要性阈值: {importance:.2f}"
        
        return False, ""


class YuehenRealtime:
    """月痕实时记忆系统 - 主类"""
    
    def __init__(self, base_path: str = "~/.openclaw/workspace/memory"):
        self.base_path = Path(base_path).expanduser()
        
        # 核心组件
        self.memory = LunaMemorySystem(base_path)
        self.evaluator = ImportanceEvaluator(self.memory)
        self.trigger = TriggerDetector()
        self.context = ContextWindow(max_turns=20)
        
        # 配置
        self.auto_store_threshold = 0.6  # 自动存储阈值
        self.suggest_threshold = 0.4     # 建议存储阈值
        
        # 统计
        self.stats = {
            'turns_processed': 0,
            'auto_stored': 0,
            'suggested': 0,
            'user_confirmed': 0,
        }
        
        print("✅ 月痕实时记忆系统初始化完成")
    
    def process_turn(self, speaker: str, content: str) -> Dict:
        """
        处理对话轮次
        
        Args:
            speaker: 'user' 或 'assistant'
            content: 对话内容
        
        Returns:
            处理结果
        """
        # 1. 创建对话轮次
        turn_id = f"turn_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(content) % 10000:04d}"
        turn = DialogueTurn(
            turn_id=turn_id,
            speaker=speaker,
            content=content,
            timestamp=datetime.now()
        )
        
        # 2. 编码
        turn.embedding = self.memory.embedder.encode(content)
        
        # 3. 评估重要性
        importance = self.evaluator.evaluate(turn, self.context)
        
        # 4. 检查触发
        should_store, trigger_reason = self.trigger.check_trigger(turn, importance)
        
        # 5. 决策
        result = {
            'turn_id': turn_id,
            'importance': importance,
            'triggered': should_store,
            'trigger_reason': trigger_reason,
            'action': 'ignore',
            'memory_id': None,
            'suggestion': None,
        }
        
        if should_store:
            # 自动存储
            memory_id = self._store_turn(turn)
            result['action'] = 'auto_stored'
            result['memory_id'] = memory_id
            self.stats['auto_stored'] += 1
            
        elif importance > self.suggest_threshold:
            # 建议存储
            result['action'] = 'suggest'
            result['suggestion'] = f"这段内容看起来重要(得分:{importance:.2f})，要存储吗？"
            self.stats['suggested'] += 1
        
        # 6. 加入上下文
        self.context.add(turn)
        self.stats['turns_processed'] += 1
        
        return result
    
    def _store_turn(self, turn: DialogueTurn) -> str:
        """存储对话轮次到月痕"""
        # 构建存储内容
        content = f"[{turn.speaker}] {turn.content}"
        
        # 确定层级
        if turn.importance > 0.8:
            level = 'L2'
        elif turn.importance > 0.5:
            level = 'L1'
        else:
            level = 'L0'
        
        # 存储
        memory_id = self.memory.store(
            content=content,
            level=level,
            source=f'dialogue_{turn.speaker}'
        )
        
        turn.stored = True
        return memory_id
    
    def confirm_store(self, turn_id: str) -> Optional[str]:
        """用户确认存储"""
        for turn in self.context.turns:
            if turn.turn_id == turn_id and not turn.stored:
                memory_id = self._store_turn(turn)
                self.stats['user_confirmed'] += 1
                return memory_id
        return None
    
    def proactive_recall(self, current_topic: str, top_k: int = 3) -> List[Dict]:
        """
        主动回忆 - 基于当前话题主动检索相关记忆
        """
        # 结合当前话题和上下文
        context_summary = self.context.get_summary()
        query = f"{current_topic} {context_summary}"
        
        # 检索
        results = self.memory.retrieve(query, top_k=top_k, use_network=True)
        
        # 过滤低相关度
        filtered = [r for r in results if r['score'] > 0.2]
        
        return filtered
    
    def get_session_summary(self) -> str:
        """生成会话摘要"""
        turns = list(self.context.turns)
        
        lines = ["会话摘要", "=" * 50]
        lines.append(f"总轮次: {len(turns)}")
        lines.append(f"已存储: {self.stats['auto_stored'] + self.stats['user_confirmed']}")
        lines.append(f"建议存储: {self.stats['suggested']}")
        
        # 高重要性内容
        important = [t for t in turns if t.importance > 0.5]
        if important:
            lines.append(f"\n重要内容 ({len(important)}条):")
            for t in important[-5:]:
                status = "✓" if t.stored else "○"
                lines.append(f"  {status} [{t.importance:.2f}] {t.content[:60]}...")
        
        return "\n".join(lines)
    
    def get_stats(self) -> Dict:
        """获取统计"""
        base_stats = self.memory.get_stats()
        return {
            **base_stats,
            **self.stats,
            'context_turns': len(self.context.turns),
        }


# ============ 测试 ============

def test_yuehen_rt():
    """测试月痕实时系统"""
    print("\n" + "=" * 70)
    print("月痕实时记忆系统 - 测试")
    print("=" * 70)
    
    # 初始化
    rt = YuehenRealtime()
    
    # 模拟对话
    dialogues = [
        ('user', '你好，今天讨论一下记忆系统'),
        ('assistant', '好的，月痕实时记忆系统已经准备好了'),
        ('user', '我们决定把新的记忆引擎命名为月痕'),
        ('assistant', '明白了，月痕这个名字很好，月承月魂，痕喻记忆'),
        ('user', '记住这个命名'),
        ('assistant', '已记录：新的记忆引擎命名为月痕'),
        ('user', '以后优先使用月痕'),
        ('assistant', '收到，已设置月痕为首选记忆引擎'),
        ('user', '测试一下速度'),
        ('assistant', '月痕存储速度约2.67ms，检索约6.28ms'),
    ]
    
    print("\n[模拟对话处理]")
    print("-" * 70)
    
    for speaker, content in dialogues:
        result = rt.process_turn(speaker, content)
        
        action_icon = {
            'auto_stored': '💾',
            'suggest': '💡',
            'ignore': '○'
        }.get(result['action'], '?')
        
        print(f"\n{action_icon} [{speaker}] {content[:50]}...")
        print(f"   重要性: {result['importance']:.2f}")
        
        if result['triggered']:
            print(f"   触发: {result['trigger_reason']}")
            print(f"   存储ID: {result['memory_id'][:25]}...")
        elif result['suggestion']:
            print(f"   建议: {result['suggestion']}")
    
    # 主动回忆
    print("\n" + "-" * 70)
    print("[主动回忆测试]")
    print("-" * 70)
    
    recalls = rt.proactive_recall("月痕命名", top_k=3)
    print(f"\n当前话题: '月痕命名'")
    print(f"找到 {len(recalls)} 条相关记忆:")
    for r in recalls:
        print(f"  - [{r['level']}] 相关度:{r['score']:.2f} {r['content'][:60]}...")
    
    # 会话摘要
    print("\n" + "-" * 70)
    print(rt.get_session_summary())
    
    # 统计
    print("\n" + "-" * 70)
    print("[系统统计]")
    stats = rt.get_stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")
    
    print("\n" + "=" * 70)
    print("✅ 月痕实时记忆系统测试完成")
    print("=" * 70)


if __name__ == "__main__":
    test_yuehen_rt()
