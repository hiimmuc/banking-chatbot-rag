from app.answer_guard import has_valid_citation, split_tag, unverified_numbers

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
    assert has_valid_citation("x [S2]", 3)
    assert not has_valid_citation("x [S4]", 3)
    assert not has_valid_citation("x", 3)
