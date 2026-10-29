import json, pathlib, threading, uuid
import pymupdf
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from .. import config
from . import session
from ..container import Container, get_container

router = APIRouter()

MIME = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".txt": "text/plain"}
MAGIC = {".pdf": b"%PDF-", ".png": b"\x89PNG", ".jpg": b"\xff\xd8", ".jpeg": b"\xff\xd8", ".docx": b"PK"}
PUBLIC_FIELDS = ("id", "name", "title", "doc_no", "issued", "pages", "status", "stage", "done", "total", "error")


@router.get("/documents")
def list_documents(c: Container = Depends(get_container)):
    return [{k: d[k] for k in PUBLIC_FIELDS} for d in c.store.list_documents()]


@router.post("/documents", status_code=202)
async def upload(file: UploadFile = File(...), c: Container = Depends(get_container)):
    name = pathlib.Path(file.filename or "").name
    ext = pathlib.Path(name).suffix.lower()
    if ext not in MIME:
        raise HTTPException(415, "Định dạng không hỗ trợ (PDF, DOCX, TXT, PNG, JPG)")
    if len(c.store.list_documents()) >= config.MAX_DOCUMENTS:
        raise HTTPException(409, "Đã đạt giới hạn số tài liệu")
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    data = await file.read(limit + 1)  # never buffer more than the cap
    if len(data) > limit:
        raise HTTPException(413, f"File quá {config.MAX_UPLOAD_MB} MB")
    if ext in MAGIC and not data.startswith(MAGIC[ext]):
        raise HTTPException(400, f"File không phải {ext[1:].upper()} hợp lệ")
    doc_id = uuid.uuid4().hex[:10]
    config.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.UPLOADS_DIR / f"{doc_id}_{name}"  # server-chosen prefix; the client filename is never a path
    path.write_bytes(data)
    threading.Thread(target=c.ingest.ingest_file, args=(path, MIME[ext], doc_id), daemon=True).start()
    return {"id": doc_id}


@router.get("/documents/{doc_id}/file")
def document_file(doc_id: str, c: Container = Depends(get_container)):
    doc = c.store.get_document(doc_id)
    if not doc or not pathlib.Path(doc["file_path"]).exists():
        raise HTTPException(404)
    return FileResponse(doc["file_path"], media_type=doc["mime"], headers={"Content-Disposition": "inline"})


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: str, c: Container = Depends(get_container)):
    """Removes the document from the index and deletes its derived OCR/page files and its uploaded copy.
    Originals placed by hand in data/raw are left alone."""
    doc = c.store.get_document(doc_id)
    if not doc:
        raise HTTPException(404)
    c.store.delete_document(doc_id)
    for folder in (config.OCR_DIR, config.PAGES_DIR):
        for f in folder.glob(f"{doc_id}_p*"):
            f.unlink(missing_ok=True)
    path = pathlib.Path(doc["file_path"]).resolve()
    if path.parent == config.UPLOADS_DIR.resolve():
        path.unlink(missing_ok=True)


@router.get("/documents/{doc_id}/page/{n}")
def document_page(doc_id: str, n: int, c: Container = Depends(get_container)):
    """OCR text (and MinerU block boxes, if any) of one page for the source popup; null when absent (txt/docx, Gemini OCR)."""
    if not c.store.get_document(doc_id):  # doc_id is only used in a path after it is known to be a real id
        raise HTTPException(404)
    md = config.OCR_DIR / f"{doc_id}_p{n:02d}.md"
    boxes = md.with_suffix(".json")  # only MinerU writes block boxes
    return {"text": md.read_text(encoding="utf-8") if md.exists() else None,
            "blocks": json.loads(boxes.read_text(encoding="utf-8")) if boxes.exists() else None}


@router.get("/documents/{doc_id}/page/{n}/image")
def document_page_image(doc_id: str, n: int, c: Container = Depends(get_container)):
    doc = c.store.get_document(doc_id)
    path = pathlib.Path(doc["file_path"]) if doc else None
    if not path or not path.exists():
        raise HTTPException(404)
    if doc["mime"] == "application/pdf":
        with pymupdf.open(path) as pdf:
            if not 1 <= n <= len(pdf):
                raise HTTPException(404)
            return Response(pdf[n - 1].get_pixmap(dpi=110).tobytes("png"), media_type="image/png")
    if doc["mime"].startswith("image/") and n == 1:
        return FileResponse(path, media_type=doc["mime"])
    raise HTTPException(404)


@router.get("/documents/{doc_id}/link")
def document_link(doc_id: str, c: Container = Depends(get_container)):
    """Short-lived URL for <iframe>/<a>, which cannot send an Authorization header."""
    if not c.store.get_document(doc_id):
        raise HTTPException(404)
    base = f"/api/documents/{doc_id}/file"
    return {"url": f"{base}?t={session.signer.issue(f'file:{doc_id}', config.FILE_LINK_TTL)}" if config.AUTH_PASSWORD else base}
