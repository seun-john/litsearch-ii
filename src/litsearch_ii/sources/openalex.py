"""OpenAlex: broad coverage, citation links and open-access locations. No key needed."""

from __future__ import annotations

from typing import Any

from ..http import Http
from ..identifiers import Identifier
from ..models import LitSearchError, Paper, clean_text, normalise_doi

BASE = "https://api.openalex.org"
FIELDS = (
    "id,doi,title,publication_year,cited_by_count,open_access,authorships,primary_location,"
    "abstract_inverted_index,type,ids,referenced_works,related_works"
)
NAME = "openalex"


def rebuild_abstract(index: dict[str, list[int]] | None) -> str | None:
    """OpenAlex ships abstracts as {word: [positions]}; put them back in order."""
    if not index:
        return None
    slots: dict[int, str] = {}
    for word, positions in index.items():
        for pos in positions:
            slots[pos] = word
    return " ".join(slots[i] for i in sorted(slots)) or None


def to_paper(work: dict[str, Any]) -> Paper:
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    access = work.get("open_access") or {}
    ids = {"openalex": str(work.get("id", "")).rsplit("/", 1)[-1]}
    raw_ids = work.get("ids") or {}
    if raw_ids.get("pmid"):
        ids["pmid"] = str(raw_ids["pmid"]).rstrip("/").rsplit("/", 1)[-1]
    if raw_ids.get("pmcid"):
        ids["pmcid"] = str(raw_ids["pmcid"]).rstrip("/").rsplit("/", 1)[-1]
    doi = normalise_doi(work.get("doi"))
    return Paper(
        title=clean_text(work.get("title")) or "(untitled)",
        authors=[
            a["author"]["display_name"]
            for a in work.get("authorships", [])
            if (a.get("author") or {}).get("display_name")
        ],
        year=work.get("publication_year"),
        venue=source.get("display_name"),
        doi=doi,
        abstract=clean_text(rebuild_abstract(work.get("abstract_inverted_index"))),
        citations=work.get("cited_by_count"),
        is_open_access=access.get("is_oa"),
        open_access_url=access.get("oa_url"),
        url=location.get("landing_page_url") or (f"https://doi.org/{doi}" if doi else None),
        type=work.get("type"),
        ids=ids,
        sources=[NAME],
    )


def _filters(
    year_from: int | None, year_to: int | None, open_access_only: bool, country: str | None
) -> str:
    parts = []
    if year_from or year_to:
        parts.append(f"publication_year:{year_from or ''}-{year_to or ''}")
    if open_access_only:
        parts.append("is_oa:true")
    if country:
        parts.append(f"authorships.institutions.country_code:{country.upper()}")
    return ",".join(parts)


async def search(
    http: Http,
    query: str,
    limit: int,
    *,
    year_from: int | None = None,
    year_to: int | None = None,
    open_access_only: bool = False,
    country: str | None = None,
) -> list[Paper]:
    data = await http.get(
        f"{BASE}/works",
        {
            "search": query,
            "per-page": limit,
            "select": FIELDS,
            "filter": _filters(year_from, year_to, open_access_only, country) or None,
        },
    )
    return [to_paper(w) for w in data.get("results", [])]


def _work_path(ident: Identifier) -> str:
    if ident.kind == "openalex":
        return ident.value
    doi = ident.doi_form()
    if doi:
        return f"doi:{doi}"
    if ident.kind == "pmid":
        return f"pmid:{ident.value}"
    if ident.kind == "pmcid":
        return f"pmcid:{ident.value}"
    raise LitSearchError(f"OpenAlex cannot look up a {ident.kind} identifier")


async def get_work(http: Http, ident: Identifier) -> dict[str, Any]:
    return dict(await http.get(f"{BASE}/works/{_work_path(ident)}", {"select": FIELDS}))


async def get(http: Http, ident: Identifier) -> Paper:
    return to_paper(await get_work(http, ident))


async def citing(http: Http, ident: Identifier, limit: int) -> list[Paper]:
    work = await get_work(http, ident)
    short = str(work["id"]).rsplit("/", 1)[-1]
    data = await http.get(
        f"{BASE}/works",
        {
            "filter": f"cites:{short}",
            "per-page": limit,
            "select": FIELDS,
            "sort": "cited_by_count:desc",
        },
    )
    return [to_paper(w) for w in data.get("results", [])]


async def _many(http: Http, urls: list[str], limit: int) -> list[Paper]:
    ids = [u.rsplit("/", 1)[-1] for u in urls[:limit]]
    if not ids:
        return []
    data = await http.get(
        f"{BASE}/works",
        {"filter": "openalex:" + "|".join(ids), "per-page": min(len(ids), 100), "select": FIELDS},
    )
    return [to_paper(w) for w in data.get("results", [])]


async def references(http: Http, ident: Identifier, limit: int) -> list[Paper]:
    work = await get_work(http, ident)
    return await _many(http, work.get("referenced_works", []), min(limit, 100))


async def related(http: Http, ident: Identifier, limit: int) -> list[Paper]:
    work = await get_work(http, ident)
    return await _many(http, work.get("related_works", []), min(limit, 100))
