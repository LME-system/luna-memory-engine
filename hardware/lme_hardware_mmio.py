#!/usr/bin/env python3
"""
LME Hardware Driver for PYNQ-Z2 - Direct MMIO Version
直接使用 mmap 访问 FPGA 寄存器，不依赖 PYNQ Overlay
"""

import mmap
import struct
import time
import numpy as np
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum

class TimeMode(Enum):
    T1_SYSTEM = 0
    T2_SEMANTIC = 1
    T3_UTC = 2

@dataclass
class MemoryEvent:
    neuron_id: int
    weight: float
    t1: int = 0
    t2_offset: int = 0
    t3_anchor: Optional[int] = None

class LMEHardwareMMIO:
    """
    LME 硬件驱动 - 直接 MMIO 版本
    通过 /dev/mem 直接访问 FPGA 寄存器
    """
    
    # 寄存器地址映射 (根据 Vivado 配置)
    REG_VERSION     = 0x00
    REG_CONTROL     = 0x04
    REG_STATUS      = 0x08
    REG_T3_HI       = 0x10
    REG_T3_LO       = 0x14
    REG_EVENT_DATA  = 0x20
    REG_EVENT_CTRL  = 0x24
    REG_VITALITY_BASE = 0x100
    
    def __init__(self, base_addr: int = 0x43C00000, size: int = 0x10000):
        self.base_addr = base_addr
        self.size = size
        self.mem = None
        self._open()
        
    def _open(self):
        """打开 /dev/mem 并映射 FPGA 寄存器"""
        try:
            f = open("/dev/mem", "r+b")
            self.mem = mmap.mmap(f.fileno(), self.size, offset=self.base_addr)
            f.close()
            print(f"✅ LME Hardware mapped at 0x{self.base_addr:08X}")
        except Exception as e:
            raise RuntimeError(f"Failed to map FPGA: {e}")
    
    def _read32(self, offset: int) -> int:
        """读取 32 位寄存器"""
        return struct.unpack("<I", self.mem[offset:offset+4])[0]
    
    def _write32(self, offset: int, value: int):
        """写入 32 位寄存器"""
        self.mem[offset:offset+4] = struct.pack("<I", value)
    
    def get_version(self) -> int:
        """读取版本寄存器"""
        return self._read32(self.REG_VERSION)
    
    def get_control(self) -> int:
        """读取控制寄存器"""
        return self._read32(self.REG_CONTROL)
    
    def get_status(self) -> int:
        """读取状态寄存器"""
        return self._read32(self.REG_STATUS)
    
    def sync_t3(self, utc_timestamp_us: int):
        """同步 T3 UTC 时间"""
        hi = (utc_timestamp_us >> 32) & 0xFFFFFFFF
        lo = utc_timestamp_us & 0xFFFFFFFF
        self._write32(self.REG_T3_HI, hi)
        self._write32(self.REG_T3_LO, lo)
        
    def get_t3(self) -> int:
        """读取 T3 时间"""
        hi = self._read32(self.REG_T3_HI)
        lo = self._read32(self.REG_T3_LO)
        return (hi << 32) | lo
    
    def write_event(self, event_data: int):
        """写入事件数据"""
        self._write32(self.REG_EVENT_DATA, event_data)
    
    def get_vitality(self, neuron_id: int) -> float:
        """读取神经元活力值 (Q8.8 定点数)"""
        if neuron_id < 0 or neuron_id >= 128:
            raise ValueError(f"Neuron ID must be 0-127, got {neuron_id}")
        raw = self._read32(self.REG_VITALITY_BASE + neuron_id * 4)
        return raw / 256.0  # 转换为浮点
    
    def get_all_vitality(self) -> np.ndarray:
        """读取所有神经元活力值"""
        vitality = np.zeros(128)
        for i in range(128):
            vitality[i] = self.get_vitality(i)
        return vitality
    
    def reset(self):
        """复位硬件"""
        # 写入复位命令到控制寄存器
        ctrl = self.get_control()
        self._write32(self.REG_CONTROL, ctrl | 0x01)
        time.sleep(0.001)
        self._write32(self.REG_CONTROL, ctrl & ~0x01)
    
    def close(self):
        """关闭内存映射"""
        if self.mem:
            self.mem.close()
            self.mem = None
    
    def __del__(self):
        self.close()
    
    def get_stats(self) -> Dict:
        """获取硬件状态统计"""
        return {
            'version': f"0x{self.get_version():08X}",
            'control': f"0x{self.get_control():08X}",
            'status': f"0x{self.get_status():08X}",
            't3': self.get_t3(),
            'mean_vitality': np.mean(self.get_all_vitality()),
            'max_vitality': np.max(self.get_all_vitality()),
        }


def test_hardware():
    """测试 LME 硬件"""
    print("=" * 60)
    print("LME Hardware Test (Direct MMIO)")
    print("=" * 60)
    
    # 初始化硬件
    lme = LMEHardwareMMIO()
    
    # 读取版本信息
    print(f"\n1. Version: 0x{lme.get_version():08X}")
    print(f"2. Control: 0x{lme.get_control():08X}")
    print(f"3. Status:  0x{lme.get_status():08X}")
    
    # T3 时间同步
    print("\n4. T3 Time Sync Test")
    utc_now = int(time.time() * 1000000)
    lme.sync_t3(utc_now)
    read_t3 = lme.get_t3()
    print(f"   Written: {utc_now}")
    print(f"   Read:    {read_t3}")
    print(f"   Diff:    {abs(utc_now - read_t3)} us")
    
    # 写入测试事件
    print("\n5. Event Write Test")
    lme.write_event(0x12345678)
    print("   Written: 0x12345678")
    
    # 读取活力值
    print("\n6. Vitality Test")
    vitality = lme.get_all_vitality()
    print(f"   Mean vitality: {np.mean(vitality):.4f}")
    print(f"   Max vitality:  {np.max(vitality):.4f}")
    print(f"   Active neurons: {np.sum(vitality > 0.01)}")
    
    # 完整统计
    print("\n7. Full Stats")
    stats = lme.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    lme.close()
    
    print("\n" + "=" * 60)
    print("✅ Hardware Test Complete!")
    print("=" * 60)


if __name__ == '__main__':
    test_hardware()
