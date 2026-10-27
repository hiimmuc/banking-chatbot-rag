import ipaddress, json, re, socket
import httpx
from threading import Lock
from typing import Mapping
from urllib.parse import urlparse
from . import config
from .config import Provider
from .llm import ChatProvider, OpenAICompatProvider

QWEN_NO_THINK = {"chat_template_kwargs": {"enable_thinking": False}}


class EndpointError(ValueError):
    """Message is safe to show the client."""


def normalize_url(raw: str) -> str:
    """http(s) URL with a path (default /v1). Loopback and private hosts are allowed (local vLLM); link-local and metadata addresses are not."""
    raw = raw.strip()
    url = urlparse(raw if "://" in raw else f"http://{raw}")
    if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
        raise EndpointError("URL không hợp lệ (chỉ http/https, không kèm tài khoản)")
    try:
        addrs = {ipaddress.ip_address(a[4][0]) for a in socket.getaddrinfo(url.hostname, url.port or 80)}
    except (socket.gaierror, ValueError):
        raise EndpointError("Không phân giải được địa chỉ máy chủ") from None
    if any(a.is_link_local or a.is_multicast or a.is_unspecified or a.is_reserved for a in addrs):
        raise EndpointError("Địa chỉ không được phép")
    # ponytail: DNS is checked once here, so a hostname that later rebinds is not caught; pin the IP if hosts become untrusted
    return f"{url.scheme}://{url.netloc}{url.path.rstrip('/') or '/v1'}"


def discover_models(base_url: str, api_key: str | None) -> list[str]:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        r = httpx.get(f"{base_url}/models", headers=headers, timeout=5, follow_redirects=False)
        r.raise_for_status()
        return [m["id"] for m in r.json()["data"]][:50]
    except Exception:
        return []


class ProviderRegistry(Mapping):
    """Built-in providers from .env plus endpoints saved from the settings dialog (data/endpoints.json, mode 600)."""

    def __init__(self, static: Mapping[str, Provider], path):
        self._static, self._path, self._lock, self._clients = dict(static), path, Lock(), {}
        self._custom = self._load()

    def _load(self) -> dict[str, Provider]:
        try:
            rows = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {r["key"]: Provider(r["key"], r["label"], r["base_url"], r["api_key"] or "EMPTY", tuple(r["models"]),
                                   extra_body=QWEN_NO_THINK, needs_key=False) for r in rows}

    def _save(self) -> None:
        rows = [{"key": p.key, "label": p.label, "base_url": p.base_url, "api_key": p.api_key if p.api_key != "EMPTY" else "", "models": list(p.models)}
                for p in self._custom.values()]
        self._path.write_text(json.dumps(rows), encoding="utf-8")
        self._path.chmod(0o600)

    def configs(self) -> dict[str, Provider]:
        return {**self._static, **self._custom}

    def is_custom(self, key: str) -> bool:
        return key in self._custom

    def __getitem__(self, key: str) -> ChatProvider:
        with self._lock:
            if key not in self._clients:
                self._clients[key] = OpenAICompatProvider(self.configs()[key])
            return self._clients[key]

    def __iter__(self):
        return iter(self.configs())

    def __len__(self):
        return len(self.configs())

    def add(self, label: str, url: str, api_key: str | None, models: list[str]) -> str:
        label = label.strip()[:60] or "Endpoint"
        base_url = normalize_url(url)
        models = [m.strip() for m in models if m.strip()][:50] or discover_models(base_url, api_key)
        if not models:
            raise EndpointError("Không lấy được danh sách model từ URL này, hãy nhập tên model")
        with self._lock:
            if len(self._custom) >= config.MAX_CUSTOM_ENDPOINTS:
                raise EndpointError("Đã đạt số endpoint tối đa")
            key = "ep-" + re.sub(r"[^a-z0-9]+", "-", f"{label}".lower()).strip("-")[:30]
            while key in self.configs():
                key += "x"
            self._custom[key] = Provider(key, label, base_url, api_key or "EMPTY", tuple(models), extra_body=QWEN_NO_THINK, needs_key=False)
            self._save()
        return key

    def remove(self, key: str) -> bool:
        with self._lock:
            if key not in self._custom:
                return False
            del self._custom[key]
            self._clients.pop(key, None)
            self._save()
        return True
