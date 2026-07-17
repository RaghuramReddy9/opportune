"""Privacy-preserving resume cleanup before a remote model sees career text."""
from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"
)
_ADDRESS_LINE_RE = re.compile(
    r"^\s*\d{1,6}\s+[^\n,]{2,60}\b(?:street|st|avenue|ave|road|rd|boulevard|blvd|lane|ln|drive|dr|court|ct|way)\b.*(?:\d{5}(?:-\d{4})?)?\s*$",
    re.IGNORECASE,
)
_CONTACT_LABEL_RE = re.compile(
    r"^\s*(?:email|phone|mobile|address)\s*:\s*.*$",
    re.IGNORECASE,
)


def sanitize_resume_for_remote(text: str) -> str:
    """Remove common contact details while preserving career evidence."""
    clean_lines: list[str] = []
    for raw_line in str(text or "").splitlines():
        if _ADDRESS_LINE_RE.match(raw_line) or _CONTACT_LABEL_RE.match(raw_line):
            continue
        line = _EMAIL_RE.sub("", raw_line)
        line = _PHONE_RE.sub("", line)
        line = re.sub(r"\s*\|\s*(?=\||$)", "", line)
        line = re.sub(r"\s{2,}", " ", line).strip(" |·-")
        if line:
            clean_lines.append(line)
    return "\n".join(clean_lines).strip()
