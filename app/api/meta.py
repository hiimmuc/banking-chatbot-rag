from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from .. import config

router = APIRouter()


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/config")
def public_config():
    """Names and limits only: endpoints, keys and file paths never leave the server."""
    return {"default_provider": config.DEFAULT_PROVIDER, "max_output_tokens_cap": config.MAX_OUTPUT_TOKENS_CAP,
            "styles": list(config.STYLES), "max_upload_mb": config.MAX_UPLOAD_MB,
            "providers": {k: {"label": p.label, "models": list(p.models)} for k, p in config.PROVIDERS.items()}}


@router.get("/branding")
def branding():
    """Public, so the login screen can show the logo before anyone signs in."""
    b = config.BRANDING
    return {"authRequired": bool(config.AUTH_PASSWORD), "orgName": b.org_name, "author": b.author,
            "logos": {slot: f"/api/brand/{slot}" for slot in b.logos}}


@router.get("/brand/{slot}")
def brand_logo(slot: str):
    path = config.BRANDING.logos.get(slot)
    if not path:
        raise HTTPException(404)
    return FileResponse(path, media_type=config.LOGO_TYPES[path.suffix.lower()], headers={"Cache-Control": "no-cache"})
