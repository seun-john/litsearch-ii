"""Merge results from several sources into one ranked, de-duplicated list."""

from __future__ import annotations

import math
import re

from .models import Paper

RRF_K = 60


def _title_key(title: str) -> str:
    return re.sub(r"\W+", " ", title.casefold()).strip()


def paper_key(paper: Paper) -> str:
    """DOI when there is one, otherwise the normalised title."""
    return f"doi:{paper.doi}" if paper.doi else f"title:{_title_key(paper.title)}"


def merge(into: Paper, other: Paper) -> Paper:
    """Fold `other` into `into`, keeping whichever side has more information."""
    if into.title == "(untitled)" and other.title != "(untitled)":
        into.title = other.title
    if len(other.authors) > len(into.authors):
        into.authors = other.authors
    into.year = into.year or other.year
    into.venue = into.venue or other.venue
    into.doi = into.doi or other.doi
    if len(other.abstract or "") > len(into.abstract or ""):
        into.abstract = other.abstract
    if other.citations is not None and (into.citations or 0) < other.citations:
        into.citations = other.citations
    if other.is_open_access:
        into.is_open_access = True
    into.open_access_url = into.open_access_url or other.open_access_url
    into.url = into.url or other.url
    into.type = into.type or other.type
    for key, value in other.ids.items():
        into.ids.setdefault(key, value)
    for source in other.sources:
        if source not in into.sources:
            into.sources.append(source)
    return into


def fuse(ranked_lists: dict[str, list[Paper]], limit: int) -> list[Paper]:
    """Reciprocal-rank fusion across sources, with a small boost for citation count.

    A paper that several sources rank highly beats one that a single source ranks first.
    """
    merged: dict[str, Paper] = {}
    scores: dict[str, float] = {}
    aliases: dict[str, str] = {}
    for papers in ranked_lists.values():
        for rank, paper in enumerate(papers, start=1):
            key = aliases.get(paper_key(paper)) or paper_key(paper)
            if key not in merged:
                merged[key] = paper
                scores[key] = 0.0
            else:
                merge(merged[key], paper)
            aliases[paper_key(paper)] = key
            if paper.doi:
                aliases[f"title:{_title_key(paper.title)}"] = key
            scores[key] += 1.0 / (RRF_K + rank)
    for key, paper in merged.items():
        scores[key] += 0.0015 * math.log10(1 + (paper.citations or 0))
        paper.score = scores[key]
    ordered = sorted(merged.values(), key=lambda p: p.score or 0.0, reverse=True)
    return ordered[:limit]
