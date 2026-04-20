"""
Pytest configuration and fixtures.
"""

import pytest

@pytest.fixture
def sample_memory():
    """Return a sample memory entry."""
    return {
        'content': 'Sample test memory',
        'timestamp': 1234567890,
        'vitality': 0.8,
        'metadata': {'test': True}
    }

@pytest.fixture
def pynq_config():
    """Return PYNQ configuration."""
    return {
        'ip': '192.168.1.9',
        'ports': {
            'event': 8888,
            'vitality': 8889,
            'report': 8890
        }
    }
