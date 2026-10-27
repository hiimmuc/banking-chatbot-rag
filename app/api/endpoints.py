from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from .. import config
from ..container import Container, get_container
from ..providers import EndpointError

router = APIRouter()


class EndpointRequest(BaseModel):
    label: str = Field(default="", max_length=60)
    url: str = Field(min_length=3, max_length=300)
    api_key: str | None = Field(default=None, max_length=300)
    models: list[str] = Field(default_factory=list, max_length=50)


def _enabled() -> None:
    if not config.ALLOW_CUSTOM_ENDPOINTS:
        raise HTTPException(403, "Chưa bật thêm endpoint (ALLOW_CUSTOM_ENDPOINTS=1 trong .env)")


@router.post("/endpoints", dependencies=[Depends(_enabled)])
def add_endpoint(req: EndpointRequest, c: Container = Depends(get_container)):
    try:
        return {"key": c.providers.add(req.label, req.url, req.api_key, req.models)}
    except EndpointError as e:
        raise HTTPException(400, str(e)) from None


@router.delete("/endpoints/{key}", dependencies=[Depends(_enabled)])
def delete_endpoint(key: str, c: Container = Depends(get_container)):
    if not c.providers.remove(key):
        raise HTTPException(404, "Không tìm thấy endpoint")
    return {"ok": True}
