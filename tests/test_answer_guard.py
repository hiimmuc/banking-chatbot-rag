from app.answer_guard import audit, split_tag, strip_placeholders, unverified_numbers

CTX = "lãi suất cho vay ưu đãi là 6%/năm, văn bản 549/NHNo.TH ngày 12/02/2026, 1,25%"


def test_split_tag():
    assert split_tag("[HỎI_LẠI] Kỳ hạn nào?") == ("clarify", "Kỳ hạn nào?")
    assert split_tag("[THIẾU_CĂN_CỨ] x")[0] == "insufficient"
    assert split_tag("Lãi suất 6%") == ("answer", "Lãi suất 6%")


def test_numbers_found_in_sources_pass():
    assert unverified_numbers("Lãi suất 6% [S1], NIM 1,25% ngày 12/02/2026", CTX) == []


def test_invented_number_is_flagged():
    assert unverified_numbers("Lãi suất 7,5% [S1]", CTX) == ["7,5%"]


def test_date_spelled_out_in_source():
    assert unverified_numbers("ngày 14/05/2026", "ngày 14 tháng 05 năm 2026") == []
    assert unverified_numbers("ngày 14/06/2026", "ngày 14 tháng 05 năm 2026") == ["14/06/2026"]


def test_citation_must_reference_a_real_source():
    assert audit("x [S2]", "", 3) == []
    assert audit("x [S4]", "", 3) and "S4" in audit("x [S1] [S4]", "", 3)[0]
    assert "trích dẫn" in audit("x", "", 3)[0]


def test_placeholders_are_stripped_but_comparisons_stay():
    assert strip_placeholders("<kết luận> Khoản vay [S1]") == "Khoản vay [S1]"
    assert strip_placeholders("Lãi suất < 6% và > 4% [S1]") == "Lãi suất < 6% và > 4% [S1]"
