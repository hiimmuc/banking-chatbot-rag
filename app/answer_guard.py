import re

TAGS = {"HỎI_LẠI": "clarify", "THIẾU_CĂN_CỨ": "insufficient", "TRẢ_LỜI": "answer"}
TAG_RE = re.compile(r"^\s*\[(HỎI_LẠI|THIẾU_CĂN_CỨ|TRẢ_LỜI)\]\s*")
NUM_RE = re.compile(r"\d[\d.,]*\d%?|\d%")
DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
CITE_RE = re.compile(r"\[(S\d+)\]")


def split_tag(text: str) -> tuple[str, str]:
    """(mode, rest). Untagged text counts as an answer."""
    m = TAG_RE.match(text)
    return (TAGS[m.group(1)], text[m.end():]) if m else ("answer", text)


def has_valid_citation(answer: str, source_count: int) -> bool:
    return bool(set(CITE_RE.findall(answer)) & {f"S{i}" for i in range(1, source_count + 1)})


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

