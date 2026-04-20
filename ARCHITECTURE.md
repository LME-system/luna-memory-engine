# LME Architecture

## System Overview

Luna Memory Engine (LME) is a bio-inspired neuromorphic memory system combining software simulation with FPGA hardware acceleration.

```
┌─────────────────────────────────────────────────────────────┐
│                     LME System Architecture                  │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │   Mac Host   │◄──►│  LME Bridge  │◄──►│  PYNQ-Z2     │  │
│  │  (Software)  │    │  (Fusion)    │    │  (Hardware)  │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│         │                   │                   │           │
│    ┌────┴────┐         ┌────┴────┐         ┌────┴────┐     │
│    │ 月痕    │         │  LME    │         │  RTL    │     │
│    │ Memory  │         │ Stream  │         │ Engine  │     │
│    └─────────┘         └─────────┘         └─────────┘     │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Software Layer (Mac Host)

**Files:**
- `yuehen_lme_daemon_v3.py` - Main daemon process
- `yuehen_realtime.py` - Real-time memory processing
- `luna_memory_system.py` - Core memory system
- `lme_driver.py` - Software simulation driver

**Functions:**
- Event-driven memory storage
- STDP (Spike-Timing-Dependent Plasticity) learning
- Natural forgetting mechanism
- Vitality-based attention

### 2. Hardware Layer (PYNQ-Z2 FPGA)

**Files:**
- `lme_hardware_mmio.py` - Hardware driver interface
- `rtl/core/lif_neuron_core.v` - LIF neuron implementation
- `rtl/core/stdp_engine_v2.v` - STDP learning engine
- `rtl/lti/lti_core.v` - LTI temporal indexing

**Functions:**
- Real-time spike processing
- Hardware-accelerated STDP
- Temporal event encoding
- Low-power inference (< 5W)

### 3. Fusion Bridge

**Protocol:**
- Event streaming (port 8888)
- Vitality sync (port 8889)
- Learning reports (port 8890)

## Data Flow

```
User Input → Text Parser → Importance Scorer → Pulse Encoder
                                                  ↓
Memory Store ← Vitality Update ← Neuron Activation ← FPGA
     ↓
Knowledge Distillation → Long-term Storage
```

## Key Innovations

1. **Time-Indexed Memory**: T1/T2/T3 three-layer temporal encoding
2. **Bio-Inspired Forgetting**: Natural decay based on vitality
3. **Hardware-Software Co-design**: Seamless FPGA acceleration
4. **Event-Driven Architecture**: Efficient spike-based processing

## Performance

| Metric | Software | Hardware | Unit |
|--------|----------|----------|------|
| Latency | ~30 | < 10 | ms |
| Throughput | 32K | > 10K | events/s |
| Power | N/A | < 5 | W |

