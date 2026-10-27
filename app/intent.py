import logging
from dataclasses import dataclass
from . import config
from .config import Provider
from .llm import ChatError, ChatProvider, OpenAICompatProvider
from .prompt import INTENT
from .smalltalk import OUT_OF_SCOPE_REPLY, about, smalltalk

log = logging.getLogger(__name__)
LABELS = ("chitchat", "out_of_scope", "vague", "domain")


@dataclass(frozen=True)
class Intent:
    label: str
    reply: str | None = None


def label_of(client: ChatProvider, model: str, question: str, history: list[dict]) -> str:
    """One of LABELS; 'domain' when the model fails or answers something else, so retrieval still runs."""
    try:
        out = client.complete(model, [{"role": "system", "content": INTENT}, *history[-2:], {"role": "user", "content": question}], 8, 0)
    except ChatError:
        log.warning("intent model failed, falling back to domain")
        return "domain"
    return next((w for w in LABELS if w in out.lower()), "domain")


class IntentClassifier:
    """Fixed rules first; then an optional small model (INTENT_*) labels the question. Any failure means 'domain', so retrieval still runs."""

    def __init__(self, client: ChatProvider | None = None, model: str | None = None):
        self._client, self._model = client, model

    @classmethod
    def from_config(cls) -> "IntentClassifier":
        if not (config.INTENT_BASE_URL and config.INTENT_MODEL):
            return cls()
        cfg = Provider("intent", "intent", config.INTENT_BASE_URL, config.INTENT_API_KEY, (config.INTENT_MODEL,),
                       extra_body={"chat_template_kwargs": {"enable_thinking": False}}, needs_key=False)
        return cls(OpenAICompatProvider(cfg), config.INTENT_MODEL)

    def classify(self, question: str, history: list[dict]) -> Intent:
        reply = smalltalk(question)
        if reply:
            return Intent("chitchat", reply)
        if not self._client:
            return Intent("domain")
        label = label_of(self._client, self._model, question, history)
        return Intent(label, {"chitchat": about(), "out_of_scope": OUT_OF_SCOPE_REPLY}.get(label))
