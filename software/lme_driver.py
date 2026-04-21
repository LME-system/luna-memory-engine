#!/usr/bin/env python3
"""
Luna Memory Engine (LME) Driver - LTI + Bio-STDP Fusion
统一驱动接口，支持软件仿真和PYNQ-Z2硬件

Author: Luna Project
Date: 2026-03-25
"""

import numpy as np
import time
from typing import List, Tuple, Optional, Dict, Union
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod

try:
    from pynq import Overlay, allocate, MMIO
    PYNQ_AVAILABLE = True
except ImportError:
    PYNQ_AVAILABLE = False


class TimeMode(Enum):
    """时间坐标模式"""
    T1_SYSTEM = 0      # 系统时间
    T2_SEMANTIC = 1    # 语义时间 (相对偏移)
    T3_UTC = 2         # 绝对UTC时间


@dataclass
class MemoryEvent:
    """记忆事件 - 支持三层时间坐标"""
    neuron_id: int
    weight: float
    t1: int = 0                    # 系统时间 (微秒)
    t2_offset: int = 0             # 语义偏移 (微秒，相对)
    t3_anchor: Optional[int] = None  # UTC锚定时间
    content: Optional[np.ndarray] = None  # 语义向量 q
    vitality: float = 0.0          # 激活动力 p
    
    def get_unified_time(self, mode: TimeMode, t3_ref: Optional[int] = None) -> int:
        """获取统一时间戳"""
        if mode == TimeMode.T1_SYSTEM:
            return self.t1
        elif mode == TimeMode.T2_SEMANTIC:
            return self.t1 + self.t2_offset
        elif mode == TimeMode.T3_UTC:
            if t3_ref is not None:
                return self.t1 + (t3_ref - self.t1)  # 简化: 使用T3参考
            return self.t1
        return self.t1


@dataclass
class SymplecticState:
    """辛流形上的状态 (q, p)"""
    q: np.ndarray   # 语义向量 (内容)
    p: np.ndarray   # 激活动量 (活力)
    
    def omega(self, other: 'SymplecticState') -> float:
        """辛形式 ω = dq ∧ dp"""
        # 简化: 点积近似
        return np.dot(self.q, other.p) - np.dot(other.q, self.p)
    
    def hamiltonian(self) -> float:
        """哈密顿量 H = H_content + H_activation + H_coupling"""
        H_content = np.dot(self.q, self.q) / 2  # 语义自洽性
        H_activation = np.dot(self.p, self.p) / 2  # 激活强度
        H_coupling = np.dot(self.q, self.p)  # 耦合
        return H_content + H_activation + H_coupling


class BaseLME(ABC):
    """Luna Memory Engine 抽象基类"""
    
    @abstractmethod
    def process(self, events: List[MemoryEvent]) -> Dict:
        """处理事件流"""
        pass
    
    @abstractmethod
    def query_causal_cone(self, center_event: int, radius: int, 
                          direction: str = 'past') -> List[int]:
        """光锥查询"""
        pass
    
    @abstractmethod
    def get_vitality(self, neuron_id: int) -> float:
        """获取神经元活力"""
        pass


class LMESimulator(BaseLME):
    """
    LME 软件模拟器
    实现完整的 LTI + Bio-STDP 融合逻辑
    """
    
    def __init__(self, n_neurons: int = 128, vec_dim: int = 512):
        self.n_neurons = n_neurons
        self.vec_dim = vec_dim
        
        # Bio-STDP 状态
        self.v_mem = np.zeros(n_neurons, dtype=np.float32)
        self.last_spike_time = np.zeros(n_neurons, dtype=np.int64)
        self.weights = np.random.randn(n_neurons, n_neurons) * 0.01
        self.weight_active = np.zeros((n_neurons, n_neurons), dtype=bool)
        
        # LTI 状态
        self.time_mode = TimeMode.T1_SYSTEM
        self.t3_reference = None  # UTC同步参考
        self.vitality = np.zeros(n_neurons, dtype=np.float32)
        self.last_access = np.zeros(n_neurons, dtype=np.int64)
        
        # 辛流形状态
        self.states = [SymplecticState(
            q=np.random.randn(vec_dim) * 0.01,
            p=np.zeros(vec_dim)
        ) for _ in range(n_neurons)]
        
        # 因果图
        self.causal_edges = {i: {'precedes': [], 'follows': []} 
                            for i in range(n_neurons)}
        
        # 配置参数
        self.tau_mem = 20.0
        self.v_th = 1.0
        self.A_plus = 0.01
        self.A_minus = -0.01
        self.tau_forget = 3600 * 1000 * 1000  # 1小时
        self.vitality_tau = 3600 * 1000 * 1000  # 1小时
        self.vitality_boost = 0.1
        
        # 统计
        self.forget_count = 0
        self.prune_count = 0
    
    def sync_t3(self, utc_timestamp_us: int):
        """同步T3 UTC时间"""
        self.t3_reference = utc_timestamp_us
        self.time_mode = TimeMode.T3_UTC
        print(f"[LTI] T3同步完成: UTC={utc_timestamp_us}")
    
    def set_time_mode(self, mode: TimeMode):
        """设置时间坐标模式"""
        self.time_mode = mode
        print(f"[LTI] 时间模式切换: {mode.name}")
    
    def stdp_window(self, dt_ms: float) -> float:
        """STDP窗口函数"""
        if dt_ms > 0 and dt_ms < 20:
            return self.A_plus * np.exp(-dt_ms / 20.0)
        elif dt_ms < 0 and dt_ms > -20:
            return self.A_minus * np.exp(dt_ms / 20.0)
        return 0.0
    
    def vitality_decay(self, time_diff_us: int) -> float:
        """活力衰减"""
        time_diff_h = time_diff_us / (3600 * 1000 * 1000)
        return np.exp(-time_diff_h)
    
    def update_vitality(self, neuron_id: int, timestamp: int):
        """更新神经元活力"""
        time_diff = timestamp - self.last_access[neuron_id]
        decay = self.vitality_decay(time_diff)
        
        self.vitality[neuron_id] = self.vitality[neuron_id] * decay + self.vitality_boost
        self.vitality[neuron_id] = min(self.vitality[neuron_id], 2.0)  # 上限
        self.last_access[neuron_id] = timestamp
        
        # 更新辛流形 p (活力)
        self.states[neuron_id].p[0] = self.vitality[neuron_id]
    
    def lif_update(self, events: List[MemoryEvent]) -> List[MemoryEvent]:
        """LIF神经元更新"""
        output_events = []
        current_time = int(time.time() * 1000000)
        
        for evt in events:
            nid = evt.neuron_id % self.n_neurons
            unified_time = evt.get_unified_time(self.time_mode, self.t3_reference)
            
            # 检查不应期
            time_since_spike = (unified_time - self.last_spike_time[nid]) / 1000.0
            if time_since_spike < 10:  # 10ms
                continue
            
            # 泄漏积分
            alpha = np.exp(-1.0 / self.tau_mem)
            self.v_mem[nid] = self.v_mem[nid] * alpha + evt.weight
            
            # 更新活力 (LTI)
            self.update_vitality(nid, unified_time)
            
            # 检查发放
            if self.v_mem[nid] >= self.v_th:
                output_evt = MemoryEvent(
                    neuron_id=nid,
                    weight=self.v_mem[nid],
                    t1=unified_time
                )
                output_events.append(output_evt)
                self.v_mem[nid] = 0.0
                self.last_spike_time[nid] = unified_time
                
                # 更新辛流形 q (内容)
                if evt.content is not None:
                    self.states[nid].q = evt.content
        
        return output_events
    
    def stdp_update(self, pre_events: List[MemoryEvent], 
                   post_events: List[MemoryEvent]):
        """STDP权重更新"""
        for post in post_events:
            for pre in pre_events:
                pre_id = pre.neuron_id % self.n_neurons
                post_id = post.neuron_id % self.n_neurons
                
                dt = (post.t1 - pre.t1) / 1000.0  # ms
                delta_w = self.stdp_window(dt)
                
                # 应用遗忘衰减
                time_diff = post.t1 - self.last_access[pre_id]
                decay = self.vitality_decay(time_diff)
                
                new_weight = self.weights[pre_id, post_id] * decay + delta_w
                new_weight = np.clip(new_weight, -1.0, 1.0)
                
                # 剪枝检查
                if abs(new_weight) < 0.05:
                    if self.weight_active[pre_id, post_id]:
                        self.prune_count += 1
                        self.weight_active[pre_id, post_id] = False
                    new_weight = 0.0
                else:
                    self.weight_active[pre_id, post_id] = True
                
                self.weights[pre_id, post_id] = new_weight
                
                # 更新因果图
                if delta_w > 0:
                    if post_id not in self.causal_edges[pre_id]['precedes']:
                        self.causal_edges[pre_id]['precedes'].append(post_id)
                    if pre_id not in self.causal_edges[post_id]['follows']:
                        self.causal_edges[post_id]['follows'].append(pre_id)
    
    def query_causal_cone(self, center_event: int, radius: int, 
                          direction: str = 'past') -> List[int]:
        """光锥查询 - 因果邻域"""
        visited = set()
        queue = [(center_event, 0)]
        result = []
        
        while queue:
            node, depth = queue.pop(0)
            if node in visited or depth > radius:
                continue
            visited.add(node)
            if depth > 0:  # 不包含中心
                result.append(node)
            
            # 扩展邻居
            if direction == 'past':
                neighbors = self.causal_edges[node]['follows']
            else:  # 'future'
                neighbors = self.causal_edges[node]['precedes']
            
            for neighbor in neighbors:
                if neighbor not in visited:
                    queue.append((neighbor, depth + 1))
        
        return result
    
    def get_vitality(self, neuron_id: int) -> float:
        """获取神经元活力"""
        return self.vitality[neuron_id % self.n_neurons]
    
    def get_symplectic_state(self, neuron_id: int) -> SymplecticState:
        """获取辛流形状态"""
        return self.states[neuron_id % self.n_neurons]
    
    def process(self, events: List[MemoryEvent]) -> Dict:
        """完整处理流程"""
        # 1. LIF更新 + 活力追踪
        output_events = self.lif_update(events)
        
        # 2. STDP学习
        self.stdp_update(events, output_events)
        
        # 3. 生成因果向量
        causal_vector = np.zeros(self.vec_dim)
        for evt in output_events:
            idx = evt.neuron_id % self.vec_dim
            causal_vector[idx] = evt.weight
        
        return {
            'output_events': output_events,
            'causal_vector': causal_vector,
            'vitality_mean': np.mean(self.vitality),
            'active_synapses': np.sum(self.weight_active),
            'time_mode': self.time_mode.name
        }
    
    def get_stats(self) -> Dict:
        """获取系统统计"""
        return {
            'n_neurons': self.n_neurons,
            'time_mode': self.time_mode.name,
            't3_synced': self.t3_reference is not None,
            'mean_vitality': np.mean(self.vitality),
            'max_vitality': np.max(self.vitality),
            'active_synapses': np.sum(self.weight_active),
            'sparsity': 1.0 - np.sum(self.weight_active) / (self.n_neurons ** 2),
            'forget_count': self.forget_count,
            'prune_count': self.prune_count
        }


class LMEHardware(BaseLME):
    """
    LME PYNQ-Z2 硬件驱动
    通过MMIO与RTL模块通信
    """
    
    def __init__(self, bitstream_path: Optional[str] = None):
        if not PYNQ_AVAILABLE:
            raise RuntimeError("PYNQ not available")
        
        if bitstream_path:
            self.overlay = Overlay(bitstream_path)
        else:
            raise ValueError("Bitstream path required for hardware mode")
        
        # MMIO寄存器映射
        self.mmio = self.overlay.lti_top.mmio
        
    def sync_t3(self, utc_timestamp_us: int):
        """同步T3 UTC时间到硬件"""
        # 写入T3同步寄存器
        self.mmio.write(0x10, utc_timestamp_us & 0xFFFFFFFF)
        self.mmio.write(0x14, (utc_timestamp_us >> 32) & 0xFFFFFFFF)
        
    def set_time_mode(self, mode: TimeMode):
        """设置硬件时间模式"""
        self.mmio.write(0x00, mode.value)
        
    def process(self, events: List[MemoryEvent]) -> Dict:
        """硬件事件处理"""
        # 通过DMA发送事件到硬件
        # 等待处理完成
        # 读取结果
        raise NotImplementedError("Hardware DMA interface TBD")
        
    def query_causal_cone(self, center_event: int, radius: int, 
                          direction: str = 'past') -> List[int]:
        """硬件光锥查询"""
        raise NotImplementedError("Hardware query interface TBD")
        
    def get_vitality(self, neuron_id: int) -> float:
        """读取硬件活力值"""
        # 读取活力追踪器寄存器
        vitality_raw = self.mmio.read(0x100 + neuron_id * 4)
        return vitality_raw / 256.0  # Q8.8定点数转换


# 工厂函数
def create_lme(mode: str = 'simulator', **kwargs) -> BaseLME:
    """创建LME实例"""
    if mode == 'simulator':
        return LMESimulator(**kwargs)
    elif mode == 'hardware':
        return LMEHardware(**kwargs)
    else:
        raise ValueError(f"Unknown mode: {mode}")


# 测试
if __name__ == '__main__':
    print("=" * 60)
    print("Luna Memory Engine (LME) - LTI + Bio-STDP Fusion Test")
    print("=" * 60)
    
    # 创建模拟器
    lme = create_lme('simulator', n_neurons=128, vec_dim=512)
    
    # 测试T3同步
    print("\n[测试1] T3时间同步")
    utc_now = int(time.time() * 1000000)
    lme.sync_t3(utc_now)
    
    # 测试事件处理
    print("\n[测试2] 事件处理 + 活力追踪")
    events = [
        MemoryEvent(neuron_id=0, weight=1.0, t1=utc_now),
        MemoryEvent(neuron_id=1, weight=0.8, t1=utc_now + 5000),
    ]
    result = lme.process(events)
    print(f"输出事件数: {len(result['output_events'])}")
    print(f"平均活力: {result['vitality_mean']:.4f}")
    
    # 测试辛几何
    print("\n[测试3] 辛流形状态")
    state0 = lme.get_symplectic_state(0)
    state1 = lme.get_symplectic_state(1)
    omega = state0.omega(state1)
    H = state0.hamiltonian()
    print(f"辛形式 ω(q₀,p₁) = {omega:.4f}")
    print(f"哈密顿量 H(q₀,p₀) = {H:.4f}")
    
    # 测试光锥查询
    print("\n[测试4] 光锥查询")
    past_cone = lme.query_causal_cone(0, radius=2, direction='past')
    future_cone = lme.query_causal_cone(0, radius=2, direction='future')
    print(f"过去光锥: {past_cone}")
    print(f"未来光锥: {future_cone}")
    
    # 统计
    print("\n[统计]")
    stats = lme.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
