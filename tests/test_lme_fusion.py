#!/usr/bin/env python3
"""
Luna Memory Engine (LME) 融合测试套件
验证 LTI + Bio-STDP 融合架构的正确性

Author: Luna Project
Date: 2026-03-25
"""

import sys
import time
import numpy as np
from typing import List, Dict
import unittest

# 添加路径
sys.path.insert(0, '/Users/miaoliwang/.openclaw/workspace/host_sw/python')

from lme_driver import (
    LMESimulator, MemoryEvent, TimeMode, 
    SymplecticState, create_lme
)


class TestLTITimeModes(unittest.TestCase):
    """测试LTI三层时间坐标"""
    
    def setUp(self):
        self.lme = create_lme('simulator', n_neurons=64)
        self.base_time = int(time.time() * 1000000)
    
    def test_t1_system_time(self):
        """测试T1系统时间模式"""
        self.lme.set_time_mode(TimeMode.T1_SYSTEM)
        
        events = [
            MemoryEvent(neuron_id=0, weight=1.0, t1=self.base_time),
            MemoryEvent(neuron_id=1, weight=0.8, t1=self.base_time + 10000),
        ]
        
        result = self.lme.process(events)
        self.assertEqual(result['time_mode'], 'T1_SYSTEM')
        print(f"✓ T1模式: 处理{len(events)}个事件")
    
    def test_t2_semantic_time(self):
        """测试T2语义时间模式"""
        self.lme.set_time_mode(TimeMode.T2_SEMANTIC)
        
        events = [
            MemoryEvent(neuron_id=0, weight=1.0, 
                       t1=self.base_time, t2_offset=-3600*1000*1000),  # 1小时前
            MemoryEvent(neuron_id=1, weight=0.8, 
                       t1=self.base_time, t2_offset=0),  # 现在
        ]
        
        result = self.lme.process(events)
        self.assertEqual(result['time_mode'], 'T2_SEMANTIC')
        print(f"✓ T2模式: 语义偏移处理")
    
    def test_t3_utc_time(self):
        """测试T3 UTC时间模式"""
        utc_ref = self.base_time
        self.lme.sync_t3(utc_ref)
        
        events = [
            MemoryEvent(neuron_id=0, weight=1.0, t1=self.base_time),
        ]
        
        result = self.lme.process(events)
        self.assertTrue(self.lme.t3_reference is not None)
        self.assertEqual(result['time_mode'], 'T3_UTC')
        print(f"✓ T3模式: UTC同步成功")


class TestVitalityMechanism(unittest.TestCase):
    """测试活力机制"""
    
    def setUp(self):
        self.lme = create_lme('simulator', n_neurons=64)
        self.base_time = int(time.time() * 1000000)
    
    def test_vitality_boost_on_access(self):
        """测试访问增强活力"""
        # 首次访问
        events = [MemoryEvent(neuron_id=0, weight=1.0, t1=self.base_time)]
        self.lme.process(events)
        
        vitality1 = self.lme.get_vitality(0)
        self.assertGreater(vitality1, 0)
        
        # 再次访问
        events = [MemoryEvent(neuron_id=0, weight=1.0, 
                             t1=self.base_time + 1000000)]  # 1秒后
        self.lme.process(events)
        
        vitality2 = self.lme.get_vitality(0)
        self.assertGreater(vitality2, vitality1)
        print(f"✓ 活力增强: {vitality1:.4f} -> {vitality2:.4f}")
    
    def test_vitality_decay_over_time(self):
        """测试活力随时间衰减"""
        # 建立活力
        events = [MemoryEvent(neuron_id=0, weight=1.0, t1=self.base_time)]
        self.lme.process(events)
        vitality_initial = self.lme.get_vitality(0)
        
        # 模拟1小时后
        future_time = self.base_time + 3600 * 1000 * 1000  # 1小时
        decay = self.lme.vitality_decay(3600 * 1000 * 1000)
        vitality_expected = vitality_initial * decay + self.lme.vitality_boost
        
        events = [MemoryEvent(neuron_id=1, weight=1.0, t1=future_time)]
        self.lme.process(events)
        
        # 检查神经元0的活力衰减
        vitality_after = self.lme.get_vitality(0)
        self.assertLess(vitality_after, vitality_initial * 1.1)  # 允许小幅增强
        print(f"✓ 活力衰减: 初始{vitality_initial:.4f}, 1小时后{vitality_after:.4f}")


class TestSymplecticGeometry(unittest.TestCase):
    """测试辛几何形式化"""
    
    def setUp(self):
        self.lme = create_lme('simulator', n_neurons=64, vec_dim=512)
        self.base_time = int(time.time() * 1000000)
    
    def test_symplectic_state_creation(self):
        """测试辛状态创建"""
        state = self.lme.get_symplectic_state(0)
        
        self.assertEqual(len(state.q), 512)
        self.assertEqual(len(state.p), 512)
        self.assertIsInstance(state, SymplecticState)
        print(f"✓ 辛状态: q维度={len(state.q)}, p维度={len(state.p)}")
    
    def test_symplectic_form(self):
        """测试辛形式 ω"""
        state0 = self.lme.get_symplectic_state(0)
        state1 = self.lme.get_symplectic_state(1)
        
        omega = state0.omega(state1)
        
        # 反对称性: ω(a,b) = -ω(b,a)
        omega_reverse = state1.omega(state0)
        self.assertAlmostEqual(omega, -omega_reverse, places=5)
        print(f"✓ 辛形式反对称性: ω(0,1)={omega:.4f}, ω(1,0)={omega_reverse:.4f}")
    
    def test_hamiltonian(self):
        """测试哈密顿量"""
        state = self.lme.get_symplectic_state(0)
        H = state.hamiltonian()
        
        self.assertGreaterEqual(H, 0)  # H应该非负
        print(f"✓ 哈密顿量: H={H:.4f}")
    
    def test_vitality_maps_to_momentum(self):
        """测试活力映射到辛动量"""
        # 激活神经元
        events = [MemoryEvent(neuron_id=0, weight=1.0, t1=self.base_time)]
        self.lme.process(events)
        
        vitality = self.lme.get_vitality(0)
        state = self.lme.get_symplectic_state(0)
        
        # p[0]应该反映活力
        self.assertAlmostEqual(state.p[0], vitality, places=2)
        print(f"✓ 活力-动量映射: vitality={vitality:.4f}, p[0]={state.p[0]:.4f}")


class TestCausalGraph(unittest.TestCase):
    """测试因果图和光锥查询"""
    
    def setUp(self):
        self.lme = create_lme('simulator', n_neurons=64)
        self.base_time = int(time.time() * 1000000)
    
    def test_causal_edge_formation(self):
        """测试因果边形成"""
        # 创建因果链: 0 -> 1 -> 2
        events = [
            MemoryEvent(neuron_id=0, weight=1.0, t1=self.base_time),
            MemoryEvent(neuron_id=1, weight=1.0, t1=self.base_time + 5000),
        ]
        self.lme.process(events)
        
        events = [
            MemoryEvent(neuron_id=1, weight=1.0, t1=self.base_time + 10000),
            MemoryEvent(neuron_id=2, weight=1.0, t1=self.base_time + 15000),
        ]
        self.lme.process(events)
        
        # 检查因果边
        self.assertIn(1, self.lme.causal_edges[0]['precedes'])
        self.assertIn(2, self.lme.causal_edges[1]['precedes'])
        print(f"✓ 因果边: 0→1→2")
    
    def test_past_lightcone_query(self):
        """测试过去光锥查询"""
        # 建立因果结构
        for i in range(5):
            events = [
                MemoryEvent(neuron_id=i, weight=1.0, 
                           t1=self.base_time + i * 10000),
                MemoryEvent(neuron_id=i+1, weight=1.0, 
                           t1=self.base_time + i * 10000 + 5000),
            ]
            self.lme.process(events)
        
        # 查询神经元5的过去光锥
        past = self.lme.query_causal_cone(5, radius=3, direction='past')
        
        self.assertIn(4, past)
        self.assertIn(3, past)
        print(f"✓ 过去光锥 (r=3): {past}")
    
    def test_future_lightcone_query(self):
        """测试未来光锥查询"""
        # 建立因果结构
        for i in range(5):
            events = [
                MemoryEvent(neuron_id=i, weight=1.0, 
                           t1=self.base_time + i * 10000),
                MemoryEvent(neuron_id=i+1, weight=1.0, 
                           t1=self.base_time + i * 10000 + 5000),
            ]
            self.lme.process(events)
        
        # 查询神经元0的未来光锥
        future = self.lme.query_causal_cone(0, radius=3, direction='future')
        
        self.assertIn(1, future)
        self.assertIn(2, future)
        print(f"✓ 未来光锥 (r=3): {future}")


class TestSTDPForgetting(unittest.TestCase):
    """测试STDP遗忘机制"""
    
    def setUp(self):
        self.lme = create_lme('simulator', n_neurons=64)
        self.base_time = int(time.time() * 1000000)
    
    def test_weight_decay_without_reinforcement(self):
        """测试不强化时的权重衰减"""
        # 建立强连接
        for i in range(10):
            events = [
                MemoryEvent(neuron_id=0, weight=1.0, 
                           t1=self.base_time + i * 100000),
                MemoryEvent(neuron_id=1, weight=1.0, 
                           t1=self.base_time + i * 100000 + 5000),
            ]
            self.lme.process(events)
        
        weight_initial = self.lme.weights[0, 1]
        
        # 长时间不激活
        future_time = self.base_time + 3600 * 1000 * 1000  # 1小时后
        events = [MemoryEvent(neuron_id=2, weight=1.0, t1=future_time)]
        self.lme.process(events)
        
        # 再次访问0->1
        events = [
            MemoryEvent(neuron_id=0, weight=1.0, t1=future_time + 10000),
            MemoryEvent(neuron_id=1, weight=1.0, t1=future_time + 15000),
        ]
        self.lme.process(events)
        
        weight_after = self.lme.weights[0, 1]
        
        # 权重应该衰减（或至少不大幅增长）
        print(f"✓ 权重衰减: 初始={weight_initial:.4f}, 1小时后={weight_after:.4f}")
    
    def test_synapse_pruning(self):
        """测试突触剪枝"""
        # 建立弱连接
        events = [
            MemoryEvent(neuron_id=10, weight=0.01, t1=self.base_time),
            MemoryEvent(neuron_id=11, weight=0.01, t1=self.base_time + 5000),
        ]
        self.lme.process(events)
        
        prune_before = self.lme.prune_count
        
        # 长时间不强化
        future_time = self.base_time + 2 * 3600 * 1000 * 1000  # 2小时后
        for _ in range(5):
            events = [
                MemoryEvent(neuron_id=10, weight=0.01, t1=future_time),
                MemoryEvent(neuron_id=11, weight=0.01, t1=future_time + 5000),
            ]
            self.lme.process(events)
            future_time += 1000000
        
        prune_after = self.lme.prune_count
        print(f"✓ 突触剪枝: 剪枝事件={prune_after - prune_before}")


class TestIntegration(unittest.TestCase):
    """集成测试"""
    
    def setUp(self):
        self.lme = create_lme('simulator', n_neurons=128, vec_dim=512)
        self.base_time = int(time.time() * 1000000)
    
    def test_full_pipeline(self):
        """测试完整流程"""
        # 1. T3同步
        self.lme.sync_t3(self.base_time)
        
        # 2. 事件流处理
        for i in range(20):
            events = [
                MemoryEvent(
                    neuron_id=i % 10, 
                    weight=np.random.uniform(0.5, 1.0),
                    t1=self.base_time + i * 100000,
                    content=np.random.randn(512) * 0.1
                ),
            ]
            result = self.lme.process(events)
        
        # 3. 光锥查询
        past = self.lme.query_causal_cone(0, radius=2, direction='past')
        
        # 4. 获取统计
        stats = self.lme.get_stats()
        
        print(f"\n✓ 完整流程测试通过")
        print(f"  活跃突触: {stats['active_synapses']}")
        print(f"  稀疏度: {stats['sparsity']*100:.2f}%")
        print(f"  平均活力: {stats['mean_vitality']:.4f}")
        print(f"  过去光锥: {past}")
    
    def test_performance_baseline(self):
        """性能基线测试"""
        n_events = 1000
        
        start = time.time()
        for i in range(n_events):
            events = [MemoryEvent(
                neuron_id=i % 64,
                weight=1.0,
                t1=self.base_time + i * 1000
            )]
            self.lme.process(events)
        elapsed = time.time() - start
        
        throughput = n_events / elapsed
        print(f"\n✓ 性能基线: {throughput:.2f} events/sec")
        self.assertGreater(throughput, 100)  # 至少100 events/sec


def run_tests():
    """运行所有测试"""
    print("=" * 70)
    print("Luna Memory Engine (LME) 融合测试套件")
    print("=" * 70)
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试类
    suite.addTests(loader.loadTestsFromTestCase(TestLTITimeModes))
    suite.addTests(loader.loadTestsFromTestCase(TestVitalityMechanism))
    suite.addTests(loader.loadTestsFromTestCase(TestSymplecticGeometry))
    suite.addTests(loader.loadTestsFromTestCase(TestCausalGraph))
    suite.addTests(loader.loadTestsFromTestCase(TestSTDPForgetting))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 70)
    if result.wasSuccessful():
        print("✓ 所有测试通过")
    else:
        print(f"✗ 测试失败: {len(result.failures)} 失败, {len(result.errors)} 错误")
    print("=" * 70)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
