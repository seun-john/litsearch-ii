"""Europe PMC: biomedical and life-science literature, with open-access full text. No key needed."""

from __future__ import annotations

import re
from typing import Any

from ..http import Http
from ..identifiers import Identifier
from ..models import LitSearchError, Paper, clean_text, normalise_doi, parse_year
from ..xmlsafe import parse_xml, strip_ns, text_of

BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
NAME = "europepmc"


def to_paper(item: dict[str, Any]) -> Paper:
    ids: dict[str, str] = {}
    if item.get("pmid"):
        ids["pmid"] = str(item["pmid"])
    if item.get("pmcid"):
        ids["pmcid"] = str(item["pmcid"])
    authors = [
        a.get("fullName", "")
        for a in (item.get("authorList") or {}).get("author", [])
        if a.get("fullName")
    ]
    if not authors and item.get("authorString"):
        authors = [a.strip() for a in str(item["authorString"]).rstrip(".").split(",") if a.strip()]
    doi = normalise_doi(item.get("doi"))
    journal = (item.get("journalInfo") or {}).get("journal", {}).get("title") or item.get(
        "bookOrReportDetails", {}
    ).get("publisher")
    free = item.get("isOpenAccess") == "Y"
    pmcid = ids.get("pmcid")
    link = None
    for entry in (item.get("fullTextUrlList") or {}).get("fullTextUrl", []):
        if entry.get("availabilityCode") == "OA" and entry.get("url"):
            link = entry["url"]
            break
    if not link and free and pmcid:
        link = f"https://europepmc.org/article/PMC/{pmcid}"
    src, ident = item.get("source"), item.get("id")
    return Paper(
        title=clean_text(item.get("title")) or "(untitled)",
        authors=authors,
        year=parse_year(item.get("pubYear")),
        venue=clean_text(journal),
        doi=doi,
        abstract=clean_text(item.get("abstractText")),
        citations=item.get("citedByCount"),
        is_open_access=free,
        open_access_url=link,
        url=f"https://europepmc.org/article/{src}/{ident}" if src and ident else None,
        type=item.get("pubType"),
        ids=ids,
        sources=[NAME],
    )


async def search(
    http: Http,
    query: str,
    limit: int,
    *,
    year_from: int | None = None,
    year_to: int | None = None,
    open_access_only: bool = False,
) -> list[Paper]:
    q = query
    if year_from or year_to:
        q += f" AND (PUB_YEAR:[{year_from or 1500} TO {year_to or 2100}])"
    if open_access_only:
        q += " AND OPEN_ACCESS:y"
    data = await http.get(
        f"{BASE}/search",
        {"query": q, "format": "json", "pageSize": limit, "resultType": "core"},
    )
    return [to_paper(i) for i in data.get("resultList", {}).get("result", [])]


def _query_for(ident: Identifier) -> str:
    if ident.kind == "pmid":
        return f"EXT_ID:{ident.value} AND SRC:MED"
    if ident.kind == "pmcid":
        return f"PMCID:{ident.value}"
    doi = ident.doi_form()
    if doi:
        return f'DOI:"{doi}"'
    raise LitSearchError(f"Europe PMC cannot look up a {ident.kind} identifier")


async def get(http: Http, ident: Identifier) -> Paper:
    data = await http.get(
        f"{BASE}/search",
        {"query": _query_for(ident), "format": "json", "pageSize": 1, "resultType": "core"},
    )
    results = data.get("resultList", {}).get("result", [])
    if not results:
        raise LitSearchError("Europe PMC: not found")
    return to_paper(results[0])


async def fulltext(http: Http, pmcid: str, max_chars: int) -> dict[str, Any]:
    """Open-access full text as plain paragraphs. Only PMC open-access articles have it."""
    if not re.fullmatch(r"PMC\d+", pmcid):
        raise LitSearchError("a PMCID like PMC1234567 is required")
    xml = await http.get(f"{BASE}/{pmcid}/fullTextXML", as_json=False)
    root = parse_xml(xml)
    body = next((e for e in root.iter() if strip_ns(e.tag) == "body"), None)
    if body is None:
        raise LitSearchError("no open-access full text body is available for this article")
    parts: list[str] = []
    for element in body.iter():
        tag = strip_ns(element.tag)
        if tag == "title" and text_of(element):
            parts.append(f"\n## {text_of(element)}")
        elif tag == "p":
            text = text_of(element)
            if text:
                parts.append(text)
    text = "\n".join(parts).strip()
    truncated = len(text) > max_chars
    return {
        "pmcid": pmcid,
        "text": text[:max_chars],
        "characters": len(text),
        "truncated": truncated,
        "license_note": "Open-access text from Europe PMC; check the article's own licence before reuse.",
    }
