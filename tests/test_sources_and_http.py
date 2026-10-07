from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from litsearch_ii.identifiers import parse_identifier
from litsearch_ii.models import LitSearchError
from litsearch_ii.sources import arxiv, crossref, europepmc, openalex, pubmed, trials
from tests.conftest import ARXIV_ERROR, PUBMED_EFETCH, Mock, cr_item, oa_work


def run(coro: Any) -> Any:
    return asyncio.run(coro)


# -- http layer ----------------------------------------------------------------------------


def test_only_known_hosts_are_contacted(mock: Mock) -> None:
    http = mock.http()
    with pytest.raises(LitSearchError, match="not a supported source"):
        run(http.get("https://evil.example/steal"))
    assert mock.calls == []


def test_responses_are_cached(mock: Mock) -> None:
    mock.add("api.crossref.org", {"message": {"items": []}})
    http = mock.http()

    async def twice() -> None:
        await http.get("https://api.crossref.org/works", {"query": "a"})
        await http.get("https://api.crossref.org/works", {"query": "a"})
        await http.get("https://api.crossref.org/works", {"query": "b"})

    run(twice())
    assert len(mock.calls) == 2


def test_none_params_are_dropped(mock: Mock) -> None:
    mock.add("api.crossref.org", {})
    run(mock.http().get("https://api.crossref.org/works", {"a": None, "b": 1}))
    assert dict(mock.calls[0].url.params) == {"b": "1"}


def test_retries_then_succeeds(mock: Mock) -> None:
    state = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        state["n"] += 1
        return httpx.Response(503) if state["n"] < 3 else httpx.Response(200, json={"ok": True})

    mock.add("api.crossref.org", flaky)
    http = mock.http(retries=2)
    assert run(http.get("https://api.crossref.org/works")) == {"ok": True}
    assert state["n"] == 3


def test_gives_up_with_a_clear_message(mock: Mock) -> None:
    mock.add("api.crossref.org", lambda r: httpx.Response(503))
    with pytest.raises(LitSearchError, match="HTTP 503"):
        run(mock.http(retries=1).get("https://api.crossref.org/works"))


@pytest.mark.parametrize(("status", "text"), [(404, "not found"), (400, "HTTP 400")])
def test_client_errors_are_not_retried(mock: Mock, status: int, text: str) -> None:
    mock.add("api.crossref.org", lambda r: httpx.Response(status))
    with pytest.raises(LitSearchError, match=text):
        run(mock.http(retries=3).get("https://api.crossref.org/works"))
    assert len(mock.calls) == 1


def test_invalid_json_and_oversize_are_rejected(mock: Mock) -> None:
    mock.add("api.crossref.org/bad", "not json")
    with pytest.raises(LitSearchError, match="not valid JSON"):
        run(mock.http().get("https://api.crossref.org/bad"))
    mock.add(
        "api.crossref.org/big", lambda r: httpx.Response(200, content=b"x" * (9 * 1024 * 1024))
    )
    with pytest.raises(LitSearchError, match="larger than"):
        run(mock.http().get("https://api.crossref.org/big", as_json=False))


def test_timeouts_become_clear_errors(mock: Mock) -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    mock.add("api.crossref.org", slow)
    with pytest.raises(LitSearchError, match="timed out"):
        run(mock.http(retries=0).get("https://api.crossref.org/works"))


# -- sources -------------------------------------------------------------------------------


def test_openalex_search_and_filters(full: Mock) -> None:
    papers = run(
        openalex.search(
            full.http(), "sleep", 5, year_from=2015, open_access_only=True, country="ng"
        )
    )
    request = full.calls[0]
    assert (
        request.url.params["filter"]
        == "publication_year:2015-,is_oa:true,authorships.institutions.country_code:NG"
    )
    first = papers[0]
    assert first.abstract == "Exercise helps sleep."
    assert first.doi == "10.1/a" and first.ids["pmid"] == "123" and first.is_open_access
    assert first.authors == ["Ada Lovelace"] and first.venue == "J Things"


def test_openalex_untitled_and_missing_doi(mock: Mock) -> None:
    mock.add("api.openalex.org", {"results": [oa_work(3, title=None, doi=None)]})  # type: ignore[arg-type]
    paper = run(openalex.search(mock.http(), "x", 1))[0]
    assert paper.title == "(untitled)" and paper.doi is None


@pytest.mark.parametrize(
    ("raw", "path"),
    [
        ("10.1/a", "/works/doi:10.1/a"),
        ("W5", "/works/W5"),
        ("123", "/works/pmid:123"),
        ("PMC5", "/works/pmcid:PMC5"),
        ("1706.03762", "/works/doi:10.48550/arxiv.1706.03762"),
    ],
)
def test_openalex_lookup_paths(mock: Mock, raw: str, path: str) -> None:
    mock.add("api.openalex.org", oa_work())
    run(openalex.get(mock.http(), parse_identifier(raw)))
    assert mock.calls[0].url.path == path


def test_openalex_citing_references_related(full: Mock) -> None:
    http = full.http()
    assert len(run(openalex.citing(http, parse_identifier("10.1/a"), 5))) == 2
    assert full.calls[-1].url.params["filter"] == "cites:W1"
    run(openalex.references(http, parse_identifier("10.1/a"), 5))
    assert full.calls[-1].url.params["filter"] == "openalex:W7|W8"
    run(openalex.related(http, parse_identifier("10.1/a"), 5))
    assert full.calls[-1].url.params["filter"] == "openalex:W9"


def test_openalex_with_no_references(mock: Mock) -> None:
    mock.add("api.openalex.org", oa_work(referenced_works=[]))
    assert run(openalex.references(mock.http(), parse_identifier("10.1/a"), 5)) == []


def test_crossref_parsing_and_filters(full: Mock) -> None:
    paper = run(crossref.search(full.http(), "sleep", 3, year_from=2010, year_to=2020))[0]
    assert full.calls[0].url.params["filter"] == "from-pub-date:2010,until-pub-date:2020"
    assert (paper.doi, paper.year, paper.abstract) == ("10.1/a", 2020, "Exercise helps sleep.")
    assert paper.authors == ["Ada Lovelace"]


def test_crossref_handles_missing_dates_and_titles(mock: Mock) -> None:
    item = cr_item(issued={"date-parts": [[None]]})
    item["title"] = []
    mock.add("api.crossref.org", {"message": {"items": [item]}})
    paper = run(crossref.search(mock.http(), "x", 1))[0]
    assert paper.year is None and paper.title == "(untitled)"


def test_europepmc_parsing(full: Mock) -> None:
    paper = run(europepmc.search(full.http(), "sleep", 2, year_from=2019, open_access_only=True))[0]
    query = full.calls[0].url.params["query"]
    assert "PUB_YEAR:[2019 TO 2100]" in query and "OPEN_ACCESS:y" in query
    assert paper.ids == {"pmid": "123", "pmcid": "PMC555"}
    assert paper.abstract == "Background Exercise helps sleep." and paper.is_open_access
    assert paper.open_access_url == "https://europepmc.org/x"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("123", "EXT_ID:123 AND SRC:MED"), ("PMC555", "PMCID:PMC555"), ("10.1/a", 'DOI:"10.1/a"')],
)
def test_europepmc_lookup_queries(full: Mock, raw: str, expected: str) -> None:
    run(europepmc.get(full.http(), parse_identifier(raw)))
    assert full.calls[0].url.params["query"] == expected


def test_europepmc_not_found(mock: Mock) -> None:
    mock.add("europepmc", {"resultList": {"result": []}})
    with pytest.raises(LitSearchError, match="not found"):
        run(europepmc.get(mock.http(), parse_identifier("123")))


def test_europepmc_fulltext(full: Mock) -> None:
    result = run(europepmc.fulltext(full.http(), "PMC555", 1000))
    assert (
        result["text"]
        == "## Introduction\nFirst paragraph.\nSecond paragraph.\n\n## Methods\nWe did things."
    )
    short = run(europepmc.fulltext(full.http(), "PMC555", 20))
    assert short["truncated"] and len(short["text"]) == 20
    with pytest.raises(LitSearchError, match="PMCID"):
        run(europepmc.fulltext(full.http(), "123", 100))


def test_europepmc_fulltext_without_a_body(mock: Mock) -> None:
    mock.add("fullTextXML", "<article><front/></article>")
    with pytest.raises(LitSearchError, match="no open-access full text"):
        run(europepmc.fulltext(mock.http(), "PMC9", 100))


def test_arxiv_feed(full: Mock) -> None:
    paper = run(arxiv.search(full.http(), "attention is all", 3, year_from=2017))[0]
    assert (
        full.calls[0].url.params["search_query"].startswith("all:attention AND all:is AND all:all")
    )
    assert (
        "submittedDate:[201701010000 TO 210012312359]" in full.calls[0].url.params["search_query"]
    )
    assert paper.title == "Attention Is All You Need"
    assert paper.ids == {"arxiv": "1706.03762"} and paper.doi == "10.48550/arxiv.1706.03762"
    assert paper.authors == ["Ashish Vaswani", "Noam Shazeer"] and paper.year == 2017
    assert paper.open_access_url == "http://arxiv.org/pdf/1706.03762v7"


def test_arxiv_ignores_error_entries_and_empty_queries(mock: Mock) -> None:
    mock.add("arxiv", ARXIV_ERROR)
    assert run(arxiv.search(mock.http(), "x", 1)) == []
    with pytest.raises(LitSearchError, match="no searchable words"):
        run(arxiv.search(mock.http(), "!!! ???", 1))
    with pytest.raises(LitSearchError, match="not found"):
        run(arxiv.get(mock.http(), parse_identifier("1706.03762")))


def test_pubmed_search_with_abstracts(full: Mock) -> None:
    papers = run(pubmed.search(full.http(), "sleep", 3, year_from=2019))
    esearch = next(c for c in full.calls if "esearch" in str(c.url))
    assert esearch.url.params["mindate"] == "2019" and esearch.url.params["datetype"] == "pdat"
    paper = papers[0]
    assert paper.abstract == "BACKGROUND: Sleep matters. RESULTS: Exercise helped."
    assert paper.doi == "10.1/a" and paper.ids == {"pmid": "123", "pmcid": "PMC555"}
    assert paper.url == "https://pubmed.ncbi.nlm.nih.gov/123/"


def test_pubmed_without_abstracts_and_with_no_hits(full: Mock, mock: Mock) -> None:
    run(pubmed.search(full.http(), "sleep", 3, with_abstracts=False))
    assert not any("efetch" in str(c.url) for c in full.calls)
    mock.add("esearch", {"esearchresult": {"idlist": []}})
    assert run(pubmed.search(mock.http(), "none", 3)) == []


def test_pubmed_get_by_doi_and_pmid(full: Mock) -> None:
    assert run(pubmed.get(full.http(), parse_identifier("10.1/a"))).ids["pmid"] == "123"
    assert full.calls[0].url.params["term"] == "10.1/a[DOI]"
    assert run(pubmed.get(full.http(), parse_identifier("123"))).title == "Sleep and exercise."
    with pytest.raises(LitSearchError):
        run(pubmed.get(full.http(), parse_identifier("W5")))


def test_pubmed_efetch_parser_tolerates_the_public_doctype() -> None:
    assert pubmed.parse_abstracts(PUBMED_EFETCH) == {
        "123": "BACKGROUND: Sleep matters. RESULTS: Exercise helped."
    }


def test_trials(full: Mock) -> None:
    found = run(trials.search(full.http(), "sleep", 2, status="completed"))
    assert full.calls[0].url.params["filter.overallStatus"] == "COMPLETED"
    trial = found[0]
    assert (
        trial["nct_id"] == "NCT01234567" and trial["enrollment"] == 80 and trial["locations"] == 2
    )
    assert trial["summary"] == "A trial." and trial["url"].endswith("NCT01234567")
    with pytest.raises(LitSearchError, match="status must be"):
        run(trials.search(full.http(), "x", 1, status="vanished"))
