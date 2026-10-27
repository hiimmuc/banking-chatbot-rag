import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from . import config
from .api import chat, documents, meta, session
from .api.auth import AccessControl
from .api.security import RateLimit, SecurityHeaders


class NoCacheStatic(StaticFiles):
    """The UI is a single file that changes with deploys; never serve a stale copy."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


def create_app() -> FastAPI:
    app = FastAPI(title="Banking Docs RAG")
    # add_middleware wraps outward: the last one added runs first. CORS sits outside auth and the rate limit so preflights are
    # answered without credentials and 401/429 responses stay readable by the browser.
    if config.AUTH_PASSWORD:
        app.add_middleware(AccessControl, user=config.AUTH_USER, password=config.AUTH_PASSWORD, signer=session.signer)
    else:
        logging.getLogger(__name__).warning("APP_PASSWORD is not set: the app is open to anyone who can reach it")
    app.add_middleware(RateLimit, limits=config.RATE_LIMITS, trust_proxy=config.TRUST_PROXY)
    if config.ALLOWED_ORIGINS:
        app.add_middleware(CORSMiddleware, allow_origins=config.ALLOWED_ORIGINS, allow_methods=["GET", "POST"],
                           allow_headers=["Authorization", "Content-Type"], max_age=600)
    app.add_middleware(SecurityHeaders, framers=config.ALLOWED_ORIGINS)
    for router in (meta.router, session.router, documents.router, chat.router):
        app.include_router(router, prefix="/api")
    app.mount("/", NoCacheStatic(directory=config.WEB_DIR, html=True), name="web")
    return app


app = create_app()
