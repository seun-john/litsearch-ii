"""The one paper shape every source is converted into."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


class LitSearchError(Exception):
    """A problem the caller can act on (bad identifier, unknown paper, source unavailable)."""


@dataclass
class Paper:
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    abstract: str | None = None
    citations: int | None = None
    is_open_access: bool | None = None
    open_access_url: str | None = None
    url: str | None = None
    type: str | None = None
    ids: dict[str, str] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
    score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready dict without empty values."""
        raw = {
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "venue": self.venue,
            "doi": self.doi,
            "abstract": self.abstract,
            "citations": self.citations,
            "is_open_access": self.is_open_access,
            "open_access_url": self.open_access_url,
            "url": self.url,
            "type": self.type,
            "ids": self.ids,
            "sources": self.sources,
            "score": None if self.score is None else round(self.score, 4),
        }
        return {k: v for k, v in raw.items() if v not in (None, [], {}, "")}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Paper:
        """Rebuild a Paper from `to_dict` output (used by export)."""
        if not isinstance(data, dict) or not str(data.get("title", "")).strip():
            raise LitSearchError("each paper needs at least a title")
        year = data.get("year")
        return cls(
            title=str(data["title"]).strip(),
            authors=[str(a) for a in data.get("authors", []) if str(a).strip()],
            year=int(year) if str(year).isdigit() else None,
            venue=data.get("venue"),
            doi=normalise_doi(data.get("doi")),
            abstract=data.get("abstract"),
            citations=data.get("citations") if isinstance(data.get("citations"), int) else None,
            is_open_access=data.get("is_open_access"),
            open_access_url=data.get("open_access_url"),
            url=data.get("url"),
            type=data.get("type"),
            ids={str(k): str(v) for k, v in (data.get("ids") or {}).items()},
            sources=[str(s) for s in data.get("sources", [])],
        )


DOI_PREFIX = re.compile(r"^(?:https?://)?(?:dx\.)?doi\.org/|^doi:\s*", re.I)


def normalise_doi(value: Any) -> str | None:
    """Lowercase DOI without URL or 'doi:' prefix and without trailing punctuation."""
    if not value:
        return None
    text = DOI_PREFIX.sub("", str(value).strip()).rstrip(".,;)").lower()
    return text if re.fullmatch(r"10\.\d+/\S+", text) else None


def clean_text(value: Any) -> str | None:
    """Strip markup and collapse whitespace; None for empty."""
    if value is None:
        return None
    # Block-level tags separate words; inline tags (<b>, <i>, <sup>) must not add spaces.
    text = re.sub(
        r"</?(?:br|p|div|li|ul|ol|h\d|title|sec|jats:p|jats:title|jats:sec)[^>]*>",
        " ",
        str(value),
        flags=re.I,
    )
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def parse_year(value: Any) -> int | None:
    match = re.search(r"(?<!\d)(1[5-9]\d{2}|20\d{2})(?!\d)", str(value or ""))
    return int(match.group()) if match else None
