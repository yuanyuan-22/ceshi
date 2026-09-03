# backend/core/rag/pipeline.py
from typing import Dict, Any, List
from backend.core.embeddings.embedder import Embedder
from backend.core.rag.faiss_store import FaissStore, RetrievedChunk

class RAGPipeline:
    def __init__(
        self,
        embedder: Embedder,
        store: FaissStore,
    ):
        self.embedder = embedder
        self.store = store

    def retrieve(self, query: str, top_k: int = 5) -> List[RetrievedChunk]:
        q_emb = self.embedder.embed([query], batch_size=1)[0]
        ids_scores = self.store.search(q_emb, top_k=top_k)
        return self.store.fetch(ids_scores)

    def build_context(self, chunks: List[RetrievedChunk], max_chars: int = 2500) -> str:
        """
        将 chunks 拼成带引用编号的 context，便于前端展示“溯源”
        """
        parts = []
        total = 0
        for i, ch in enumerate(chunks, start=1):
            src = ch.meta.get("source", "unknown")
            page = ch.meta.get("page", None)
            loc = f"{src}" + (f" p{page}" if page is not None else "")
            block = f"[{i}] ({loc})\n{ch.text}\n"
            if total + len(block) > max_chars:
                break
            parts.append(block)
            total += len(block)
        return "\n".join(parts).strip()

    def answer(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        chunks = self.retrieve(query, top_k=top_k)
        context = self.build_context(chunks)

        # 生成答案：先不强绑定大模型，保持可替换
        # 你可以接入 core/llm/qa_generator.py 的 generate(context, query) 方法
        answer = "（当前演示：已完成检索与溯源，生成模型可后续替换/微调）"

        citations = []
        for i, ch in enumerate(chunks, start=1):
            citations.append({
                "id": i,
                "score": ch.score,
                "source": ch.meta.get("source", "unknown"),
                "chunk_id": ch.meta.get("chunk_id"),
            })

        return {
            "query": query,
            "answer": answer,
            "context": context,
            "citations": citations,
        }