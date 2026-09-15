#!/usr/bin/env python3
"""
Luna SGP Blockchain Verification - Production Implementation
============================================================

基于 v2.5 设计的生产级区块链验证功能
集成到现有 yuehen_memory.db

Author: Luna SGP + Gemma
Date: 2026-08-23
"""

import hashlib
import json
import time
import sqlite3
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List, Tuple, Union
from pathlib import Path
from datetime import datetime
import threading

# 可选依赖
import numpy as np

try:
    import msgpack
    MSGPACK_AVAILABLE = True
except ImportError:
    MSGPACK_AVAILABLE = False
    import pickle as msgpack


# =============================================================================
# 第一部分: 区块数据结构
# =============================================================================

@dataclass
class StateBlock:
    """
    状态区块 - 通用区块头
    兼容现有 yuehen_memory.db 结构
    """
    # 基础字段 (兼容现有表)
    id: str  # 对应 memory.id
    content: str  # 对应 memory.content
    version: int = 1  # 对应 memory.version
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    entity_type: str = "transient"  # 对应 memory.entity_type
    volatility_level: Optional[str] = None
    saliency: float = 0.5
    metadata: Optional[str] = None
    
    # 区块链新增字段
    block_id: int = 0
    timestamp: float = field(default_factory=time.time)
    layer_type: str = "L2"  # "L1" | "L2" | "L3" | "L4"
    
    # 链式验证
    prev_hash: str = "0" * 64  # 创世区块前哈希
    data_hash: str = ""
    merkle_root: Optional[str] = None
    
    # 区块头哈希 (整个区块的指纹)
    block_hash: str = ""
    
    def __post_init__(self):
        if not self.data_hash:
            self.data_hash = self._compute_data_hash()
        if not self.block_hash:
            self.block_hash = self._compute_block_hash()
    
    def _compute_data_hash(self) -> str:
        """计算内容哈希"""
        content_str = f"{self.id}:{self.content}:{self.version}:{self.updated_at}"
        return hashlib.sha256(content_str.encode()).hexdigest()
    
    def _compute_block_hash(self) -> str:
        """计算区块头哈希"""
        header = {
            "block_id": self.block_id,
            "timestamp": self.timestamp,
            "layer_type": self.layer_type,
            "prev_hash": self.prev_hash,
            "data_hash": self.data_hash,
            "merkle_root": self.merkle_root,
            "id": self.id,
            "version": self.version
        }
        return hashlib.sha256(
            json.dumps(header, sort_keys=True).encode()
        ).hexdigest()
    
    def to_db_dict(self) -> Dict[str, Any]:
        """转换为数据库存储格式"""
        return {
            # 现有字段
            "id": self.id,
            "content": self.content,
            "version": self.version,
            "updated_at": self.updated_at,
            "entity_type": self.entity_type,
            "volatility_level": self.volatility_level,
            "saliency": self.saliency,
            "metadata": self._pack_metadata(),
            # 新增区块链字段 (存储在metadata中)
        }
    
    def _pack_metadata(self) -> str:
        """将区块链字段打包到 metadata JSON"""
        meta = {
            "block_id": self.block_id,
            "timestamp": self.timestamp,
            "layer_type": self.layer_type,
            "prev_hash": self.prev_hash,
            "data_hash": self.data_hash,
            "merkle_root": self.merkle_root,
            "block_hash": self.block_hash,
            "original_metadata": self.metadata
        }
        return json.dumps(meta, ensure_ascii=False)
    
    @classmethod
    def from_db_row(cls, row: Tuple) -> 'StateBlock':
        """从数据库行创建 StateBlock"""
        # 解析现有字段
        id_, content, version, updated_at, entity_type, volatility, saliency, metadata = row
        
        # 解析 metadata 中的区块链字段
        block_id = 0
        timestamp = time.time()
        layer_type = "L2"
        prev_hash = "0" * 64
        data_hash = ""
        merkle_root = None
        block_hash = ""
        original_metadata = metadata
        
        if metadata:
            try:
                meta = json.loads(metadata)
                if "block_id" in meta:
                    block_id = meta.get("block_id", 0)
                    timestamp = meta.get("timestamp", time.time())
                    layer_type = meta.get("layer_type", "L2")
                    prev_hash = meta.get("prev_hash", "0" * 64)
                    data_hash = meta.get("data_hash", "")
                    merkle_root = meta.get("merkle_root")
                    block_hash = meta.get("block_hash", "")
                    original_metadata = meta.get("original_metadata", metadata)
            except json.JSONDecodeError:
                pass
        
        return cls(
            id=id_,
            content=content,
            version=version,
            updated_at=updated_at,
            entity_type=entity_type or "transient",
            volatility_level=volatility,
            saliency=saliency or 0.5,
            metadata=original_metadata,
            block_id=block_id,
            timestamp=timestamp,
            layer_type=layer_type,
            prev_hash=prev_hash,
            data_hash=data_hash,
            merkle_root=merkle_root,
            block_hash=block_hash
        )


# =============================================================================
# 第二部分: 区块链管理器
# =============================================================================

class BlockchainManager:
    """
    区块链管理器 - 管理 Luna SGP 的哈希链
    """
    
    def __init__(self, db_path: str = "~/.openclaw/yuehen_memory.db"):
        self.db_path = Path(db_path).expanduser()
        self._lock = threading.RLock()
        self._last_block_hash: Optional[str] = None
        self._last_block_id: int = 0
        self._init_blockchain()
    
    def _init_blockchain(self):
        """初始化区块链状态"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 检查是否有区块链字段
            cursor.execute("PRAGMA table_info(memory)")
            columns = [c[1] for c in cursor.fetchall()]
            
            # 获取最新区块
            cursor.execute("""
                SELECT id, content, version, updated_at, entity_type, 
                       volatility_level, saliency, metadata
                FROM memory
                WHERE metadata LIKE '%block_hash%'
                ORDER BY json_extract(metadata, '$.block_id') DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            
            if row:
                block = StateBlock.from_db_row(row)
                self._last_block_hash = block.block_hash
                self._last_block_id = block.block_id
            else:
                # 没有区块链记录，从现有数据计算
                cursor.execute("SELECT COUNT(*) FROM memory")
                count = cursor.fetchone()[0]
                self._last_block_id = count
                self._last_block_hash = self._compute_genesis_hash()
    
    def _compute_genesis_hash(self) -> str:
        """计算创世哈希"""
        genesis = {
            "timestamp": 0,
            "message": "Luna SGP Genesis Block",
            "version": "2.5"
        }
        return hashlib.sha256(json.dumps(genesis).encode()).hexdigest()
    
    def create_block(
        self,
        id: str,
        content: str,
        entity_type: str = "transient",
        layer_type: str = "L2",
        saliency: float = 0.5,
        metadata: Optional[str] = None
    ) -> StateBlock:
        """创建新区块"""
        with self._lock:
            self._last_block_id += 1
            
            block = StateBlock(
                id=id,
                content=content,
                version=1,
                updated_at=datetime.now().isoformat(),
                entity_type=entity_type,
                layer_type=layer_type,
                saliency=saliency,
                metadata=metadata,
                block_id=self._last_block_id,
                prev_hash=self._last_block_hash
            )
            
            # 更新链状态
            self._last_block_hash = block.block_hash
            
            return block
    
    def verify_chain(self) -> Tuple[bool, List[str]]:
        """验证整个区块链的完整性"""
        errors = []
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 获取所有带区块链标记的记录
            cursor.execute("""
                SELECT id, content, version, updated_at, entity_type, 
                       volatility_level, saliency, metadata
                FROM memory
                WHERE metadata LIKE '%block_hash%'
                ORDER BY json_extract(metadata, '$.block_id') ASC
            """)
            
            rows = cursor.fetchall()
            if not rows:
                return True, ["No blockchain records found"]
            
            prev_hash = self._compute_genesis_hash()
            
            for i, row in enumerate(rows):
                block = StateBlock.from_db_row(row)
                
                # 验证区块ID连续性
                if block.block_id != i + 1:
                    errors.append(f"Block {block.id}: ID mismatch (expected {i+1}, got {block.block_id})")
                
                # 验证前哈希
                if block.prev_hash != prev_hash:
                    errors.append(f"Block {block.id}: Prev hash mismatch")
                
                # 验证数据哈希
                expected_data_hash = block._compute_data_hash()
                if block.data_hash != expected_data_hash:
                    errors.append(f"Block {block.id}: Data hash corrupted")
                
                # 验证区块哈希
                expected_block_hash = block._compute_block_hash()
                if block.block_hash != expected_block_hash:
                    errors.append(f"Block {block.id}: Block hash corrupted")
                
                prev_hash = block.block_hash
        
        return len(errors) == 0, errors
    
    def save_block(self, block: StateBlock) -> bool:
        """保存区块到数据库"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                data = block.to_db_dict()
                
                cursor.execute("""
                    INSERT OR REPLACE INTO memory 
                    (id, content, version, updated_at, entity_type, 
                     volatility_level, saliency, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    data["id"],
                    data["content"],
                    data["version"],
                    data["updated_at"],
                    data["entity_type"],
                    data["volatility_level"],
                    data["saliency"],
                    data["metadata"]
                ))
                
                conn.commit()
                return True
        except Exception as e:
            print(f"Error saving block: {e}")
            return False


# =============================================================================
# 第三部分: 与现有系统集成
# =============================================================================

class LunaSGPBlockchain:
    """
    Luna SGP 区块链集成类
    提供与现有 yuehen_autostart 的兼容接口
    """
    
    _instance: Optional['LunaSGPBlockchain'] = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, db_path: str = "~/.openclaw/yuehen_memory.db"):
        if hasattr(self, '_initialized'):
            return
        
        self.manager = BlockchainManager(db_path)
        self._initialized = True
    
    def 记录记忆(
        self,
        content: str,
        entity_type: str = "transient",
        layer_type: str = "L2",
        saliency: float = 0.5,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        记录记忆并创建区块链区块
        
        返回: 记忆ID
        """
        # 生成ID
        memory_id = f"mem_{int(time.time() * 1000)}_{hashlib.sha256(content.encode()).hexdigest()[:8]}"
        
        # 创建区块
        meta_str = json.dumps(metadata, ensure_ascii=False) if metadata else None
        
        block = self.manager.create_block(
            id=memory_id,
            content=content,
            entity_type=entity_type,
            layer_type=layer_type,
            saliency=saliency,
            metadata=meta_str
        )
        
        # 保存
        if self.manager.save_block(block):
            print(f"📝 记忆已记录: {memory_id}")
            print(f"   区块ID: {block.block_id}")
            print(f"   区块哈希: {block.block_hash[:16]}...")
            return memory_id
        else:
            raise RuntimeError("Failed to save memory block")
    
    def 验证链(self) -> Tuple[bool, List[str]]:
        """验证区块链完整性"""
        return self.manager.verify_chain()
    
    def 获取链状态(self) -> Dict[str, Any]:
        """获取区块链状态"""
        return {
            "last_block_id": self.manager._last_block_id,
            "last_block_hash": self.manager._last_block_hash[:16] + "..." if self.manager._last_block_hash else None,
            "db_path": str(self.manager.db_path)
        }


# =============================================================================
# 第四部分: 迁移工具
# =============================================================================

def migrate_existing_memories(db_path: str = "~/.openclaw/yuehen_memory.db") -> int:
    """
    将现有记忆迁移到区块链结构
    
    返回: 迁移的记录数
    """
    db_path = Path(db_path).expanduser()
    manager = BlockchainManager(db_path)
    
    migrated = 0
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # 获取没有区块链标记的记录
        cursor.execute("""
            SELECT id, content, version, updated_at, entity_type, 
                   volatility_level, saliency, metadata
            FROM memory
            WHERE metadata IS NULL OR metadata NOT LIKE '%block_hash%'
            ORDER BY updated_at ASC
        """)
        
        rows = cursor.fetchall()
        
        print(f"发现 {len(rows)} 条需要迁移的记录")
        
        for row in rows:
            # 创建区块
            block = manager.create_block(
                id=row[0],
                content=row[1],
                entity_type=row[4] or "transient",
                layer_type="L2",  # 默认几何层
                saliency=row[6] or 0.5,
                metadata=row[7]
            )
            
            # 保存
            if manager.save_block(block):
                migrated += 1
                if migrated % 100 == 0:
                    print(f"已迁移 {migrated}/{len(rows)} 条记录...")
        
        print(f"✅ 迁移完成: {migrated} 条记录")
    
    return migrated


# =============================================================================
# 第五部分: 测试
# =============================================================================

def test_blockchain():
    """测试区块链功能"""
    print("=" * 60)
    print("Luna SGP 区块链功能测试")
    print("=" * 60)
    
    # 初始化
    sgp = LunaSGPBlockchain()
    
    # 显示状态
    print("\n📊 链状态:")
    state = sgp.获取链状态()
    for k, v in state.items():
        print(f"   {k}: {v}")
    
    # 记录测试记忆
    print("\n📝 记录测试记忆...")
    mem_id = sgp.记录记忆(
        content="测试记忆内容",
        entity_type="test",
        layer_type="L2",
        saliency=0.8,
        metadata={"test": True}
    )
    
    # 验证链
    print("\n🔍 验证区块链...")
    is_valid, errors = sgp.验证链()
    
    if is_valid:
        print("✅ 区块链验证通过")
    else:
        print("❌ 区块链验证失败:")
        for err in errors:
            print(f"   - {err}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    test_blockchain()
