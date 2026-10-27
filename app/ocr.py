import base64, pathlib, subprocess, time
from typing import Protocol
import httpx
from . import config

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_PROMPT = ("Transcribe this Vietnamese bank document page to Markdown, exactly as printed. "
                 "Keep all diacritics, numbers, percentages, dates and document numbers exact. "
                 "Render tables as Markdown tables (keep every row and column, merged cells repeated). "
                 "Write stamps and signatures only as [con dấu: ...] and [chữ ký]. No commentary.")
RETRY_STATUS = {429, 500, 503}


class OcrEngine(Protocol):
    def run(self, pngs: list[pathlib.Path], out_dir: pathlib.Path) -> None:
        """Write `<png stem>.md` into out_dir for every page image."""


class MinerUEngine:
    """Local MinerU2.5-Pro in its own venv; page images never leave the machine."""

    def run(self, pngs, out_dir):
        proc = subprocess.run([str(config.OCR_PYTHON), str(config.OCR_SCRIPT), str(out_dir), *map(str, pngs)], capture_output=True, text=True)
        if proc.returncode:
            raise RuntimeError(f"MinerU exited {proc.returncode}: {proc.stderr[-300:]}")


class GeminiEngine:
    """Sends page images to the Gemini API. Needs GEMINI_API_KEY and, for bank documents, a data-sharing decision."""

    def __init__(self, api_key: str, model: str, client: httpx.Client | None = None, backoff: float = 15.0):
        self._key, self._model, self._backoff = api_key, model, backoff
        self._client = client or httpx.Client(timeout=180)

    def run(self, pngs, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        for png in pngs:
            (out_dir / f"{png.stem}.md").write_text(self._ocr(png), encoding="utf-8")

    def _ocr(self, png: pathlib.Path) -> str:
        body = {"contents": [{"parts": [{"text": GEMINI_PROMPT},
                                        {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(png.read_bytes()).decode()}}]}],
                "generationConfig": {"temperature": 0}}
        for attempt in range(5):
            r = self._client.post(GEMINI_URL.format(model=self._model), headers={"x-goog-api-key": self._key}, json=body)
            if r.status_code == 200:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            if r.status_code not in RETRY_STATUS:
                break
            time.sleep(self._backoff * (attempt + 1))
        raise RuntimeError(f"Gemini OCR failed (HTTP {r.status_code})")  # response body omitted on purpose


def make_engine(backend: str | None = None) -> OcrEngine:
    backend = backend or config.OCR_BACKEND
    if backend == "gemini":
        if not config.GEMINI_API_KEY:
            raise RuntimeError("OCR_BACKEND=gemini needs GEMINI_API_KEY")
        return GeminiEngine(config.GEMINI_API_KEY, config.GEMINI_OCR_MODEL)
    if backend == "mineru":
        return MinerUEngine()
    raise RuntimeError(f"unknown OCR_BACKEND {backend!r}")
