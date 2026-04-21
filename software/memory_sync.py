#!/usr/bin/env python3
"""
Memory Sync - 月魂记忆同步模块

实现月魂记忆文件与三宇宙架构的双向同步：
- 加载：MEMORY.md / memory/ → 三宇宙图库/向量库
- 保存：三宇宙更新 → memory/ 日文件
"""

import os
import re
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path


class MemorySync:
    """
    月魂记忆同步器
    
    职责：
    - 解析月魂记忆文件（Markdown 格式）
    - 提取实体、关系、事件
    - 同步到三宇宙图库/向量库
    - 保存会话记忆到日文件
    """
    
    def __init__(self, workspace_path: str = None):
        """初始化同步器"""
        if workspace_path is None:
            workspace_path = "/Users/miaoliwang/.openclaw/workspace"
        
        self.workspace = Path(workspace_path)
        self.memory_dir = self.workspace / "memory"
        self.memory_file = self.workspace / "MEMORY.md"
        
        # 确保 memory 目录存在
        self.memory_dir.mkdir(exist_ok=True)
        
        print(f"📚 记忆同步器初始化: {self.workspace}")
    
    def parse_memory_md(self, file_path: str) -> Dict[str, Any]:
        """
        解析 MEMORY.md 文件
        
        提取：
        - 主人信息
        - 重要事件
        - 偏好设置
        - 教训洞察
        """
        if not os.path.exists(file_path):
            return {}
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        memory_data = {
            'entities': [],
            'relations': [],
            'events': [],
            'preferences': {},
            'lessons': []
        }
        
        # 提取主人信息
        if '老吴' in content or '吴老师' in content:
            memory_data['entities'].append({
                'name': '吴老师',
                'type': 'person',
                'aliases': ['老吴', '吴仙', '主人']
            })
        
        # 提取日期事件（格式：- **YYYY-MM-DD** — 描述）
        event_pattern = r'- \*\*(\d{4}-\d{2}-\d{2})\*\* — (.+)'
        events = re.findall(event_pattern, content)
        for date, desc in events:
            memory_data['events'].append({
                'date': date,
                'description': desc.strip()
            })
        
        # 提取偏好（格式：- **偏好**：值）
        pref_pattern = r'- \*\*(.+?)\*\*[:：](.+)'
        prefs = re.findall(pref_pattern, content)
        for key, value in prefs:
            memory_data['preferences'][key.strip()] = value.strip()
        
        # 提取教训（格式：- **日期** — 教训描述）
        lesson_pattern = r'- \*\*(\d{4}-\d{2}-\d{2})\*\* — (.+?)(?=\n\n|\Z)'
        lessons = re.findall(lesson_pattern, content, re.DOTALL)
        for date, desc in lessons:
            if '教训' in desc or '洞察' in desc:
                memory_data['lessons'].append({
                    'date': date,
                    'content': desc.strip()[:200]  # 限制长度
                })
        
        return memory_data
    
    def load_to_trinity(self, bridge) -> Dict[str, Any]:
        """
        加载月魂记忆到三宇宙架构
        
        Args:
            bridge: TrinityBridge 实例
            
        Returns:
            加载统计
        """
        print("📥 加载月魂记忆到三宇宙...")
        
        stats = {
            'entities_added': 0,
            'relations_added': 0,
            'events_added': 0
        }
        
        # 1. 加载 MEMORY.md
        if self.memory_file.exists():
            memory_data = self.parse_memory_md(str(self.memory_file))
            
            # 添加实体到图库
            for entity in memory_data.get('entities', []):
                bridge.graph_store.add_node(
                    entity['name'],
                    {'type': entity.get('type', 'unknown')}
                )
                stats['entities_added'] += 1
            
            # 添加事件（简化处理）
            for event in memory_data.get('events', [])[:10]:  # 限制数量
                event_key = f"event_{event['date']}"
                bridge.graph_store.add_node(event_key, {
                    'type': 'event',
                    'date': event['date'],
                    'description': event['description'][:100]
                })
                bridge.graph_store.add_edge('吴老师', event_key, '经历', 0.8)
                stats['events_added'] += 1
        
        # 2. 加载近期日文件（最近3天）
        recent_files = self._get_recent_day_files(3)
        for file_path in recent_files:
            self._load_day_file(file_path, bridge)
        
        print(f"✅ 记忆加载完成: {stats}")
        return stats
    
    def _get_recent_day_files(self, days: int = 3) -> List[str]:
        """获取最近 N 天的记忆文件"""
        files = []
        for i in range(days):
            date = datetime.now()
            date_str = date.strftime('%Y-%m-%d')
            file_path = self.memory_dir / f"{date_str}.md"
            if file_path.exists():
                files.append(str(file_path))
        return files
    
    def _load_day_file(self, file_path: str, bridge):
        """加载单日记忆文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 简单提取关键信息
            if '吴老师' in content:
                # 提取对话主题（简化）
                topics = self._extract_topics(content)
                for topic in topics[:5]:
                    bridge.vector_store.add(topic, {
                        'source': file_path,
                        'type': 'daily_topic'
                    })
                    
        except Exception as e:
            print(f"   加载失败: {file_path} - {e}")
    
    def _extract_topics(self, content: str) -> List[str]:
        """提取内容主题（简化版）"""
        # 按行分割，过滤短行
        lines = [l.strip() for l in content.split('\n') if len(l.strip()) > 20]
        return lines[:10]  # 限制数量
    
    def save_session(self, bridge, session_data: Dict[str, Any]) -> str:
        """
        保存会话记忆到日文件
        
        Args:
            bridge: TrinityBridge 实例
            session_data: 会话数据
            
        Returns:
            保存的文件路径
        """
        date_str = datetime.now().strftime('%Y-%m-%d')
        file_path = self.memory_dir / f"{date_str}.md"
        
        # 构建内容
        content = self._format_session_memory(session_data)
        
        # 追加或创建
        mode = 'a' if file_path.exists() else 'w'
        with open(file_path, mode, encoding='utf-8') as f:
            if mode == 'a':
                f.write('\n\n---\n\n')
            f.write(content)
        
        print(f"💾 会话记忆已保存: {file_path}")
        return str(file_path)
    
    def _format_session_memory(self, session_data: Dict) -> str:
        """格式化会话记忆"""
        now = datetime.now().strftime('%H:%M')
        
        lines = [
            f"## 会话记录 {now}",
            "",
            f"**交互次数**: {session_data.get('interaction_count', 0)}",
            f"**会话时长**: {session_data.get('duration', 0):.1f}秒",
            "",
            "### 关键交互",
        ]
        
        # 添加交互记录
        for interaction in session_data.get('interactions', [])[:5]:
            lines.append(f"- 用户: {interaction.get('input', '')[:50]}")
            lines.append(f"  阿月: {interaction.get('response', '')[:50]}")
            lines.append("")
        
        # 添加三宇宙统计
        lines.append("### 三宇宙统计")
        lines.append(f"- 图库节点: {session_data.get('graph_nodes', 0)}")
        lines.append(f"- 图库边数: {session_data.get('graph_edges', 0)}")
        lines.append(f"- 平均对齐度: {session_data.get('avg_alignment', 0):.2f}")
        
        return '\n'.join(lines)
    
    def sync_summary(self) -> str:
        """生成记忆同步摘要"""
        # 统计 memory 目录
        day_files = list(self.memory_dir.glob('*.md'))
        
        summary = f"""# 记忆同步摘要

**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}

## 存储统计

- **长期记忆**: {self.memory_file.exists() and '存在' or '缺失'}
- **日文件数量**: {len(day_files)}
- **Memory 目录**: {self.memory_dir}

## 最近文件

"""
        for f in sorted(day_files)[-5:]:
            summary += f"- {f.name}\n"
        
        return summary


# 测试函数
if __name__ == "__main__":
    print("🧪 测试 Memory Sync")
    print("=" * 50)
    
    # 创建同步器
    sync = MemorySync()
    
    # 测试解析
    print("\n📄 解析 MEMORY.md:")
    memory_data = sync.parse_memory_md(str(sync.memory_file))
    print(f"   实体: {len(memory_data.get('entities', []))}")
    print(f"   事件: {len(memory_data.get('events', []))}")
    print(f"   偏好: {len(memory_data.get('preferences', {}))}")
    print(f"   教训: {len(memory_data.get('lessons', []))}")
    
    # 测试摘要
    print("\n📊 同步摘要:")
    print(sync.sync_summary())
    
    print("✅ 测试完成")
