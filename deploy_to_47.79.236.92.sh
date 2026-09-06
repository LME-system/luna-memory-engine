#!/bin/bash
# =============================================================================
# 🌱 SporeCiv Bootstrap Node - 阿里云香港一键部署
# 目标服务器: 47.79.236.92
# 使用方法: ssh root@47.79.236.92 后执行本脚本
# =============================================================================

set -e

echo "🌱 SporeCiv Bootstrap Node - 阿里云部署脚本"
echo "============================================"
echo "目标: 47.79.236.92:8467"
echo ""

# =============================================================================
# 1. 系统更新
# =============================================================================
echo "📦 [1/7] 更新系统..."
apt-get update -qq
apt-get upgrade -y -qq

# =============================================================================
# 2. 安装依赖
# =============================================================================
echo "📦 [2/7] 安装依赖..."
apt-get install -y -qq python3 python3-pip python3-venv git curl ufw

# =============================================================================
# 3. 创建目录
# =============================================================================
echo "📁 [3/7] 创建工作目录..."
mkdir -p /opt/sporeciv
mkdir -p /var/log/sporeciv
cd /opt/sporeciv

# =============================================================================
# 4. Python 环境
# =============================================================================
echo "🐍 [4/7] 配置 Python..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -q --upgrade pip
pip install -q kademlia

# =============================================================================
# 5. 创建 Bootstrap 节点
# =============================================================================
echo "📝 [5/7] 创建节点..."

cat > /opt/sporeciv/bootstrap.py << 'PYEOF'
#!/usr/bin/env python3
"""
SporeCiv Bootstrap Node - Hong Kong
Location: 阿里云轻量应用服务器
IP: 47.79.236.92:8467
"""

import asyncio
import logging
import time
import signal
import sys
from kademlia.network import Server
from kademlia.utils import digest

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/var/log/sporeciv/bootstrap.log')
    ]
)
logger = logging.getLogger("spore_bootstrap")

class BootstrapNode:
    def __init__(self, port=8467):
        self.port = port
        self.server = Server(node_id=digest("spore_bootstrap_hk"))
        self.running = False
        self.stats = {
            "started_at": None,
            "nodes_seen": set(),
            "lookups": 0,
            "stores": 0,
        }
        
    async def start(self):
        await self.server.listen(self.port)
        self.running = True
        self.stats["started_at"] = time.time()
        
        logger.info("=" * 60)
        logger.info("🌱 SporeCiv Bootstrap Node - Hong Kong")
        logger.info("=" * 60)
        logger.info(f"   IP: 47.79.236.92")
        logger.info(f"   Port: {self.port}")
        logger.info(f"   Kademlia ID: {self.server.node.long_id}")
        logger.info("=" * 60)
        logger.info("")
        logger.info("📋 客户端配置:")
        logger.info("   CONFIG['P2P_BOOTSTRAP'] = [('47.79.236.92', 8467)]")
        logger.info("=" * 60)
        
        asyncio.create_task(self._stats_reporter())
        
    async def stop(self):
        self.server.stop()
        self.running = False
        logger.info("👋 Bootstrap stopped")
        
    async def _stats_reporter(self, interval=300):
        while self.running:
            await asyncio.sleep(interval)
            uptime = int(time.time() - self.stats["started_at"]) if self.stats["started_at"] else 0
            logger.info(f"📊 Uptime: {uptime}s | Nodes: {len(self.stats['nodes_seen'])}")

async def main():
    node = BootstrapNode()
    
    def signal_handler(sig, frame):
        logger.info("收到停止信号...")
        asyncio.create_task(node.stop())
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    await node.start()
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
PYEOF

chmod +x /opt/sporeciv/bootstrap.py

# =============================================================================
# 6. Systemd 服务
# =============================================================================
echo "⚙️  [6/7] 创建系统服务..."

cat > /etc/systemd/system/spore-bootstrap.service << 'SVCEOF'
[Unit]
Description=SporeCiv Bootstrap Node (Hong Kong)
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/sporeciv
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/sporeciv/venv/bin/python /opt/sporeciv/bootstrap.py
Restart=always
RestartSec=5
StandardOutput=append:/var/log/sporeciv/bootstrap.log
StandardError=append:/var/log/sporeciv/bootstrap.log

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable spore-bootstrap

# =============================================================================
# 7. 防火墙
# =============================================================================
echo "🛡️  [7/7] 配置防火墙..."

# 配置 UFW
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 8467/tcp comment 'SporeCiv DHT'
ufw allow 8467/udp comment 'SporeCiv DHT'

echo "y" | ufw enable

# =============================================================================
# 8. 启动
# =============================================================================
echo ""
echo "🚀 启动 Bootstrap 节点..."
systemctl start spore-bootstrap
sleep 2

# =============================================================================
# 完成
# =============================================================================
echo ""
echo "============================================"
echo "✅ 部署完成!"
echo "============================================"
echo ""
echo "📊 服务状态:"
systemctl status spore-bootstrap --no-pager | head -5 || true
echo ""
echo "📁 文件位置:"
echo "   代码: /opt/sporeciv/bootstrap.py"
echo "   日志: /var/log/sporeciv/bootstrap.log"
echo ""
echo "🛠️  管理命令:"
echo "   查看状态: systemctl status spore-bootstrap"
echo "   查看日志: tail -f /var/log/sporeciv/bootstrap.log"
echo "   重启服务: systemctl restart spore-bootstrap"
echo "   停止服务: systemctl stop spore-bootstrap"
echo ""
echo "🌐 连接信息:"
echo "   IP: 47.79.236.92"
echo "   Port: 8467"
echo ""
echo "📋 母巢配置:"
echo "   CONFIG['P2P_BOOTSTRAP'] = [('47.79.236.92', 8467)]"
echo "============================================"
