# LME API Documentation

## Software API

### LunaMemorySystem

```python
from luna_memory_system import LunaMemorySystem

# Initialize
lms = LunaMemorySystem()

# Store memory
lms.store(content, importance=0.5, metadata={})

# Query memories
results = lms.query(query_text, top_k=5)

# Get vitality stats
stats = lms.get_vitality_stats()
```

### YuehenLMEDaemon

```python
from yuehen_lme_daemon_v3 import YuehenLMEDaemon

# Initialize daemon
daemon = YuehenLMEDaemon(pynq_ip='192.168.1.9')

# Start daemon
daemon.start()

# Stop daemon
daemon.stop()
```

## Hardware API

### LMEHardwareDriver

```python
from lme_hardware_mmio import LMEHardwareDriver

# Connect to PYNQ
driver = LMEHardwareDriver(pynq_ip='192.168.1.9')

# Send event
driver.send_event(neuron_id, timestamp, vitality)

# Read vitality
driver.read_vitality(neuron_id)

# Get hardware stats
driver.get_stats()
```

## REST API (PYNQ)

### Event Stream (Port 8888)

```bash
POST /event
Content-Type: application/json

{
  "neuron_id": 1,
  "timestamp": 1234567890,
  "vitality": 0.75
}
```

### Vitality Sync (Port 8889)

```bash
GET /vitality

Response:
{
  "vitality": [0.8, 0.6, 0.9, ...],
  "timestamp": 1234567890
}
```

### Learning Report (Port 8890)

```bash
GET /report

Response:
{
  "learning_events": 42,
  "weight_updates": 156,
  "pruned_synapses": 3
}
```

## Configuration

### Environment Variables

```bash
export PYNQ_IP=192.168.1.9
export LME_LOG_LEVEL=INFO
export LME_VITALITY_DECAY=0.95
```

### Config File (config.yaml)

```yaml
pynq:
  ip: 192.168.1.9
  ports:
    event: 8888
    vitality: 8889
    report: 8890

memory:
  capacity: 10000
  vitality_threshold: 0.1
  decay_rate: 0.95

learning:
  stdp_window: 20
  learning_rate: 0.01
```

