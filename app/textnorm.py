import re, unicodedata

def fold(s: str) -> str:
    """Lowercase, strip diacritics (incl. đ) so 'lãi suất' matches 'lai suat'."""
    s = unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()

def fts_query(q: str) -> str:
    """Escape user text into an OR of quoted tokens; never passes FTS syntax through."""
    toks = re.findall(r"[0-9a-z]+", fold(q))
    return " OR ".join(f'"{t}"' for t in dict.fromkeys(toks) if len(t) > 1)
