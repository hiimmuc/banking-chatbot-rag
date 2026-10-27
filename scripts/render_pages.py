import pymupdf, pathlib, re
raw = pathlib.Path("data/raw"); out = pathlib.Path("data/pages"); out.mkdir(parents=True, exist_ok=True)
for pdf in sorted(raw.glob("*.pdf")):
    doc_id = re.match(r"(\d+[A-Z]+)", pdf.name).group(1)
    for i, page in enumerate(pymupdf.open(pdf), 1):
        page.get_pixmap(dpi=200).save(out / f"{doc_id}_p{i:02d}.png")
print(len(list(out.glob("*.png"))), "pages")
