"""
Luna SGP Memory Store v4.2+
FAISS + NetworkX 图增强索引，支持自我增强
"""
import os, json, time, pickle
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import faiss
import networkx as nx

DATA_DIR = Path("/Users/miaoliwang/.openclaw/workspace/luna_pipeline/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

FAISS_PATH = DATA_DIR / "memory.faiss"
META_PATH = DATA_DIR / "memory.jsonl"
GRAPH_PATH = DATA_DIR / "memory.graph.pkl"

class MemoryStore:
    def __init__(self, dim: int = 768):
        self.dim = dim
        self._index: Optional[faiss.Index] = None
        self._meta: List[Dict[str, Any]] = []
        self._graph = nx.Graph()
        self._id2idx: Dict[str, int] = {}
        self._load()

    def _load(self):
        if FAISS_PATH.exists():
            self._index = faiss.read_index(str(FAISS_PATH))
            print(f"[MemoryStore] FAISS loaded: {self._index.ntotal} vectors")
        else:
            self._index = faiss.IndexFlatIP(self.dim)  # inner product = cosine for normalized
            print("[MemoryStore] FAISS new")
        if META_PATH.exists():
            with open(META_PATH, 'r', encoding='utf-8') as f:
                self._meta = [json.loads(line) for line in f if line.strip()]
            self._id2idx = {m['id']: i for i, m in enumerate(self._meta)}
        if GRAPH_PATH.exists():
            with open(GRAPH_PATH, 'rb') as f:
                self._graph = pickle.load(f)
            print(f"[MemoryStore] Graph loaded: {self._graph.number_of_nodes()} nodes, {self._graph.number_of_edges()} edges")
        else:
            print("[MemoryStore] Graph new")

    def _save(self):
        faiss.write_index(self._index, str(FAISS_PATH))
        with open(META_PATH, 'w', encoding='utf-8') as f:
            for m in self._meta:
                f.write(json.dumps(m, ensure_ascii=False) + '\n')
        with open(GRAPH_PATH, 'wb') as f:
            pickle.dump(self._graph, f)

    def add(self, article_id: str, embedding: np.ndarray, title: str,
            entities: List[str], facts: List[str], timestamp: Optional[float] = None):
        if article_id in self._id2idx:
            return  # dedup
        ts = timestamp or time.time()
        vec = np.array(embedding, dtype=np.float32).reshape(1, -1)
        # normalize for cosine similarity
        faiss.normalize_L2(vec)
        self._index.add(vec)
        idx = len(self._meta)
        self._meta.append({
            'id': article_id, 'title': title, 'entities': entities,
            'facts': facts, 'timestamp': ts, 'idx': idx
        })
        self._id2idx[article_id] = idx
        # graph node
        self._graph.add_node(article_id, title=title, entities=entities, timestamp=ts)
        # connect by shared entities (weight = Jaccard-like)
        for other_id, other in [(m['id'], m) for m in self._meta[:-1]]:
            shared = set(entities) & set(other.get('entities', []))
            if shared:
                weight = len(shared) / max(len(entities), len(other.get('entities', [])), 1)
                self._graph.add_edge(article_id, other_id, weight=weight, shared=list(shared))
        self._save()
        print(f"[MemoryStore] Added {article_id}: {title[:40]}... | graph now {self._graph.number_of_nodes()} nodes")

    def search(self, embedding: np.ndarray, k: int = 5) -> List[Dict[str, Any]]:
        if self._index.ntotal == 0:
            return []
        vec = np.array(embedding, dtype=np.float32).reshape(1, -1)
        faiss.normalize_L2(vec)
        D, I = self._index.search(vec, min(k, self._index.ntotal))
        results = []
        for score, idx in zip(D[0], I[0]):
            if idx < 0 or idx >= len(self._meta):
                continue
            m = self._meta[idx].copy()
            m['similarity'] = float(score)
            results.append(m)
        return results

    def remove(self, article_id: str) -> bool:
        """删除指定 id 的记忆条目（同 id 重跑前清理，避免检索到自指）。

        IndexFlatIP 不支持按 id 删除，用 reconstruct 逐条取留存向量重建索引。
        不存在则返回 False 且不改动任何状态。
        """
        if article_id not in self._id2idx:
            return False
        keep_meta = [m for m in self._meta if m['id'] != article_id]
        dim = self._index.d if self._index is not None else self.dim
        new_index = faiss.IndexFlatIP(dim)
        if keep_meta:
            vecs = np.zeros((len(keep_meta), dim), dtype=np.float32)
            for i, m in enumerate(keep_meta):
                vecs[i] = self._index.reconstruct(int(m['idx']))
            new_index.add(vecs)
        self._index = new_index
        # 重编号剩余条目 idx 与 _id2idx
        for i, m in enumerate(keep_meta):
            m['idx'] = i
        self._meta = keep_meta
        self._id2idx = {m['id']: i for i, m in enumerate(keep_meta)}
        # 图：删节点及其边
        if self._graph is not None and article_id in self._graph:
            self._graph.remove_node(article_id)
        self._save()
        print(f"[MemoryStore] Removed {article_id} | now {len(self._meta)} articles, "
              f"{self._index.ntotal} vectors, graph {self._graph.number_of_nodes()} nodes")
        return True

    def graph_neighbors_by_entities(self, entities: List[str], k: int = 3,
                                    exclude_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """以「当前文章自己抽出的实体」为准找图邻居。

        与 graph_neighbors 不同：不依赖 FAISS 首条命中（可能完全不相关），
        而是遍历全图节点、按与当前实体的共享实体数（Jaccard 权重）排序，
        零共享项直接剔除。返回最多 k 条，含 edge_shared / edge_weight。
        exclude_id: 排除自身（与旧 graph_neighbors 的 discard(article_id) 行为对齐，防止自指）。
        """
        if not entities:
            return []
        cur = set(e for e in entities if e)
        if not cur:
            return []
        results: List[Dict[str, Any]] = []
        for nid, data in self._graph.nodes(data=True):
            if exclude_id is not None and nid == exclude_id:
                continue
            node_ents = set(data.get('entities') or [])
            shared = cur & node_ents
            if not shared:            # 零共享 → 剔除（修掉"软银扩出伊朗/美国"）
                continue
            weight = len(shared) / max(len(cur), len(node_ents), 1)
            item = dict(data)
            item['id'] = nid
            item['edge_weight'] = weight
            item['edge_shared'] = sorted(shared)
            results.append(item)
        results.sort(key=lambda x: (-x.get('edge_weight', 0), -len(x.get('edge_shared', []))))
        return results[:k]

    def graph_neighbors(self, article_id: str, depth: int = 1) -> List[Dict[str, Any]]:
        if article_id not in self._graph:
            return []
        nodes = set([article_id])
        for _ in range(depth):
            frontier = set()
            for n in nodes:
                frontier.update(self._graph.neighbors(n))
            nodes |= frontier
        nodes.discard(article_id)
        results = []
        for nid in nodes:
            data = dict(self._graph.nodes[nid])
            edges = self._graph[article_id][nid] if article_id in self._graph and self._graph.has_edge(article_id, nid) else {}
            data['edge_weight'] = edges.get('weight', 0)
            data['edge_shared'] = edges.get('shared', [])
            results.append(data)
        return sorted(results, key=lambda x: -x.get('edge_weight', 0))

    def get_stats(self) -> Dict[str, Any]:
        return {
            'faiss_vectors': self._index.ntotal if self._index else 0,
            'graph_nodes': self._graph.number_of_nodes(),
            'graph_edges': self._graph.number_of_edges(),
            'articles': len(self._meta)
        }
