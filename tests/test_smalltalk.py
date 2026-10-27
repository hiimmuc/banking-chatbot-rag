import pytest
from app.smalltalk import smalltalk


@pytest.mark.parametrize("q", ["Hello", "hi!", "Xin chào", "chào bạn ạ", "Cảm ơn nhé", "thanks", "Bạn là ai?", "Bạn có thể cung cấp thông tin gì?", "bạn giúp được gì", "Hello, bạn là ai?", "chào em, bạn tên là gì", "bạn tên là gì", "Tên là gì", "bạn làm được gì", "tạm biệt"])
def test_smalltalk_gets_fixed_reply(q):
    assert smalltalk(q)


@pytest.mark.parametrize("q", ["Hello, lãi suất vay là bao nhiêu?", "chào, bạn là ai mà biết lãi suất", "chào anh, điều kiện vay ưu đãi", "Lãi suất", "ok thì sao về thời hạn vay"])
def test_real_questions_fall_through(q):
    assert smalltalk(q) is None
