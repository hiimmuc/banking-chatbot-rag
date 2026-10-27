from app.chunking import chunk_pages, html_tables_to_md
from app.metadata import parse_meta
from app.textnorm import fold, fts_query


def test_fold_removes_diacritics_and_d_stroke():
    assert fold("Lãi suất đối với") == "lai suat doi voi"


def test_fts_query_never_passes_syntax_through():
    import re
    q = fts_query('lãi" OR NEAR(x) -- * ^ :col')
    assert re.fullmatch(r'"[a-z0-9]+"( OR "[a-z0-9]+")*', q), q
    assert fts_query("!!! ??") == ""


def test_parse_meta():
    assert parse_meta("Số: 549 /NHNo.TH-KHCN\nThanh Hóa, ngày 12 tháng 02 năm 2026") == ("549/NHNo.TH-KHCN", "12/02/2026")
    assert parse_meta("không có gì") == (None, None)


def test_table_stays_in_one_chunk_and_html_becomes_markdown():
    md = html_tables_to_md("<table><tr><td>A</td><td>B</td></tr><tr><td>1</td><td>2</td></tr></table>")
    assert md.splitlines()[0] == "| A | B |"
    chunks = chunk_pages(["Điều 1. Phạm vi\n\nNội dung.\n\n" + md])
    assert any("| A | B |" in c["text"] for c in chunks)
