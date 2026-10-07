"""Parse XML from the internet without entity tricks."""

from __future__ import annotations

import re
from xml.etree import ElementTree as ET

from .models import LitSearchError

DANGEROUS = re.compile(r"<!\s*(?:ENTITY|DOCTYPE[^>]*\[)", re.I)


def parse_xml(text: str) -> ET.Element:
    """Parse XML, refusing entity declarations (billion-laughs, external entities)."""
    if DANGEROUS.search(text):
        raise LitSearchError("refusing XML that declares entities")
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        raise LitSearchError(f"the source returned malformed XML ({exc})") from None


def strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def text_of(element: ET.Element | None) -> str | None:
    """All text inside an element, whitespace collapsed."""
    if element is None:
        return None
    joined = re.sub(r"\s+", " ", "".join(element.itertext())).strip()
    return joined or None
