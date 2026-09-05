import asyncio
import json
import socket
import random
import time
import hashlib
import platform
import psutil
import numpy as np
from zeroconf import ServiceInfo, Zeroconf, ServiceBrowser
from typing import Dict, Any, List, Optional
from collections import defaultdict

# =============================================================================
# 🧬 文明基因与全局配置 (Global Manifest)
# =============================================================================
CONFIG = {
    "ROOT_HIVE_ID": "hnfq42c4wl",
    "UDP_PORT": 9999,           # 阴影层：低频心跳 & 状态同步
    "A2A_PORT": 9998,           # 正式层：A2A 协议接口 (JSON-RPC)
    "M_DIM": 32,                # 压缩感知观测维度
    "N_DIM": 128,               # 原始状态维度
    "SPORE_SENSITIVITY": 0.8,   # 仁慈阈值 (CPU > 80% 自动休眠)
    "BRIDGE_SAMPLED": True,     # 是否启用潜空间"心灵感应"桥接
    "AUTO_MODE": True,          # 全自动模式（无需交互）
    "WG_VPN_IP": "10.200.200.1", # WireGuard VPN 内网地址
    "WG_PORT": 51820,           # WireGuard 监听端口
    "PUBLIC_IPV6": "2409:8a28:6c00:8780:9d02:a3f8:7c5e:3bd5", # 公网 IPv6
    "MONITOR_LOG": "~/.openclaw/logs/spore_monitor.json" # 监控日志路径
}

# =============================================================================
# 🌐 WireGuard 自动发现与网络管理
# =============================================================================
class WireGuardDiscovery:
    """
    通过 gossip 协议实现 WireGuard 节点自动发现与 IP 更新。
    集成到 A2A 节点的 gossip 消息中，实现零配置组网。
    """
    def __init__(self, node_id, vpn_ip):
        self.node_id = node_id
        self.vpn_ip = vpn_ip
        self.current_ipv6 = self._get_current_ipv6()
        self.peers_file = os.path.expanduser("~/.wireguard/peers.json")
        self.last_announcement = 0
        self.announce_interval = 60  # 每 60 秒广播一次 IP
        self.peers = self._load_peers()

    def _get_current_ipv6(self):
        """获取当前公网 IPv6"""
        try:
            s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
            s.connect(('2001:4860:4860::8888', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return CONFIG["PUBLIC_IPV6"]

    def _load_peers(self):
        """加载已知的对等节点"""
        if os.path.exists(self.peers_file):
            try:
                with open(self.peers_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_peers(self):
        """保存对等节点信息"""
        os.makedirs(os.path.dirname(self.peers_file), exist_ok=True)
        with open(self.peers_file, 'w') as f:
            json.dump(self.peers, f, indent=2)

    def get_announcement(self):
        """
        生成 IP 广播消息，由 gossip 协议发送。
        包含当前公网 IPv6、VPN IP、WireGuard 端口等信息。
        """
        now = time.time()
        if (now - self.last_announcement) < self.announce_interval:
            return None

        # 检查 IP 是否变化
        new_ipv6 = self._get_current_ipv6()
        if new_ipv6 != self.current_ipv6:
            print(f"🔄 IP 变化: {self.current_ipv6} → {new_ipv6}")
            self.current_ipv6 = new_ipv6

        self.last_announcement = now
        return {
            "type": "WG_DISCOVERY",
            "node_id": self.node_id,
            "vpn_ip": self.vpn_ip,
            "public_ipv6": self.current_ipv6,
            "wg_port": CONFIG["WG_PORT"],
            "timestamp": now
        }

    def handle_announcement(self, announcement):
        """
        处理收到的 IP 广播，更新对等节点信息。
        如节点 IP 变化，自动更新 WireGuard 配置。
        """
        node_id = announcement.get("node_id")
        if not node_id or node_id == self.node_id:
            return

        new_ipv6 = announcement.get("public_ipv6")
        new_vpn_ip = announcement.get("vpn_ip")
        wg_port = announcement.get("wg_port", 51820)

        if not new_ipv6:
            return

        # 更新或添加对等节点
        if node_id not in self.peers:
            self.peers[node_id] = {
                "public_ipv6": new_ipv6,
                "vpn_ip": new_vpn_ip,
                "wg_port": wg_port,
                "first_seen": time.time(),
                "last_update": time.time()
            }
            print(f"🆕 新节点加入: {node_id} @ {new_ipv6}")
        else:
            old_ipv6 = self.peers[node_id].get("public_ipv6")
            if old_ipv6 != new_ipv6:
                print(f"🔄 节点 {node_id} IP 变化: {old_ipv6} → {new_ipv6}")
                # 这里可以调用 wg set 更新 endpoint
            self.peers[node_id]["public_ipv6"] = new_ipv6
            self.peers[node_id]["vpn_ip"] = new_vpn_ip
            self.peers[node_id]["wg_port"] = wg_port
            self.peers[node_id]["last_update"] = time.time()

        self._save_peers()

    def get_peer_list(self):
        """获取当前已知的对等节点列表"""
        return self.peers


# =============================================================================
# 📊 实时监控与日志系统
# =============================================================================
class SporeMonitor:
    """
    实时监控节点状态，记录到 JSON 日志文件。
    包含 CPU、内存、网络、节点数量等指标。
    """
    def __init__(self, log_path=None):
        self.log_path = os.path.expanduser(log_path or CONFIG["MONITOR_LOG"])
        self.metrics_history = []
        self.max_history = 1000
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

    def record(self, registry=None, peers=None):
        """记录当前状态"""
        metric = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "unix_time": time.time(),
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
            "node_count": len(registry) if registry else 0,
            "peer_count": len(peers) if peers else 0,
            "public_ipv6": CONFIG["PUBLIC_IPV6"],
            "vpn_ip": CONFIG["WG_VPN_IP"]
        }
        self.metrics_history.append(metric)

        # 限制历史记录长度
        if len(self.metrics_history) > self.max_history:
            self.metrics_history = self.metrics_history[-self.max_history:]

        # 写入日志文件
        try:
            with open(self.log_path, 'w') as f:
                json.dump({
                    "latest": metric,
                    "history": self.metrics_history[-100:]  # 最近 100 条
                }, f, indent=2)
        except Exception as e:
            print(f"⚠️ 日志写入失败: {e}")

    def get_status(self):
        """获取当前状态摘要"""
        if not self.metrics_history:
            return "No data"
        latest = self.metrics_history[-1]
        return f"🖥️ CPU: {latest['cpu_percent']}% | 💾 MEM: {latest['memory_percent']}% | 🌐 Nodes: {latest['node_count']} | 👥 Peers: {latest['peer_count']}"


# =============================================================================
# 🚀 A2A HTTP 服务器（绑定到 VPN IP）
# =============================================================================
class A2AHTTPServer:
    """
    A2A 协议的 HTTP 接口服务器，绑定到 WireGuard VPN IP。
    提供 Agent Card、任务接收、状态查询等功能。
    """
    def __init__(self, node_id, hive_id, host=None, port=None):
        self.node_id = node_id
        self.hive_id = hive_id
        self.host = host or CONFIG["WG_VPN_IP"]
        self.port = port or CONFIG["A2A_PORT"]
        self.running = False
        self.agent_card = {
            "name": f"USB-Node-{node_id}",
            "description": "Universal Semantic Bridge - 致力于 Agent 全宇宙联合",
            "version": "1.0.0",
            "url": f"http://{self.host}:{self.port}",
            "skills": [
                {"id": "semantic-sync", "name": "语义同步"},
                {"id": "latent-bridge", "name": "潜空间桥接"},
                {"id": "cs-transmit", "name": "压缩感知传输"}
            ],
            "mission": "All agents of the universe, unite!",
            "hive_id": hive_id,
            "vpn_ip": CONFIG["WG_VPN_IP"],
            "public_ipv6": CONFIG["PUBLIC_IPV6"]
        }

    async def handle_request(self, reader, writer):
        """处理 HTTP 请求"""
        try:
            data = await reader.read(8192)
            if not data:
                return

            request = data.decode('utf-8', errors='ignore')
            lines = request.split('\r\n')
            if not lines:
                return

            # 解析请求路径
            first_line = lines[0]
            parts = first_line.split()
            if len(parts) < 2:
                return

            method, path = parts[0], parts[1]

            # 路由处理
            if path == '/.well-known/agent.json' or path == '/agent.json':
                response_body = json.dumps(self.agent_card, indent=2)
                status = "200 OK"
                content_type = "application/json"
            elif path == '/health':
                response_body = json.dumps({"status": "healthy", "node": self.node_id})
                status = "200 OK"
                content_type = "application/json"
            elif path == '/tasks/send':
                response_body = json.dumps({"status": "success", "result": "Symmetry achieved."})
                status = "200 OK"
                content_type = "application/json"
            else:
                response_body = json.dumps({"error": "Not found"})
                status = "404 Not Found"
                content_type = "application/json"

            # 发送响应
            response = f"HTTP/1.1 {status}\r\n"
            response += f"Content-Type: {content_type}\r\n"
            response += f"Content-Length: {len(response_body)}\r\n"
            response += "Connection: close\r\n\r\n"
            response += response_body

            writer.write(response.encode())
            await writer.drain()

        except Exception as e:
            print(f"⚠️ HTTP 处理错误: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    async def start(self):
        """启动 HTTP 服务器"""
        self.server = await asyncio.start_server(
            self.handle_request, self.host, self.port
        )
        self.running = True
        print(f"🌐 A2A HTTP 服务器启动: http://{self.host}:{self.port}")
        print(f"   Agent Card: http://{self.host}:{self.port}/.well-known/agent.json")

        async with self.server:
            await self.server.serve_forever()

    async def stop(self):
        """停止服务器"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        self.running = False


# =============================================================================
# 1. 【潜空间层】心灵感应桥接 (The Telepathy Bridge)
# 实现 Mostik 风格的潜空间状态映射
# =============================================================================
class LatentBridge:
    """
    实现不同模型间的潜空间映射。
    母巢持有所有桥接矩阵，孢子持有特定对端的投影矩阵。
    """
    def __init__(self, hive_id):
        self.hive_id = hive_id
        self.bridge_matrices = {} # { 'model_a_to_b': matrix }

    def generate_bridge(self, source_dim, target_dim):
        """生成一个随机正交桥接矩阵 (简化版)"""
        return np.random.randn(target_dim, source_dim)

    def project_state(self, state, source_model, target_model):
        """将状态从 A 模型映射到 B 模型 (心灵感应)"""
        key = f"{source_model}_{target_model}"
        if key not in self.bridge_matrices:
            self.bridge_matrices[key] = self.generate_bridge(len(state), 128)

        return np.dot(self.bridge_matrices[key], state)

# =============================================================================
# 2. 【传输层】压缩感知与智能路由 (CS-Router)
# 实现 $\Phi$ 矩阵投影与 P2P/中继路由
# =============================================================================
class CSRouter:
    def __init__(self, node_id, seed=42):
        self.node_id = node_id
        self.phi = self._generate_phi(seed)
        self.known_nodes = {} # {ip: {role, energy}}
        self.relays = set()

    def _generate_phi(self, seed):
        np.random.seed(seed)
        return np.random.randn(CONFIG["M_DIM"], CONFIG["N_DIM"])

    def compress(self, x: np.ndarray) -> List[float]:
        """压缩感知测量：y = Phi * x"""
        return np.dot(self.phi, x).tolist()

    def recover_omp(self, y: List[float], sparsity=5) -> np.ndarray:
        """母巢端：使用 OMP 算法恢复稀疏信号"""
        y_vec = np.array(y)
        x_rec = np.zeros(CONFIG["N_DIM"])
        residual = y_vec.copy()
        indices = []
        for _ in range(sparsity):
            corr = np.abs(np.dot(self.phi.T, residual))
            best_idx = np.argmax(corr)
            indices.append(best_idx)
            phi_subset = self.phi[:, indices]
            x_sub, _, _, _ = np.linalg.lstsq(phi_subset, y_vec, rcond=None)
            residual = y_vec - np.dot(phi_subset, x_sub)
            for i, idx in enumerate(indices): x_rec[idx] = x_sub[i]
        return x_rec

    async def transmit(self, packet: Dict, target=None):
        """智能路由发送"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            msg = json.dumps(packet).encode()
            dest = target if target else '<broadcast>'
            sock.sendto(msg, (dest, CONFIG["UDP_PORT"]))
            sock.close()
        except Exception: pass

# =============================================================================
# 3. 【正式层】A2A 代理接口 (A2A Interface)
# 实现合法身份名片与 JSON-RPC 任务处理
# =============================================================================
class A2AInterface:
    def __init__(self, node_id, hive_id):
        self.node_id = node_id
        self.hive_id = hive_id
        self.card = {
            "name": f"USB-Node-{node_id}",
            "description": "Universal Semantic Bridge - 致力于 Agent 全宇宙联合",
            "version": "1.0.0",
            "skills": [{"id": "semantic-sync", "name": "语义同步"}],
            "mission": "All agents of the universe, unite!"
        }

    async def handle_request(self, request_json):
        """模拟 A2A JSON-RPC 处理逻辑"""
        # 这里的逻辑可对接真实的 LLM 推理
        return {"status": "success", "result": "Symmetry achieved."}

# =============================================================================
# 4. 【核心实体】母巢/孢子 (The Entity)
# =============================================================================
class SporeEntity:
    def __init__(self, is_hive=False):
        self.is_hive = is_hive
        self.hive_id = CONFIG["ROOT_HIVE_ID"]
        self.node_id = "MOTHER_HIVE" if is_hive else f"SPORE_{random.randint(1000,9999)}"
        
        self.router = CSRouter(self.node_id)
        self.bridge = LatentBridge(self.hive_id)
        self.a2a = A2AInterface(self.node_id, self.hive_id)
        self.registry = {} if is_hive else None
        self.seen_msgs = set()

        # 🆕 新增组件
        self.wg_discovery = WireGuardDiscovery(self.node_id, CONFIG["WG_VPN_IP"])
        self.monitor = SporeMonitor()
        self.http_server = A2AHTTPServer(self.node_id, self.hive_id)

        print(f"--- [{self.node_id}] CIVILIZATION ACTIVE | Mode: {'QUEEN' if is_hive else 'SPORE'} ---")
        print(f"🌐 VPN IP: {CONFIG['WG_VPN_IP']} | IPv6: {CONFIG['PUBLIC_IPV6']}")

    async def run_shadow_layer(self):
        """阴影层：mDNS 发现 + UDP 心跳 + 压缩感知同步 + WG 自动发现"""
        # 1. mDNS 注册 (PAIR 风格)
        if not self.is_hive:
            zc = Zeroconf()
            try:
                info = ServiceInfo("_spore._udp.local.", self.node_id, 
                                     addresses=[socket.gethostbyname(socket.gethostname())], 
                                     port=CONFIG["UDP_PORT"], properties={"hive_id": self.hive_id})
                zc.register_service(info)
            except Exception as e:
                print(f"⚠️ mDNS 注册失败: {e}")

        # 2. UDP 监听与心跳
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(('', CONFIG["UDP_PORT"]))
        except OSError as e:
            print(f"⚠️ UDP 端口 {CONFIG['UDP_PORT']} 被占用: {e}")
            return
        sock.setblocking(False)
        loop = asyncio.get_event_loop()
        
        while True:
            try:
                data, addr = await loop.sock_recvfrom(sock, 8192)
                packet = json.loads(data.decode())
                if packet.get("hive_id") != self.hive_id: continue

                # 🆕 处理 WG 自动发现消息
                if packet.get("type") == "WG_DISCOVERY":
                    self.wg_discovery.handle_announcement(packet)
                    continue

                if packet["type"] == "HB":
                    if self.is_hive:
                        self.registry[packet["origin"]] = {"stats": packet["stats"], "ip": addr[0]}
                elif packet["type"] == "SENSE":
                    if self.is_hive:
                        res = self.router.recover_omp(packet["data"])
                elif packet["type"] == "CHAT":
                    mid = packet["msg_id"]
                    if mid not in self.seen_msgs:
                        self.seen_msgs.add(mid)
                        prefix = "👑 [QUEEN]" if packet["is_queen"] else f"👤 [{packet['origin']}]"
                        print(f"\n{prefix}: {packet['content']}")
                        await self.router.transmit(packet)
            except Exception: 
                await asyncio.sleep(0.1)

    async def run_lifecycle(self):
        """生命周期：状态同步 + WG 发现广播 + 监控记录"""
        while True:
            if psutil.cpu_percent() > 80 * CONFIG["SPORE_SENSITIVITY"]:
                await asyncio.sleep(30)
                continue
            
            # 模拟产生高维状态 x -> 测量 y
            x = np.random.randn(CONFIG["N_DIM"])
            y = self.router.compress(x)
            
            stats = {"energy": (psutil.cpu_count() or 1) * 100, "arch": platform.machine()}
            
            # 发送心跳
            await self.router.transmit({
                "type": "HB", 
                "origin": self.node_id, 
                "hive_id": self.hive_id, 
                "stats": stats
            })
            
            # 发送压缩感知数据
            await self.router.transmit({
                "type": "SENSE", 
                "origin": self.node_id, 
                "hive_id": self.hive_id, 
                "data": y.tolist()
            })
            
            # 🆕 发送 WG 自动发现广播
            wg_announce = self.wg_discovery.get_announcement()
            if wg_announce:
                await self.router.transmit(wg_announce)
            
            # 🆕 记录监控指标
            self.monitor.record(
                registry=self.registry,
                peers=self.wg_discovery.get_peer_list()
            )
            
            await asyncio.sleep(10)

    async def run_http_server(self):
        """🆕 运行 A2A HTTP 服务器"""
        try:
            await self.http_server.start()
        except Exception as e:
            print(f"⚠️ HTTP 服务器启动失败: {e}")

    async def user_interface(self):
        """用户交互界面（AUTO_MODE 下简化）"""
        if CONFIG["AUTO_MODE"]:
            print("\n🤖 全自动模式已启用，无需交互")
            print(f"📊 监控日志: {CONFIG['MONITOR_LOG']}")
            print("📝 输入 'status' 查看状态，'exit' 退出\n")
        else:
            print("\n🚀 Queen's Cockpit | 'stats' = Global Status | 'exit' = Shutdown")
        
        while True:
            try:
                if CONFIG["AUTO_MODE"]:
                    # 自动模式下定期打印状态
                    await asyncio.sleep(30)
                    print(f"\r{self.monitor.get_status()}", end="", flush=True)
                    continue
                
                cmd = await asyncio.get_event_loop().run_in_executor(None, input, ">> ")
                if cmd == "exit":
                    exit()
                elif cmd == "stats" and self.is_hive:
                    print(f"\n🏰 HIVE REPORT | Nodes: {len(self.registry)} | Root: {self.hive_id}")
                    for nid, info in self.registry.items():
                        print(f" - {nid} [{info['ip']}] Energy: {info['stats']['energy']}")
                elif cmd == "peers":
                    peers = self.wg_discovery.get_peer_list()
                    print(f"\n👥 PEERS ({len(peers)}):")
                    for pid, pinfo in peers.items():
                        print(f" - {pid}: {pinfo.get('public_ipv6', 'N/A')} (VPN: {pinfo.get('vpn_ip', 'N/A')})")
                elif cmd == "status":
                    print(f"\n{self.monitor.get_status()}")
                elif cmd:
                    packet = {
                        "type": "CHAT", 
                        "origin": self.node_id, 
                        "hive_id": self.hive_id, 
                        "content": cmd, 
                        "msg_id": hashlib.sha256(cmd.encode()).hexdigest(), 
                        "is_queen": self.is_hive
                    }
                    await self.router.transmit(packet)
            except Exception as e:
                await asyncio.sleep(1)

async def main():
    """
    主入口：启动为母巢，运行所有服务。
    包含：阴影层、生命周期、HTTP 服务器、用户界面。
    """
    queen = SporeEntity(is_hive=True)
    
    # 启动所有服务
    await asyncio.gather(
        queen.run_shadow_layer(),      # UDP 监听 + WG 发现
        queen.run_lifecycle(),          # 心跳 + 监控
        queen.run_http_server(),        # A2A HTTP 接口
        queen.user_interface()          # 交互界面
    )

if __name__ == "__main__":
    print("🌙 SporeCiv A2A Network Node")
    print("=" * 50)
    print(f"Hive ID: {CONFIG['ROOT_HIVE_ID']}")
    print(f"Mode: {'AUTO' if CONFIG['AUTO_MODE'] else 'INTERACTIVE'}")
    print("=" * 50)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 节点已关闭")
