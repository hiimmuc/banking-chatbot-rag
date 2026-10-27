import re

TAGS = {"HỎI_LẠI": "clarify", "THIẾU_CĂN_CỨ": "insufficient", "TRẢ_LỜI": "answer", "NGOÀI_PHẠM_VI": "offscope"}
TAG_RE = re.compile(r"^\s*\[(HỎI_LẠI|THIẾU_CĂN_CỨ|TRẢ_LỜI|NGOÀI_PHẠM_VI)\]\s*")
NUM_RE = re.compile(r"\d[\d.,]*\d%?|\d%")
DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
CITE_RE = re.compile(r"\[(S\d+)\]")
PLACEHOLDER_RE = re.compile(r"<[^\W\d_][^<>\n]{0,38}>")


def split_tag(text: str) -> tuple[str, str]:
    """(mode, rest). Untagged text counts as an answer."""
    m = TAG_RE.match(text)
    return (TAGS[m.group(1)], text[m.end():]) if m else ("answer", text)


def strip_placeholders(text: str) -> str:
    return re.sub(r"[ \t]{2,}", " ", PLACEHOLDER_RE.sub("", text)).strip()


def audit(answer: str, context: str, source_count: int) -> list[str]:
    """Reasons an [TRẢ_LỜI] answer cannot be trusted; empty when it passes."""
    issues = []
    cited = set(CITE_RE.findall(answer))
    valid = {f"S{i}" for i in range(1, source_count + 1)}
    if not cited & valid:
        issues.append("câu trả lời không có trích dẫn nguồn hợp lệ")
    elif cited - valid:
        issues.append("có mã nguồn không tồn tại: " + ", ".join(sorted(cited - valid)))
    bad = unverified_numbers(answer, context)
    if bad:
        issues.append("số liệu không có trong nguồn: " + ", ".join(bad))
    return issues


def unverified_numbers(answer: str, context: str) -> list[str]:
    """Rates, amounts, dates and numbers in the answer that never appear in the sources."""
    ans = CITE_RE.sub("", answer)
    ctx = re.sub(r"\s+", "", context)
    ctx_nums = {n.lstrip("0") or "0" for n in re.findall(r"\d+", context)}
    bad = []
    for d, m, y in DATE_RE.findall(ans):  # sources often spell dates 'ngày 14 tháng 05 năm 2026'
        if not all((x.lstrip("0") or "0") in ctx_nums for x in (d, m, y)):
            bad.append(f"{d}/{m}/{y}")
    for n in dict.fromkeys(NUM_RE.findall(DATE_RE.sub("", ans))):
        n = n.rstrip(".,")
        if len(n) >= 2 and re.sub(r"\s+", "", n) not in ctx:
            bad.append(n)
    return bad

