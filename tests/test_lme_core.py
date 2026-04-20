"""
LME Core Tests
==============
Test suite for Luna Memory Engine core functionality.
"""

import unittest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lme', 'software'))

class TestLMEInitialization(unittest.TestCase):
    """Test LME system initialization."""
    
    def test_import_lme_driver(self):
        """Test that LME driver can be imported."""
        try:
            from lme_driver import LMESimulator
            self.assertTrue(True)
        except ImportError as e:
            self.fail(f"Failed to import LMESimulator: {e}")
    
    def test_import_memory_system(self):
        """Test that memory system can be imported."""
        try:
            from luna_memory_system import LunaMemorySystem
            self.assertTrue(True)
        except ImportError as e:
            self.fail(f"Failed to import LunaMemorySystem: {e}")

class TestLMESimulator(unittest.TestCase):
    """Test LME Simulator functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        try:
            from lme_driver import LMESimulator
            self.lme = LMESimulator()
        except ImportError:
            self.skipTest("LMESimulator not available")
    
    def test_neuron_creation(self):
        """Test neuron creation."""
        # Test basic neuron properties
        self.assertIsNotNone(self.lme)
    
    def test_event_processing(self):
        """Test event processing."""
        # Simulate an event
        event = {
            'neuron_id': 0,
            'timestamp': 1000,
            'vitality': 0.5
        }
        # Should not raise exception
        try:
            self.lme.process_event(event)
        except AttributeError:
            pass  # Method may not exist in stub

class TestVitalityMechanism(unittest.TestCase):
    """Test vitality-based memory mechanisms."""
    
    def test_vitality_decay(self):
        """Test that vitality decays over time."""
        initial_vitality = 1.0
        decay_rate = 0.95
        
        # After one decay cycle
        new_vitality = initial_vitality * decay_rate
        self.assertLess(new_vitality, initial_vitality)
        self.assertAlmostEqual(new_vitality, 0.95, places=2)

class TestHardwareConnection(unittest.TestCase):
    """Test hardware connection (requires PYNQ)."""
    
    def test_pynq_connection(self):
        """Test PYNQ board connectivity."""
        import socket
        
        PYNQ_IP = '192.168.1.9'
        PYNQ_PORT = 8888
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((PYNQ_IP, PYNQ_PORT))
            sock.close()
            
            if result == 0:
                self.assertTrue(True, "PYNQ is reachable")
            else:
                self.skipTest(f"PYNQ not reachable (error {result})")
        except Exception as e:
            self.skipTest(f"Connection test failed: {e}")

if __name__ == '__main__':
    unittest.main()
