"""Text extraction from uploaded files. Pure Python except PDF (pypdf); no external services."""
import csv
import html
import io
import json
import re
import zipfile
from xml.etree import ElementTree  # noqa: S405 - parses docx XML from a size-limited upload

TEXT_TYPES = {".txt", ".md", ".markdown", ".rst", ".log", ".py", ".js", ".ts", ".java", ".go", ".sql", ".yaml",
              ".yml", ".toml", ".ini", ".xml"}
SUPPORTED = sorted(TEXT_TYPES | {".pdf", ".docx", ".html", ".htm", ".csv", ".json"})


class UnsupportedDocument(ValueError):
    pass


def _ext(filename: str) -> str:
    return ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _html_to_text(s: str) -> str:
    s = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr|section|article)>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    return html.unescape(s)


def _docx_to_text(data: bytes) -> str:
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        info = z.getinfo("word/document.xml")
        if info.file_size > 50_000_000:
            raise UnsupportedDocument("document.xml is too large")
        root = ElementTree.fromstring(z.read(info))  # noqa: S314
    paras = []
    for p in root.iter(f"{ns}p"):
        paras.append("".join(t.text or "" for t in p.iter(f"{ns}t")))
    return "\n".join(paras)


def _pdf_to_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = []
    for i, page in enumerate(reader.pages):
        pages.append(f"[page {i + 1}]\n{page.extract_text() or ''}")
    return "\n\n".join(pages)


def extract_text(filename: str, data: bytes) -> str:
    ext = _ext(filename)
    if ext in TEXT_TYPES or ext == "":
        text = _decode(data)
    elif ext in (".html", ".htm"):
        text = _html_to_text(_decode(data))
    elif ext == ".csv":
        rows = list(csv.reader(io.StringIO(_decode(data))))
        header = rows[0] if rows else []
        text = "\n".join(", ".join(f"{h}: {v}" for h, v in zip(header, r, strict=False)) for r in rows[1:]) \
            if header else ""
    elif ext == ".json":
        text = json.dumps(json.loads(_decode(data)), indent=1, ensure_ascii=False)
    elif ext == ".docx":
        text = _docx_to_text(data)
    elif ext == ".pdf":
        text = _pdf_to_text(data)
    else:
        raise UnsupportedDocument(f"unsupported file type {ext}; supported: {', '.join(SUPPORTED)}")
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise UnsupportedDocument("no extractable text (scanned PDFs need OCR first)")
    return text


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Paragraph-aware chunks of about ``size`` characters with ``overlap`` characters of context."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    cur = ""
    for p in paras:
        while len(p) > size:  # very long paragraph: hard split on sentence/word boundary
            cut = max(p.rfind(". ", 0, size), p.rfind(" ", 0, size))
            cut = cut + 1 if cut > size // 2 else size
            pieces = [p[:cut].strip(), p[cut:].strip()]
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(pieces[0])
            p = pieces[1]
        if cur and len(cur) + len(p) + 2 > size:
            chunks.append(cur)
            tail = cur[-overlap:] if overlap else ""
            tail = tail[tail.find(" ") + 1:] if " " in tail else tail
            cur = f"{tail}\n\n{p}" if tail else p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        chunks.append(cur)
    return [c for c in chunks if c.strip()]
