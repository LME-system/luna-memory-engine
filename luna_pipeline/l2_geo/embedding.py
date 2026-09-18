"""L2 嵌入底座 — ollama nomic-embed-text (768d)。
Dual-Embedding 的欧氏侧来源。
"""
from __future__ import annotations
import json, urllib.request, os

OLLAMA_EMBED = os.getenv("OLLAMA_EMBED", "http://localhost:11434/api/embed")
MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")


def embed(texts, timeout: int = 120):
    """返回 List[List[float]] (768d)。"""
    if isinstance(texts, str):
        texts = [texts]
    payload = {"model": MODEL, "input": texts}
    req = urllib.request.Request(OLLAMA_EMBED, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode())
    return d.get("embeddings", [])
