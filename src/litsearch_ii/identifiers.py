"""Work out what kind of identifier a string is: DOI, PMID, PMCID, arXiv, OpenAlex or NCT."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import LitSearchError, normalise_doi

ARXIV_NEW = re.compile(r"^(\d{4}\.\d{4,5})(v\d+)?$")
ARXIV_OLD = re.compile(r"^([a-z-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?$")


@dataclass(frozen=True)
class Identifier:
    kind: str  # doi | pmid | pmcid | arxiv | openalex | nct
    value: str

    def doi_form(self) -> str | None:
        """A DOI for this identifier where one is derivable (arXiv has one)."""
        if self.kind == "doi":
            return self.value
        if self.kind == "arxiv":
            return f"10.48550/arxiv.{self.value.lower()}"
        return None


def parse_identifier(raw: str) -> Identifier:
    text = (raw or "").strip()
    if not text:
        raise LitSearchError("an identifier is required (DOI, PMID, PMCID, arXiv id, OpenAlex id)")
    lowered = text.lower()
    if "arxiv.org/" in lowered:
        tail = re.split(r"arxiv\.org/(?:abs|pdf)/", text, flags=re.I)[-1]
        text = re.sub(r"\.pdf$", "", tail.strip("/"))
    elif lowered.startswith("arxiv:"):
        text = text[6:].strip()
    for pattern in (ARXIV_NEW, ARXIV_OLD):
        match = pattern.match(text)
        if match:
            return Identifier("arxiv", match.group(1))
    if "openalex.org/" in lowered:
        text = text.rstrip("/").rsplit("/", 1)[-1]
    if re.fullmatch(r"[Ww]\d+", text):
        return Identifier("openalex", text.upper())
    if re.fullmatch(r"PMC\d+", text, re.I):
        return Identifier("pmcid", text.upper())
    if re.fullmatch(r"NCT\d{8}", text, re.I):
        return Identifier("nct", text.upper())
    pmid = re.sub(r"^pmid:\s*", "", text, flags=re.I)
    if re.fullmatch(r"\d{1,9}", pmid):
        return Identifier("pmid", pmid)
    doi = normalise_doi(text)
    if doi:
        return Identifier("doi", doi)
    raise LitSearchError(
        f"could not recognise {raw!r} as a DOI, PMID, PMCID, arXiv id, OpenAlex id or NCT id"
    )
