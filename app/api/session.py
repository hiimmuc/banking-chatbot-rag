from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from .. import config
from .auth import check_password, make_signer

router = APIRouter()
signer = make_signer(config.AUTH_SECRET, config.AUTH_PASSWORD or "")


class Login(BaseModel):
    password: str = Field(max_length=200)
    user: str = Field(default="", max_length=100)


@router.post("/login")
def login(body: Login):
    """Exchange the shared password for a session token. The user name is optional: one shared password gates the app."""
    if not config.AUTH_PASSWORD:
        return {"token": None, "expiresIn": 0}
    if not check_password(body.user or config.AUTH_USER, body.password, config.AUTH_USER, config.AUTH_PASSWORD):
        raise HTTPException(401, "Sai mật khẩu")
    return {"token": signer.issue("session", config.SESSION_TTL), "expiresIn": config.SESSION_TTL}
