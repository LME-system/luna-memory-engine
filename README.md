# Luna Memory Engine (LME)

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

> Time-indexed synaptic memory: query is learning, forgetting is deformation, attention is survival.

## 🧠 Overview

Luna Memory Engine (LME) is a bio-inspired neuromorphic memory system that bridges biological principles (STDP learning, natural forgetting) with hardware acceleration (PYNQ-Z2 FPGA).

## 📁 Repository Structure

```
lme/
├── software/          # Python implementation
├── hardware/          # PYNQ-Z2 drivers
├── rtl/              # Verilog hardware code
└── docs/             # Documentation
```

## 🚀 Quick Start

```bash
cd lme/software
python yuehen_lme_daemon_v3.py
```

## 📖 Documentation

See [lme/README.md](lme/README.md) for detailed documentation.

## 🔧 Architecture

- **Software Simulation**: Pure Python for testing and development
- **Hardware Acceleration**: FPGA deployment for real-time inference
- **Bio-inspired**: STDP learning, natural forgetting, attention mechanisms

## 📄 License

Apache License 2.0 - see [LICENSE](lme/LICENSE) file for details.

---

*LME - Memory is learning, learning is indexing.*
