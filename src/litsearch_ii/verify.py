"""Check that a citation exists and that its details match a real record."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from .http import Http
from .identifiers import Identifier
from .models import LitSearchError, Paper, normalise_doi
from .sources import crossref, openalex

SAME_TITLE = 0.95
NEAR_TITLE = 0.85
RETRACTION_TYPES = {"retraction", "withdrawal", "removal"}


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.casefold()).strip()


def title_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _family(name: str) -> str:
    cleaned = name.split(",")[0] if "," in name else name.strip().split(" ")[-1]
    return _norm(cleaned)


def compare(
    record: Paper,
    title: str | None,
    authors: list[str] | None,
    year: int | None,
) -> dict[str, Any]:
    """Differences between what was cited and what the record says."""
    differences: dict[str, Any] = {}
    if title:
        ratio = title_similarity(title, record.title)
        if ratio < SAME_TITLE:
            differences["title"] = {
                "cited": title,
                "record": record.title,
                "similarity": round(ratio, 3),
                "note": "probably a typo" if ratio >= NEAR_TITLE else "different title",
            }
    if year and record.year and abs(year - record.year) > 0:
        differences["year"] = {"cited": year, "record": record.year}
    if authors and record.authors:
        cited = {_family(a) for a in authors}
        actual = {_family(a) for a in record.authors}
        if not cited & actual:
            differences["authors"] = {
                "cited": authors,
                "record": record.authors[:6],
                "note": "no shared surnames",
            }
        elif _family(authors[0]) != _family(record.authors[0]):
            differences["first_author"] = {"cited": authors[0], "record": record.authors[0]}
    return differences


async def _retraction_notice(http: Http, doi: str) -> list[dict[str, Any]]:
    """Crossref lists retractions, withdrawals and removals that update a DOI."""
    data = await http.get(f"{crossref.BASE}/works/{doi}")
    message = data.get("message", {})
    notices = []
    for update in message.get("updated-by", []):
        if str(update.get("type", "")).lower() in RETRACTION_TYPES:
            notices.append({"type": update.get("type"), "doi": update.get("DOI")})
    return notices


async def verify_citation(
    http: Http,
    *,
    doi: str | None = None,
    title: str | None = None,
    authors: list[str] | None = None,
    year: int | None = None,
) -> dict[str, Any]:
    """Look a citation up in Crossref (then OpenAlex) and report how well it matches."""
    clean_doi = normalise_doi(doi)
    if not clean_doi and not (title and title.strip()):
        raise LitSearchError("give a DOI, or at least a title")
    record: Paper | None = None
    how = ""
    if clean_doi:
        try:
            record = await crossref.get(http, clean_doi)
            how = "DOI found in Crossref"
        except LitSearchError as exc:
            if "not found" not in str(exc):
                raise
            try:
                record = await openalex.get(http, Identifier("doi", clean_doi))
                how = "DOI found in OpenAlex"
            except LitSearchError as exc2:
                if "not found" not in str(exc2):
                    raise
        if record is None:
            return {
                "status": "NOT_FOUND",
                "doi": clean_doi,
                "message": "The DOI is not in Crossref or OpenAlex. That is a strong warning, "
                "but not proof of fabrication: the DOI may be new or mistyped.",
            }
    else:
        assert title is not None
        found = await crossref.search(http, title, 5)
        scored = sorted(
            ((title_similarity(title, p.title), p) for p in found), key=lambda t: t[0], reverse=True
        )
        if not scored or scored[0][0] < NEAR_TITLE:
            return {
                "status": "NOT_FOUND",
                "title": title,
                "message": "No Crossref record has a similar title. This is not proof of "
                "fabrication: the work may not have a DOI or may be indexed elsewhere.",
            }
        best_score, record = scored[0]
        how = "closest title match in Crossref (no DOI was given)"
        if best_score < SAME_TITLE:
            return {
                "status": "POSSIBLE_MATCH",
                "how": how,
                "similarity": round(best_score, 3),
                "record": record.to_dict(),
                "message": "No exact title match. This record is the closest, and may be a "
                "different work. Check it before treating the citation as verified.",
            }
    differences = compare(record, title, authors, year)
    result: dict[str, Any] = {
        "status": "METADATA_MISMATCH" if differences else "VERIFIED",
        "how": how,
        "record": record.to_dict(),
        "differences": differences,
    }
    if record.doi:
        try:
            notices = await _retraction_notice(http, record.doi)
        except LitSearchError:
            notices = []
        if notices:
            result["status"] = "RETRACTED"
            result["retraction_notices"] = notices
    return result
