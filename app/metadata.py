import re

_DOC_NO = re.compile(r"Số[:\s]*([0-9]+\s*/\s*[\w.]+(?:\s*-\s*[\w.]+)*)")
_ISSUED = re.compile(r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})")


def parse_meta(first_page: str) -> tuple[str | None, str | None]:
    """Document number and issue date (DD/MM/YYYY) from a circular's first page."""
    no, dt = _DOC_NO.search(first_page), _ISSUED.search(first_page)
    return (re.sub(r"\s+", "", no.group(1)) if no else None,
            f"{int(dt.group(1)):02d}/{int(dt.group(2)):02d}/{dt.group(3)}" if dt else None)


def doc_label(doc_no: str | None, issued: str | None, fallback: str) -> str:
    return f"Văn bản {doc_no or fallback}" + (f", ngày {issued}" if issued else "")


def chunk_label(chunk: dict) -> str:
    return doc_label(chunk["doc_no"], chunk["issued"], chunk["document_id"])
