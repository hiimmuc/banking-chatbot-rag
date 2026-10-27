import re
from html.parser import HTMLParser

class _Table(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows = []; self.cur = None; self.cell = None
    def handle_starttag(self, tag, attrs):
        if tag == "tr": self.cur = []
        elif tag in ("td", "th"): self.cell = []
    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.cur is not None:
            self.cur.append(" ".join("".join(self.cell).split()).replace("|", "/")); self.cell = None
        elif tag == "tr" and self.cur is not None:
            self.rows.append(self.cur); self.cur = None
    def handle_data(self, d):
        if self.cell is not None: self.cell.append(d)

def html_tables_to_md(text: str) -> str:
    def conv(m):
        p = _Table(); p.feed(m.group(0)); rows = [r for r in p.rows if r]
        if not rows: return ""
        w = max(len(r) for r in rows); rows = [r + [""] * (w - len(r)) for r in rows]
        lines = ["| " + " | ".join(r) + " |" for r in rows]
        lines.insert(1, "|" + "---|" * w)
        return "\n".join(lines)
    return re.sub(r"<table.*?</table>", conv, text, flags=re.S | re.I)

HEAD = re.compile(r"^(Điều\s+\d+|[IVX]+\.\s|\d+\.\s+\S|[a-zđ]\)\s)")
MAX_CHARS, MIN_CHARS = 1400, 500

def split_table(block: str, limit: int):
    """Tables stay whole unless over the limit; then split by rows, repeating the header."""
    if len(block) <= limit: return [block]
    lines = block.split("\n"); head, rows = lines[:2], lines[2:]
    out, cur = [], []
    for r in rows:
        if cur and len("\n".join(head + cur + [r])) > limit: out.append("\n".join(head + cur)); cur = []
        cur.append(r)
    if cur: out.append("\n".join(head + cur))
    return out

def chunk_pages(pages: list[str]):
    """pages: text per page (1-indexed by position). Returns [{text, heading, page_start, page_end}]."""
    units = []  # (page, text, is_table)
    for pno, txt in enumerate(pages, 1):
        for blk in re.split(r"\n\s*\n", html_tables_to_md(txt)):
            blk = blk.strip()
            if not blk: continue
            if blk.startswith("|"):
                units += [(pno, t, True) for t in split_table(blk, 2400)]
            else:
                units.append((pno, blk, False))
    chunks, cur, heading, cur_head = [], [], None, None

    def flush():
        nonlocal cur, cur_head
        if cur:
            chunks.append({"text": "\n\n".join(t for _, t in cur), "heading": cur_head,
                           "page_start": cur[0][0], "page_end": cur[-1][0]})
        cur, cur_head = [], heading

    for pno, t, is_tab in units:
        first = t.split("\n", 1)[0]
        is_head = bool(HEAD.match(first)) and not is_tab and len(first) < 160
        size = sum(len(x) for _, x in cur)
        if cur and (size + len(t) > MAX_CHARS or (is_head and size >= MIN_CHARS) or is_tab or (cur and cur[-1][1].startswith("|"))):
            flush()
        if is_head and not is_tab: heading = first[:120]
        if not cur: cur_head = heading
        cur.append((pno, t))
    flush()
    return chunks
