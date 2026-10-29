import logging
from dataclasses import dataclass
from typing import Iterator, Mapping
from .answer_guard import audit, split_tag, strip_placeholders
from .intent import IntentClassifier, label_of
from .llm import ChatError, ChatProvider
from .metadata import chunk_label
from .prompt import CLARIFY, REWRITE, RETRY, build_messages
from .retrieval import HybridRetriever
from .smalltalk import OUT_OF_SCOPE_REPLY
from .version_service import VersionService

log = logging.getLogger(__name__)
SAFE_ERROR = "Lỗi hệ thống khi xử lý câu hỏi"
FALLBACK_QUESTION = "Anh/chị cho em biết rõ hơn về sản phẩm, đối tượng, kỳ hạn hoặc số hiệu văn bản cần tra cứu được không ạ?"


@dataclass(frozen=True)
class ChatParams:
    provider: str
    model: str
    max_tokens: int
    temperature: float | None
    style: str
    doc_ids: frozenset[str] | None = None  # documents the user selected; None = all


class ChatService:
    """Question in, ordered (event, payload) pairs out: status*, sources?, mode, delta, done | error.

    An answer is held back until it passes the guard (valid citations, numbers found in the sources). A failing answer is
    retried once; if it still fails, the user gets the reason and one clarifying question instead of an unverified answer.
    """

    def __init__(self, retriever: HybridRetriever, providers: Mapping[str, ChatProvider], versions: VersionService, intent: IntentClassifier):
        self._retriever, self._providers, self._versions, self._intent = retriever, providers, versions, intent

    def answer(self, question: str, history: list[dict], params: ChatParams) -> Iterator[tuple[str, dict]]:
        try:
            yield from self._answer(question, history, params)
        except ChatError as e:
            yield "error", {"message": str(e)}
        except Exception:
            log.exception("chat failed")
            yield "error", {"message": SAFE_ERROR}

    def _answer(self, question: str, history: list[dict], params: ChatParams) -> Iterator[tuple[str, dict]]:
        intent = self._intent.classify(question, history)
        if intent.reply:
            yield from self._finish("chitchat", intent.reply)
            return
        provider = self._providers[params.provider]
        if intent.label == "vague":
            yield from self._finish("clarify", self._clarify(provider, params, question, [], None))
            return

        query = self._standalone_query(provider, params, question, history)
        sources, labels, versions = self._versions.plan(query, self._retriever.retrieve(query, params.doc_ids), params.doc_ids)
        messages = build_messages(question, history, sources, params.style, labels, versions)
        known = "\n".join(f"{chunk_label(c)} {c['text']}" for c in sources)  # headers carry the document number and issue date
        mode, text, usage, issues = self._generate(provider, params, messages, known, len(sources))
        if issues:
            yield "status", {"text": "Đang kiểm tra lại câu trả lời"}
            retry = [*messages, {"role": "assistant", "content": text}, {"role": "user", "content": RETRY.format(issues="; ".join(issues))}]
            mode, text, usage2, issues = self._generate(provider, params, retry, known, len(sources))
            usage = _add(usage, usage2)
        if mode == "offscope":
            yield from self._finish("offscope", OUT_OF_SCOPE_REPLY, usage)
            return
        if issues:
            log.info("answer rejected: %s", issues)
            if label_of(provider, params.model, question, history) == "out_of_scope":
                yield from self._finish("offscope", OUT_OF_SCOPE_REPLY, usage)
                return
            yield from self._finish("clarify", self._clarify(provider, params, question, sources, "; ".join(issues)), usage)
            return
        view = {"query": query, "versions": versions, "sources": [self._source_view(i, c) for i, c in enumerate(sources, 1)]}
        yield "sources", view
        yield from self._finish(mode, text, usage)

    def _generate(self, provider: ChatProvider, params: ChatParams, messages: list[dict], known: str, n_sources: int):
        """(mode, clean text, usage, issues). Only an answer is audited: clarify and insufficient make no claims."""
        raw, usage = "", {}
        for ev in provider.stream(params.model, messages, params.max_tokens, params.temperature):
            if ev["type"] == "usage":
                usage = {"inputTokens": ev["in"], "outputTokens": ev["out"]}
            else:
                raw += ev["text"]
        mode, text = split_tag(raw)
        text = strip_placeholders(text)
        issues = audit(text, known, n_sources) if mode == "answer" else []
        if not text and mode != "offscope":
            issues = ["câu trả lời rỗng"]
        return mode, text, usage, issues

    def _clarify(self, provider: ChatProvider, params: ChatParams, question: str, sources: list[dict], reason: str | None) -> str:
        hints = "; ".join(dict.fromkeys(chunk_label(c) for c in sources[:4]))
        user = f"CÂU HỎI: {question}\nVĂN BẢN GẦN NHẤT: {hints or '(không có)'}\nLÝ DO CHƯA TRẢ LỜI ĐƯỢC: {reason or 'câu hỏi còn chung chung'}"
        try:
            ask = strip_placeholders(provider.complete(params.model, [{"role": "system", "content": CLARIFY}, {"role": "user", "content": user}], 120, 0.2)).strip()
        except ChatError:
            ask = ""
        ask = ask if 0 < len(ask) <= 300 and "?" in ask else FALLBACK_QUESTION
        intro = f"Em chưa tìm được căn cứ đủ chắc để trả lời ({reason})." if reason else "Câu hỏi còn khá chung nên em cần làm rõ thêm."
        return f"{intro} Để tra cứu chính xác, {ask[0].lower() + ask[1:]}"

    def _standalone_query(self, provider: ChatProvider, params: ChatParams, question: str, history: list[dict]) -> str:
        if not history:
            return question
        try:
            messages = [{"role": "system", "content": REWRITE}, *history[-4:], {"role": "user", "content": question}]
            return provider.complete(params.model, messages, 120, 0).strip() or question
        except ChatError:
            return question

    @staticmethod
    def _finish(mode: str, text: str, usage: dict | None = None) -> Iterator[tuple[str, dict]]:
        yield "mode", {"mode": mode}
        yield "delta", {"text": text}
        yield "done", {"usage": usage or {}}

    @staticmethod
    def _source_view(n: int, c: dict) -> dict:
        return {"id": f"S{n}", "chunkId": c["id"], "documentId": c["document_id"], "fileName": c["name"], "docNo": c["doc_no"],
                "issued": c["issued"], "score": round(c["score"], 2), "pageStart": c["page_start"], "pageEnd": c["page_end"],
                "excerpt": c["text"][:3000]}


def _add(a: dict, b: dict) -> dict:
    return {k: a.get(k, 0) + b.get(k, 0) for k in {*a, *b}}
