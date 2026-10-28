"""Compare OCR engines page by page: text similarity and the numbers, dates and document numbers each one reads.

    python eval/ocr_compare.py            # reads data/ocr (MinerU), data/ocr_vintern1b, data/ocr_openai; writes eval/ocr_report.md
A token counts as 'supported' when at least one other engine reads it too; 'unsupported' tokens are likely misreads or inventions.
"""
import difflib, pathlib, re, statistics, zlib
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINES = {"mineru": ROOT / "data/ocr", "vintern1b": ROOT / "data/ocr_vintern1b", "openai": ROOT / "data/ocr_openai"}
TOKEN = re.compile(r"\d{1,2}/\d{1,2}/\d{4}|\d+/[A-Za-zĐđ][\w.\-]*|\d[\d.,]*\d%?|\d%?")


def canon(tok: str) -> str:
    """Same value, different typography: 7,7 = 7.7, 14/5/2026 = 14/05/2026."""
    tok = tok.replace(" ", "").replace(",", ".")
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", tok)
    return f"{int(m[1]):02d}/{int(m[2]):02d}/{m[3]}" if m else tok


def tokens(text: str) -> set[str]:
    return {canon(t) for t in TOKEN.findall(text) if len(t) > 1}


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[|#*\-:_]", " ", text)).strip().lower()


def repetitive(text: str) -> bool:
    return len(text) > 400 and len(zlib.compress(text.encode())) / len(text.encode()) < 0.12


pages = sorted(p.stem for p in ENGINES["mineru"].glob("*.md") if all((d / f"{p.stem}.md").exists() for d in ENGINES.values()))
FENCE = re.compile(r"^```(?:markdown)?\s*|\s*```$")
text = {e: {p: FENCE.sub("", (d / f"{p}.md").read_text(encoding="utf-8").strip()) for p in pages} for e, d in ENGINES.items()}
rows, stats = [], {e: Counter() for e in ENGINES}
bad = {e: [] for e in ENGINES}
for p in pages:
    tok = {e: tokens(text[e][p]) for e in ENGINES}
    for e in ENGINES:
        others = set().union(*(tok[o] for o in ENGINES if o != e))
        both = {t for o in ENGINES if o != e for t in tok[o] if all(t in tok[x] for x in ENGINES if x != e)}
        s = stats[e]
        s["tokens"] += len(tok[e]); s["unsupported"] += len(tok[e] - others)
        s["consensus_missed"] += len(both - tok[e]); s["consensus"] += len(both)
        s["rep"] += repetitive(text[e][p]); s["empty"] += len(text[e][p].strip()) < 50
        s["chars"] += len(text[e][p]); s["table_rows"] += sum(1 for l in text[e][p].splitlines() if l.lstrip().startswith("|")) + text[e][p].count("<tr>")
        bad[e] += [(p, t) for t in sorted(tok[e] - others)]
    sim = lambda a, b: difflib.SequenceMatcher(None, norm(text[a][p]), norm(text[b][p]), autojunk=False).ratio()
    rows.append((p, sim("vintern1b", "mineru"), sim("vintern1b", "openai"), sim("mineru", "openai")))

mean = lambda i: statistics.mean(r[i] for r in rows)
out = [f"# So sánh OCR trên {len(pages)} trang\n", "Độ giống văn bản (0 đến 1, trung bình theo trang):\n",
       "| Cặp | Trung bình | Thấp nhất |", "|---|---|---|"]
for name, i in (("Vintern-1B và MinerU", 1), ("Vintern-1B và OpenAI", 2), ("MinerU và OpenAI", 3)):
    out.append(f"| {name} | {mean(i):.2f} | {min(r[i] for r in rows):.2f} |")
ref = [r for r in rows if r[3] >= 0.9]
out += ["", f"Trên {len(ref)} trang MinerU và OpenAI giống nhau từ 0,9 trở lên (tham chiếu đáng tin hơn): Vintern-1B giống MinerU trung bình {statistics.mean(r[1] for r in ref):.2f}, giống OpenAI {statistics.mean(r[2] for r in ref):.2f}."]
out += ["", "Số liệu (số, ngày, số hiệu văn bản). *Không được ủng hộ* = chỉ engine này đọc ra, hai engine kia không; *bỏ sót* = hai engine kia cùng đọc ra mà engine này không.\n",
        "| Engine | Token | Không được ủng hộ | Bỏ sót so với đồng thuận | Trang lặp chữ | Trang rỗng | Dòng bảng |", "|---|---|---|---|---|---|---|"]
for e, s in stats.items():
    out.append(f"| {e} | {s['tokens']} | {s['unsupported']} ({s['unsupported'] / max(1, s['tokens']):.1%}) | {s['consensus_missed']} / {s['consensus']} ({s['consensus_missed'] / max(1, s['consensus']):.1%}) | {s['rep']} | {s['empty']} | {s['table_rows']} |")
out += ["", "## Trang Vintern-1B khác MinerU nhiều nhất\n", "| Trang | Vintern–MinerU | Vintern–OpenAI | MinerU–OpenAI |", "|---|---|---|---|"]
out += [f"| {r[0]} | {r[1]:.2f} | {r[2]:.2f} | {r[3]:.2f} |" for r in sorted(rows, key=lambda r: r[1])[:10]]
for e in ("vintern1b", "mineru", "openai"):
    out += ["", f"## Token chỉ {e} đọc ra (20 đầu)\n", ", ".join(f"`{t}` ({p})" for p, t in bad[e][:20]) or "không có"]
(ROOT / "eval/ocr_report.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out[:22]))
