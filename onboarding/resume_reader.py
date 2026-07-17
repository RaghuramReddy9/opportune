"""Read text from common resume file formats without remote processing."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

_MAX_BYTES = 5 * 1024 * 1024


def extract_resume_text(filename: str, content: bytes) -> str:
    if len(content) > _MAX_BYTES:
        raise ValueError("Resume files must be 5 MB or smaller")
    suffix = Path(filename or "resume.txt").suffix.lower()
    if suffix in {".txt", ".md", ".markdown"}:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
    elif suffix == ".pdf":
        try:
            import pymupdf
        except ImportError as exc:
            raise ValueError("PDF support is not installed") from exc
        try:
            document = pymupdf.open(stream=content, filetype="pdf")
            text = "\n".join(page.get_text("text") for page in document)
        except Exception as exc:
            raise ValueError("This PDF could not be read") from exc
        if len(text.strip()) < 20:
            raise ValueError("This PDF appears to be scanned. Paste the resume text instead.")
    elif suffix == ".docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise ValueError("DOCX support is not installed") from exc
        try:
            document = Document(BytesIO(content))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        except Exception as exc:
            raise ValueError("This DOCX file could not be read") from exc
    else:
        raise ValueError("Use a PDF, DOCX, TXT, or Markdown resume")
    clean = text.strip()
    if len(clean) < 20:
        raise ValueError("We could not find enough resume text to analyze")
    return clean
