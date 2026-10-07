from __future__ import annotations

import json

import pytest

from litsearch_ii.aggregate import fuse, paper_key
from litsearch_ii.export import export, to_bibtex
from litsearch_ii.identifiers import parse_identifier
from litsearch_ii.models import LitSearchError, Paper, clean_text, normalise_doi, parse_year
from litsearch_ii.sources.openalex import rebuild_abstract
from litsearch_ii.verify import compare, title_similarity
from litsearch_ii.xmlsafe import parse_xml


@pytest.mark.parametrize(
    ("raw", "kind", "value"),
    [
        ("10.1038/NATURE14539", "doi", "10.1038/nature14539"),
        ("https://doi.org/10.1038/nature14539", "doi", "10.1038/nature14539"),
        ("doi:10.1038/nature14539.", "doi", "10.1038/nature14539"),
        ("31452104", "pmid", "31452104"),
        ("PMID: 31452104", "pmid", "31452104"),
        ("pmc13177148", "pmcid", "PMC13177148"),
        ("W2741809807", "openalex", "W2741809807"),
        ("https://openalex.org/w2741809807", "openalex", "W2741809807"),
        ("1706.03762", "arxiv", "1706.03762"),
        ("arXiv:1706.03762v5", "arxiv", "1706.03762"),
        ("https://arxiv.org/abs/1706.03762v5", "arxiv", "1706.03762"),
        ("https://arxiv.org/pdf/1706.03762.pdf", "arxiv", "1706.03762"),
        ("hep-th/9901001", "arxiv", "hep-th/9901001"),
        ("nct01234567", "nct", "NCT01234567"),
    ],
)
def test_identifier_kinds(raw: str, kind: str, value: str) -> None:
    ident = parse_identifier(raw)
    assert (ident.kind, ident.value) == (kind, value)


@pytest.mark.parametrize("bad", ["", "   ", "not an id", "10.x/y", "http://example.org/paper"])
def test_unrecognised_identifiers(bad: str) -> None:
    with pytest.raises(LitSearchError):
        parse_identifier(bad)


def test_arxiv_has_a_derived_doi() -> None:
    assert parse_identifier("1706.03762").doi_form() == "10.48550/arxiv.1706.03762"
    assert parse_identifier("31452104").doi_form() is None


def test_model_helpers() -> None:
    assert normalise_doi("DOI: 10.5/X)") == "10.5/x"
    assert normalise_doi("hello") is None
    assert clean_text("<p>A  <b>b</b>\n c</p>") == "A b c"
    assert clean_text("  ") is None
    assert parse_year("2020 May") == 2020
    assert parse_year("n.d.") is None


def test_paper_round_trip_and_validation() -> None:
    paper = Paper(
        title="T", authors=["A B"], year=2020, doi="10.1/x", sources=["openalex"], score=0.123456
    )
    data = paper.to_dict()
    assert data["score"] == 0.1235 and "abstract" not in data
    again = Paper.from_dict(data)
    assert (again.title, again.year, again.doi) == ("T", 2020, "10.1/x")
    with pytest.raises(LitSearchError):
        Paper.from_dict({"title": " "})


def test_abstract_is_rebuilt_in_order() -> None:
    assert (
        rebuild_abstract({"world": [1], "Hello": [0], "again": [2, 3]}) == "Hello world again again"
    )
    assert rebuild_abstract(None) is None


def p(title: str, doi: str | None = None, **kw: object) -> Paper:
    return Paper(title=title, doi=doi, sources=["x"], **kw)  # type: ignore[arg-type]


def test_fusion_merges_by_doi_and_rewards_agreement() -> None:
    a = [p("Alpha", "10.1/a"), p("Beta", "10.1/b")]
    b = [p("Gamma", "10.1/c"), p("Beta (preprint)", "10.1/b", citations=50)]
    for paper in b:
        paper.sources = ["y"]
    out = fuse({"s1": a, "s2": b}, 10)
    # Beta is ranked second by both sources; Alpha and Gamma are each first in one only.
    assert out[0].doi == "10.1/b"
    beta = out[0]
    assert sorted(beta.sources) == ["x", "y"] and beta.citations == 50
    assert len(out) == 3


def test_fusion_joins_a_doi_less_record_to_its_doi_twin_by_title() -> None:
    a = [p("The Same Title", "10.1/a")]
    b = [p("the same   title!", None, abstract="longer abstract")]
    out = fuse({"s1": a, "s2": b}, 10)
    assert len(out) == 1 and out[0].abstract == "longer abstract"


def test_fusion_respects_the_limit_and_sets_scores() -> None:
    papers = [p(f"Paper {i}", f"10.1/{i}") for i in range(5)]
    out = fuse({"s": papers}, 2)
    assert len(out) == 2 and out[0].score and out[0].score > out[1].score  # type: ignore[operator]


def test_paper_key_prefers_doi() -> None:
    assert paper_key(p("T", "10.1/x")) == "doi:10.1/x"
    assert paper_key(p("A, B!")) == "title:a b"


def sample() -> list[dict[str, object]]:
    return [
        {
            "title": "Sleep & Exercise: 100% effective_",
            "authors": ["Ada Lovelace", "Turing, Alan"],
            "year": 2020,
            "venue": "J Things",
            "doi": "10.1/x",
            "url": "https://doi.org/10.1/x",
            "abstract": "Short.",
        },
        {"title": "Untitled preprint", "type": "preprint", "venue": "arXiv"},
    ]


def test_bibtex() -> None:
    text = export(sample(), "bibtex")
    assert text.startswith("@article{lovelace2020sleep,")
    assert r"Sleep \& Exercise: 100\% effective\_" in text
    assert "author = {Ada Lovelace and Turing, Alan}" in text
    assert "@misc{anon" in text  # preprints and unnamed works are @misc


def test_bibtex_keys_are_unique() -> None:
    twins = [{"title": "Same title here", "year": 2020, "authors": ["A B"]}] * 3
    keys = [
        line
        for line in to_bibtex([Paper.from_dict(t) for t in twins]).splitlines()
        if line.startswith("@")
    ]
    assert len(set(keys)) == 3


def test_ris() -> None:
    text = export(sample(), "ris")
    assert "TY  - JOUR" in text and "AU  - Turing, Alan" in text and "DO  - 10.1/x" in text
    assert text.count("ER  - ") == 2


def test_csl_json_splits_names() -> None:
    items = json.loads(export(sample(), "csl-json"))
    names = items[0]["author"]
    assert names[0] == {"family": "Lovelace", "given": "Ada"}
    assert names[1] == {"family": "Turing", "given": "Alan"}
    assert items[0]["issued"] == {"date-parts": [[2020]]} and items[0]["DOI"] == "10.1/x"


def test_export_errors() -> None:
    with pytest.raises(LitSearchError):
        export(sample(), "docx")
    with pytest.raises(LitSearchError):
        export([], "bibtex")
    with pytest.raises(LitSearchError):
        export([{"authors": ["x"]}], "bibtex")


def record() -> Paper:
    return Paper(title="Deep learning", authors=["Yann LeCun", "Yoshua Bengio"], year=2015)


def test_compare_clean_and_differences() -> None:
    assert compare(record(), "Deep Learning", ["LeCun, Yann"], 2015) == {}
    diff = compare(record(), "Shallow learning", ["Someone Else"], 1999)
    assert set(diff) == {"title", "year", "authors"}
    assert diff["title"]["note"] == "different title"


def test_compare_near_title_and_author_order() -> None:
    near = compare(record(), "Deep lernng", None, None)
    assert near["title"]["note"] == "probably a typo"
    swapped = compare(record(), None, ["Yoshua Bengio", "Yann LeCun"], None)
    assert "first_author" in swapped and "authors" not in swapped


def test_title_similarity() -> None:
    assert title_similarity("Deep Learning!", "deep learning") == 1.0


def test_xml_parser_refuses_entities() -> None:
    assert parse_xml("<a><b>x</b></a>").tag == "a"
    bomb = '<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x "boom">]><a>&x;</a>'
    with pytest.raises(LitSearchError, match="entities"):
        parse_xml(bomb)
    with pytest.raises(LitSearchError, match="malformed"):
        parse_xml("<a><b></a>")
