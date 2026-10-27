from dataclasses import dataclass
from functools import lru_cache
from . import config
from .chat_service import ChatService
from .embedding import Embedder, Reranker
from .extract import OcrRunner
from .ingest import IngestService
from .llm import OpenAICompatProvider
from .retrieval import HybridRetriever
from .store import Store
from .version_service import VersionService


@dataclass(frozen=True)
class Container:
    store: Store
    ingest: IngestService
    retriever: HybridRetriever
    chat: ChatService


@lru_cache
def get_container() -> Container:
    """Composition root: the only place concrete classes are wired together."""
    store, embedder = Store(config.DB_PATH), Embedder()
    retriever = HybridRetriever(store, embedder, Reranker(), config.RETRIEVAL)
    providers = {key: OpenAICompatProvider(cfg) for key, cfg in config.PROVIDERS.items()}
    versions = VersionService(store, retriever, config.RETRIEVAL.context_top_k)
    return Container(store, IngestService(store, embedder, OcrRunner()), retriever, ChatService(retriever, providers, versions))
