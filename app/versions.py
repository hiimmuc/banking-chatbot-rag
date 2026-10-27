import re
from dataclasses import dataclass
from .textnorm import fold

AMENDMENT = re.compile(r"\b(sua doi|dieu chinh|gia han|bo sung|thay the)\b")
IGNORED = {"sua", "doi", "dieu", "chinh", "gia", "han", "bo", "sung", "thay", "the", "hieu", "luc", "thoi", "gian", "trien", "khai", "ve", "cua", "cho", "va", "voi"}
SAME_SUBJECT = 0.6  # Jaccard of title words; keeps unrelated loan programs apart


def _date_key(issued: str | None) -> tuple:
    d, m, y = (issued or "00/00/0000").split("/")
    return (y, m, d)


def _subject(title: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", fold(title)) if t not in IGNORED and len(t) > 1}


def is_amendment(title: str) -> bool:
    return bool(AMENDMENT.search(fold(title)))


def amendment_edges(docs: list[dict]) -> list[tuple[str, str]]:
    """(newer_id, older_id): an amending circular and an earlier one about the same subject."""
    edges = []
    for new in docs:
        if not is_amendment(new["title"] or ""):
            continue
        for old in docs:
            if old is new or _date_key(old["issued"]) >= _date_key(new["issued"]):
                continue
            a, b = _subject(new["title"]), _subject(old["title"] or "")
            if a and b and len(a & b) / len(a | b) >= SAME_SUBJECT:
                edges.append((new["id"], old["id"]))
    return edges


@dataclass(frozen=True)
class VersionGroup:
    """Documents connected by amendments, newest first."""
    doc_ids: tuple[str, ...]

    @property
    def latest(self) -> str:
        return self.doc_ids[0]


def groups(docs: list[dict], wanted: set[str] | None = None) -> list[VersionGroup]:
    """Connected components of the amendment graph (size >= 2), restricted to `wanted` ids when given."""
    by_id = {d["id"]: d for d in docs}
    parent = {i: i for i in by_id}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for new, old in amendment_edges(docs):
        parent[find(new)] = find(old)
    members: dict[str, list[str]] = {}
    for i in by_id:
        if wanted is None or i in wanted:
            members.setdefault(find(i), []).append(i)
    return [VersionGroup(tuple(sorted(ids, key=lambda i: _date_key(by_id[i]["issued"]), reverse=True)))
            for ids in members.values() if len(ids) > 1]
