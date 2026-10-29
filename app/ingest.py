import hashlib, pathlib, re, sys, traceback
from .chunking import chunk_pages
from .embedding import Embedder
from .extract import OcrRunner, extractor_for
from .metadata import doc_label, parse_meta
from .store import NewChunk, Store
from .textnorm import fold


EMBED_STEP = 16


def doc_id_for(path: pathlib.Path) -> str:
    """Corpus files are named '<id>_<title>.pdf'; anything else gets a content-free hash of the name."""
    m = re.match(r"(\d+[A-Z]+)_", path.name)
    return m.group(1) if m else hashlib.sha1(path.name.encode()).hexdigest()[:10]


class IngestService:
    """Extract, chunk, embed and index one file. Safe to re-run: chunks are replaced, never appended."""

    def __init__(self, store: Store, embedder: Embedder, ocr: OcrRunner):
        self._store, self._embedder, self._ocr = store, embedder, ocr

    def ingest_file(self, path: pathlib.Path, mime: str = "application/pdf", doc_id: str | None = None) -> str:
        doc_id = doc_id or doc_id_for(path)
        title = re.sub(r"^(\d+[A-Z]+|[0-9a-f]{10})_", "", path.stem).strip()
        self._store.upsert_document(doc_id, path.name, title, mime, str(path))
        try:
            progress = lambda done, total: self._store.set_progress(doc_id, done, total)
            self._store.update_document(doc_id, stage="extract"); progress(0, 0)
            pages = extractor_for(path.suffix, self._ocr).pages(doc_id, path, progress)
            if not any(p.strip() for p in pages):
                raise RuntimeError("no text extracted")
            doc_no, issued = parse_meta(pages[0])
            self._store.update_document(doc_id, doc_no=doc_no, issued=issued, pages=len(pages), stage="embed"); progress(0, 0)
            self._store.replace_chunks(doc_id, self._build_chunks(pages, f"[{doc_label(doc_no, issued, doc_id)}: {title}]", progress))
            self._store.update_document(doc_id, status="ready", stage="done")
        except Exception as e:
            traceback.print_exc()
            self._store.update_document(doc_id, status="failed", error=str(e)[:300])
        return doc_id

    def resume_interrupted(self) -> None:
        """A restart kills ingest threads and leaves their documents 'processing' forever; finish them (OCR is cached per page)."""
        for d in self._store.list_documents():
            if d["status"] != "processing":
                continue
            path = pathlib.Path(d["file_path"])
            if path.exists():
                self.ingest_file(path, d["mime"], d["id"])
            else:
                self._store.update_document(d["id"], status="failed", error="Không tìm thấy tệp gốc, hãy tải lại")

    def _build_chunks(self, pages: list[str], header: str, progress=lambda done, total: None) -> list[NewChunk]:
        chunks = chunk_pages(pages)
        texts = [f"{header}\n{c['text']}" for c in chunks]
        vectors = []
        for i in range(0, len(texts), EMBED_STEP):  # small steps so the UI can show embedding progress
            vectors.extend(self._embedder.encode(texts[i:i + EMBED_STEP]))
            progress(len(vectors), len(texts))
        return [NewChunk(c["text"], c["heading"], c["page_start"], c["page_end"], v.tobytes(), fold(f"{header}\n{c['text']}"))
                for c, v in zip(chunks, vectors)]


if __name__ == "__main__":
    from .container import get_container
    service = get_container().ingest
    for p in sorted(pathlib.Path(sys.argv[1]).glob("[!.]*")):  # skips .DS_Store
        print(service.ingest_file(p), p.name[:50], flush=True)
