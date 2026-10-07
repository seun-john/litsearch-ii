"""arXiv: preprints in physics, maths, computer science and more. No key needed."""

from __future__ import annotations

import re

from ..http import Http
from ..identifiers import Identifier
from ..models import LitSearchError, Paper, clean_text, normalise_doi, parse_year
from ..xmlsafe import parse_xml, strip_ns, text_of

BASE = "https://export.arxiv.org/api/query"
NAME = "arxiv"


def _terms(query: str) -> str:
    tokens = [t for t in re.findall(r"[\w-]+", query) if t.upper() not in {"AND", "OR", "NOT"}]
    if not tokens:
        raise LitSearchError("the query has no searchable words")
    return " AND ".join(f"all:{t}" for t in tokens[:12])


def parse_feed(xml: str) -> list[Paper]:
    root = parse_xml(xml)
    papers: list[Paper] = []
    for entry in (e for e in root if strip_ns(e.tag) == "entry"):
        fields: dict[str, str] = {}
        authors: list[str] = []
        pdf = None
        for child in entry:
            tag = strip_ns(child.tag)
            if tag == "author":
                name = text_of(next((c for c in child if strip_ns(c.tag) == "name"), None))
                if name:
                    authors.append(name)
            elif tag == "link" and child.attrib.get("title") == "pdf":
                pdf = child.attrib.get("href")
            else:
                fields.setdefault(tag, text_of(child) or "")
        raw_id = fields.get("id", "")
        if "/abs/" not in raw_id:
            continue  # arXiv returns an "Error" entry for bad queries
        arxiv_id = re.sub(r"v\d+$", "", raw_id.split("/abs/", 1)[1])
        doi = normalise_doi(fields.get("doi")) or f"10.48550/arxiv.{arxiv_id.lower()}"
        papers.append(
            Paper(
                title=clean_text(fields.get("title")) or "(untitled)",
                authors=authors,
                year=parse_year(fields.get("published")),
                venue="arXiv",
                doi=doi,
                abstract=clean_text(fields.get("summary")),
                is_open_access=True,
                open_access_url=pdf or f"https://arxiv.org/pdf/{arxiv_id}",
                url=f"https://arxiv.org/abs/{arxiv_id}",
                type="preprint",
                ids={"arxiv": arxiv_id},
                sources=[NAME],
            )
        )
    return papers


async def search(
    http: Http,
    query: str,
    limit: int,
    *,
    year_from: int | None = None,
    year_to: int | None = None,
) -> list[Paper]:
    q = _terms(query)
    if year_from or year_to:
        q += f" AND submittedDate:[{year_from or 1991}01010000 TO {year_to or 2100}12312359]"
    xml = await http.get(
        BASE,
        {"search_query": q, "max_results": limit, "sortBy": "relevance"},
        as_json=False,
    )
    return parse_feed(xml)


async def get(http: Http, ident: Identifier) -> Paper:
    if ident.kind != "arxiv":
        raise LitSearchError("an arXiv id is required")
    xml = await http.get(BASE, {"id_list": ident.value, "max_results": 1}, as_json=False)
    papers = parse_feed(xml)
    if not papers:
        raise LitSearchError("arXiv: not found")
    return papers[0]
