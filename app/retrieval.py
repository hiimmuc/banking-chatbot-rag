import numpy as np
from .config import RetrievalParams
from .embedding import Embedder, Reranker
from .metadata import chunk_label
from .store import Store
from .textnorm import fts_query


def fuse_rrf(*rankings: list[str], c: int = 60) -> list[str]:
    """Reciprocal rank fusion: ranks are comparable across BM25 and cosine, raw scores are not."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking, 1):
            scores[cid] = scores.get(cid, 0.0) + 1 / (c + rank)
    return sorted(scores, key=scores.get, reverse=True)


class HybridRetriever:
    """FTS5 top-k + dense top-k, fused by RRF, then reordered by a cross-encoder."""

    def __init__(self, store: Store, embedder: Embedder, reranker: Reranker, params: RetrievalParams):
        self._store, self._embedder, self._reranker, self._p = store, embedder, reranker, params

    def retrieve(self, question: str) -> list[dict]:
        fused = fuse_rrf(self._keyword(question), self._vector(question))[: self._p.rerank_top_k]
        found = self._store.get_chunks(fused)
        candidates = [found[i] for i in fused if i in found]
        if not candidates:
            return []
        return self.rank(question, candidates)[: self._p.context_top_k]

    def rank(self, question: str, chunks: list[dict]) -> list[dict]:
        """Score chunks against the question (adds `score`) and sort best first."""
        scores = self._reranker.score(question, [f"{chunk_label(c)}: {c['text']}" for c in chunks])
        for chunk, score in zip(chunks, scores):
            chunk["score"] = score
        return sorted(chunks, key=lambda c: c["score"], reverse=True)

    def _keyword(self, question: str) -> list[str]:
        match = fts_query(question)
        return self._store.keyword_search(match, self._p.keyword_top_k) if match else []

    def _vector(self, question: str) -> list[str]:
        ids, matrix = self._store.ready_embeddings()
        if not ids:
            return []
        sims = matrix @ self._embedder.encode([question])[0]
        return [ids[i] for i in np.argsort(-sims)[: self._p.vector_top_k]]
