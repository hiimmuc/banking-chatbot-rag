import re, time
from collections import defaultdict, deque
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-src 'self'; "
       "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'")
FILE_PATH = re.compile(r"^/api/documents/[^/]+/file$")
BASE_HEADERS = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "X-Frame-Options": "SAMEORIGIN",
                "Permissions-Policy": "camera=(), microphone=(), geolocation=()"}


class SecurityHeaders:
    """CSP on HTML only: the PDF viewer inside the source panel breaks under a strict CSP on the PDF itself."""

    def __init__(self, app, framers: list[str] | None = None):
        self.app, self._framers = app, framers or []

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in BASE_HEADERS.items():
                    headers[name] = value
                if FILE_PATH.match(path):  # a separately hosted UI embeds this in its source panel
                    del headers["X-Frame-Options"]
                    headers["Content-Security-Policy"] = " ".join(["frame-ancestors 'self'", *self._framers])
                if path.startswith("/api/") and not path.startswith("/api/brand/"):
                    headers["Cache-Control"] = "no-store"
                if headers.get("content-type", "").startswith("text/html"):
                    headers["Content-Security-Policy"] = CSP
            await send(message)

        await self.app(scope, receive, send_with_headers)


def bucket_for(method: str, path: str) -> str:
    if method == "POST" and path == "/api/chat":
        return "chat"
    if method == "POST" and path == "/api/documents":
        return "upload"
    if method == "POST" and path == "/api/login":
        return "login"
    return "default"


class RateLimit:
    """Sliding-window limiter per client IP. In-memory: fine for one process, not for several."""

    MAX_KEYS = 10_000

    def __init__(self, app, limits: dict[str, tuple[int, int]], trust_proxy: bool = False):
        self.app, self._limits, self._trust_proxy = app, limits, trust_proxy
        self._hits: dict[tuple[str, str], deque] = defaultdict(deque)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == "/api/health":
            return await self.app(scope, receive, send)
        bucket = bucket_for(scope["method"], scope["path"])
        retry_after = self._check(self._client_ip(scope), bucket)
        if retry_after:
            response = JSONResponse({"detail": "Quá nhiều yêu cầu, thử lại sau"}, 429, headers={"Retry-After": str(retry_after)})
            return await response(scope, receive, send)
        await self.app(scope, receive, send)

    def _client_ip(self, scope) -> str:
        if self._trust_proxy:
            headers = Headers(scope=scope)
            forwarded = headers.get("cf-connecting-ip") or headers.get("x-forwarded-for", "").split(",")[0].strip()
            if forwarded:
                return forwarded
        return (scope.get("client") or ("unknown", 0))[0]

    def _check(self, ip: str, bucket: str) -> int:
        limit, window = self._limits[bucket]
        now = time.monotonic()
        if len(self._hits) > self.MAX_KEYS:
            self._hits = defaultdict(deque, {k: v for k, v in self._hits.items() if v and now - v[-1] < window})
        hits = self._hits[(ip, bucket)]
        while hits and now - hits[0] >= window:
            hits.popleft()
        if len(hits) >= limit:
            return max(1, int(window - (now - hits[0])))
        hits.append(now)
        return 0
