from typing import Iterator, Protocol
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
from .config import Provider

_STATUS_MESSAGES = {401: "Sai hoặc thiếu API key", 402: "Hết hạn mức/tín dụng của nhà cung cấp", 403: "Không có quyền truy cập model",
                    404: "Model không tồn tại", 429: "Bị giới hạn tốc độ, thử lại sau"}


class ChatError(Exception):
    """Message is safe to show the client: never contains keys, URLs or provider payloads."""


class ChatProvider(Protocol):
    def stream(self, model: str, messages: list[dict], max_tokens: int, temperature: float | None) -> Iterator[dict]: ...
    def complete(self, model: str, messages: list[dict], max_tokens: int, temperature: float | None) -> str: ...


def _sanitize(e: Exception) -> ChatError:
    if isinstance(e, APIStatusError):
        return ChatError(_STATUS_MESSAGES.get(e.status_code, f"Lỗi nhà cung cấp ({e.status_code})"))
    if isinstance(e, APITimeoutError):
        return ChatError("Model phản hồi quá lâu")
    if isinstance(e, APIConnectionError):
        return ChatError("Không kết nối được tới model")
    return ChatError("Lỗi không xác định khi gọi model")


class OpenAICompatProvider:
    """Serves OpenAI, Gemini's OpenAI-compatible endpoint and vLLM through one client."""

    def __init__(self, cfg: Provider):
        self._cfg = cfg
        self._client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key or "EMPTY", timeout=120, max_retries=0)

    def _kwargs(self, model, messages, max_tokens, temperature) -> dict:
        kw = {"model": model, "messages": messages, self._cfg.token_param: max_tokens}
        if temperature is not None:
            kw["temperature"] = temperature
        if self._cfg.extra_body:
            kw["extra_body"] = self._cfg.extra_body
        return kw

    def stream(self, model, messages, max_tokens, temperature):
        try:
            resp = self._client.chat.completions.create(stream=True, stream_options={"include_usage": True},
                                                        **self._kwargs(model, messages, max_tokens, temperature))
            for ev in resp:
                if ev.usage:
                    yield {"type": "usage", "in": ev.usage.prompt_tokens, "out": ev.usage.completion_tokens}
                if ev.choices and ev.choices[0].delta.content:
                    yield {"type": "delta", "text": ev.choices[0].delta.content}
        except Exception as e:
            raise _sanitize(e) from None

    def complete(self, model, messages, max_tokens=120, temperature=0):
        try:
            return self._client.chat.completions.create(**self._kwargs(model, messages, max_tokens, temperature)).choices[0].message.content or ""
        except Exception as e:
            raise _sanitize(e) from None
