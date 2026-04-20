#!/usr/bin/env python3
"""
月痕 (Yuehen) - 月魂记忆引擎 v1.0

命名含义:
- "月"承月魂之名
- "痕"喻记忆如痕，深浅由时，聚散由缘
- 音近"月魂"，暗合传承

特性:
- SelectiveSTDP 神经形态学习
- 动态关联网络
- 三级遗忘机制 (L0/L1/L2)
- 向量语义检索

作者: 阿月
日期: 2026-03-28
版本: 1.0.0
"""

import json
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, asdict
from collections import defaultdict
import hashlib
import re

# 尝试导入sentence-transformers
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False


# ============ 配置 ============
MEMORY_BASE_PATH = Path("~/.openclaw/workspace/memory").expanduser()


# ============ 数据模型 ============

@dataclass
class MemoryNode:
    """记忆节点 - 关联网络中的节点"""
    id: str
    content: str
    embedding: np.ndarray
    timestamp: datetime
    level: str
    source: str = "manual"  # manual, rss, conversation, system
    activation_count: int = 0
    last_accessed: Optional[datetime] = None
    associations: Dict[str, float] = None
    
    def __post_init__(self):
        if self.associations is None:
            self.associations = {}
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'content': self.content,
            'embedding': self.embedding.tolist() if isinstance(self.embedding, np.ndarray) else self.embedding,
            'timestamp': self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
            'level': self.level,
            'source': self.source,
            'activation_count': self.activation_count,
            'last_accessed': self.last_accessed.isoformat() if isinstance(self.last_accessed, datetime) else self.last_accessed,
            'associations': self.associations
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'MemoryNode':
        ts = data['timestamp']
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        
        last_accessed = data.get('last_accessed')
        if isinstance(last_accessed, str):
            last_accessed = datetime.fromisoformat(last_accessed)
        
        embedding = data['embedding']
        if isinstance(embedding, list):
            embedding = np.array(embedding)
        
        return cls(
            id=data['id'],
            content=data['content'],
            embedding=embedding,
            timestamp=ts,
            level=data['level'],
            source=data.get('source', 'manual'),
            activation_count=data.get('activation_count', 0),
            last_accessed=last_accessed,
            associations=data.get('associations', {})
        )


# ============ 嵌入编码器 ============

class LunaEmbedder:
    """月魂嵌入编码器 - 支持真实模型或fallback"""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.dim = 384
        self.model = None
        
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                print(f"🔄 加载嵌入模型: {model_name}")
                self.model = SentenceTransformer(model_name)
                print(f"✅ 模型加载完成，维度: {self.dim}")
            except Exception as e:
                print(f"⚠️  模型加载失败: {e}")
                self._init_fallback()
        else:
            print(f"⚠️  sentence-transformers 未安装，使用fallback编码")
            self._init_fallback()
    
    def _init_fallback(self):
        """初始化fallback词典"""
        self.vocab = {}
        keywords = [
            # 技术
            'fpga', 'verilog', '硬件', '芯片', 'mamba', 'transformer', '模型', '训练',
            'luna', '月魂', '三宇宙', '阿月', 'stdp', '脉冲', '神经网络', 'pac',
            # 记忆
            '记忆', '备份', '检索', '索引', '存储', '遗忘', '编码', '向量',
            # 时间
            '今天', '昨天', '上周', '之前', '最近', '现在', '未来',
            # 动作
            '创建', '修改', '删除', '完成', '实现', '设计', '优化', '整合',
            # 情感/重要性
            '好', '问题', '错误', '成功', '重要', '关键', '突破', '决定',
            # 实体
            '老吴', '主人', '项目', '代码', '系统', '架构', '框架', '模块',
            # 金融
            '美元', '日元', '利率', '汇率', '股市', '债市', '美联储', '央行',
            # 硬件
            'pynq', 'basys', 'vivado', 'xilinx', 'asic', 'soc', 'lpu',
        ]
        for i, kw in enumerate(keywords):
            self.vocab[kw] = i % self.dim
    
    def encode(self, text: str) -> np.ndarray:
        """将文本编码为向量"""
        if self.model:
            return self.model.encode(text, convert_to_numpy=True)
        else:
            return self._fallback_encode(text)
    
    def _fallback_encode(self, text: str) -> np.ndarray:
        """Fallback编码"""
        vec = np.zeros(self.dim)
        text_lower = text.lower()
        
        # 关键词匹配
        for word, idx in self.vocab.items():
            if word in text_lower:
                vec[idx] += 1.0
        
        # 如果无匹配，使用哈希
        if np.sum(vec) == 0:
            hash_val = int(hashlib.md5(text[:50].encode()).hexdigest(), 16)
            for i in range(min(20, self.dim)):
                vec[(hash_val + i * 7) % self.dim] = 0.5
        
        # 归一化
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        
        return vec
    
    def similarity(self, text1: str, text2: str) -> float:
        """计算两个文本的相似度"""
        vec1 = self.encode(text1)
        vec2 = self.encode(text2)
        return float(np.dot(vec1, vec2))


# ============ 关联网络 ============

class LunaAssociationNetwork:
    """月魂关联网络 - 记忆间的动态连接"""
    
    def __init__(self, base_path: Path = MEMORY_BASE_PATH):
        self.base_path = base_path
        self.nodes: Dict[str, MemoryNode] = {}
        self.edges: Dict[Tuple[str, str], float] = {}
        self.network_file = base_path / 'index' / 'association_network.json'
        
        self._load_network()
    
    def _load_network(self):
        """加载关联网络"""
        if self.network_file.exists():
            try:
                with open(self.network_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for node_data in data.get('nodes', []):
                        try:
                            node = MemoryNode.from_dict(node_data)
                            self.nodes[node.id] = node
                        except Exception as e:
                            print(f"⚠️  加载节点失败: {e}")
                    
                    edges_data = data.get('edges', {})
                    for k, v in edges_data.items():
                        parts = k.split('|')
                        if len(parts) == 2:
                            self.edges[(parts[0], parts[1])] = v
                
                print(f"🔄 加载关联网络: {len(self.nodes)} 节点, {len(self.edges)} 边")
            except Exception as e:
                print(f"⚠️  加载网络失败: {e}")
    
    def save_network(self):
        """保存关联网络"""
        self.network_file.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            'nodes': [node.to_dict() for node in self.nodes.values()],
            'edges': {f"{k[0]}|{k[1]}": v for k, v in self.edges.items()},
            'updated_at': datetime.now().isoformat()
        }
        
        with open(self.network_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def add_node(self, node: MemoryNode, build_associations: bool = True):
        """添加节点"""
        self.nodes[node.id] = node
        
        if build_associations:
            self._build_associations(node)
        
        self.save_network()
    
    def _build_associations(self, new_node: MemoryNode, threshold: float = 0.3):
        """自动构建关联"""
        for existing_id, existing_node in self.nodes.items():
            if existing_id == new_node.id:
                continue
            
            # 向量相似度
            similarity = float(np.dot(new_node.embedding, existing_node.embedding))
            
            # 时间邻近性
            time_diff = abs((new_node.timestamp - existing_node.timestamp).total_seconds())
            time_proximity = np.exp(-time_diff / (7 * 24 * 3600))
            
            # 综合权重
            weight = similarity * 0.6 + time_proximity * 0.4
            
            if weight > threshold:
                new_node.associations[existing_id] = weight
                existing_node.associations[new_node.id] = weight
                self.edges[(new_node.id, existing_id)] = weight
                self.edges[(existing_id, new_node.id)] = weight
    
    def activate(self, node_id: str, spread_depth: int = 2) -> Dict[str, float]:
        """激活节点并扩散"""
        if node_id not in self.nodes:
            return {}
        
        activated = {node_id: 1.0}
        current_layer = {node_id}
        
        for depth in range(spread_depth):
            next_layer = set()
            
            for current_id in current_layer:
                if current_id not in self.nodes:
                    continue
                    
                current_node = self.nodes[current_id]
                current_strength = activated[current_id]
                
                current_node.activation_count += 1
                current_node.last_accessed = datetime.now()
                
                for assoc_id, weight in current_node.associations.items():
                    new_strength = current_strength * weight * 0.7
                    
                    if new_strength > 0.05:
                        if assoc_id not in activated or activated[assoc_id] < new_strength:
                            activated[assoc_id] = new_strength
                            next_layer.add(assoc_id)
            
            current_layer = next_layer
            if not current_layer:
                break
        
        self.save_network()
        return activated
    
    def get_related(self, node_id: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """获取相关节点"""
        if node_id not in self.nodes:
            return []
        
        node = self.nodes[node_id]
        related = sorted(node.associations.items(), key=lambda x: x[1], reverse=True)
        return related[:top_k]


# ============ 遗忘机制 ============

class LunaForgetting:
    """月魂遗忘机制"""
    
    def __init__(self):
        self.tau_fast = 24 * 3600       # 1天
        self.tau_slow = 30 * 24 * 3600  # 30天
        self.tau_meta = 365 * 24 * 3600 # 1年
        self.activation_threshold = 0.1
    
    def calculate_strength(self, node: MemoryNode) -> float:
        """计算记忆强度"""
        base_strength = {'L0': 0.3, 'L1': 0.6, 'L2': 0.9}.get(node.level, 0.5)
        activation_boost = min(0.3, node.activation_count * 0.05)
        
        if node.last_accessed:
            time_since = (datetime.now() - node.last_accessed).total_seconds()
        else:
            time_since = (datetime.now() - node.timestamp).total_seconds()
        
        tau = {'L0': self.tau_fast, 'L1': self.tau_slow, 'L2': self.tau_meta}.get(node.level, self.tau_slow)
        decay = np.exp(-time_since / tau)
        
        strength = (base_strength + activation_boost) * decay
        return min(1.0, max(0.0, strength))
    
    def should_forget(self, node: MemoryNode) -> bool:
        """判断是否应该遗忘"""
        return self.calculate_strength(node) < self.activation_threshold
    
    def get_candidates(self, nodes: List[MemoryNode]) -> List[MemoryNode]:
        """获取遗忘候选"""
        candidates = [n for n in nodes if self.should_forget(n) and n.level in ['L0', 'L1']]
        candidates.sort(key=lambda n: self.calculate_strength(n))
        return candidates


# ============ 主存储系统 ============

class LunaMemorySystem:
    """月魂记忆系统 - 主入口"""
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, base_path: Path = MEMORY_BASE_PATH):
        if self._initialized:
            return
        
        self.base_path = Path(base_path)
        self.embedder = LunaEmbedder()
        self.network = LunaAssociationNetwork(self.base_path)
        self.forgetting = LunaForgetting()
        
        self._init_directories()
        self.stats = {'stored': 0, 'retrieved': 0, 'forgotten': 0}
        self._initialized = True
        
        print(f"✅ LunaMemorySystem 初始化完成")
        print(f"   节点数: {len(self.network.nodes)}")
        print(f"   关联数: {len(self.network.edges)}")
    
    def _init_directories(self):
        """初始化目录结构"""
        for d in ['working', 'daily', 'essence', 'index', 'archive', 'finance/incoming']:
            (self.base_path / d).mkdir(parents=True, exist_ok=True)
    
    # ============ 核心API ============
    
    def store(self, content: str, level: Optional[str] = None, 
              source: str = "manual") -> str:
        """
        存储记忆
        
        Args:
            content: 记忆内容
            level: L0(工作)/L1(短期)/L2(长期)，None则自动判断
            source: 来源 (manual/rss/conversation/system)
        
        Returns:
            记忆ID
        """
        # 生成ID
        memory_id = f"mem_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(content) % 10000:04d}"
        
        # 编码
        embedding = self.embedder.encode(content)
        
        # 选择性决策
        if level is None:
            level = self._decide_level(content, embedding)
        
        # 创建节点
        node = MemoryNode(
            id=memory_id,
            content=content,
            embedding=embedding,
            timestamp=datetime.now(),
            level=level,
            source=source
        )
        
        # 添加到网络
        self.network.add_node(node)
        
        # 保存到文件
        self._save_to_file(node)
        
        self.stats['stored'] += 1
        return memory_id
    
    def retrieve(self, query: str, top_k: int = 5, 
                 time_window_days: int = 365,
                 use_network: bool = True) -> List[Dict]:
        """
        检索记忆
        
        Args:
            query: 查询文本
            top_k: 返回数量
            time_window_days: 时间窗口
            use_network: 是否使用关联网络增强
        
        Returns:
            记忆列表
        """
        if not self.network.nodes:
            return []
        
        query_embedding = self.embedder.encode(query)
        
        # 向量搜索
        candidates = []
        for node in self.network.nodes.values():
            time_diff = (datetime.now() - node.timestamp).days
            if time_diff > time_window_days:
                continue
            
            similarity = float(np.dot(query_embedding, node.embedding))
            strength = self.forgetting.calculate_strength(node)
            score = similarity * strength
            
            if score > 0.05:
                candidates.append((node, score))
        
        # 网络增强
        if use_network and candidates:
            candidates = self._network_enhance(candidates, query_embedding)
        
        # 排序
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        # 格式化
        results = []
        for node, score in candidates[:top_k]:
            results.append({
                'id': node.id,
                'content': node.content,
                'timestamp': node.timestamp.isoformat(),
                'level': node.level,
                'source': node.source,
                'score': float(score),
                'strength': self.forgetting.calculate_strength(node),
                'activation_count': node.activation_count,
                'associations': len(node.associations)
            })
        
        self.stats['retrieved'] += 1
        return results
    
    def remember(self, query: str) -> str:
        """
        回忆 - 自然语言接口
        
        Args:
            query: 查询（如"昨天讨论的FPGA方案"）
        
        Returns:
            格式化的回忆文本
        """
        results = self.retrieve(query, top_k=3)
        
        if not results:
            return "记忆中未找到相关内容。"
        
        lines = [f"找到 {len(results)} 条相关记忆："]
        for i, r in enumerate(results, 1):
            lines.append(f"\n{i}. [{r['level']}] 相关度: {r['score']:.2f}")
            lines.append(f"   {r['content'][:200]}...")
            lines.append(f"   时间: {r['timestamp'][:10]} | 激活: {r['activation_count']}次")
        
        return "\n".join(lines)
    
    def cleanup(self, dry_run: bool = True) -> Dict:
        """
        清理遗忘记忆
        
        Returns:
            清理统计
        """
        candidates = self.forgetting.get_candidates(list(self.network.nodes.values()))
        
        forgotten_ids = []
        for node in candidates[:20]:  # 每次最多20个
            forgotten_ids.append(node.id)
            
            if not dry_run:
                del self.network.nodes[node.id]
                for assoc_id in list(node.associations.keys()):
                    if assoc_id in self.network.nodes:
                        del self.network.nodes[assoc_id].associations[node.id]
                self.stats['forgotten'] += 1
        
        if not dry_run:
            self.network.save_network()
        
        return {
            'candidates': len(candidates),
            'forgotten': len(forgotten_ids),
            'dry_run': dry_run,
            'ids': forgotten_ids[:5]  # 只显示前5个
        }
    
    def get_stats(self) -> Dict:
        """获取系统统计"""
        return {
            'nodes': len(self.network.nodes),
            'edges': len(self.network.edges),
            'stored': self.stats['stored'],
            'retrieved': self.stats['retrieved'],
            'forgotten': self.stats['forgotten'],
            'embedding_model': 'sentence-transformers' if self.embedder.model else 'fallback',
            'memory_path': str(self.base_path)
        }
    
    # ============ 内部方法 ============
    
    def _decide_level(self, content: str, embedding: np.ndarray) -> str:
        """选择性决策"""
        important_keywords = ['完成', '成功', '决定', '设计', '架构', '关键', '重要', '突破', '整合']
        is_important = any(kw in content for kw in important_keywords)
        
        temp_keywords = ['测试', '临时', '草稿', '尝试', '可能', '也许']
        is_temp = any(kw in content for kw in temp_keywords)
        
        # 检查重复
        if self.network.nodes:
            max_sim = max(
                (float(np.dot(embedding, n.embedding)) for n in self.network.nodes.values()),
                default=0
            )
            if max_sim > 0.9:
                return 'L0'
        
        if is_important and not is_temp:
            return 'L2'
        elif is_temp:
            return 'L0'
        else:
            return 'L1'
    
    def _save_to_file(self, node: MemoryNode):
        """保存到文件"""
        if node.level == 'L0':
            file_path = self.base_path / 'working' / 'current_session.jsonl'
        elif node.level == 'L1':
            date_str = node.timestamp.strftime('%Y-%m-%d')
            file_path = self.base_path / 'daily' / f'{date_str}.jsonl'
        else:
            file_path = self.base_path / 'essence' / 'core_memories.jsonl'
        
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(node.to_dict(), ensure_ascii=False) + '\n')
    
    def _network_enhance(self, candidates: List[Tuple[MemoryNode, float]], 
                        query_embedding: np.ndarray) -> List[Tuple[MemoryNode, float]]:
        """关联网络增强"""
        enhanced = {node.id: score for node, score in candidates}
        
        for node, base_score in candidates[:3]:
            activated = self.network.activate(node.id, spread_depth=2)
            
            for assoc_id, activation in activated.items():
                if assoc_id not in enhanced and assoc_id in self.network.nodes:
                    assoc_node = self.network.nodes[assoc_id]
                    sim = float(np.dot(query_embedding, assoc_node.embedding))
                    score = sim * activation * 0.5
                    if score > 0.05:
                        enhanced[assoc_id] = score
        
        return [(self.network.nodes[nid], score) for nid, score in enhanced.items() if nid in self.network.nodes]


# ============ 便捷函数 ============

def get_memory_system() -> LunaMemorySystem:
    """获取记忆系统单例"""
    return LunaMemorySystem()


def store_memory(content: str, level: Optional[str] = None, source: str = "manual") -> str:
    """便捷存储函数"""
    return get_memory_system().store(content, level, source)


def retrieve_memory(query: str, top_k: int = 5) -> List[Dict]:
    """便捷检索函数"""
    return get_memory_system().retrieve(query, top_k)


def remember(query: str) -> str:
    """便捷回忆函数"""
    return get_memory_system().remember(query)


# ============ 测试 ============

def test_system():
    """系统测试"""
    print("=" * 70)
    print("Luna Memory System - 整合测试")
    print("=" * 70)
    
    # 初始化
    memory = LunaMemorySystem()
    
    print(f"\n[系统状态]")
    stats = memory.get_stats()
    print(f"  嵌入模型: {stats['embedding_model']}")
    print(f"  现有节点: {stats['nodes']}")
    print(f"  关联边: {stats['edges']}")
    
    # 测试存储
    print(f"\n[测试存储]")
    test_memories = [
        ("完成SelectiveSTDP的P1实现，整合到月魂主系统", "system"),
        ("sentence-transformers作为基准参照，STDP作为演进目标", "system"),
        ("临时测试数据，用于验证存储功能", "manual"),
    ]
    
    for content, source in test_memories:
        mid = memory.store(content, source=source)
        print(f"  ✅ {mid[:20]}... - {content[:40]}...")
    
    # 测试检索
    print(f"\n[测试检索]")
    queries = ["STDP实现", "sentence-transformers", "测试数据"]
    
    for query in queries:
        print(f"\n  查询: '{query}'")
        results = memory.retrieve(query, top_k=2)
        for r in results:
            print(f"    - [{r['level']}] 得分:{r['score']:.3f} {r['content'][:50]}...")
    
    # 测试回忆
    print(f"\n[测试回忆]")
    print(memory.remember("STDP整合"))
    
    # 测试清理
    print(f"\n[测试清理]")
    cleanup_result = memory.cleanup(dry_run=True)
    print(f"  遗忘候选: {cleanup_result['candidates']} 个")
    
    # 最终统计
    print(f"\n[最终统计]")
    stats = memory.get_stats()
    print(f"  总节点: {stats['nodes']}")
    print(f"  本次存储: {stats['stored']}")
    print(f"  本次检索: {stats['retrieved']}")
    
    print("\n" + "=" * 70)
    print("✅ 整合测试完成")
    print("=" * 70)
    
    return memory


if __name__ == "__main__":
    test_system()
