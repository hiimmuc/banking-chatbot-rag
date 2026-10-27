import logging, os, pathlib
from dataclasses import dataclass, field
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
log = logging.getLogger(__name__)

PLACEHOLDER = "***REMOVED***"


def env(name: str, default: str | None = None) -> str | None:
    """Env var, or `default` when it is empty or still a template placeholder."""
    value = os.environ.get(name, "").strip()
    return default if not value or value == PLACEHOLDER or value.startswith("your-") else value


DATA_DIR = pathlib.Path(env("RAG_DATA_DIR", str(ROOT / "data")))
DB_PATH = DATA_DIR / "rag.db"
UPLOADS_DIR = DATA_DIR / "uploads"
OCR_DIR = DATA_DIR / "ocr"
PAGES_DIR = DATA_DIR / "pages"
WEB_DIR = ROOT / "web"
OCR_PYTHON = ROOT / ".venv-mineru" / "bin" / "python"
OCR_SCRIPT = ROOT / "scripts" / "ocr_mineru.py"

EMBED_MODEL = env("EMBED_MODEL", "BAAI/bge-m3")
RERANK_MODEL = env("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
DEVICE = env("RAG_DEVICE", "cuda")

MAX_UPLOAD_MB = 20
MAX_DOCUMENTS = int(env("MAX_DOCUMENTS", "200"))  # bounds disk use when uploads are open to anyone
MAX_OUTPUT_TOKENS_CAP = 2000
STYLES = {"concise": "Trả lời ngắn gọn, đi thẳng vào kết luận.",
          "detailed": "Trả lời chi tiết, nêu rõ điều kiện và ngoại lệ."}

OCR_BACKEND = env("OCR_BACKEND", "mineru")  # mineru (local) | gemini (sends page images to Google)
GEMINI_OCR_MODEL = env("GEMINI_OCR_MODEL", "gemini-3.5-flash")

AUTH_USER = env("APP_USER", "admin")
AUTH_PASSWORD = env("APP_PASSWORD")
AUTH_SECRET = env("APP_SECRET")  # signs session and file-link tokens; derived from the password when unset
SESSION_TTL = 12 * 3600
FILE_LINK_TTL = 600
ALLOWED_ORIGINS = [o.strip().rstrip("/") for o in (env("ALLOWED_ORIGINS", "") or "").split(",") if o.strip()]  # exact origins of a separately hosted UI
TRUST_PROXY = env("TRUST_PROXY", "0") == "1"  # read the client IP from CF-Connecting-IP / X-Forwarded-For
RATE_LIMITS = {"chat": (20, 60), "upload": (6, 60), "login": (10, 60), "default": (240, 60)}  # bucket -> (requests, seconds)

LOGO_TYPES = {".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}  # no SVG: it can carry script
LOGO_SLOTS = {"header": "BRAND_LOGO_HEADER", "footer-light": "BRAND_LOGO_FOOTER_LIGHT", "footer-dark": "BRAND_LOGO_FOOTER_DARK"}


@dataclass(frozen=True)
class Branding:
    """Organisation identity, read from .env so the repository itself stays anonymous."""
    org_name: str | None
    author: str | None
    logos: dict[str, pathlib.Path] = field(default_factory=dict)


def _load_branding() -> Branding:
    logos = {}
    for slot, var in LOGO_SLOTS.items():
        raw = env(var)
        if not raw:
            continue
        path = pathlib.Path(raw) if pathlib.Path(raw).is_absolute() else ROOT / raw
        if path.suffix.lower() in LOGO_TYPES and path.is_file():
            logos[slot] = path
        else:
            log.warning("%s ignored: not a png/webp/jpg file at %s", var, path)
    return Branding(env("ORG_NAME"), env("AUTHOR_INFO"), logos)


BRANDING = _load_branding()


@dataclass(frozen=True)
class Provider:
    """A chat backend that speaks the OpenAI chat-completions protocol."""
    key: str
    label: str
    base_url: str
    api_key: str | None
    models: tuple[str, ...]
    extra_body: dict = field(default_factory=dict)
    token_param: str = "max_tokens"
    needs_key: bool = True

    @property
    def available(self) -> bool:
        return bool(self.api_key) or not self.needs_key


@dataclass(frozen=True)
class RetrievalParams:
    keyword_top_k: int = 20
    vector_top_k: int = 20
    rerank_top_k: int = 30
    context_top_k: int = 6


def _providers() -> dict[str, Provider]:
    items = (
        Provider("qwen", "Qwen3.5-2B (local vLLM)", env("QWEN_BASE_URL", "http://127.0.0.1:8000/v1"), env("QWEN_API_KEY", "EMPTY"),
                 ("Qwen/Qwen3.5-2B",), extra_body={"chat_template_kwargs": {"enable_thinking": False}}, needs_key=False),
        Provider("gemini", "Gemini", "https://generativelanguage.googleapis.com/v1beta/openai/", env("GEMINI_API_KEY"),
                 (env("GEMINI_CHAT_MODEL", "gemini-3.5-flash"),)),
        Provider("openai", "OpenAI", "https://api.openai.com/v1", env("OPENAI_API_KEY"),
                 (env("OPENAI_CHAT_MODEL", "gpt-4.1-mini"),), token_param="max_completion_tokens"),
    )
    return {p.key: p for p in items}


PROVIDERS = {k: p for k, p in _providers().items() if p.available}
DEFAULT_PROVIDER = env("CHAT_PROVIDER", "qwen") if env("CHAT_PROVIDER", "qwen") in PROVIDERS else next(iter(PROVIDERS))
RETRIEVAL = RetrievalParams()
GEMINI_API_KEY = env("GEMINI_API_KEY")
