# backend/core/rag/faiss_store.py
import json
import os
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple

import numpy as np
import faiss


@dataclass
class RetrievedChunk:
    text: str
    score: float
    meta: Dict[str, Any]


class FaissStore:
    """
    索引文件：faiss.index
    元数据：meta.json  (与 index 向量顺序一一对应)
    """
    def __init__(self, index_path: str, meta_path: str):
        self.index_path = index_path
        self.meta_path = meta_path
        self.index: Optional[faiss.Index] = None
        self.meta: List[Dict[str, Any]] = []

    def exists(self) -> bool:
        return os.path.exists(self.index_path) and os.path.exists(self.meta_path)

    def load(self):
        if not self.exists():
            raise FileNotFoundError("FAISS index or meta not found.")
        self.index = faiss.read_index(self.index_path)
        with open(self.meta_path, "r", encoding="utf-8") as f:
            self.meta = json.load(f)

    def save(self):
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        if self.index is None:
            raise ValueError("index is None")
        faiss.write_index(self.index, self.index_path)
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(self.meta, f, ensure_ascii=False, indent=2)

    def build(self, embeddings: np.ndarray, meta: List[Dict[str, Any]]):
        """
        embeddings: (N, D) float32, 已归一化
        使用 IndexFlatIP 做内积检索（等价余弦相似）
        """
        if embeddings.ndim != 2:
            raise ValueError("embeddings must be 2D array")
        n, d = embeddings.shape
        index = faiss.IndexFlatIP(d)
        index.add(embeddings)
        self.index = index
        self.meta = meta

    def search(self, query_emb: np.ndarray, top_k: int = 5) -> List[Tuple[int, float]]:
        if self.index is None:
            raise ValueError("index not loaded")
        if query_emb.ndim == 1:
            query_emb = query_emb.reshape(1, -1)
        scores, ids = self.index.search(query_emb.astype(np.float32), top_k)
        results = []
        for i, s in zip(ids[0].tolist(), scores[0].tolist()):
            if i == -1:
                continue
            results.append((i, float(s)))
        return results

    def fetch(self, ids_scores: List[Tuple[int, float]]) -> List[RetrievedChunk]:
        out: List[RetrievedChunk] = []
        for idx, score in ids_scores:
            m = self.meta[idx]
            out.append(RetrievedChunk(
                text=m["text"],
                score=score,
                meta={k: v for k, v in m.items() if k != "text"},
            ))
        return out