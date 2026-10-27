import sqlite3, threading
from dataclasses import dataclass
import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, title TEXT, doc_no TEXT, issued TEXT,
  mime TEXT NOT NULL, file_path TEXT NOT NULL, pages INTEGER DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'processing', stage TEXT NOT NULL DEFAULT 'queued', error TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
  ordinal INTEGER NOT NULL, text TEXT NOT NULL, heading TEXT,
  page_start INTEGER, page_end INTEGER, embedding BLOB,
  UNIQUE(document_id, ordinal));
CREATE INDEX IF NOT EXISTS chunks_doc_idx ON chunks(document_id);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(chunk_id UNINDEXED, text);
"""
UPDATABLE = {"title", "doc_no", "issued", "pages", "status", "stage", "error"}
NEWEST_FIRST = "issued IS NULL, substr(issued,7,4)||substr(issued,4,2)||substr(issued,1,2) DESC, name"


@dataclass(frozen=True)
class NewChunk:
    text: str
    heading: str | None
    page_start: int
    page_end: int
    embedding: bytes
    fts_text: str


class Store:
    """SQLite persistence for documents, chunks, embeddings and the FTS index."""

    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()  # one shared connection, shared by API and ingest threads
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(SCHEMA)

    def _rows(self, sql: str, params=()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, params)]

    def _exec(self, sql: str, params=()) -> None:
        with self._lock:
            self._db.execute(sql, params)
            self._db.commit()

    def upsert_document(self, doc_id: str, name: str, title: str, mime: str, file_path: str) -> None:
        self._exec("INSERT INTO documents(id,name,title,mime,file_path) VALUES(?,?,?,?,?) "
                   "ON CONFLICT(id) DO UPDATE SET status='processing',stage='queued',error=NULL",
                   (doc_id, name, title, mime, file_path))

    def update_document(self, doc_id: str, **fields) -> None:
        if not fields.keys() <= UPDATABLE:
            raise ValueError(f"cannot update {fields.keys() - UPDATABLE}")
        self._exec(f"UPDATE documents SET {','.join(f'{k}=?' for k in fields)} WHERE id=?", [*fields.values(), doc_id])

    def get_document(self, doc_id: str) -> dict | None:
        return next(iter(self._rows("SELECT * FROM documents WHERE id=?", (doc_id,))), None)

    def list_documents(self) -> list[dict]:
        return self._rows(f"SELECT * FROM documents ORDER BY {NEWEST_FIRST}")

    def replace_chunks(self, doc_id: str, chunks: list[NewChunk]) -> None:
        """Delete and reinsert in one transaction so a retried ingest never duplicates."""
        with self._lock:
            self._db.execute("DELETE FROM chunks_fts WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id=?)", (doc_id,))
            self._db.execute("DELETE FROM chunks WHERE document_id=?", (doc_id,))
            for i, c in enumerate(chunks):
                cid = f"{doc_id}:{i}"
                self._db.execute("INSERT INTO chunks(id,document_id,ordinal,text,heading,page_start,page_end,embedding) VALUES(?,?,?,?,?,?,?,?)",
                                 (cid, doc_id, i, c.text, c.heading, c.page_start, c.page_end, c.embedding))
                self._db.execute("INSERT INTO chunks_fts(chunk_id,text) VALUES(?,?)", (cid, c.fts_text))
            self._db.commit()

    def ready_embeddings(self) -> tuple[list[str], np.ndarray]:
        rows = self._rows("SELECT c.id, c.embedding FROM chunks c JOIN documents d ON d.id=c.document_id WHERE d.status='ready'")
        if not rows:
            return [], np.empty((0, 0), dtype="float32")
        return [r["id"] for r in rows], np.frombuffer(b"".join(r["embedding"] for r in rows), dtype="float32").reshape(len(rows), -1)

    def keyword_search(self, match_query: str, k: int) -> list[str]:
        rows = self._rows("SELECT f.chunk_id FROM chunks_fts f JOIN chunks c ON c.id=f.chunk_id JOIN documents d ON d.id=c.document_id "
                          "WHERE chunks_fts MATCH ? AND d.status='ready' ORDER BY bm25(chunks_fts) LIMIT ?", (match_query, k))
        return [r["chunk_id"] for r in rows]

    def ready_documents(self) -> list[dict]:
        return self._rows("SELECT id, title, doc_no, issued FROM documents WHERE status='ready'")

    def chunks_of(self, doc_id: str) -> list[dict]:
        return list(self.get_chunks([r["id"] for r in self._rows("SELECT id FROM chunks WHERE document_id=? ORDER BY ordinal", (doc_id,))]).values())

    def get_chunks(self, ids: list[str]) -> dict[str, dict]:
        if not ids:
            return {}
        rows = self._rows("SELECT c.id,c.document_id,c.ordinal,c.text,c.heading,c.page_start,c.page_end,d.name,d.title,d.doc_no,d.issued "
                          f"FROM chunks c JOIN documents d ON d.id=c.document_id WHERE c.id IN ({','.join('?' * len(ids))})", ids)
        return {r["id"]: r for r in rows}
