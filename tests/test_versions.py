import pathlib
from app.store import NewChunk, Store
from app.version_service import VersionService
from app.versions import amendment_edges, groups, is_amendment

DOCS = [
    {"id": "66", "title": "Chương trình cho vay ưu đãi KHCN Có vốn trong tay - Kinh doanh vững bền", "issued": "01/01/2026", "doc_no": "66/X"},
    {"id": "549", "title": "Sửa đổi lãi suất Chương trình cho vay ưu đãi KHCN Có vốn trong tay - Kinh doanh vững bền", "issued": "12/02/2026", "doc_no": "549/X"},
    {"id": "1866", "title": "Sửa đổi lãi suất Chương trình cho vay ưu đãi KHCN Có vốn trong tay- Kinh doanh vững bền", "issued": "05/06/2026", "doc_no": "1866/X"},
    {"id": "1650", "title": "Triển khai chương trình cho vay ưu đãi tín dụng xanh đối với khách hàng cá nhân", "issued": "14/05/2026", "doc_no": "1650/X"},
]


def test_amendment_detection_by_title():
    assert is_amendment("Gia hạn thời gian triển khai Chương trình") and not is_amendment("Chương trình cho vay ưu đãi")


def test_edges_link_same_subject_only_and_only_to_older_documents():
    edges = set(amendment_edges(DOCS))
    assert edges == {("549", "66"), ("1866", "66"), ("1866", "549")}
    assert not any("1650" in e for e in edges)


def test_group_is_ordered_newest_first_and_respects_wanted():
    (g,) = groups(DOCS)
    assert g.doc_ids == ("1866", "549", "66") and g.latest == "1866"
    assert groups(DOCS, {"66"}) == []  # a single present version is not a conflict
    assert groups(DOCS, {"66", "549"})[0].doc_ids == ("549", "66")


class FakeRetriever:
    def rank(self, question, chunks):
        for c in chunks:
            c["score"] = 0.5
        return chunks


def chunk(doc, text="t"):
    return {"id": f"{doc}:0", "document_id": doc, "text": text, "doc_no": f"{doc}/X", "issued": next(d["issued"] for d in DOCS if d["id"] == doc), "score": 0.9}


def service(tmp_path: pathlib.Path) -> VersionService:
    store = Store(tmp_path / "t.db")
    for d in DOCS:
        store.upsert_document(d["id"], d["id"] + ".pdf", d["title"], "application/pdf", "x")
        store.update_document(d["id"], doc_no=d["doc_no"], issued=d["issued"], status="ready")
        store.replace_chunks(d["id"], [NewChunk("noi dung " + d["id"], None, 1, 1, b"", "noi dung")])
    return VersionService(store, FakeRetriever(), context_size=3)


def test_asked_question_pulls_in_missing_versions_and_keeps_context_size(tmp_path):
    svc = service(tmp_path)
    sources, labels, payload = svc.plan("chuong trinh co von trong tay lai suat", [chunk("66"), chunk("1650"), chunk("1650")])
    docs = [c["document_id"] for c in sources]
    assert len(sources) == 3 and {"1866", "549"} <= set(docs) and docs.count("1650") == 0
    assert payload and payload[0][0]["latest"]


def test_unrelated_question_is_left_alone_even_if_a_family_member_was_retrieved(tmp_path):
    svc = service(tmp_path)
    src = [chunk("1650"), chunk("66")]
    sources, labels, payload = svc.plan("tin dung xanh cho khach hang ca nhan", src)
    assert sources == src and payload == [] and labels == ["", ""]


def test_document_number_in_the_question_counts_as_asking(tmp_path):
    svc = service(tmp_path)
    _, _, payload = svc.plan("van ban 1866 thay the van ban nao", [chunk("1866"), chunk("66")])
    assert payload


def test_labels_mark_latest_and_older_and_list_versions_newest_first(tmp_path):
    svc = service(tmp_path)
    sources, labels, payload = svc.plan("van ban 549 va 1866 co von trong tay", [chunk("549"), chunk("66"), chunk("1866")])
    assert labels[2].startswith("[MỚI NHẤT") and "549/X" in labels[2]
    assert labels[0].startswith("[CŨ HƠN") and "1866/X" in labels[0]
    assert [(v["id"], v["latest"]) for v in payload[0]] == [("S3", True), ("S1", False), ("S2", False)]
