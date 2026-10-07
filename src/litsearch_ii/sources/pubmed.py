"""PubMed through NCBI E-utilities: biomedical literature. No key needed (3 requests a second)."""

from __future__ import annotations

from typing import Any

from ..http import Http
from ..identifiers import Identifier
from ..models import LitSearchError, Paper, clean_text, normalise_doi, parse_year
from ..xmlsafe import parse_xml, strip_ns, text_of

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NAME = "pubmed"


def summary_to_paper(item: dict[str, Any]) -> Paper:
    ids: dict[str, str] = {"pmid": str(item.get("uid", ""))}
    doi = None
    for entry in item.get("articleids", []):
        if entry.get("idtype") == "doi":
            doi = normalise_doi(entry.get("value"))
        elif entry.get("idtype") == "pmc":
            ids["pmcid"] = str(entry.get("value"))
    pmid = ids["pmid"]
    return Paper(
        title=clean_text(item.get("title")) or "(untitled)",
        authors=[a["name"] for a in item.get("authors", []) if a.get("name")],
        year=parse_year(item.get("pubdate")),
        venue=clean_text(item.get("fulljournalname") or item.get("source")),
        doi=doi,
        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
        type=(item.get("pubtype") or [None])[0],
        ids=ids,
        sources=[NAME],
    )


def parse_abstracts(xml: str) -> dict[str, str]:
    """PMID -> abstract text, keeping section labels (BACKGROUND, METHODS, ...)."""
    root = parse_xml(xml)
    out: dict[str, str] = {}
    for article in (e for e in root if strip_ns(e.tag) == "PubmedArticle"):
        pmid = text_of(next((e for e in article.iter() if strip_ns(e.tag) == "PMID"), None))
        sections = []
        for node in (e for e in article.iter() if strip_ns(e.tag) == "AbstractText"):
            text = text_of(node)
            if text:
                label = node.attrib.get("Label")
                sections.append(f"{label}: {text}" if label else text)
        if pmid and sections:
            out[pmid] = " ".join(sections)
    return out


async def _summaries(http: Http, pmids: list[str], with_abstracts: bool) -> list[Paper]:
    if not pmids:
        return []
    data = await http.get(
        f"{BASE}/esummary.fcgi", {"db": "pubmed", "id": ",".join(pmids), "retmode": "json"}
    )
    result = data.get("result", {})
    papers = [summary_to_paper(result[p]) for p in pmids if p in result]
    if with_abstracts and papers:
        xml = await http.get(
            f"{BASE}/efetch.fcgi",
            {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml", "rettype": "abstract"},
            as_json=False,
        )
        abstracts = parse_abstracts(xml)
        for paper in papers:
            paper.abstract = abstracts.get(paper.ids.get("pmid", ""))
    return papers


async def search(
    http: Http,
    query: str,
    limit: int,
    *,
    year_from: int | None = None,
    year_to: int | None = None,
    with_abstracts: bool = True,
) -> list[Paper]:
    params: dict[str, Any] = {"db": "pubmed", "term": query, "retmax": limit, "retmode": "json"}
    if year_from or year_to:
        params.update(datetype="pdat", mindate=str(year_from or 1500), maxdate=str(year_to or 2100))
    found = await http.get(f"{BASE}/esearch.fcgi", params)
    pmids = [str(p) for p in found.get("esearchresult", {}).get("idlist", [])]
    return await _summaries(http, pmids, with_abstracts)


async def get(http: Http, ident: Identifier) -> Paper:
    if ident.kind == "pmid":
        pmids = [ident.value]
    else:
        doi = ident.doi_form()
        if not doi:
            raise LitSearchError(f"PubMed cannot look up a {ident.kind} identifier")
        found = await http.get(
            f"{BASE}/esearch.fcgi",
            {"db": "pubmed", "term": f"{doi}[DOI]", "retmax": 1, "retmode": "json"},
        )
        pmids = [str(p) for p in found.get("esearchresult", {}).get("idlist", [])]
    papers = await _summaries(http, pmids, True)
    if not papers:
        raise LitSearchError("PubMed: not found")
    return papers[0]
