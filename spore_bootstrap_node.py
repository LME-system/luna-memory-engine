#!/usr/bin/env python3
"""
🌱 SporeCiv Bootstrap Node
公共种子节点，帮助新节点加入 DHT 网络。

Usage:
    python3 spore_bootstrap_node.py [port]

Features:
- 长期运行，稳定在线
- 记录加入网络的节点
- 提供网络状态查询
"""

import asyncio
import json
import time
import logging
from typing import Dict, Set
from datetime import datetime

from kademlia.network import Server
from kademlia.utils import digest

# =============================================================================
# 📊 Logging
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("spore_bootstrap")

# =============================================================================
# 🌱 Bootstrap Node
# =============================================================================

class SporeBootstrapNode:
    """
    SporeCiv 网络引导节点。
    作为 DHT 网络的入口点，帮助新节点发现其他节点。
    """
    
    def __init__(self, node_id: str = "spore_bootstrap_1", port: int = 8467):
        self.node_id = node_id
        self.port = port
        self.server = Server(node_id=digest(node_id))
        self.running = False
        
        # 统计信息
        self.stats = {
            "started_at": None,
            "nodes_seen": set(),  # 见过的节点 ID
            "lookup_count": 0,
            "store_count": 0,
        }
        
    async def start(self):
        """启动 Bootstrap 节点"""
        await self.server.listen(self.port)
        self.running = True
        self.stats["started_at"] = time.time()
        
        logger.info("=" * 60)
        logger.info("🌱 SporeCiv Bootstrap Node Started")
        logger.info("=" * 60)
        logger.info(f"   Node ID: {self.node_id}")
        logger.info(f"   Port: {self.port}")
        logger.info(f"   Kademlia ID: {self.server.node.long_id}")
        logger.info("=" * 60)
        logger.info("")
        logger.info("📋 其他节点连接配置:")
        logger.info(f"   CONFIG['P2P_BOOTSTRAP'] = [('127.0.0.1', {self.port})]")
        logger.info("")
        logger.info("🌐 或者使用公网地址:")
        logger.info("   CONFIG['P2P_BOOTSTRAP'] = [('your-public-ip', 8467)]")
        logger.info("=" * 60)
        
        # 启动统计监控
        asyncio.create_task(self._stats_reporter())
        
    async def stop(self):
        """停止 Bootstrap 节点"""
        self.server.stop()
        self.running = False
        logger.info("👋 Bootstrap node stopped")
        
    async def _stats_reporter(self, interval: int = 60):
        """定期报告统计信息"""
        while self.running:
            await asyncio.sleep(interval)
            
            uptime = time.time() - self.stats["started_at"] if self.stats["started_at"] else 0
            logger.info(f"📊 Stats | Uptime: {int(uptime)}s | "
                       f"Nodes seen: {len(self.stats['nodes_seen'])} | "
                       f"Lookups: {self.stats['lookup_count']} | "
                       f"Stores: {self.stats['store_count']}")
            
    def get_connection_info(self) -> dict:
        """获取连接信息，供其他节点使用"""
        return {
            "node_id": self.node_id,
            "port": self.port,
            "kademlia_id": str(self.server.node.long_id) if self.server.node else None,
            "uptime": time.time() - self.stats["started_at"] if self.stats["started_at"] else 0,
        }


async def main():
    """主入口"""
    import sys
    
    port = 8467
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
        
    bootstrap = SporeBootstrapNode(port=port)
    
    try:
        await bootstrap.start()
        
        # 保持运行
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("\n收到停止信号...")
    finally:
        await bootstrap.stop()


if __name__ == "__main__":
    print("🌱 SporeCiv Bootstrap Node")
    print("=" * 50)
    asyncio.run(main())
