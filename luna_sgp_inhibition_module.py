#!/usr/bin/env python3
"""
Luna SGP - 激励/抑制模块 (Inhibition/Excitation Module)
=========================================================

实现交互感知、自我评价、递归改进的核心机制

设计哲学:
- 激励 (Excitation): 正向反馈，强化有效认知路径
- 抑制 (Inhibition): 负向反馈，削弱无效或冲突路径
- 递归改进: 基于历史表现的元学习

架构位置: Layer 4 编排器之上，作为元认知层 (Meta-Cognition Layer)

Author: 阿月 + 老吴
Date: 2026-08-28
Version: 0.1.0
"""

import time
import json
import sqlite3
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Callable, Any, Tuple
from enum import Enum, auto
from collections import deque
import numpy as np
from pathlib import Path


# =============================================================================
# 核心数据类型
# =============================================================================

class SignalType(Enum):
    """信号类型"""
    EXCITATION = auto()   # 激励 - 正向反馈
    INHIBITION = auto()   # 抑制 - 负向反馈
    NEUTRAL = auto()      # 中性 - 观察中


class InteractionPhase(Enum):
    """交互阶段"""
    PERCEPTION = "perception"      # 感知阶段
    PROCESSING = "processing"      # 处理阶段
    RESPONSE = "response"          # 响应阶段
    FEEDBACK = "feedback"          # 反馈阶段
    REFLECTION = "reflection"      # 反思阶段


@dataclass
class CognitiveTrace:
    """
    认知痕迹 - 单次交互的完整记录
    
    类比: 神经元的动作电位记录
    """
    trace_id: str
    timestamp: float
    query: str
    
    # 各层参与情况
    l1_contribution: float = 0.0   # L1 符号层贡献度
    l2_contribution: float = 0.0   # L2 几何层贡献度
    l3_contribution: float = 0.0   # L3 拓扑层贡献度
    
    # 性能指标
    latency_ms: float = 0.0        # 响应延迟
    token_count: int = 0           # 生成 token 数
    confidence: float = 0.0        # 置信度 (0-1)
    
    # 反馈信号
    user_feedback: Optional[float] = None  # 用户显式反馈 (-1 到 +1)
    implicit_feedback: Optional[float] = None  # 隐式反馈 (如后续追问)
    
    # 自我评价
    self_score: float = 0.0        # 自我评分
    coherence: float = 0.0         # 内部一致性
    novelty: float = 0.0           # 新颖性
    
    # 元数据
    tags: List[str] = field(default_factory=list)
    context_hash: str = ""         # 上下文指纹


@dataclass
class PathwayWeight:
    """
    认知路径权重 - 动态调节各层协作
    
    类比: 神经突触的可塑性
    """
    pathway_id: str
    
    # 路径定义: 如 "L1->L2->L3", "L1->L2", "L1->Synthesis"
    route: List[str]
    
    # 权重参数
    base_weight: float = 1.0       # 基础权重
    current_weight: float = 1.0    # 当前权重 (动态调节)
    
    # 历史表现
    success_count: int = 0
    failure_count: int = 0
    total_invocations: int = 0
    
    # 时间衰减
    last_used: float = 0.0
    decay_rate: float = 0.01       # 每次未使用的衰减率
    
    # 激励/抑制积累
    excitation_accumulator: float = 0.0
    inhibition_accumulator: float = 0.0
    
    def compute_effective_weight(self) -> float:
        """计算有效权重 (考虑激励/抑制)"""
        # 激励增强，抑制削弱
        ei_ratio = self.excitation_accumulator - self.inhibition_accumulator
        
        # 时间衰减
        time_since_use = time.time() - self.last_used if self.last_used > 0 else 0
        decay_factor = max(0.5, 1.0 - self.decay_rate * time_since_use / 86400)  # 按天衰减
        
        # 成功率调节
        if self.total_invocations > 0:
            success_rate = self.success_count / self.total_invocations
        else:
            success_rate = 0.5
        
        effective = self.base_weight * (1 + 0.3 * ei_ratio) * decay_factor * (0.5 + 0.5 * success_rate)
        return max(0.1, min(2.0, effective))  # 限制在 0.1-2.0 范围


# =============================================================================
# 激励/抑制核心引擎
# =============================================================================

class InhibitionEngine:
    """
    激励/抑制引擎
    
    核心功能:
    1. 交互感知 - 捕获并分析每次认知过程
    2. 自我评价 - 基于多维度指标的自我评估
    3. 递归改进 - 动态调整认知路径权重
    """
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or Path.home() / ".openclaw" / "luna_inhibition.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 内存缓存
        self.recent_traces: deque = deque(maxlen=100)  # 最近 100 条痕迹
        self.pathway_weights: Dict[str, PathwayWeight] = {}
        
        # 回调函数
        self.on_excitation: Optional[Callable] = None
        self.on_inhibition: Optional[Callable] = None
        
        # 初始化数据库
        self._init_database()
        self._load_pathways()
    
    def _init_database(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cognitive_traces (
                    trace_id TEXT PRIMARY KEY,
                    timestamp REAL,
                    query TEXT,
                    l1_contribution REAL,
                    l2_contribution REAL,
                    l3_contribution REAL,
                    latency_ms REAL,
                    token_count INTEGER,
                    confidence REAL,
                    user_feedback REAL,
                    implicit_feedback REAL,
                    self_score REAL,
                    coherence REAL,
                    novelty REAL,
                    tags TEXT,
                    context_hash TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pathway_weights (
                    pathway_id TEXT PRIMARY KEY,
                    route TEXT,
                    base_weight REAL,
                    current_weight REAL,
                    success_count INTEGER,
                    failure_count INTEGER,
                    total_invocations INTEGER,
                    last_used REAL,
                    decay_rate REAL,
                    excitation_accumulator REAL,
                    inhibition_accumulator REAL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS feedback_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT,
                    signal_type TEXT,
                    magnitude REAL,
                    timestamp REAL,
                    reason TEXT
                )
            """)
    
    def _load_pathways(self):
        """从数据库加载路径权重"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT * FROM pathway_weights")
            for row in cursor:
                pw = PathwayWeight(
                    pathway_id=row[0],
                    route=json.loads(row[1]),
                    base_weight=row[2],
                    current_weight=row[3],
                    success_count=row[4],
                    failure_count=row[5],
                    total_invocations=row[6],
                    last_used=row[7],
                    decay_rate=row[8],
                    excitation_accumulator=row[9],
                    inhibition_accumulator=row[10]
                )
                self.pathway_weights[pw.pathway_id] = pw
    
    # ========================================================================
    # 交互感知接口
    # ========================================================================
    
    def perceive_interaction(self, 
                           query: str,
                           l1_result: Optional[Dict] = None,
                           l2_result: Optional[Dict] = None,
                           l3_result: Optional[Dict] = None,
                           latency_ms: float = 0.0,
                           **kwargs) -> CognitiveTrace:
        """
        感知一次交互 - 记录认知痕迹
        
        这是激励/抑制模块的入口点，在每次 Luna SGP 处理后被调用
        """
        # 从 kwargs 提取或计算各层贡献
        l1_contrib = kwargs.pop('l1_contribution', l1_result.get("contribution", 0.0) if l1_result else 0.0)
        l2_contrib = kwargs.pop('l2_contribution', l2_result.get("contribution", 0.0) if l2_result else 0.0)
        l3_contrib = kwargs.pop('l3_contribution', l3_result.get("contribution", 0.0) if l3_result else 0.0)
        
        trace = CognitiveTrace(
            trace_id=f"trace_{int(time.time() * 1000)}_{hash(query) % 10000}",
            timestamp=time.time(),
            query=query,
            l1_contribution=l1_contrib,
            l2_contribution=l2_contrib,
            l3_contribution=l3_contrib,
            latency_ms=latency_ms,
            **kwargs
        )
        
        # 计算自我评分
        trace.self_score = self._compute_self_score(trace)
        trace.coherence = self._compute_coherence(trace)
        trace.novelty = self._compute_novelty(trace)
        
        # 缓存和持久化
        self.recent_traces.append(trace)
        self._persist_trace(trace)
        
        return trace
    
    def _compute_self_score(self, trace: CognitiveTrace) -> float:
        """基于内部指标计算自我评分"""
        # 多因素评分
        latency_score = max(0, 1.0 - trace.latency_ms / 10000)  # 延迟惩罚
        confidence_score = trace.confidence
        layer_balance = 1.0 - abs(trace.l1_contribution - trace.l2_contribution - trace.l3_contribution)
        
        return (latency_score * 0.3 + confidence_score * 0.5 + layer_balance * 0.2)
    
    def _compute_coherence(self, trace: CognitiveTrace) -> float:
        """计算内部一致性"""
        contributions = [trace.l1_contribution, trace.l2_contribution, trace.l3_contribution]
        if sum(contributions) == 0:
            return 0.5
        
        # 检查各层贡献是否协调
        variance = np.var(contributions)
        coherence = 1.0 - min(1.0, variance * 3)  # 方差越小越一致
        return coherence
    
    def _compute_novelty(self, trace: CognitiveTrace) -> float:
        """计算相对于历史的新颖性"""
        if not self.recent_traces:
            return 0.5
        
        # 简单的上下文哈希相似度
        recent_hashes = [t.context_hash for t in list(self.recent_traces)[-10:]]
        if trace.context_hash in recent_hashes:
            return 0.2  # 重复场景
        
        return 0.8  # 新场景
    
    # ========================================================================
    # 自我评价
    # ========================================================================
    
    def self_evaluate(self, trace_id: str) -> Dict[str, Any]:
        """
        对特定认知痕迹进行自我评价
        
        返回多维度评估报告
        """
        trace = self._get_trace(trace_id)
        if not trace:
            return {"error": "Trace not found"}
        
        evaluation = {
            "trace_id": trace_id,
            "overall_score": trace.self_score,
            "dimensions": {
                "efficiency": {
                    "score": max(0, 1.0 - trace.latency_ms / 10000),
                    "latency_ms": trace.latency_ms,
                    "token_efficiency": trace.token_count / max(1, trace.latency_ms) * 1000
                },
                "quality": {
                    "score": trace.confidence,
                    "coherence": trace.coherence,
                    "layer_balance": {
                        "l1": trace.l1_contribution,
                        "l2": trace.l2_contribution,
                        "l3": trace.l3_contribution
                    }
                },
                "adaptability": {
                    "score": trace.novelty,
                    "is_novel": trace.novelty > 0.5
                }
            },
            "recommendations": self._generate_recommendations(trace)
        }
        
        return evaluation
    
    def _generate_recommendations(self, trace: CognitiveTrace) -> List[str]:
        """基于评估生成改进建议"""
        recommendations = []
        
        if trace.latency_ms > 5000:
            recommendations.append("考虑简化查询或降低复杂度")
        
        if trace.coherence < 0.5:
            recommendations.append("各层贡献不平衡，需要调整权重")
        
        if trace.confidence < 0.6:
            recommendations.append("置信度较低，建议增加验证步骤")
        
        return recommendations
    
    # ========================================================================
    # 激励/抑制应用
    # ========================================================================
    
    def apply_signal(self, 
                    trace_id: str, 
                    signal_type: SignalType,
                    magnitude: float = 1.0,
                    reason: str = ""):
        """
        应用激励或抑制信号
        
        这是递归改进的核心机制
        """
        trace = self._get_trace(trace_id)
        if not trace:
            return
        
        # 记录反馈事件
        self._record_feedback(trace_id, signal_type, magnitude, reason)
        
        # 确定受影响的路径
        pathway_id = self._determine_pathway(trace)
        
        if pathway_id not in self.pathway_weights:
            # 创建新路径
            route = self._build_route_from_trace(trace)
            self.pathway_weights[pathway_id] = PathwayWeight(
                pathway_id=pathway_id,
                route=route
            )
        
        pw = self.pathway_weights[pathway_id]
        
        # 应用信号
        if signal_type == SignalType.EXCITATION:
            pw.excitation_accumulator += magnitude
            pw.success_count += 1
            if self.on_excitation:
                self.on_excitation(pathway_id, magnitude, reason)
                
        elif signal_type == SignalType.INHIBITION:
            pw.inhibition_accumulator += magnitude
            pw.failure_count += 1
            if self.on_inhibition:
                self.on_inhibition(pathway_id, magnitude, reason)
        
        pw.total_invocations += 1
        pw.last_used = time.time()
        
        # 更新当前权重
        pw.current_weight = pw.compute_effective_weight()
        
        # 持久化
        self._persist_pathway(pw)
        
        return {
            "pathway_id": pathway_id,
            "new_weight": pw.current_weight,
            "signal_applied": signal_type.name
        }
    
    def _determine_pathway(self, trace: CognitiveTrace) -> str:
        """根据痕迹确定路径 ID"""
        # 基于各层贡献构建路径签名
        layers = []
        if trace.l1_contribution > 0.1:
            layers.append("L1")
        if trace.l2_contribution > 0.1:
            layers.append("L2")
        if trace.l3_contribution > 0.1:
            layers.append("L3")
        
        if not layers:
            layers = ["L1"]
        
        return "->".join(layers)
    
    def _build_route_from_trace(self, trace: CognitiveTrace) -> List[str]:
        """从痕迹构建路径"""
        route = ["Input"]
        if trace.l1_contribution > 0.1:
            route.append("L1")
        if trace.l2_contribution > 0.1:
            route.append("L2")
        if trace.l3_contribution > 0.1:
            route.append("L3")
        route.append("Output")
        return route
    
    # ========================================================================
    # 递归改进 - 路径选择
    # ========================================================================
    
    def select_optimal_pathway(self, 
                              query: str, 
                              complexity_hint: int = 1) -> PathwayWeight:
        """
        为给定查询选择最优认知路径
        
        这是递归改进的应用层接口
        """
        # 基于复杂度生成候选路径
        candidates = []
        
        if complexity_hint == 0:
            candidates = ["L1", "L1->L2", "L1->Output"]
        elif complexity_hint == 1:
            candidates = ["L1->L2", "L1->L2->L3", "L1->Output"]
        else:
            candidates = ["L1->L2->L3", "L1->L2->L3->L2", "L1->L2->L3->Synthesis"]
        
        # 选择权重最高的路径
        best_pathway = None
        best_weight = -1
        
        for candidate in candidates:
            pw = self.pathway_weights.get(candidate)
            if pw:
                weight = pw.compute_effective_weight()
            else:
                # 新路径，给予探索奖励
                weight = 1.0 + 0.2  # 探索奖励
            
            if weight > best_weight:
                best_weight = weight
                best_pathway = candidate
        
        # 返回或创建
        if best_pathway in self.pathway_weights:
            return self.pathway_weights[best_pathway]
        else:
            return PathwayWeight(
                pathway_id=best_pathway,
                route=best_pathway.split("->")
            )
    
    def get_learning_summary(self, n_recent: int = 100) -> Dict[str, Any]:
        """
        获取学习总结报告
        
        展示递归改进的效果
        """
        recent = list(self.recent_traces)[-n_recent:]
        
        if not recent:
            return {"message": "No traces recorded yet"}
        
        # 统计
        avg_score = np.mean([t.self_score for t in recent])
        avg_latency = np.mean([t.latency_ms for t in recent])
        avg_confidence = np.mean([t.confidence for t in recent])
        
        # 路径表现
        pathway_stats = {}
        for pw in self.pathway_weights.values():
            pathway_stats[pw.pathway_id] = {
                "current_weight": pw.current_weight,
                "success_rate": pw.success_count / max(1, pw.total_invocations),
                "total_uses": pw.total_invocations
            }
        
        return {
            "period": f"Last {len(recent)} interactions",
            "overall_metrics": {
                "avg_self_score": round(avg_score, 3),
                "avg_latency_ms": round(avg_latency, 1),
                "avg_confidence": round(avg_confidence, 3)
            },
            "pathway_performance": pathway_stats,
            "improvement_trend": self._compute_trend(recent)
        }
    
    def _compute_trend(self, traces: List[CognitiveTrace]) -> str:
        """计算改进趋势"""
        if len(traces) < 20:
            return "insufficient_data"
        
        # 分两半比较
        mid = len(traces) // 2
        first_half = traces[:mid]
        second_half = traces[mid:]
        
        first_score = np.mean([t.self_score for t in first_half])
        second_score = np.mean([t.self_score for t in second_half])
        
        diff = second_score - first_score
        if diff > 0.1:
            return "improving"
        elif diff < -0.1:
            return "declining"
        else:
            return "stable"
    
    # ========================================================================
    # 持久化
    # ========================================================================
    
    def _persist_trace(self, trace: CognitiveTrace):
        """持久化认知痕迹"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO cognitive_traces VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
            """, (
                trace.trace_id, trace.timestamp, trace.query,
                trace.l1_contribution, trace.l2_contribution, trace.l3_contribution,
                trace.latency_ms, trace.token_count, trace.confidence,
                trace.user_feedback, trace.implicit_feedback,
                trace.self_score, trace.coherence, trace.novelty,
                json.dumps(trace.tags), trace.context_hash
            ))
    
    def _persist_pathway(self, pw: PathwayWeight):
        """持久化路径权重"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO pathway_weights VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
            """, (
                pw.pathway_id, json.dumps(pw.route),
                pw.base_weight, pw.current_weight,
                pw.success_count, pw.failure_count, pw.total_invocations,
                pw.last_used, pw.decay_rate,
                pw.excitation_accumulator, pw.inhibition_accumulator
            ))
    
    def _record_feedback(self, trace_id: str, signal_type: SignalType, 
                        magnitude: float, reason: str):
        """记录反馈事件"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO feedback_events (trace_id, signal_type, magnitude, timestamp, reason)
                VALUES (?, ?, ?, ?, ?)
            """, (trace_id, signal_type.name, magnitude, time.time(), reason))
    
    def _get_trace(self, trace_id: str) -> Optional[CognitiveTrace]:
        """获取特定痕迹"""
        # 先查内存
        for t in self.recent_traces:
            if t.trace_id == trace_id:
                return t
        
        # 再查数据库
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM cognitive_traces WHERE trace_id = ?", (trace_id,)
            )
            row = cursor.fetchone()
            if row:
                return CognitiveTrace(
                    trace_id=row[0], timestamp=row[1], query=row[2],
                    l1_contribution=row[3], l2_contribution=row[4], l3_contribution=row[5],
                    latency_ms=row[6], token_count=row[7], confidence=row[8],
                    user_feedback=row[9], implicit_feedback=row[10],
                    self_score=row[11], coherence=row[12], novelty=row[13],
                    tags=json.loads(row[14]) if row[14] else [],
                    context_hash=row[15]
                )
        return None


# =============================================================================
# 与 Luna SGP Layer 4 的集成接口
# =============================================================================

class LunaSGPInhibitionAdapter:
    """
    Luna SGP 集成适配器
    
    将激励/抑制模块无缝集成到现有 Layer 4 编排器
    """
    
    def __init__(self, orchestrator: Any):
        self.orchestrator = orchestrator
        self.engine = InhibitionEngine()
        
        # 注册回调
        self.engine.on_excitation = self._on_excitation
        self.engine.on_inhibition = self._on_inhibition
    
    def _on_excitation(self, pathway_id: str, magnitude: float, reason: str):
        """激励回调 - 可以触发外部通知"""
        print(f"🟢 Excitation: {pathway_id} (+{magnitude}) - {reason}")
    
    def _on_inhibition(self, pathway_id: str, magnitude: float, reason: str):
        """抑制回调 - 可以触发告警或调整"""
        print(f"🔴 Inhibition: {pathway_id} (-{magnitude}) - {reason}")
    
    def process_with_feedback(self, query: str, **kwargs) -> Dict[str, Any]:
        """
        带反馈的处理流程
        
        包装原有的 orchestrator.process，添加激励/抑制机制
        """
        start_time = time.time()
        
        # 1. 选择最优路径
        complexity = kwargs.get("complexity", 1)
        optimal_path = self.engine.select_optimal_pathway(query, complexity)
        print(f"[Inhibition] Selected pathway: {optimal_path.pathway_id} (weight: {optimal_path.current_weight:.2f})")
        
        # 2. 执行原有处理
        try:
            result = self.orchestrator.process(query, **kwargs)
            latency = (time.time() - start_time) * 1000
            
            # 3. 感知交互
            trace = self.engine.perceive_interaction(
                query=query,
                l1_result=result.get("l1_result"),
                l2_result=result.get("l2_result"),
                l3_result=result.get("l3_result"),
                latency_ms=latency,
                confidence=result.get("confidence", 0.5)
            )
            
            # 4. 自我评价
            evaluation = self.engine.self_evaluate(trace.trace_id)
            
            # 5. 根据评价应用激励/抑制
            if evaluation["overall_score"] > 0.7:
                self.engine.apply_signal(
                    trace.trace_id, 
                    SignalType.EXCITATION, 
                    magnitude=0.2,
                    reason="High self-evaluation score"
                )
            elif evaluation["overall_score"] < 0.4:
                self.engine.apply_signal(
                    trace.trace_id,
                    SignalType.INHIBITION,
                    magnitude=0.15,
                    reason="Low self-evaluation score"
                )
            
            return {
                "result": result,
                "trace_id": trace.trace_id,
                "evaluation": evaluation,
                "pathway_used": optimal_path.pathway_id
            }
            
        except Exception as e:
            # 失败时应用抑制
            trace = self.engine.perceive_interaction(
                query=query,
                latency_ms=(time.time() - start_time) * 1000,
                confidence=0.0
            )
            self.engine.apply_signal(
                trace.trace_id,
                SignalType.INHIBITION,
                magnitude=0.3,
                reason=f"Processing error: {str(e)}"
            )
            raise
    
    def provide_user_feedback(self, trace_id: str, feedback: float, comment: str = ""):
        """
        接收用户显式反馈
        
        feedback: -1.0 (非常不满意) 到 +1.0 (非常满意)
        """
        trace = self.engine._get_trace(trace_id)
        if trace:
            trace.user_feedback = feedback
            self.engine._persist_trace(trace)
            
            # 应用相应信号
            if feedback > 0.5:
                signal = SignalType.EXCITATION
                magnitude = feedback * 0.3
            elif feedback < -0.5:
                signal = SignalType.INHIBITION
                magnitude = abs(feedback) * 0.3
            else:
                signal = SignalType.NEUTRAL
                magnitude = 0.1
            
            self.engine.apply_signal(
                trace_id, signal, magnitude,
                reason=f"User feedback: {comment} ({feedback})"
            )
    
    def get_learning_report(self) -> Dict[str, Any]:
        """获取学习报告"""
        return self.engine.get_learning_summary()


# =============================================================================
# 测试和演示
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Luna SGP 激励/抑制模块测试")
    print("=" * 60)
    
    # 创建引擎
    engine = InhibitionEngine()
    
    # 模拟一些交互
    print("\n1. 模拟认知痕迹...")
    
    for i in range(5):
        trace = engine.perceive_interaction(
            query=f"Test query {i}",
            l1_contribution=0.3 + i * 0.1,
            l2_contribution=0.4,
            l3_contribution=0.2 + i * 0.05,
            latency_ms=1000 + i * 200,
            confidence=0.6 + i * 0.05
        )
        print(f"   Trace {i}: score={trace.self_score:.2f}, coherence={trace.coherence:.2f}")
    
    # 应用激励/抑制
    print("\n2. 应用激励/抑制信号...")
    
    recent_traces = list(engine.recent_traces)
    
    # 对表现好的激励
    engine.apply_signal(
        recent_traces[3].trace_id,
        SignalType.EXCITATION,
        magnitude=0.5,
        reason="Good performance on complex query"
    )
    
    # 对表现差的抑制
    engine.apply_signal(
        recent_traces[0].trace_id,
        SignalType.INHIBITION,
        magnitude=0.3,
        reason="Slow response time"
    )
    
    # 选择最优路径
    print("\n3. 路径选择...")
    for complexity in [0, 1, 2]:
        pathway = engine.select_optimal_pathway("test", complexity)
        print(f"   Complexity {complexity}: {pathway.pathway_id} (weight: {pathway.current_weight:.2f})")
    
    # 学习总结
    print("\n4. 学习总结...")
    summary = engine.get_learning_summary()
    print(f"   Overall score: {summary['overall_metrics']['avg_self_score']:.3f}")
    print(f"   Trend: {summary['improvement_trend']}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
