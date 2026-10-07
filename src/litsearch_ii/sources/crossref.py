"""Crossref: the authority for DOIs and publisher metadata. No key needed."""

from __future__ import annotations

from typing import Any

from ..http import Http
from ..models import Paper, clean_text, normalise_doi, parse_year

BASE = "https://api.crossref.org"
FIELDS = "DOI,title,author,issued,container-title,is-referenced-by-count,type,abstract,URL,license"
NAME = "crossref"


def _authors(item: dict[str, Any]) -> list[str]:
    names = []
    for a in item.get("author", []):
        full = " ".join(p for p in (a.get("given"), a.get("family")) if p) or a.get("name")
        if full:
            names.append(full)
    return names


def to_paper(item: dict[str, Any]) -> Paper:
    issued = (item.get("issued") or {}).get("date-parts") or [[None]]
    doi = normalise_doi(item.get("DOI"))
    return Paper(
        title=clean_text((item.get("title") or [""])[0]) or "(untitled)",
        authors=_authors(item),
        year=parse_year(issued[0][0] if issued and issued[0] else None),
        venue=clean_text((item.get("container-title") or [None])[0]),
        doi=doi,
        abstract=clean_text(item.get("abstract")),
        citations=item.get("is-referenced-by-count"),
        url=item.get("URL") or (f"https://doi.org/{doi}" if doi else None),
        type=item.get("type"),
        ids={},
        sources=[NAME],
    )


async def search(
    http: Http,
    query: str,
    limit: int,
    *,
    year_from: int | None = None,
    year_to: int | None = None,
) -> list[Paper]:
    filters = []
    if year_from:
        filters.append(f"from-pub-date:{year_from}")
    if year_to:
        filters.append(f"until-pub-date:{year_to}")
    data = await http.get(
        f"{BASE}/works",
        {
            "query": query,
            "rows": limit,
            "select": FIELDS,
            "filter": ",".join(filters) or None,
        },
    )
    return [to_paper(i) for i in data.get("message", {}).get("items", [])]


async def get(http: Http, doi: str) -> Paper:
    data = await http.get(f"{BASE}/works/{doi}")
    return to_paper(data["message"])
