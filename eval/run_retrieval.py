"""Retrieval eval: expected doc in top-6 context and (when given) the fact string inside the retrieved chunks."""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.container import get_container
from app.textnorm import fold

retrieve = get_container().retriever.retrieve
qs = json.load(open(pathlib.Path(__file__).with_name("questions.json")))
bad = 0
for i, t in enumerate(qs, 1):
    if not t["docs"]: continue
    got = retrieve(t["q"])
    ids = [c["document_id"] for c in got]
    hit_docs = all(d in ids for d in t["docs"]) if len(t["docs"]) > 1 and t.get("fact") is None else any(d in ids for d in t["docs"])
    hit_fact = t["fact"] is None or any(fold(t["fact"]).replace(" ", "") in fold(c["text"]).replace(" ", "") for c in got if c["document_id"] in t["docs"])
    ok = hit_docs and hit_fact; bad += not ok
    print(f"{'PASS' if ok else 'FAIL'} #{i} doc={hit_docs} fact={hit_fact} top={ids}  {t['q'][:60]}")
print(f"\n{len(qs)-bad-1}/{len(qs)-1} retrieval pass"); sys.exit(1 if bad else 0)
