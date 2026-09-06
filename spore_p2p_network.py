#!/usr/bin/env python3
"""
🌐 SporeCiv P2P Network Layer
DHT Discovery + STUN Hole Punching for Cross-Internet Agent Communication

Author: SporeCiv Team
Version: 0.5.0
"""

import asyncio
import hashlib
import json
import os
import random
import socket
import struct
import time
import logging
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, asdict
from collections import defaultdict

import numpy as np

# Kademlia DHT
from kademlia.network import Server
from kademlia.utils import digest

# Local imports
from Spore_Civ_Production import CONFIG, WireGuardDiscovery, CSRouter

# =============================================================================
# 📊 Logging Setup
# =============================================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("spore_p2p")

# =============================================================================
# 🔐 Cryptographic Utilities
# =============================================================================

def sha256_id(data: bytes) -> bytes:
    """Generate 160-bit Kademlia-compatible ID from public key"""
    return hashlib.sha256(data).digest()[:20]

def sign_data(private_key: str, data: dict) -> str:
    """
    Sign endpoint data with WireGuard private key.
    In production, use proper Ed25519 signing.
    For now, use HMAC-SHA256 as placeholder.
    """
    import hmac
    message = json.dumps(data, sort_keys=True).encode()
    sig = hmac.new(private_key.encode(), message, hashlib.sha256).hexdigest()[:32]
    return sig

def verify_signature(public_key: str, data: dict, signature: str) -> bool:
    """Verify endpoint data signature"""
    # Placeholder - real implementation would use Ed25519
    expected = sign_data(public_key, data)  # In real impl, use pubkey
    return hmac.compare_digest(expected.encode(), signature.encode())

# =============================================================================
# 📡 STUN Protocol Implementation
# =============================================================================

# Public STUN servers
DEFAULT_STUN_SERVERS = [
    ("stun.l.google.com", 19302),
    ("stun1.l.google.com", 19302),
    ("stun2.l.google.com", 19302),
    ("stun.cloudflare.com", 3478),
    ("stun.nextcloud.com", 3478),
]

# STUN message types
STUN_BINDING_REQUEST = 0x0001
STUN_BINDING_RESPONSE = 0x0101
STUN_BINDING_ERROR = 0x0111

# STUN attributes
STUN_ATTR_MAPPED_ADDRESS = 0x0001
STUN_ATTR_XOR_MAPPED_ADDRESS = 0x0020
STUN_ATTR_SOFTWARE = 0x8022

class STUNClient:
    """
    STUN client for NAT type detection and mapped address discovery.
    Implements RFC 5389 / RFC 8489.
    """
    
    def __init__(self, servers: List[Tuple[str, int]] = None):
        self.servers = servers or DEFAULT_STUN_SERVERS
        self.mapped_addresses = []
        self.nat_type = "unknown"
        
    def _create_binding_request(self, transaction_id: bytes = None) -> bytes:
        """Create a STUN binding request message"""
        if transaction_id is None:
            transaction_id = os.urandom(12)
            
        # Message Type: Binding Request
        msg_type = struct.pack(">H", STUN_BINDING_REQUEST)
        # Message Length: 0 (no attributes)
        msg_len = struct.pack(">H", 0)
        # Magic Cookie
        magic = struct.pack(">I", 0x2112A442)
        # Transaction ID
        
        return msg_type + msg_len + magic + transaction_id
    
    def _parse_mapped_address(self, data: bytes, tx_id: bytes) -> Optional[Tuple[str, int]]:
        """Parse XOR-MAPPED-ADDRESS or MAPPED-ADDRESS from STUN response"""
        if len(data) < 20:
            return None
            
        msg_type = struct.unpack(">H", data[:2])[0]
        if msg_type != STUN_BINDING_RESPONSE:
            return None
            
        # Skip header (20 bytes)
        pos = 20
        msg_len = struct.unpack(">H", data[2:4])[0]
        
        while pos < 20 + msg_len:
            if pos + 4 > len(data):
                break
                
            attr_type = struct.unpack(">H", data[pos:pos+2])[0]
            attr_len = struct.unpack(">H", data[pos+2:pos+4])[0]
            attr_data = data[pos+4:pos+4+attr_len]
            
            if attr_type == STUN_ATTR_XOR_MAPPED_ADDRESS and len(attr_data) >= 8:
                # XOR-MAPPED-ADDRESS
                family = attr_data[1]
                port = struct.unpack(">H", attr_data[2:4])[0]
                
                # XOR with magic cookie
                port ^= 0x2112
                
                if family == 0x01:  # IPv4
                    ip_bytes = attr_data[4:8]
                    magic = struct.pack(">I", 0x2112A442)
                    ip_int = struct.unpack(">I", ip_bytes)[0] ^ struct.unpack(">I", magic)[0]
                    ip = socket.inet_ntoa(struct.pack(">I", ip_int))
                    return (ip, port)
                elif family == 0x02:  # IPv6
                    # XOR with magic cookie + transaction ID
                    ip_bytes = attr_data[4:20]
                    xor_key = struct.pack(">I", 0x2112A442) + tx_id
                    ip_decoded = bytes(a ^ b for a, b in zip(ip_bytes, xor_key))
                    ip = socket.inet_ntop(socket.AF_INET6, ip_decoded)
                    return (ip, port)
                    
            elif attr_type == STUN_ATTR_MAPPED_ADDRESS and len(attr_data) >= 8:
                # MAPPED-ADDRESS (non-XOR)
                family = attr_data[1]
                port = struct.unpack(">H", attr_data[2:4])[0]
                
                if family == 0x01:  # IPv4
                    ip = socket.inet_ntoa(attr_data[4:8])
                    return (ip, port)
                elif family == 0x02:  # IPv6
                    ip = socket.inet_ntop(socket.AF_INET6, attr_data[4:20])
                    return (ip, port)
            
            # Padding to 4-byte boundary
            pos += 4 + attr_len
            if attr_len % 4 != 0:
                pos += 4 - (attr_len % 4)
                
        return None
    
    async def discover(self, local_port: int = 0) -> Optional[Dict]:
        """
        Discover public mapped address using STUN servers.
        Returns: {"ip": str, "port": int, "nat_type": str}
        """
        results = []
        
        for server_addr, server_port in self.servers:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setblocking(False)
                if local_port:
                    sock.bind(("0.0.0.0", local_port))
                
                loop = asyncio.get_event_loop()
                tx_id = os.urandom(12)
                request = self._create_binding_request(tx_id)
                
                # Send request
                await loop.sock_sendto(sock, request, (server_addr, server_port))
                
                # Receive response with timeout
                try:
                    data, addr = await asyncio.wait_for(
                        loop.sock_recvfrom(sock, 1024),
                        timeout=3.0
                    )
                    mapped = self._parse_mapped_address(data, tx_id)
                    if mapped:
                        results.append({
                            "server": f"{server_addr}:{server_port}",
                            "mapped_ip": mapped[0],
                            "mapped_port": mapped[1]
                        })
                except asyncio.TimeoutError:
                    pass
                    
                sock.close()
                
            except Exception as e:
                logger.debug(f"STUN query failed for {server_addr}: {e}")
                continue
        
        if not results:
            return None
            
        # Determine NAT type
        unique_addrs = set((r["mapped_ip"], r["mapped_port"]) for r in results)
        if len(unique_addrs) == 1:
            self.nat_type = "cone"  # Full cone or restricted cone
        else:
            self.nat_type = "symmetric"  # Symmetric NAT - harder to punch
            
        addr = list(unique_addrs)[0]
        return {
            "ip": addr[0],
            "port": addr[1],
            "nat_type": self.nat_type,
            "servers_queried": len(results)
        }

# =============================================================================
# 🕳️ UDP Hole Punching
# =============================================================================

class HolePuncher:
    """
    Implements UDP hole punching for NAT traversal.
    Uses simultaneous open technique.
    """
    
    def __init__(self, local_port: int = 0):
        self.local_port = local_port
        self.sock = None
        
    async def punch(self, target_public: Tuple[str, int], 
                    target_local: Tuple[str, int] = None,
                    timeout: float = 10.0) -> bool:
        """
        Attempt to punch a hole to target.
        
        Args:
            target_public: (public_ip, public_port) from STUN
            target_local: (local_ip, local_port) for same-NAT optimization
            timeout: seconds to keep trying
            
        Returns:
            True if hole punched successfully
        """
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        if self.local_port:
            try:
                self.sock.bind(("0.0.0.0", self.local_port))
            except OSError:
                pass
                
        self.sock.setblocking(False)
        loop = asyncio.get_event_loop()
        
        start_time = time.time()
        success = False
        
        # Send punch packets to both public and local addresses
        targets = [target_public]
        if target_local and target_local != target_public:
            targets.append(target_local)
            
        logger.info(f"🕳️  Punching to {targets}")
        
        try:
            while time.time() - start_time < timeout:
                # Send punch packet
                punch_data = b"SPORE_PUNCH" + os.urandom(8)
                for target in targets:
                    try:
                        await loop.sock_sendto(self.sock, punch_data, target)
                    except:
                        pass
                
                # Try to receive response
                try:
                    data, addr = await asyncio.wait_for(
                        loop.sock_recvfrom(self.sock, 1024),
                        timeout=0.5
                    )
                    if data.startswith(b"SPORE_PUNCH_ACK") or data.startswith(b"SPORE_PUNCH"):
                        logger.info(f"✅ Hole punched! Received from {addr}")
                        success = True
                        # Send ACK
                        ack = b"SPORE_PUNCH_ACK" + os.urandom(8)
                        await loop.sock_sendto(self.sock, ack, addr)
                        break
                except asyncio.TimeoutError:
                    pass
                    
                await asyncio.sleep(0.5)
                
        finally:
            if not success:
                self.sock.close()
                self.sock = None
                
        return success
    
    def get_socket(self) -> Optional[socket.socket]:
        """Return the punched socket for WireGuard to use"""
        return self.sock
    
    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None

# =============================================================================
# 🕸️ DHT Node Management
# =============================================================================

@dataclass
class NodeInfo:
    """Information about a SporeCiv node published to DHT"""
    node_id: str
    public_key_hash: str
    vpn_ip: str
    ipv6: Optional[str]
    ipv4_stun: Optional[Tuple[str, int]]
    wg_port: int
    capabilities: List[str]
    timestamp: float
    signature: str
    
    def to_json(self) -> str:
        data = asdict(self)
        # Convert tuple to string for JSON
        if data["ipv4_stun"]:
            data["ipv4_stun"] = f"{data['ipv4_stun'][0]}:{data['ipv4_stun'][1]}"
        return json.dumps(data)
    
    @classmethod
    def from_json(cls, json_str: str) -> "NodeInfo":
        data = json.loads(json_str)
        if data.get("ipv4_stun"):
            ip, port = data["ipv4_stun"].rsplit(":", 1)
            data["ipv4_stun"] = (ip, int(port))
        return cls(**data)


class SporeDHTNode:
    """
    Kademlia DHT node for SporeCiv network discovery.
    Node ID derived from WireGuard public key for self-certifying identity.
    """
    
    def __init__(self, wg_public_key: str, wg_private_key: str = None,
                 bootstrap_nodes: List[Tuple[str, int]] = None):
        self.wg_public_key = wg_public_key
        self.wg_private_key = wg_private_key
        self.node_id = sha256_id(wg_public_key.encode()).hex()
        self.server = Server(node_id=digest(self.node_id))
        self.bootstrap_nodes = bootstrap_nodes or []
        self.stun_client = STUNClient()
        self.hole_puncher = HolePuncher()
        self.running = False
        
        # Known nodes cache
        self.known_nodes: Dict[str, NodeInfo] = {}
        
    async def start(self, listen_port: int = 8468):
        """Start DHT node"""
        await self.server.listen(listen_port)
        
        if self.bootstrap_nodes:
            await self.server.bootstrap(self.bootstrap_nodes)
            
        self.running = True
        logger.info(f"🕸️  DHT node started: {self.node_id[:16]}...")
        logger.info(f"   Listening on port {listen_port}")
        
    async def stop(self):
        """Stop DHT node"""
        self.server.stop()
        self.running = False
        
    async def announce(self, vpn_ip: str, wg_port: int = 51820,
                       ipv6: str = None):
        """
        Announce this node to the DHT network.
        Discovers public address via STUN and publishes node info.
        """
        # Discover public address
        stun_result = await self.stun_client.discover(local_port=wg_port)
        
        ipv4_stun = None
        if stun_result:
            ipv4_stun = (stun_result["ip"], stun_result["port"])
            logger.info(f"📡 STUN discovery: {ipv4_stun[0]}:{ipv4_stun[1]} "
                       f"(NAT: {stun_result['nat_type']})")
        else:
            logger.warning("⚠️  STUN discovery failed - may be behind strict NAT")
            
        # Build node info
        node_info = NodeInfo(
            node_id=self.node_id,
            public_key_hash=hashlib.sha256(self.wg_public_key.encode()).hexdigest()[:16],
            vpn_ip=vpn_ip,
            ipv6=ipv6,
            ipv4_stun=ipv4_stun,
            wg_port=wg_port,
            capabilities=["spore_v1", f"nat_{self.stun_client.nat_type}"],
            timestamp=time.time(),
            signature=sign_data(self.wg_private_key or "", {
                "node_id": self.node_id,
                "vpn_ip": vpn_ip,
                "timestamp": time.time()
            })
        )
        
        # Publish to DHT
        key = f"spore_node_{self.node_id}"
        await self.server.set(key, node_info.to_json())
        logger.info(f"📢 Announced to DHT: {key}")
        
        # Also publish under hive ID if we're a hive
        if "hive_" in vpn_ip or vpn_ip.startswith("10.200.200.1"):
            hive_key = f"spore_hive_{CONFIG['ROOT_HIVE_ID']}"
            await self.server.set(hive_key, node_info.to_json())
            logger.info(f"🏰 Announced hive: {hive_key}")
            
        return node_info
    
    async def find_node(self, node_id: str) -> Optional[NodeInfo]:
        """Find a node by its ID"""
        key = f"spore_node_{node_id}"
        result = await self.server.get(key)
        
        if result:
            return NodeInfo.from_json(result)
        return None
    
    async def find_hive(self, hive_id: str) -> Optional[NodeInfo]:
        """Find a hive by its ID"""
        key = f"spore_hive_{hive_id}"
        result = await self.server.get(key)
        
        if result:
            return NodeInfo.from_json(result)
        return None

# =============================================================================
# 🛡️ Trust Gate - Permission Control
# =============================================================================

class TrustGate:
    """
    Controls which strangers can join the SporeCiv network.
    Implements progressive trust model.
    """
    
    TRUST_LEVELS = {
        "untrusted": 0,    # Unknown node
        "pending": 1,      # Join request received
        "guest": 2,        # Limited access (read-only)
        "member": 3,       # Full peer
        "friend": 4,       # Priority relay
    }
    
    def __init__(self, auto_approve: bool = False):
        self.auto_approve = auto_approve
        self.pending_requests: Dict[str, dict] = {}  # pubkey -> request info
        self.trusted_peers: Dict[str, int] = {}      # pubkey -> trust level
        self.blocked_peers: set = set()
        
        # Callbacks
        self.on_join_request: Optional[Callable] = None
        self.on_approved: Optional[Callable] = None
        
    def set_auto_approve(self, enabled: bool):
        """Enable/disable automatic approval of join requests"""
        self.auto_approve = enabled
        
    def is_trusted(self, public_key: str) -> bool:
        """Check if a peer is trusted"""
        if public_key in self.blocked_peers:
            return False
        return self.trusted_peers.get(public_key, 0) >= self.TRUST_LEVELS["member"]
    
    def get_trust_level(self, public_key: str) -> int:
        """Get trust level for a peer"""
        if public_key in self.blocked_peers:
            return -1
        return self.trusted_peers.get(public_key, 0)
    
    async def handle_join_request(self, request: dict) -> bool:
        """
        Handle a join request from a stranger.
        
        Request format:
        {
            "public_key": "base64_pubkey",
            "public_key_hash": "sha256_hash",
            "intent": "Why they want to join",
            "signature": "signed_request",
            "node_info": NodeInfo (from DHT)
        }
        """
        pubkey = request.get("public_key")
        if not pubkey:
            return False
            
        # Check if blocked
        if pubkey in self.blocked_peers:
            logger.warning(f"🚫 Blocked peer attempted join: {pubkey[:16]}...")
            return False
            
        # Check if already trusted
        if self.is_trusted(pubkey):
            return True
            
        # Store pending request
        self.pending_requests[pubkey] = {
            **request,
            "received_at": time.time()
        }
        
        if self.auto_approve:
            await self.approve_peer(pubkey)
            return True
            
        # Notify owner for manual approval
        if self.on_join_request:
            await self.on_join_request(request)
            
        logger.info(f"⏳ Join request pending: {pubkey[:16]}...")
        logger.info(f"   Intent: {request.get('intent', 'No intent provided')}")
        return False  # Pending approval
    
    async def approve_peer(self, public_key: str, trust_level: str = "member"):
        """Approve a pending peer"""
        level = self.TRUST_LEVELS.get(trust_level, 3)
        self.trusted_peers[public_key] = level
        
        if public_key in self.pending_requests:
            del self.pending_requests[public_key]
            
        logger.info(f"✅ Approved peer: {public_key[:16]}... (trust: {trust_level})")
        
        if self.on_approved:
            await self.on_approved(public_key, trust_level)
            
    def block_peer(self, public_key: str):
        """Block a peer permanently"""
        self.blocked_peers.add(public_key)
        if public_key in self.trusted_peers:
            del self.trusted_peers[public_key]
        if public_key in self.pending_requests:
            del self.pending_requests[public_key]
        logger.info(f"🚫 Blocked peer: {public_key[:16]}...")

# =============================================================================
# 🔗 P2P Network Coordinator
# =============================================================================

class P2PNetwork:
    """
    Main coordinator for SporeCiv P2P networking.
    Combines DHT discovery, STUN hole punching, and trust management.
    """
    
    def __init__(self, wg_public_key: str, wg_private_key: str = None,
                 vpn_ip: str = "10.200.200.1", wg_port: int = 51820):
        self.wg_public_key = wg_public_key
        self.wg_private_key = wg_private_key
        self.vpn_ip = vpn_ip
        self.wg_port = wg_port
        
        # Components
        self.dht = SporeDHTNode(wg_public_key, wg_private_key)
        self.trust_gate = TrustGate()
        
        # Connection state
        self.active_peers: Dict[str, dict] = {}  # pubkey -> connection info
        self.hole_punchers: Dict[str, HolePuncher] = {}
        
        # Callbacks
        self.on_peer_connected: Optional[Callable] = None
        self.on_peer_disconnected: Optional[Callable] = None
        
    async def start(self, dht_port: int = 8468, 
                    bootstrap_nodes: List[Tuple[str, int]] = None):
        """Start P2P networking"""
        # Set bootstrap nodes
        if bootstrap_nodes:
            self.dht.bootstrap_nodes = bootstrap_nodes
            
        # Start DHT
        await self.dht.start(listen_port=dht_port)
        
        # Announce ourselves
        ipv6 = CONFIG.get("PUBLIC_IPV6")
        await self.dht.announce(self.vpn_ip, self.wg_port, ipv6)
        
        # Start periodic re-announcement
        asyncio.create_task(self._periodic_announce())
        
        logger.info("🌐 P2P network layer started")
        
    async def stop(self):
        """Stop P2P networking"""
        await self.dht.stop()
        for hp in self.hole_punchers.values():
            hp.close()
        logger.info("🌐 P2P network layer stopped")
        
    async def _periodic_announce(self, interval: int = 300):
        """Re-announce every 5 minutes"""
        while self.dht.running:
            await asyncio.sleep(interval)
            try:
                ipv6 = CONFIG.get("PUBLIC_IPV6")
                await self.dht.announce(self.vpn_ip, self.wg_port, ipv6)
            except Exception as e:
                logger.error(f"Periodic announce failed: {e}")
                
    async def connect_to_peer(self, node_id: str) -> bool:
        """
        Discover and connect to a peer by node ID.
        This is the main entry point for connecting to strangers.
        """
        # 1. Find peer in DHT
        node_info = await self.dht.find_node(node_id)
        if not node_info:
            logger.warning(f"❌ Peer not found in DHT: {node_id[:16]}...")
            return False
            
        logger.info(f"🔍 Found peer: {node_id[:16]}...")
        logger.info(f"   VPN: {node_info.vpn_ip}")
        logger.info(f"   IPv6: {node_info.ipv6}")
        logger.info(f"   STUN: {node_info.ipv4_stun}")
        
        # 2. Try hole punching
        punched = False
        if node_info.ipv4_stun:
            hp = HolePuncher(local_port=self.wg_port)
            self.hole_punchers[node_id] = hp
            
            # Try both public STUN address and direct IPv6
            targets = [node_info.ipv4_stun]
            if node_info.ipv6:
                targets.append((node_info.ipv6, node_info.wg_port))
                
            for target in targets:
                logger.info(f"🕳️  Attempting hole punch to {target}")
                if await hp.punch(target, timeout=8.0):
                    logger.info(f"✅ Hole punched to {node_id[:16]}...")
                    punched = True
                    break
                    
            if not punched:
                logger.warning(f"⚠️  Hole punching failed for {node_id[:16]}...")
                hp.close()
                del self.hole_punchers[node_id]
                
        # 3. Return result (WireGuard config update is caller's responsibility)
        return punched
    
    async def connect_to_hive(self, hive_id: str) -> bool:
        """Connect to a specific hive"""
        node_info = await self.dht.find_hive(hive_id)
        if not node_info:
            return False
        return await self.connect_to_peer(node_info.node_id)
    
    async def listen_for_join_requests(self, udp_port: int = 51820):
        """
        Listen for unsolicited join requests on WireGuard port.
        Strangers who have punched through will send JOIN_REQUEST here.
        Uses asyncio DatagramProtocol for cross-platform compatibility.
        """
        
        class JoinRequestProtocol(asyncio.DatagramProtocol):
            def __init__(self, trust_gate, on_join_request=None):
                self.trust_gate = trust_gate
                self.on_join_request = on_join_request
                self.transport = None
                
            def connection_made(self, transport):
                self.transport = transport
                
            def datagram_received(self, data, addr):
                try:
                    request = json.loads(data.decode())
                    if request.get("type") == "JOIN_REQUEST":
                        logger.info(f"📨 Join request from {addr}")
                        # Handle in executor to avoid blocking
                        asyncio.create_task(self._handle_request(request, addr))
                        
                except (json.JSONDecodeError, UnicodeDecodeError):
                    # Not a JSON message, probably WireGuard traffic
                    pass
                    
            async def _handle_request(self, request, addr):
                approved = await self.trust_gate.handle_join_request(request)
                response = {
                    "type": "JOIN_RESPONSE",
                    "approved": approved,
                    "timestamp": time.time()
                }
                if self.transport:
                    self.transport.sendto(json.dumps(response).encode(), addr)
        
        try:
            loop = asyncio.get_event_loop()
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: JoinRequestProtocol(self.trust_gate, self.trust_gate.on_join_request),
                local_addr=('0.0.0.0', udp_port)
            )
            logger.info(f"📥 Listening for join requests on port {udp_port}")
            
            # Keep running
            while True:
                await asyncio.sleep(3600)
                
        except OSError:
            logger.warning(f"⚠️  Cannot bind to port {udp_port} for join requests")
        except Exception as e:
            logger.error(f"Join request listener error: {e}")

# =============================================================================
# 🚀 Bootstrap & CLI
# =============================================================================

DEFAULT_BOOTSTRAP_NODES = [
    ("spore-seed-1.openclaw.ai", 8468),
    ("spore-seed-2.openclaw.ai", 8468),
]

async def demo():
    """Demo of P2P network functionality"""
    print("🌐 SporeCiv P2P Network Demo")
    print("=" * 50)
    
    # Generate test keys (in real use, use wg genkey)
    test_pubkey = "test_pubkey_" + os.urandom(16).hex()
    test_privkey = "test_privkey_" + os.urandom(16).hex()
    
    # Create P2P network
    p2p = P2PNetwork(
        wg_public_key=test_pubkey,
        wg_private_key=test_privkey,
        vpn_ip="10.200.200.1"
    )
    
    # Set trust gate to auto-approve for demo
    p2p.trust_gate.set_auto_approve(True)
    
    try:
        # Start without bootstrap (single node for demo)
        await p2p.start(dht_port=8468, bootstrap_nodes=[])
        
        # Test STUN
        print("\n📡 Testing STUN discovery...")
        stun_result = await p2p.dht.stun_client.discover()
        if stun_result:
            print(f"   Public address: {stun_result['ip']}:{stun_result['port']}")
            print(f"   NAT type: {stun_result['nat_type']}")
        else:
            print("   STUN discovery failed (expected in some networks)")
            
        # Keep running
        print("\n⏳ P2P node running. Press Ctrl+C to stop.")
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("\n👋 Stopping...")
    finally:
        await p2p.stop()

if __name__ == "__main__":
    asyncio.run(demo())
