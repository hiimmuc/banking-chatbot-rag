import pathlib
from typing import Callable, Protocol
import pymupdf
from .config import OCR_DIR, PAGES_DIR
from .ocr import OcrEngine, make_engine

OCR_DPI = 200


class Extractor(Protocol):
    def pages(self, doc_id: str, path: pathlib.Path) -> list[str]: ...


class OcrRunner:
    """Runs the configured OCR engine once per document and caches one markdown file per page."""

    def __init__(self, engine: OcrEngine | None = None, ocr_dir=OCR_DIR, pages_dir=PAGES_DIR):
        self._engine, self._ocr_dir, self._pages_dir = engine, ocr_dir, pages_dir

    def pages(self, doc_id: str, count: int, render: Callable[[int, pathlib.Path], None]) -> list[str]:
        self._pages_dir.mkdir(parents=True, exist_ok=True)
        todo = []
        for n in range(1, count + 1):
            if not self._md(doc_id, n).exists():
                png = self._png(doc_id, n)
                if not png.exists():
                    render(n, png)
                todo.append(png)
        if todo:
            self._run(todo)
        return [self._md(doc_id, n).read_text(encoding="utf-8") for n in range(1, count + 1)]

    def _run(self, pngs: list[pathlib.Path]) -> None:
        self._engine = self._engine or make_engine()
        self._engine.run(pngs, self._ocr_dir)
        missing = [p.name for p in pngs if not self._md(*self._key(p)).exists()]
        if missing:
            raise RuntimeError(f"OCR produced no text for {missing[:3]}")

    def _md(self, doc_id: str, n: int) -> pathlib.Path:
        return self._ocr_dir / f"{doc_id}_p{n:02d}.md"

    def _png(self, doc_id: str, n: int) -> pathlib.Path:
        return self._pages_dir / f"{doc_id}_p{n:02d}.png"

    @staticmethod
    def _key(png: pathlib.Path) -> tuple[str, int]:
        doc_id, _, page = png.stem.rpartition("_p")
        return doc_id, int(page)


class PdfExtractor:
    """Always re-OCRs: the embedded text layers in these scans are poor ('Họp đồng', '6%/nãtn')."""

    def __init__(self, ocr: OcrRunner):
        self._ocr = ocr

    def pages(self, doc_id, path):
        doc = pymupdf.open(path)
        return self._ocr.pages(doc_id, len(doc), lambda n, png: doc[n - 1].get_pixmap(dpi=OCR_DPI).save(png))


class ImageExtractor:
    def __init__(self, ocr: OcrRunner):
        self._ocr = ocr

    def pages(self, doc_id, path):
        return self._ocr.pages(doc_id, 1, lambda n, png: png.write_bytes(path.read_bytes()))


class DocxExtractor:
    def pages(self, doc_id, path):
        import mammoth
        with open(path, "rb") as f:
            return [mammoth.extract_raw_text(f).value]


class TextExtractor:
    def pages(self, doc_id, path):
        return [path.read_text(encoding="utf-8")]  # UnicodeDecodeError surfaces as a Failed document


def extractor_for(suffix: str, ocr: OcrRunner) -> Extractor:
    registry: dict[str, Callable[[], Extractor]] = {
        ".pdf": lambda: PdfExtractor(ocr), ".png": lambda: ImageExtractor(ocr), ".jpg": lambda: ImageExtractor(ocr),
        ".jpeg": lambda: ImageExtractor(ocr), ".docx": DocxExtractor, ".txt": TextExtractor,
    }
    if suffix.lower() not in registry:
        raise ValueError(f"unsupported file type {suffix}")
    return registry[suffix.lower()]()
