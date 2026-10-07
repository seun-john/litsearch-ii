"""Export papers as BibTeX, RIS or CSL-JSON."""

from __future__ import annotations

import json
import re
from typing import Any

from .models import LitSearchError, Paper

FORMATS = ("bibtex", "ris", "csl-json")
BIBTEX_SPECIAL = str.maketrans(
    {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
    }
)


def _ascii_word(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", text)


def _family(name: str) -> str:
    return name.split(",")[0].strip() if "," in name else name.strip().split(" ")[-1]


def _bib_authors(authors: list[str]) -> str:
    return " and ".join(authors)


def bibtex_key(paper: Paper, taken: set[str]) -> str:
    family = _ascii_word(_family(paper.authors[0])) if paper.authors else "anon"
    first = next((w for w in re.findall(r"[A-Za-z]{4,}", paper.title)), "paper")
    base = f"{family.lower()}{paper.year or 'nd'}{first.lower()}"
    key, n = base, 1
    while key in taken:
        n += 1
        key = f"{base}{n}"
    taken.add(key)
    return key


def to_bibtex(papers: list[Paper]) -> str:
    taken: set[str] = set()
    entries = []
    for p in papers:
        kind = "article" if p.venue and p.type != "preprint" else "misc"
        fields = {
            "title": "{" + p.title.translate(BIBTEX_SPECIAL) + "}",
            "author": "{" + _bib_authors(p.authors).translate(BIBTEX_SPECIAL) + "}"
            if p.authors
            else None,
            "year": f"{{{p.year}}}" if p.year else None,
            "journal" if kind == "article" else "howpublished": (
                "{" + p.venue.translate(BIBTEX_SPECIAL) + "}" if p.venue else None
            ),
            "doi": f"{{{p.doi}}}" if p.doi else None,
            "url": f"{{{p.url}}}" if p.url else None,
        }
        body = ",\n".join(f"  {k} = {v}" for k, v in fields.items() if v)
        entries.append(f"@{kind}{{{bibtex_key(p, taken)},\n{body}\n}}")
    return "\n\n".join(entries) + "\n"


def to_ris(papers: list[Paper]) -> str:
    records = []
    for p in papers:
        lines = ["TY  - " + ("JOUR" if p.venue and p.type != "preprint" else "GEN")]
        lines.append(f"TI  - {p.title}")
        lines.extend(f"AU  - {a}" for a in p.authors)
        if p.year:
            lines.append(f"PY  - {p.year}")
        if p.venue:
            lines.append(f"JO  - {p.venue}")
        if p.doi:
            lines.append(f"DO  - {p.doi}")
        if p.url:
            lines.append(f"UR  - {p.url}")
        if p.abstract:
            lines.append(f"AB  - {p.abstract}")
        lines.append("ER  - ")
        records.append("\n".join(lines))
    return "\n\n".join(records) + "\n"


def to_csl_json(papers: list[Paper]) -> str:
    taken: set[str] = set()
    items: list[dict[str, Any]] = []
    for p in papers:
        item: dict[str, Any] = {
            "id": bibtex_key(p, taken),
            "type": "article-journal" if p.venue and p.type != "preprint" else "article",
            "title": p.title,
            "author": [
                {"family": _family(a), "given": a.split(",", 1)[1].strip()}
                if "," in a
                else {"family": _family(a), "given": " ".join(a.strip().split(" ")[:-1])}
                for a in p.authors
            ],
        }
        if p.year:
            item["issued"] = {"date-parts": [[p.year]]}
        if p.venue:
            item["container-title"] = p.venue
        if p.doi:
            item["DOI"] = p.doi
        if p.url:
            item["URL"] = p.url
        if p.abstract:
            item["abstract"] = p.abstract
        items.append(item)
    return json.dumps(items, indent=2, ensure_ascii=False) + "\n"


def export(papers: list[dict[str, Any]], fmt: str) -> str:
    if fmt not in FORMATS:
        raise LitSearchError(f"format must be one of: {', '.join(FORMATS)}")
    if not papers:
        raise LitSearchError("no papers to export")
    parsed = [Paper.from_dict(p) for p in papers]
    return {"bibtex": to_bibtex, "ris": to_ris, "csl-json": to_csl_json}[fmt](parsed)
