import re
from .metadata import doc_label
from .retrieval import HybridRetriever
from .store import Store
from .textnorm import fold
from .versions import VersionGroup, _subject, groups

EXTRA_DOCS = 2      # related versions pulled into the context beyond what retrieval found
MAX_UNIT_SHARE = 2  # a title word names a subject only if it appears in at most this many document families


class VersionService:
    """Keeps amended and amending circulars together so an answer can use the newest and still cite the older one."""

    def __init__(self, store: Store, retriever: HybridRetriever, context_size: int):
        self._store, self._retriever, self._size = store, retriever, context_size

    def plan(self, question: str, sources: list[dict], doc_ids: frozenset[str] | None = None) -> tuple[list[dict], list[str], list[list[dict]]]:
        """(sources with missing versions added, prompt label per source, version groups for the UI). `doc_ids`: selected documents only."""
        docs = [d for d in self._store.ready_documents() if doc_ids is None or d["id"] in doc_ids]
        asked = self._asked_groups(question, docs)
        sources = self._expand(question, sources, asked)
        present = {c["document_id"] for c in sources}
        return (sources, *self._describe(sources, [g for g in asked if len(present & set(g.doc_ids)) > 1], docs))

    def _asked_groups(self, question: str, docs: list[dict]) -> list[VersionGroup]:
        """Version groups the question is actually about: it names a distinctive title word or a document number of the family."""
        found = groups(docs)
        by_id = {d["id"]: d for d in docs}
        families = found + [VersionGroup((d["id"],)) for d in docs if not any(d["id"] in g.doc_ids for g in found)]
        words = lambda g: set().union(*(_subject(by_id[i]["title"] or "") for i in g.doc_ids))
        share = {}
        for g in families:
            for w in words(g):
                share[w] = share.get(w, 0) + 1
        asked_words = set(re.findall(r"[a-z0-9]+", fold(question)))
        numbers = lambda g: {re.match(r"\d+", by_id[i]["doc_no"] or "").group(0) for i in g.doc_ids if re.match(r"\d+", by_id[i]["doc_no"] or "")}
        return [g for g in found if any(share[w] <= MAX_UNIT_SHARE and w in asked_words for w in words(g)) or numbers(g) & asked_words]

    def _expand(self, question: str, sources: list[dict], asked: list[VersionGroup]) -> list[dict]:
        present = {c["document_id"] for c in sources}
        related = [g for g in asked if present & set(g.doc_ids)]
        in_group = {i for g in related for i in g.doc_ids}
        extra = []
        for doc_id in [i for g in related for i in g.doc_ids if i not in present][:EXTRA_DOCS]:
            best = self._retriever.rank(question, self._store.chunks_of(doc_id))
            if best:
                extra.append(best[0])
        merged = sources + extra
        while len(merged) > self._size:
            unrelated = [c for c in merged if c["document_id"] not in in_group]
            merged.remove(min(unrelated or merged[len(sources) - 1:], key=lambda c: c["score"]))
        return merged

    @staticmethod
    def _describe(sources: list[dict], found: list[VersionGroup], docs: list[dict]) -> tuple[list[str], list[list[dict]]]:
        first = {}
        for n, c in enumerate(sources, 1):
            first.setdefault(c["document_id"], (n, c))
        present = {c["document_id"] for c in sources}
        label = lambda i: doc_label(first[i][1]["doc_no"], first[i][1]["issued"], i)
        notes, payload = {}, []
        for g in found:
            ids = [i for i in g.doc_ids if i in present]
            for i in ids:
                notes[i] = (f"[MỚI NHẤT; sửa đổi/cập nhật: {', '.join(label(o) for o in ids[1:])}]" if i == ids[0]
                            else f"[CŨ HƠN; đã được sửa đổi/cập nhật bởi {label(ids[0])}]")
            payload.append([{"id": f"S{first[i][0]}", "docNo": first[i][1]["doc_no"], "issued": first[i][1]["issued"], "latest": i == ids[0]} for i in ids])
        return [notes.get(c["document_id"], "") for c in sources], payload
