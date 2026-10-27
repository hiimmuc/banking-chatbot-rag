import httpx, pytest
from app.ocr import GeminiEngine


def engine(handler):
    return GeminiEngine("test-key", "test-model", client=httpx.Client(transport=httpx.MockTransport(handler)), backoff=0)


def test_writes_markdown_and_sends_key_in_header(tmp_path):
    png = tmp_path / "doc_p01.png"; png.write_bytes(b"\x89PNG fake")
    seen = {}

    def handler(request):
        seen.update(key=request.headers["x-goog-api-key"], url=str(request.url))
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": " Số: 549 \n"}]}}]})

    engine(handler).run([png], tmp_path / "out")
    assert (tmp_path / "out" / "doc_p01.md").read_text(encoding="utf-8") == "Số: 549"
    assert seen["key"] == "test-key" and "key=" not in seen["url"]


def test_retries_transient_errors_then_succeeds(tmp_path):
    png = tmp_path / "p.png"; png.write_bytes(b"x")
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429) if len(calls) < 3 else httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})

    engine(handler).run([png], tmp_path)
    assert len(calls) == 3


def test_error_message_hides_response_body(tmp_path):
    png = tmp_path / "p.png"; png.write_bytes(b"x")
    with pytest.raises(RuntimeError) as e:
        engine(lambda r: httpx.Response(402, text="secret-account-detail")).run([png], tmp_path)
    assert "402" in str(e.value) and "secret" not in str(e.value)
