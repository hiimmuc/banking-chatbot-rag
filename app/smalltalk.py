import re
from .config import BRANDING
from .textnorm import fold

_FILLER = {"oi", "a", "nhe", "nha", "ban", "em", "anh", "chi", "bot", "robot", "ad", "admin", "xin", "please"}


def _key(text: str) -> str:
    words = re.sub(r"[^\w\s]", " ", fold(text)).split()
    return " ".join(w for w in words if w not in _FILLER)

_GREET = {"hi", "hello", "hey", "chao", "alo", "xin chao", "chao buoi sang", "chao buoi chieu", "chao buoi toi", "hello there", "good morning", "hi there"}
_THANKS = {"cam on", "thanks", "thank you", "thank", "cam on nhieu", "cam on rat nhieu", "tks", "ok cam on", "ok"}
_BYE = {"tam biet", "bye", "goodbye", "hen gap lai", "bye bye"}
_WHO = {"ban la ai", "who are you", "ban ten gi", "ten gi", "ten la gi", "ban ten la gi", "ban la bot a", "ban la robot", "gioi thieu", "gioi thieu ve ban", "ban la gi"}
_CAN = {"ban lam duoc gi", "lam duoc gi", "giup duoc gi", "ban giup duoc gi", "ban co the lam gi", "help", "huong dan", "huong dan su dung", "what can you do", "ban co the cung cap thong tin ve gi", "cung cap thong tin ve gi", "ban biet gi", "ban co the tra cuu gi", "tra cuu duoc gi", "co the hoi gi", "hoi duoc gi"}

_GREET, _THANKS, _BYE, _WHO_CAN = ({_key(p) for p in s} for s in (_GREET, _THANKS, _BYE, _WHO | _CAN))


OUT_OF_SCOPE_REPLY = "Dạ, em chưa được thiết lập để trả lời câu hỏi này ạ. Anh/chị hỏi về văn bản nghiệp vụ trong tài liệu đã tải lên giúp em nhé."


def about() -> str:
    org = f" của {BRANDING.org_name}" if BRANDING.org_name else ""
    return (f"Dạ, em là trợ lý tra cứu văn bản nghiệp vụ{org}. Em trả lời theo các tài liệu đã tải lên, kèm nguồn và số trang để anh/chị đối chiếu. "
            "Anh/chị thử hỏi về lãi suất, điều kiện hay thời hạn vay xem ạ.")


def smalltalk(question: str) -> str | None:
    """Fixed reply for greetings and bot questions, None when the text is a real question. A leading greeting is ignored: "Hello, bạn là ai?"."""
    k = _key(question)
    words = k.split()
    for i in (1, 2):
        if k not in _GREET and " ".join(words[:i]) in _GREET and len(words) > i:
            rest = _reply(" ".join(words[i:]))
            if rest:
                return rest
    return _reply(k)


_CAN_RE = re.compile(r"(co the )?(cung cap|giup|ho tro|tra cuu|lam|biet|hoi)( duoc)?( thong tin)?( ve)? gi")


def _reply(k: str) -> str | None:
    if k in _GREET:
        return "Dạ, em chào anh/chị ạ! Anh/chị cần tra cứu văn bản nào, cứ hỏi em nhé."
    if k in _THANKS:
        return "Dạ, không có gì ạ. Anh/chị cần tra cứu thêm gì cứ hỏi em."
    if k in _BYE:
        return "Dạ, chào anh/chị ạ. Khi cần tra cứu văn bản, anh/chị quay lại hỏi em nhé."
    return about() if k in _WHO_CAN or (len(k.split()) <= 7 and _CAN_RE.fullmatch(k)) else None
