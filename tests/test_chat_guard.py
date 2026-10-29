import json
import pytest
from app.chat_service import ChatParams, ChatService
from app.intent import IntentClassifier
from app.llm import ChatError
from app.providers import EndpointError, ProviderRegistry, normalize_url

SRC = {"id": "c1", "document_id": "d1", "name": "a.pdf", "doc_no": "66/NHNo", "issued": "01/01/2024", "score": 0.9,
       "page_start": 1, "page_end": 1, "text": "Lãi suất ưu đãi là 6%/năm."}
PARAMS = ChatParams("p", "m", 500, 0, "concise")


class Retriever:
    def retrieve(self, q, doc_ids=None): return [SRC]


class Versions:
    def plan(self, q, sources, doc_ids=None): return sources, [""] * len(sources), []


class Fake:
    """Streams scripted answers one per call; complete() returns the scripted clarifying question."""
    def __init__(self, answers, ask="Anh/chị hỏi về kỳ hạn nào ạ?"):
        self.answers, self.ask, self.calls = list(answers), ask, 0

    def stream(self, model, messages, max_tokens, temperature):
        self.calls += 1
        yield {"type": "delta", "text": self.answers.pop(0)}

    def complete(self, model, messages, max_tokens=120, temperature=0):
        if self.ask is None:
            raise ChatError("x")
        return self.ask


def run(provider, question="Lãi suất ưu đãi?", intent=None):
    svc = ChatService(Retriever(), {"p": provider}, Versions(), intent or IntentClassifier())
    return list(svc.answer(question, [], PARAMS))


def kinds(events):
    return [e for e, _ in events]


def text(events):
    return "".join(d["text"] for e, d in events if e == "delta")


def test_good_answer_passes_and_placeholder_is_stripped():
    ev = run(Fake(["[TRẢ_LỜI] <kết luận> Lãi suất ưu đãi là 6%/năm [S1]."]))
    assert kinds(ev) == ["sources", "mode", "delta", "done"]
    assert "<" not in text(ev) and "6%" in text(ev)


def test_invented_number_is_retried_then_passes():
    p = Fake(["[TRẢ_LỜI] Lãi suất là 7,5%/năm [S1].", "[TRẢ_LỜI] Lãi suất ưu đãi là 6%/năm [S1]."])
    ev = run(p)
    assert p.calls == 2 and "status" in kinds(ev) and "6%" in text(ev)


def test_still_failing_answer_becomes_a_clarifying_question():
    p = Fake(["[TRẢ_LỜI] Lãi suất là 7,5% [S1].", "[TRẢ_LỜI] Lãi suất là 8% [S1]."])
    ev = run(p)
    assert ("mode", {"mode": "clarify"}) in ev and "sources" not in kinds(ev)
    out = text(ev)
    assert ("7,5%" in out or "8%" in out) and "kỳ hạn" in out and "?" in out


def test_uncited_answer_is_rejected():
    ev = run(Fake(["[TRẢ_LỜI] Lãi suất ưu đãi là 6%/năm.", "[TRẢ_LỜI] Lãi suất ưu đãi là 6%/năm."]))
    assert ("mode", {"mode": "clarify"}) in ev


def test_clarify_falls_back_when_model_fails():
    ev = run(Fake(["[TRẢ_LỜI] x 9% [S1]", "[TRẢ_LỜI] x 9% [S1]"], ask=None))
    assert "rõ hơn" in text(ev)


def test_clarify_and_insufficient_modes_are_not_audited():
    ev = run(Fake(["[HỎI_LẠI] Anh/chị hỏi kỳ hạn nào ạ?"]))
    assert ("mode", {"mode": "clarify"}) in ev and kinds(ev)[-1] == "done"


class IntentModel:
    def __init__(self, out): self.out = out
    def complete(self, *a, **k): return self.out


@pytest.mark.parametrize("label,expected_mode", [("out_of_scope", "chitchat"), ("vague", "clarify")])
def test_intent_model_short_circuits_without_retrieval(label, expected_mode):
    p = Fake([])
    ev = run(p, "lãi suất?", IntentClassifier(IntentModel(label), "m"))
    assert ("mode", {"mode": expected_mode}) in ev and p.calls == 0 and "sources" not in kinds(ev)


def test_intent_model_failure_falls_back_to_domain():
    class Broken:
        def complete(self, *a, **k): raise ChatError("down")
    assert IntentClassifier(Broken(), "m").classify("lãi suất vay 12 tháng", []).label == "domain"


def test_normalize_url():
    assert normalize_url("127.0.0.1:8008") == "http://127.0.0.1:8008/v1"
    assert normalize_url("http://10.148.183.8:8008/v1/") == "http://10.148.183.8:8008/v1"
    for bad in ("ftp://127.0.0.1", "http://169.254.169.254/latest", "http://user:pw@127.0.0.1", "http://0.0.0.0:80"):
        with pytest.raises(EndpointError):
            normalize_url(bad)


def test_registry_add_remove_persists_without_leaking_key(tmp_path):
    path = tmp_path / "endpoints.json"
    reg = ProviderRegistry({}, path)
    key = reg.add("Inferact/Qwen3.8-27B-NVFP4", "127.0.0.1:8008", "sekret", ["Inferact/Qwen3.8-27B-NVFP4"])
    assert reg.is_custom(key) and oct(path.stat().st_mode)[-3:] == "600"
    assert ProviderRegistry({}, path).configs()[key].models == ("Inferact/Qwen3.8-27B-NVFP4",)
    assert reg.remove(key) and not json.loads(path.read_text())
    with pytest.raises(EndpointError):
        reg.add("x", "127.0.0.1:1", None, [])  # nothing to discover on a closed port


def test_offscope_tag_gets_fixed_reply_without_sources():
    ev = run(Fake(["[NGOÀI_PHẠM_VI]"]))
    assert ("mode", {"mode": "offscope"}) in ev and "sources" not in kinds(ev)
    assert "chưa được thiết lập" in text(ev)


def test_rejected_answer_to_an_offtopic_question_gets_the_fixed_reply():
    class Offtopic(Fake):
        def complete(self, *a, **k): return "out_of_scope"
    ev = run(Offtopic(["[TRẢ_LỜI] Paris [S1] 9%", "[TRẢ_LỜI] Paris [S1] 9%"]), "Thủ đô của Pháp là gì?")
    assert ("mode", {"mode": "offscope"}) in ev
