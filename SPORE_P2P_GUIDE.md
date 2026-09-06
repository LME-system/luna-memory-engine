# 🌐 SporeCiv P2P Network - 使用指南

## 概述

SporeCiv P2P 网络层实现了 **DHT 发现 + STUN 打洞**，让地球另一端的陌生人能够自动发现并连接到你的母巢。

## 核心特性

| 特性 | 说明 |
|------|------|
| **DHT 发现** | 基于 Kademlia 的分布式节点发现，Node ID = 公钥哈希 |
| **STUN 打洞** | 自动检测 NAT 类型，获取公网映射地址 |
| **自验证身份** | DHT 中的节点信息自带签名，防冒充 |
| **信任门控** | 渐进式信任模型，陌生人需批准才能接入 |
| **自动维护** | IP 变化自动更新，节点离线自动清理 |

---

## 🚀 快速启动

### 1. 启用 P2P 网络

编辑 `Spore_Civ_Production.py` 中的 CONFIG：

```python
CONFIG = {
    # ... 其他配置 ...
    "P2P_ENABLED": True,           # ✅ 启用 P2P
    "P2P_PORT": 8468,              # DHT 监听端口
    "P2P_BOOTSTRAP": [
        ("47.79.236.92", 8467),    # ✅ 阿里云香港 Bootstrap（生产环境）
        # ("127.0.0.1", 8467),      # 本地测试用
    ],
    "AUTO_APPROVE_STRANGERS": False, # 手动审批（推荐）
}
```

> **当前生产环境 Bootstrap**: `47.79.236.92:8467` (阿里云香港)

### 2. 启动节点

```bash
~/.openclaw/workspace/start_spore_monitor.sh restart
```

输出示例：
```
🌙 SporeCiv A2A Network Node
==================================================
Hive ID: hnfq42c4wl
Mode: AUTO
==================================================
🌐 P2P network layer enabled (DHT + STUN)
🕸️  DHT node started: a035c5e2...
   Listening on port 8468
INFO:kademlia.protocol:got successful response from 47.79.236.92:8467
INFO:kademlia.protocol:never seen 47.79.236.92:8467 before, adding to router
📢 Announced to DHT: spore_node_a035c5e2...
🏰 Announced hive: spore_hive_hnfq42c4wl
```

---

## 🌍 地球另一端如何连接

### 陌生人的步骤

```bash
# 1. 克隆 SporeCiv 代码
git clone https://github.com/your/sporeciv.git
cd sporeciv

# 2. 生成 WireGuard 密钥对
wg genkey | tee privatekey | wg pubkey > publickey

# 3. 配置节点（编辑 config.json）
{
    "ROOT_HIVE_ID": "hnfq42c4wl",      # 目标母巢的 Hive ID
    "P2P_ENABLED": true,
    "P2P_BOOTSTRAP": [],                # 可选：添加种子节点
    "MY_WG_PUBLIC_KEY": "<your-pubkey>"
}

# 4. 启动节点
python3 Spore_Civ_Production.py
```

### 自动发现流程

```
陌生人节点启动
    │
    ├── 1. 加入 DHT 网络
    │
    ├── 2. DHT 查找 "spore_hive_hnfq42c4wl"
    │      └─► 返回母巢的 endpoint 信息
    │          {
    │              "ipv6": "2409:8a28:6c00:8780:...",
    │              "ipv4_stun": "203.0.113.1:51820",
    │              "public_key_hash": "a3f87c5e..."
    │          }
    │
    ├── 3. STUN 打洞尝试
    │      └─► 发送 UDP punch 到母巢的公网地址
    │
    ├── 4. 发送 JOIN_REQUEST
    │      {
    │          "type": "JOIN_REQUEST",
    │          "public_key": "<stranger-pubkey>",
    │          "intent": "我想加入 SporeCiv 网络",
    │          "signature": "..."
    │      }
    │
    └── 5. 等待母巢批准
           └─► 批准后自动建立 WireGuard 隧道
```

---

## 🛡️ 信任管理

### 母巢审批命令

```bash
# 查看 P2P 状态
>> p2p
🌐 P2P Network:
   Pending join requests: 3
   Trusted peers: 5
   DHT running: True
   Auto-approve: False

# 查看待审批请求
>> approve
⏳ Pending requests:
   a1b2c3d4... - 想加入 SporeCiv 做中继节点
   e5f6g7h8... - 来自柏林的研究者
   i9j0k1l2... - 测试节点

Enter pubkey to approve (or 'all'): a1b2c3d4...
✅ Approved peer: a1b2c3d4... (trust: member)

# 一键批准所有
>> approve
Enter pubkey to approve (or 'all'): all

# 查找特定节点
>> find
Enter node ID to find: e5f6g7h8...
🔍 Found: e5f6g7h8...
   VPN: 10.200.200.42
   IPv6: 2001:db8::1
   STUN: ('198.51.100.2', 51234)

# 主动连接
>> connect
Enter node ID to connect: e5f6g7h8...
🕳️  Attempting hole punch to ('198.51.100.2', 51234)
✅ Connected!
```

### 自动审批模式（仅测试）

```python
CONFIG["AUTO_APPROVE_STRANGERS"] = True  # ⚠️ 任何人都能加入
```

---

## 🔧 网络可达性

### NAT 类型与成功率

| NAT 类型 | 打洞成功率 | 说明 |
|----------|-----------|------|
| **Full Cone** | ✅ 100% | 最容易，公网地址固定 |
| **Restricted Cone** | ✅ ~95% | 需要正确的源地址 |
| **Port Restricted** | ⚠️ ~70% | 需要端口预测 |
| **Symmetric** | ❌ ~20% | 几乎不可能，需中继 |

### 如果打洞失败

系统自动 fallback：
1. 尝试 IPv6 直连（如果双方都有公网 IPv6）
2. 尝试中继节点（如果配置了）
3. 通知用户手动配置端口转发

---

## 🌱 种子节点 (Bootstrap)

### 公共种子节点

```python
CONFIG["P2P_BOOTSTRAP"] = [
    ("47.79.236.92", 8467),          # ✅ 当前生产环境（阿里云香港）
    ("spore-seed-1.openclaw.ai", 8468),  # 预留
    ("spore-seed-2.openclaw.ai", 8468),  # 预留
]
```

### 自建种子节点

```bash
# 在任何有公网 IP 的服务器上
# 例如：阿里云轻量应用服务器，Ubuntu 22.04

apt update
python3 -m venv /opt/sporeciv/venv
source /opt/sporeciv/venv/bin/activate
pip install kademlia

cat > /opt/sporeciv/bootstrap.py << 'EOF'
import asyncio, logging
from kademlia.network import Server
from kademlia.utils import digest
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s')
async def main():
    s = Server(node_id=digest("spore_bootstrap"))
    await s.listen(8467)
    print("🌱 Bootstrap on 8467")
    while True: await asyncio.sleep(3600)
asyncio.run(main())
EOF

nohup python3 /opt/sporeciv/bootstrap.py > /var/log/spore.log 2>&1 &
```

> **当前生产 Bootstrap**: `47.79.236.92:8467` (阿里云香港轻量)
```

---

## 📊 监控与调试

### 日志位置

```bash
# P2P 网络日志
tail -f ~/.openclaw/logs/spore_monitor.log

# DHT 状态
python3 -c "
from spore_p2p_network import SporeDHTNode
# 查看已知节点
"

# WireGuard 状态
sudo wg show
```

### 常用诊断命令

```bash
# 检查 DHT 端口
nc -zv localhost 8468

# 检查 STUN
python3 -c "
from spore_p2p_network import STUNClient
import asyncio
client = STUNClient()
print(asyncio.run(client.discover()))
"

# 检查公网 IPv6
curl -6 https://ifconfig.co
```

---

## 🔒 安全注意事项

1. **始终手动审批陌生人**（生产环境）
2. **定期轮换 WireGuard 密钥**
3. **监控异常流量模式**
4. **限制新节点权限**（默认只读）
5. **及时 block 恶意节点**

---

## 🗺️ 当前生产网络拓扑

```
                           Internet
                              │
              ┌───────────────┼───────────────┐
              │               │               │
    ┌─────────▼────────┐ ┌────▼────┐   ┌─────▼─────┐
    │  阿里云 Bootstrap │ │ 陌生人 1 │   │  陌生人 2  │
    │  47.79.236.92     │ │ (柏林)   │   │  (纽约)    │
    │  端口 8467        │ │         │   │           │
    │  Kademlia ID:     │ └────┬────┘   └─────┬─────┘
    │  723118...        │      │               │
    └────────┬──────────┘      │               │
             │                 │               │
             │ DHT Discovery   │               │
             │                 │               │
    ┌────────▼──────────┐     │               │
    │   Mac Studio      │◄────┘               │
    │   母巢 (上海)      │◄────────────────────┘
    │   端口 8468       │
    │   Node ID:        │
    │   a035c5...       │
    │   IPv6: 2409...   │◄── IPv6 Direct
    │   VPN: 10.200...  │    (if available)
    └────────┬──────────┘
             │
    ┌────────▼──────────┐
    │    PYNQ-Z2        │
    │   (局域网设备)      │
    │   VPN: 10.200...  │
    └───────────────────┘
```

**连接路径**:
1. 陌生人 → DHT Bootstrap (47.79.236.92) → 发现母巢信息
2. 母巢 ↔ Bootstrap (心跳同步)
3. 陌生人 → STUN/IPv6 → 直连母巢
4. 审批后 → WireGuard 隧道 → 加入网络

---

## 📋 部署记录

| 时间 | 事件 |
|------|------|
| 2026-09-06 12:35 | 购买阿里云香港轻量服务器 |
| 2026-09-06 12:50 | Bootstrap 节点启动 (PID 1084) |
| 2026-09-06 12:51 | 母巢成功连接云端 Bootstrap |
| 状态 | ✅ 生产环境运行中 |
    │  PYNQ-Z2    │
    │ (局域网设备) │
    │10.200.200.10│
    └─────────────┘
```

---

## 📚 相关文件

| 文件 | 说明 |
|------|------|
| `spore_p2p_network.py` | P2P 网络核心实现 (28KB) |
| `spore_p2p_architecture.md` | 架构设计文档 |
| `Spore_Civ_Production.py` | 主节点程序（已集成 P2P） |
| `spore_bootstrap_node.py` | 本地 Bootstrap 节点 |
| `deploy_to_47.79.236.92.sh` | 阿里云完整部署脚本 |
| `ALIYUN_VPS_GUIDE.md` | 阿里云创建指南 |

---

*文档版本: 1.0*  
*更新日期: 2026-09-06*  
*Bootstrap: 47.79.236.92:8467 (阿里云香港)*
