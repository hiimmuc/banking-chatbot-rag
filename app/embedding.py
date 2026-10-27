import threading
import numpy as np
from .config import DEVICE, EMBED_MODEL, RERANK_MODEL

_FP16 = {"torch_dtype": "float16"} if DEVICE == "cuda" else {}


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
        return self._load().encode(texts, batch_size=8, normalize_embeddings=True, convert_to_numpy=True).astype("float32")


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
        return [float(s) for s in self._load().predict([(query, t) for t in texts], batch_size=8)]
