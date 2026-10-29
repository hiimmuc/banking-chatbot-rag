import pathlib
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import config
from app.api.security import RateLimit
from app.main import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def test_security_headers_and_csp_on_html(client):
    r = client.get("/")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "script-src 'self'" in r.headers["content-security-policy"]
    assert "unsafe-inline" not in r.headers["content-security-policy"]


def test_api_responses_are_not_cached_and_have_no_csp(client):
    r = client.get("/api/health")
    assert r.headers["cache-control"] == "no-store"
    assert "content-security-policy" not in r.headers


def test_config_has_no_secrets_and_hides_unconfigured_providers(client):
    body = client.get("/api/config").json()
    assert set(body["providers"]) == {"qwen"}
    text = str(body).lower()
    assert "api_key" not in text and "base_url" not in text and "127.0.0.1" not in text


def test_branding_is_neutral_when_unset(client):
    b = client.get("/api/branding").json()
    assert b == {"authRequired": False, "orgName": None, "author": None, "logos": {}}
    assert client.get("/api/brand/header").status_code == 404


def test_branding_comes_from_config(client, monkeypatch, tmp_path):
    logo = tmp_path / "logo.png"; logo.write_bytes(b"\x89PNG")
    monkeypatch.setattr(config, "BRANDING", config.Branding("Org", "Someone", {"header": logo}))
    b = client.get("/api/branding").json()
    assert b["orgName"] == "Org" and b["author"] == "Someone" and b["logos"] == {"header": "/api/brand/header"}
    assert client.get("/api/brand/header").content == b"\x89PNG"
    assert client.get("/api/brand/../../etc/passwd").status_code in (404, 405)


def test_upload_validation(client):
    assert client.post("/api/documents", files={"file": ("a.exe", b"MZ")}).status_code == 415
    assert client.post("/api/documents", files={"file": ("a.pdf", b"not a pdf")}).status_code == 400
    big = b"%PDF-" + b"0" * (config.MAX_UPLOAD_MB * 1024 * 1024)
    assert client.post("/api/documents", files={"file": ("a.pdf", big)}).status_code == 413


def test_upload_stops_at_the_document_cap(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_DOCUMENTS", 0)
    assert client.post("/api/documents", files={"file": ("a.txt", b"x")}).status_code == 409


def test_chat_rejects_unknown_provider_model_and_bad_input(client):
    msg = [{"role": "user", "content": "x"}]
    assert client.post("/api/chat", json={"messages": msg, "provider": "openai"}).status_code == 400
    assert client.post("/api/chat", json={"messages": msg, "provider": "qwen", "model": "evil"}).status_code == 400
    assert client.post("/api/chat", json={"messages": [{"role": "assistant", "content": "x"}]}).status_code == 400
    assert client.post("/api/chat", json={"messages": msg, "temperature": 5}).status_code == 422


def test_document_file_unknown_id_is_404(client):
    assert client.get("/api/documents/nope/file").status_code == 404


def protected_client(monkeypatch, **extra):
    from app.api import auth, session
    monkeypatch.setattr(config, "AUTH_PASSWORD", "pw"); monkeypatch.setattr(config, "AUTH_USER", "u")
    monkeypatch.setattr(session, "signer", auth.make_signer(None, "pw"))
    for k, v in extra.items():
        monkeypatch.setattr(config, k, v)
    return TestClient(create_app())


def test_protected_routes_need_credentials(monkeypatch):
    c = protected_client(monkeypatch)
    assert c.get("/api/documents").status_code == 401
    assert "www-authenticate" not in c.get("/api/documents").headers  # no native browser prompt on fetch
    assert c.get("/api/documents", auth=("u", "wrong")).status_code == 401
    assert c.get("/api/documents", auth=("u", "pw")).status_code == 200  # Basic still works for curl and the eval scripts
    assert c.get("/api/documents", headers={"Authorization": "Bearer forged.token"}).status_code == 401
    for public in ("/api/health", "/api/branding", "/"):
        assert c.get(public).status_code == 200
    assert c.get("/api/documents").headers["x-content-type-options"] == "nosniff"  # headers also on 401


def test_login_issues_a_working_session_token(monkeypatch):
    c = protected_client(monkeypatch)
    assert c.post("/api/login", json={"password": "nope"}).status_code == 401
    token = c.post("/api/login", json={"password": "pw"}).json()["token"]
    assert c.get("/api/config", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert c.get("/api/branding").json()["authRequired"] is True


def test_login_is_a_noop_when_auth_is_off(client):
    assert client.post("/api/login", json={"password": "x"}).json()["token"] is None


def test_signed_file_link_is_scoped_and_expires(monkeypatch, tmp_path):
    from app.container import get_container
    c = protected_client(monkeypatch)
    f = tmp_path / "a.txt"; f.write_text("hello")
    get_container().store.upsert_document("doc1", "a.txt", "a", "text/plain", str(f))
    get_container().store.upsert_document("doc2", "a.txt", "a", "text/plain", str(f))
    assert c.get("/api/documents/doc1/file").status_code == 401
    link = c.get("/api/documents/doc1/link", auth=("u", "pw")).json()["url"]
    assert c.get(link).status_code == 200 and c.get(link).text == "hello"
    assert c.get(link.replace("doc1/file", "doc2/file")).status_code == 401  # token is bound to its document
    assert c.get("/api/documents/doc1/file?t=garbage").status_code == 401
    assert c.post(link).status_code in (401, 405)  # link works for GET only
    expired = protected_client(monkeypatch, FILE_LINK_TTL=-5)
    assert expired.get(expired.get("/api/documents/doc1/link", auth=("u", "pw")).json()["url"]).status_code == 401


def test_file_responses_can_be_framed_only_by_allowed_origins(monkeypatch, tmp_path):
    from app.container import get_container
    c = protected_client(monkeypatch, ALLOWED_ORIGINS=["https://ui.example.com"])
    f = tmp_path / "a.txt"; f.write_text("x")
    get_container().store.upsert_document("doc3", "a.txt", "a", "text/plain", str(f))
    h = c.get("/api/documents/doc3/file", auth=("u", "pw")).headers
    assert "x-frame-options" not in h
    assert h["content-security-policy"] == "frame-ancestors 'self' https://ui.example.com"
    assert c.get("/api/health").headers["x-frame-options"] == "SAMEORIGIN"


def test_file_csp_has_no_trailing_space_without_allowed_origins(monkeypatch, tmp_path):
    from app.container import get_container
    c = protected_client(monkeypatch)
    f = tmp_path / "a.txt"; f.write_text("x")
    get_container().store.upsert_document("doc4", "a.txt", "a", "text/plain", str(f))
    assert c.get("/api/documents/doc4/file", auth=("u", "pw")).headers["content-security-policy"] == "frame-ancestors 'self'"


def test_page_text_and_image_for_source_popup(client, monkeypatch, tmp_path):
    import pymupdf
    from app.container import get_container
    monkeypatch.setattr(config, "OCR_DIR", tmp_path / "ocr"); (tmp_path / "ocr").mkdir()
    (tmp_path / "ocr" / "pg1_p01.md").write_text("Lãi suất 8%", encoding="utf-8")
    pdf = pymupdf.open(); pdf.new_page(); f = tmp_path / "a.pdf"; pdf.save(f)
    get_container().store.upsert_document("pg1", "a.pdf", "a", "application/pdf", str(f))
    assert client.get("/api/documents/pg1/page/1").json() == {"text": "Lãi suất 8%", "blocks": None}
    (tmp_path / "ocr" / "pg1_p01.json").write_text('[{"bbox": [0.1, 0.2, 0.9, 0.3], "type": "text", "content": "Lãi suất 8%"}]', encoding="utf-8")
    assert client.get("/api/documents/pg1/page/1").json()["blocks"][0]["bbox"] == [0.1, 0.2, 0.9, 0.3]
    assert client.get("/api/documents/pg1/page/2").json() == {"text": None, "blocks": None}
    img = client.get("/api/documents/pg1/page/1/image")
    assert img.status_code == 200 and img.content.startswith(b"\x89PNG")
    assert client.get("/api/documents/pg1/page/2/image").status_code == 404
    assert client.get("/api/documents/nope/page/1").status_code == 404
    assert client.get("/api/documents/..%2F..%2Fx/page/1").status_code == 404


def test_cors_allows_only_listed_origins(monkeypatch):
    c = protected_client(monkeypatch, ALLOWED_ORIGINS=["https://ui.example.com"])
    ask = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization,content-type"}
    ok = c.options("/api/chat", headers={"Origin": "https://ui.example.com", **ask})
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == "https://ui.example.com"
    assert "access-control-allow-origin" not in c.options("/api/chat", headers={"Origin": "https://evil.example.com", **ask}).headers
    denied = c.get("/api/documents", headers={"Origin": "https://ui.example.com"})
    assert denied.status_code == 401 and denied.headers["access-control-allow-origin"] == "https://ui.example.com"  # browser can read the 401


def test_no_cors_headers_by_default(client):
    assert "access-control-allow-origin" not in client.get("/api/health", headers={"Origin": "https://ui.example.com"}).headers


def test_rate_limit_per_bucket_and_per_ip():
    app = FastAPI()

    @app.post("/api/chat")
    def chat(): return {}

    app.add_middleware(RateLimit, limits={"chat": (2, 60), "upload": (1, 60), "default": (100, 60)}, trust_proxy=True)
    c = TestClient(app)
    assert [c.post("/api/chat").status_code for _ in range(3)] == [200, 200, 429]
    assert c.post("/api/chat").headers["retry-after"].isdigit()
    assert c.post("/api/chat", headers={"x-forwarded-for": "9.9.9.9"}).status_code == 200


def test_static_js_has_no_inline_handlers_or_styles():
    web = pathlib.Path(config.WEB_DIR)
    html = (web / "index.html").read_text(encoding="utf-8")
    assert "style=" not in html and " onclick=" not in html and "<style" not in html


def test_custom_endpoints_are_off_by_default_and_config_flags_it(client):
    assert client.get("/api/config").json()["customEndpoints"] is False
    assert client.post("/api/endpoints", json={"url": "127.0.0.1:8008", "models": ["m"]}).status_code == 403
    assert client.delete("/api/endpoints/ep-x").status_code == 403


def _two_docs(store, tmp_path):
    import numpy as np
    from app.store import NewChunk
    for i, d in enumerate(("da", "db")):
        store.upsert_document(d, f"{d}.txt", d, "text/plain", str(tmp_path / f"{d}.txt"))
        store.replace_chunks(d, [NewChunk("lai suat", None, 1, 1, np.eye(2, dtype="float32")[i].tobytes(), "lai suat")])
        store.update_document(d, status="ready")


def test_selected_documents_scope_keyword_and_vector_search(tmp_path):
    from app.retrieval import HybridRetriever
    from app.config import RetrievalParams
    from app.store import Store

    class Emb:
        def encode(self, texts): import numpy as np; return np.array([[1.0, 1.0]], dtype="float32")

    store = Store(tmp_path / "s.db"); _two_docs(store, tmp_path)
    r = HybridRetriever(store, Emb(), None, RetrievalParams())
    assert sorted(store.keyword_search("lai", 10)) == ["da:0", "db:0"]
    assert store.keyword_search("lai", 10, frozenset({"db"})) == ["db:0"]
    assert store.keyword_search("lai", 10, frozenset()) == []
    assert r._vector("q", frozenset({"da"})) == ["da:0"] and r._vector("q", frozenset()) == []


def test_delete_document_removes_index_and_derived_files(client, monkeypatch, tmp_path):
    from app.container import get_container
    ocr, up = tmp_path / "ocr", tmp_path / "up"; ocr.mkdir(); up.mkdir()
    monkeypatch.setattr(config, "OCR_DIR", ocr); monkeypatch.setattr(config, "PAGES_DIR", tmp_path / "pages"); monkeypatch.setattr(config, "UPLOADS_DIR", up)
    store = get_container().store
    (ocr / "dx_p01.md").write_text("x"); (ocr / "dxy_p01.md").write_text("keep"); (up / "dx_a.txt").write_text("x")
    store.upsert_document("dx", "a.txt", "a", "text/plain", str(up / "dx_a.txt"))
    assert client.delete("/api/documents/dx").status_code == 204
    assert store.get_document("dx") is None
    assert not (ocr / "dx_p01.md").exists() and not (up / "dx_a.txt").exists() and (ocr / "dxy_p01.md").exists()
    assert client.delete("/api/documents/dx").status_code == 404


def test_ocr_runner_reports_pages_done(tmp_path):
    from app.extract import OcrRunner

    class Engine:
        def run(self, pngs, out_dir):
            for p in pngs: (out_dir / f"{p.stem}.md").write_text("x")

    (tmp_path / "ocr").mkdir()
    seen = []
    OcrRunner(Engine(), tmp_path / "ocr", tmp_path / "pages").pages("d1", 3, lambda n, png: png.write_bytes(b""), lambda d, t: seen.append((d, t)))
    assert seen[0] == (0, 3) and seen[-1] == (3, 3)


def test_store_adds_progress_columns_to_an_old_database(tmp_path):
    import sqlite3
    from app.store import Store
    old = sqlite3.connect(tmp_path / "old.db")
    old.execute("CREATE TABLE documents (id TEXT PRIMARY KEY, name TEXT NOT NULL, title TEXT, doc_no TEXT, issued TEXT, mime TEXT NOT NULL, "
                "file_path TEXT NOT NULL, pages INTEGER DEFAULT 0, status TEXT NOT NULL DEFAULT 'processing', stage TEXT NOT NULL DEFAULT 'queued', "
                "error TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    old.execute("INSERT INTO documents(id,name,mime,file_path) VALUES('a','a','text/plain','a')"); old.commit(); old.close()
    store = Store(tmp_path / "old.db")
    store.set_progress("a", 2, 5)
    assert (store.get_document("a")["done"], store.get_document("a")["total"]) == (2, 5)


def test_resume_interrupted_finishes_processing_documents(tmp_path):
    from app.ingest import IngestService
    from app.store import Store
    store = Store(tmp_path / "r.db")
    (tmp_path / "a.txt").write_text("x")
    store.upsert_document("a", "a.txt", "a", "text/plain", str(tmp_path / "a.txt"))
    store.upsert_document("gone", "g.txt", "g", "text/plain", str(tmp_path / "g.txt"))
    svc = IngestService(store, None, None); seen = []
    svc.ingest_file = lambda path, mime, doc_id: seen.append((path.name, mime, doc_id))
    svc.resume_interrupted()
    assert seen == [("a.txt", "text/plain", "a")]
    assert store.get_document("gone")["status"] == "failed"
