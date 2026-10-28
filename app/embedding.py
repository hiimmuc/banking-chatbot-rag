import threading
import numpy as np
from .config import DEVICE, EMBED_MODEL, RERANK_MODEL

_FP16 = {"torch_dtype": "float16"} if DEVICE in ("cuda", "mps") else {}


def _shrinking_batches(run):
    """GPU is shared with other services: on CUDA OOM free the cache and retry with a smaller batch before giving up."""
    import torch
    for size in (8, 4, 2, 1):
        try:
            return run(size)
        except torch.OutOfMemoryError:
            torch.cuda.empty_cache()
    return run(1)


class Embedder:
    """Lazy-loaded multilingual dense embedder (unit-norm vectors)."""

    def __init__(self, model_name: str = EMBED_MODEL):
        self._name, self._model, self._lock = model_name, None, threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self._name, device=DEVICE, model_kwargs=_FP16)
                self._model.max_seq_length = 1024
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        model = self._load()
        return _shrinking_batches(lambda n: model.encode(texts, batch_size=n, normalize_embeddings=True, convert_to_numpy=True)).astype("float32")


class Reranker:
    """Lazy-loaded cross-encoder. Scores are sigmoid-squashed, so use them for ordering only."""

    def __init__(self, model_name: str = RERANK_MODEL):
        self._name, self._model, self._lock = model_name, None, threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(self._name, device=DEVICE, max_length=1024, model_kwargs=_FP16)
        return self._model

    def score(self, query: str, texts: list[str]) -> list[float]:
        model, pairs = self._load(), [(query, t) for t in texts]
        return [float(s) for s in _shrinking_batches(lambda n: model.predict(pairs, batch_size=n))]
