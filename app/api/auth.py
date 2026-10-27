import base64, hashlib, hmac, re, secrets, time
from urllib.parse import parse_qs
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

PUBLIC_PATHS = {"/api/health", "/api/branding", "/api/login"}
FILE_PATH = re.compile(r"^/api/documents/([^/]+)/file$")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class TokenSigner:
    """Stateless HMAC tokens bound to a scope ('session' or 'file:<id>') and an expiry."""

    def __init__(self, secret: bytes):
        self._secret = secret

    def issue(self, scope: str, ttl: int) -> str:
        payload = _b64(f"{scope}|{int(time.time()) + ttl}".encode())
        return f"{payload}.{self._mac(payload)}"

    def verify(self, token: str, scope: str) -> bool:
        payload, _, mac = token.partition(".")
        if not payload or not hmac.compare_digest(mac, self._mac(payload)):
            return False
        try:
            token_scope, _, expires = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode().rpartition("|")
            return token_scope == scope and int(expires) >= time.time()
        except ValueError:
            return False

    def _mac(self, payload: str) -> str:
        return _b64(hmac.new(self._secret, payload.encode(), hashlib.sha256).digest())


def make_signer(secret: str | None, password: str) -> TokenSigner:
    return TokenSigner((secret or f"rag-v1|{password}").encode())


def check_password(user: str, password: str, expected_user: str, expected_password: str) -> bool:
    return secrets.compare_digest(user.encode(), expected_user.encode()) & secrets.compare_digest(password.encode(), expected_password.encode())


class AccessControl:
    """Every /api route except health, branding, login and logos needs a session token, Basic credentials,
    or (for a document file only) a short-lived signed link. The static UI itself is public."""

    def __init__(self, app, user: str, password: str, signer: TokenSigner):
        self.app, self._user, self._password, self._signer = app, user, password, signer

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or self._is_public(scope["path"]) or self._authorized(scope):
            return await self.app(scope, receive, send)
        await JSONResponse({"detail": "Cần đăng nhập"}, 401)(scope, receive, send)

    @staticmethod
    def _is_public(path: str) -> bool:
        return not path.startswith("/api/") or path in PUBLIC_PATHS or path.startswith("/api/brand/")

    def _authorized(self, scope) -> bool:
        header = Headers(scope=scope).get("authorization", "")
        if header.startswith("Bearer "):
            return self._signer.verify(header[7:], "session")
        if header.startswith("Basic "):
            try:
                user, _, password = base64.b64decode(header[6:]).decode().partition(":")
            except Exception:
                return False
            return check_password(user, password, self._user, self._password)
        match = FILE_PATH.match(scope["path"])
        if match and scope["method"] == "GET":
            token = parse_qs(scope["query_string"].decode()).get("t", [""])[0]
            return self._signer.verify(token, f"file:{match.group(1)}")
        return False
