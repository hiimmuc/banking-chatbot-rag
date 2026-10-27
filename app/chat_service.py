import logging
from dataclasses import dataclass
from typing import Iterator, Mapping
from .answer_guard import has_valid_citation, split_tag, unverified_numbers
from .llm import ChatError, ChatProvider
from .metadata import chunk_label
from .prompt import REWRITE, build_messages
from .retrieval import HybridRetriever
from .version_service import VersionService

log = logging.getLogger(__name__)
SAFE_ERROR = "Lỗi hệ thống khi xử lý câu hỏi"


@dataclass(frozen=True)
class ChatParams:
    provider: str
    model: str
    max_tokens: int
    temperature: float | None
    style: str


class TagSplitter:
    """Holds streamed text until the leading mode tag is complete, so the tag never reaches the client."""

    def __init__(self):
        self.full, self.mode = "", None

    def feed(self, text: str) -> tuple[str | None, str]:
        """(mode if it was just decided, text safe to emit)."""
        self.full += text
        if self.mode is not None:
            return None, text
        head = self.full.lstrip()
        if "]" in head or len(head) > 30 or (head and not head.startswith("[")):
            return self._decide()
        return None, ""

    def finish(self) -> tuple[str | None, str]:
        return (None, "") if self.mode is not None else self._decide()

    def _decide(self) -> tuple[str, str]:
        self.mode, rest = split_tag(self.full)
        return self.mode, rest


class ChatService:
    """Question in, ordered (event, payload) pairs out: sources, mode, delta*, verify*, done | error."""

    def __init__(self, retriever: HybridRetriever, providers: Mapping[str, ChatProvider], versions: VersionService):
        self._retriever, self._providers, self._versions = retriever, providers, versions

    def answer(self, question: str, history: list[dict], params: ChatParams) -> Iterator[tuple[str, dict]]:
        try:
            provider = self._providers[params.provider]
            query = self._standalone_query(provider, params, question, history)
            sources, labels, versions = self._versions.plan(query, self._retriever.retrieve(query))
            yield "sources", {"query": query, "versions": versions, "sources": [self._source_view(i, c) for i, c in enumerate(sources, 1)]}
            splitter, usage = TagSplitter(), {}
            messages = build_messages(question, history, sources, params.style, labels, versions)
            for ev in provider.stream(params.model, messages, params.max_tokens, params.temperature):
                if ev["type"] == "usage":
                    usage = {"inputTokens": ev["in"], "outputTokens": ev["out"]}
                else:
                    yield from self._emit(*splitter.feed(ev["text"]))
            yield from self._emit(*splitter.finish())
            yield from self._checks(splitter, sources)
            yield "done", {"usage": usage}
        except ChatError as e:
            yield "error", {"message": str(e)}
        except Exception:
            log.exception("chat failed")
            yield "error", {"message": SAFE_ERROR}

    def _standalone_query(self, provider: ChatProvider, params: ChatParams, question: str, history: list[dict]) -> str:
        if not history:
            return question
        try:
            messages = [{"role": "system", "content": REWRITE}, *history[-4:], {"role": "user", "content": question}]
            return provider.complete(params.model, messages, 120, 0).strip() or question
        except ChatError:
            return question

    @staticmethod
    def _emit(mode: str | None, text: str) -> Iterator[tuple[str, dict]]:
        if mode:
            yield "mode", {"mode": mode}
        if text:
            yield "delta", {"text": text}

    @staticmethod
    def _checks(splitter: TagSplitter, sources: list[dict]) -> Iterator[tuple[str, dict]]:
        if splitter.mode != "answer":
            return
        known = "\n".join(f"{chunk_label(c)} {c['text']}" for c in sources)  # headers carry the document number and issue date
        bad = unverified_numbers(split_tag(splitter.full)[1], known)
        if bad:
            yield "verify", {"unverified": bad}
        if not has_valid_citation(splitter.full, len(sources)):
            yield "verify", {"uncited": True}

    @staticmethod
    def _source_view(n: int, c: dict) -> dict:
        return {"id": f"S{n}", "chunkId": c["id"], "documentId": c["document_id"], "fileName": c["name"], "docNo": c["doc_no"],
                "issued": c["issued"], "score": round(c["score"], 2), "pageStart": c["page_start"], "pageEnd": c["page_end"],
                "excerpt": c["text"][:3000]}
