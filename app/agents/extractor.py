import asyncio
import numpy as np
from app.agents.base import BaseAgent
from app.config import settings


class ExtractorAgent(BaseAgent):
    def __init__(self, embedder):
        super().__init__("ExtractorAgent")
        self.embedder = embedder

    async def run(self, query: str, passages: list[dict], queue: asyncio.Queue) -> list[dict]:
        await self.emit(queue, "EXTRACTING", f"Ranking {len(passages)} passages by semantic relevance")

        if not passages:
            await self.emit(queue, "EXTRACTING", "No passages to rank")
            return []

        texts = [p["text"] for p in passages]

        query_embedding, passage_embeddings = await asyncio.gather(
            asyncio.to_thread(self.embedder.encode, [query]),
            asyncio.to_thread(self.embedder.encode, texts),
        )

        query_vec = query_embedding[0]
        similarities = []
        for i, pv in enumerate(passage_embeddings):
            sim = float(np.dot(query_vec, pv) / (np.linalg.norm(query_vec) * np.linalg.norm(pv) + 1e-9))
            similarities.append(sim)

        ranked = sorted(
            [{"similarity": sim, **passages[i]} for i, sim in enumerate(similarities)],
            key=lambda x: x["similarity"],
            reverse=True,
        )

        # Drop passages below minimum similarity threshold — removes junk results
        MIN_SIMILARITY = 0.15
        ranked = [p for p in ranked if p["similarity"] >= MIN_SIMILARITY]

        top_k = ranked[:settings.top_k_passages]
        await self.emit(
            queue, "EXTRACTING",
            f"Selected top {len(top_k)} passages (avg similarity: {np.mean([p['similarity'] for p in top_k]):.3f})",
            {"top_k": len(top_k), "avg_similarity": float(np.mean([p["similarity"] for p in top_k]))},
        )
        return top_k
