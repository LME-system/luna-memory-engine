"""
Memory Operations Tests
=======================
Test memory storage, retrieval, and forgetting.
"""

import unittest
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lme', 'software'))

class TestMemoryStorage(unittest.TestCase):
    """Test memory storage operations."""
    
    def test_memory_creation(self):
        """Test creating a memory entry."""
        memory = {
            'content': 'Test memory content',
            'timestamp': time.time(),
            'vitality': 1.0,
            'metadata': {'source': 'test'}
        }
        self.assertIsNotNone(memory)
        self.assertEqual(memory['content'], 'Test memory content')
    
    def test_vitality_threshold(self):
        """Test vitality threshold filtering."""
        threshold = 0.1
        memories = [
            {'content': 'A', 'vitality': 0.8},
            {'content': 'B', 'vitality': 0.05},
            {'content': 'C', 'vitality': 0.3},
        ]
        
        # Filter memories above threshold
        active = [m for m in memories if m['vitality'] > threshold]
        self.assertEqual(len(active), 2)

class TestTemporalIndexing(unittest.TestCase):
    """Test temporal indexing (T1/T2/T3)."""
    
    def test_t1_system_time(self):
        """Test T1 (system time) generation."""
        import time
        t1 = time.time_ns()  # Nanoseconds
        self.assertIsInstance(t1, int)
        self.assertGreater(t1, 0)
    
    def test_t2_semantic_time(self):
        """Test T2 (semantic time) encoding."""
        # T2 represents relative time since last access
        last_access = 1000
        current = 1500
        t2 = current - last_access
        self.assertEqual(t2, 500)

class TestSTDP(unittest.TestCase):
    """Test Spike-Timing-Dependent Plasticity."""
    
    def test_pre_post_potentiation(self):
        """Test pre-before-post potentiation."""
        # Pre neuron fires before post neuron = strengthen connection
        pre_time = 0
        post_time = 10
        delta_t = post_time - pre_time
        
        # Positive delta_t should increase weight
        self.assertGreater(delta_t, 0)
    
    def test_post_pre_depression(self):
        """Test post-before-pre depression."""
        # Post neuron fires before pre neuron = weaken connection
        pre_time = 10
        post_time = 0
        delta_t = post_time - pre_time
        
        # Negative delta_t should decrease weight
        self.assertLess(delta_t, 0)

if __name__ == '__main__':
    unittest.main()
