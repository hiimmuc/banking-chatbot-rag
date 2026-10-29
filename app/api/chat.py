from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from .. import config
from ..chat_service import ChatParams
from ..container import Container, get_container
from .sse import sse

router = APIRouter()


class ChatRequest(BaseModel):
    messages: list[dict] = Field(min_length=1, max_length=40)
    provider: str | None = None
    model: str | None = None
    max_output_tokens: int = 1200
    style: str = config.DEFAULT_STYLE
    temperature: float | None = Field(default=0.2, ge=0, le=1)
    document_ids: list[str] | None = Field(default=None, max_length=500)  # None = search every document


def _params(req: ChatRequest, c: Container) -> ChatParams:
    """Clamp and allowlist everything: the client is untrusted."""
    key = req.provider or config.DEFAULT_PROVIDER
    provider = c.providers.configs().get(key)
    if not provider:
        raise HTTPException(400, "Provider không hợp lệ")
    model = req.model or provider.models[0]
    if model not in provider.models:
        raise HTTPException(400, "Model không nằm trong danh sách cho phép")
    return ChatParams(key, model, max(100, min(req.max_output_tokens, config.MAX_OUTPUT_TOKENS_CAP)), req.temperature, req.style,
                      None if req.document_ids is None else frozenset(req.document_ids))


@router.post("/chat")
def chat(req: ChatRequest, c: Container = Depends(get_container)):
    last = req.messages[-1]
    if last.get("role") != "user" or not str(last.get("content", "")).strip():
        raise HTTPException(400, "Thiếu câu hỏi")
    history = [{"role": m["role"], "content": str(m["content"])[:4000]} for m in req.messages[:-1] if m.get("role") in ("user", "assistant")]
    events = c.chat.answer(str(last["content"])[:2000], history, _params(req, c))
    return StreamingResponse((sse(e, d) for e, d in events), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
