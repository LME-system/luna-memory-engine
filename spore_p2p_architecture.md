# 🌐 SporeCiv P2P Network Layer - DHT + STUN Architecture

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        SporeCiv Node                            │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   DHT Layer  │  │  STUN Layer  │  │   WireGuard Layer    │  │
│  │  (Kademlia)  │  │  (NAT Hole   │  │   (Crypto Tunnel)    │  │
│  │              │  │   Punching)  │  │                      │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
│         │                 │                      │              │
│         └─────────────────┼──────────────────────┘              │
│                           │                                     │
│                  ┌────────▼────────┐                           │
│                  │  P2P Bootstrap  │                           │
│                  │   Coordinator   │                           │
│                  └────────┬────────┘                           │
│                           │                                     │
└───────────────────────────┼─────────────────────────────────────┘
                            │
         ┌──────────────────┼──────────────────┐
         │                  │                  │
    ┌────▼────┐       ┌────▼────┐       ┌────▼────┐
    │ Seed A  │◄─────►│ Seed B  │◄─────►│ Seed C  │
    │(Known)  │ DHT   │(Known)  │ DHT   │(Known)  │
    └─────────┘       └─────────┘       └─────────┘
```

## 核心设计决策

### 1. DHT 节点标识

```python
node_id = SHA256(wireguard_public_key)[:20]  # 160-bit Kademlia ID
```

**为什么用公钥哈希？**
- 自验证：DHT 查找结果可验证身份
- 防冒充：无法伪造他人 node_id
- 去中心化：无需 CA 证书体系

### 2. DHT 存储格式

```json
{
  "node_id": "a3f8...7c5e",
  "public_key_hash": "SHA256(pubkey)",
  "endpoints": {
    "ipv6": "2409:8a28:6c00:8780:9d02:a3f8:7c5e:3bd5",
    "ipv4_stun": "203.0.113.1:51820",
    "vpn_ip": "10.200.200.1"
  },
  "capabilities": ["spore_v1", "relay"],
  "timestamp": 1788660000,
  "signature": "ed25519(...)"
}
```

### 3. STUN 打洞流程

```
Alice (NAT后)                    Bob (NAT后)
    │                                │
    ├──► STUN Server ──► get mapped addr ──┤
    │    203.0.113.1:50001                 │
    │                                      │
    │◄── DHT Store: Alice's mapped addr ◄──┤
    │                                      │
    │──► DHT Lookup Bob ◄──────────────────┤
    │    get Bob's mapped addr             │
    │                                      │
    │──► UDP Punch ───────────────────────►│
    │    dst: 198.51.100.2:50002           │
    │◄─────────────────────────────────────┤
    │◄── UDP Punch (simultaneous) ◄────────┤
    │                                      │
    │──► Hole Open! ──────────────────────►│
    │    WireGuard handshake over punched  │
    │    UDP port                          │
```

### 4. 信任建立流程（首次连接陌生人）

```
Stranger (地球另一端)
       │
       ├── 1. 生成 WireGuard 密钥对
       │
       ├── 2. 加入 DHT（bootstrap 到种子节点）
       │
       ├── 3. 发布自己的 endpoint 信息（带签名）
       │
       ├── 4. DHT 查找 "spore_hive_hnfq42c4wl"
       │      └─► 返回母巢的 endpoint 信息
       │
       ├── 5. STUN 打洞尝试直连母巢
       │
       ├── 6. 直连成功！但 WireGuard 拒绝（无公钥）
       │      └─► 母巢不认识这个公钥
       │
       ├── 7. 通过已打通的 UDP 发送 "JOIN_REQUEST"
       │      包含：公钥指纹、intent、签名
       │
       ├── 8. 母巢审核（人工或自动策略）
       │      └─► 批准：添加 peer，分配 VPN IP
       │      └─► 拒绝：忽略，节点无法接入
       │
       └── 9. 双方 WireGuard 握手，建立加密隧道
```

## 关键代码模块

### `spore_p2p_network.py`
- `DHTBootstrap`：DHT 节点管理
- `STUNClient`：NAT 类型检测 + 打洞
- `P2PConnector`：连接协调器
- `TrustGate`：信任策略门控

### 安全考虑

1. **DHT 数据签名**：所有存储的 endpoint 信息必须签名，防止毒化攻击
2. **Rate Limiting**：JOIN_REQUEST 限制频率，防止垃圾请求
3. **渐进信任**：新节点默认只能访问受限服务，随时间/行为提升权限
4. **Revocation**：支持移除恶意节点，广播撤销消息

## 种子节点 (Bootstrap)

```python
DEFAULT_BOOTSTRAP_NODES = [
    # 社区维护的公共种子节点
    ("spore-seed-1.openclaw.ai", 8468),
    ("spore-seed-2.openclaw.ai", 8468),
    # IPv6 直连
    ("[2409:8a28:6c00:8780::1]", 8468),
]
```

## 部署检查清单

- [ ] 安装 `kademlia` 库
- [ ] 配置 STUN 服务器列表（Google、Cloudflare 等公共 STUN）
- [ ] 选择或部署种子节点
- [ ] 实现签名/验签模块
- [ ] 实现 TrustGate 策略引擎
- [ ] 测试 NAT 打洞成功率
- [ ] 测试中继 fallback

---

*设计日期: 2026-09-06*  
*版本: SporeCiv P2P v0.5*
