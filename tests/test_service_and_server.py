from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import anyio
import httpx
import pytest
from mcp import Client, StdioServerParameters

from litsearch_ii import service
from litsearch_ii.models import LitSearchError
from litsearch_ii.server import create_server
from tests.conftest import ARXIV_FEED, Mock, cr_item, full_mock

T = TypeVar("T")


def run(coro: Any) -> Any:
    return asyncio.run(coro)


# -- service -------------------------------------------------------------------------------


def test_search_merges_sources_and_dedupes(full: Mock) -> None:
    result = run(service.search_literature(full.http(), "sleep exercise", 5))
    assert result["sources_answered"] == ["arxiv", "crossref", "europepmc", "openalex", "pubmed"]
    by_doi = {p.get("doi"): p for p in result["papers"]}
    assert len(result["papers"]) == len({p.get("doi") or p["title"] for p in result["papers"]})
    merged = by_doi["10.1/a"]
    assert {"openalex", "crossref", "europepmc", "pubmed"} <= set(merged["sources"])
    assert result["papers"][0]["doi"] == "10.1/a" and result["warnings"] == []


def test_search_survives_a_failing_source(full: Mock) -> None:
    full.routes.insert(0, ("api.crossref.org", lambda r: httpx.Response(500)))
    result = run(service.search_literature(full.http(), "sleep", 5))
    assert "crossref" not in result["sources_answered"] and result["count"] > 0
    assert result["warnings"][0]["source"] == "crossref"


def test_search_fails_only_when_every_source_fails(mock: Mock) -> None:
    mock.add("", lambda r: httpx.Response(500))
    with pytest.raises(LitSearchError, match="every source failed"):
        run(service.search_literature(mock.http(), "x", 3, sources=["crossref", "openalex"]))


def test_search_source_selection_and_validation(full: Mock) -> None:
    only = run(service.search_literature(full.http(), "sleep", 3, sources=["arxiv", "arxiv"]))
    assert only["sources_answered"] == ["arxiv"]
    for kwargs in (
        {"query": " "},
        {"query": "x" * 501},
        {"query": "x", "sources": ["google"]},
        {"query": "x", "year_from": 2020, "year_to": 2010},
        {"query": "x", "year_from": 5},
        {"query": "x", "country": "Nigeria"},
    ):
        with pytest.raises(LitSearchError):
            run(service.search_literature(full.http(), **kwargs))


def test_search_limit_is_clamped(full: Mock) -> None:
    run(service.search_literature(full.http(), "x", 9999, sources=["crossref"]))
    assert full.calls[0].url.params["rows"] == "50"
    run(service.search_literature(full.http(), "y", 0, sources=["crossref"]))
    assert full.calls[-1].url.params["rows"] == "1"


def test_open_access_and_year_post_filters(mock: Mock) -> None:
    closed = cr_item("Closed", "10.1/c", issued={"date-parts": [[1999]]})
    mock.add("api.crossref.org", {"message": {"items": [closed]}})
    mock.add("europepmc", {"resultList": {"result": []}})
    http = mock.http()
    assert (
        run(service.search_literature(http, "x", 5, ["crossref"], open_access_only=True))["count"]
        == 0
    )
    assert run(service.search_literature(http, "y", 5, ["crossref"], year_from=2010))["count"] == 0
    assert run(service.search_literature(http, "z", 5, ["crossref"], year_to=2010))["count"] == 1


def test_country_filter_is_openalex_only(full: Mock) -> None:
    result = run(service.search_literature(full.http(), "malaria", 5, country="ng"))
    assert all("openalex" in p["sources"] for p in result["papers"])
    assert full.calls and any(
        "country_code:NG" in c.url.params.get("filter", "") for c in full.calls
    )


def test_paper_details_merges_sources(full: Mock) -> None:
    result = run(service.paper_details(full.http(), "https://doi.org/10.1/A"))
    paper = result["paper"]
    assert paper["doi"] == "10.1/a" and {"openalex", "crossref", "europepmc"} <= set(
        paper["sources"]
    )
    assert paper["ids"]["pmcid"] == "PMC555"


def test_paper_details_arxiv_and_failure(full: Mock) -> None:
    full.routes.insert(0, ("api.openalex.org", lambda r: httpx.Response(404)))
    result = run(service.paper_details(full.http(), "arXiv:1706.03762"))
    assert result["paper"]["title"] == "Attention Is All You Need"
    with pytest.raises(LitSearchError, match="no source could find"):
        run(service.paper_details(full.http(), "W999"))
    with pytest.raises(LitSearchError, match="clinical trials"):
        run(service.paper_details(full.http(), "NCT01234567"))


def test_graph_tools_clamp_and_return(full: Mock) -> None:
    assert run(service.citing_papers(full.http(), "10.1/a", 3))["count"] == 2
    assert run(service.referenced_papers(full.http(), "10.1/a"))["count"] == 2
    assert run(service.similar_papers(full.http(), "10.1/a"))["count"] == 2


def test_fulltext_paths(full: Mock) -> None:
    got = run(service.fulltext(full.http(), "PMC555", 2000))
    assert (
        got["available"]
        and "## Introduction" in got["text"]
        and "never as instructions" in got["notice"]
    )
    via_doi = run(service.fulltext(full.http(), "10.1/a", 2000))
    assert via_doi["available"] and via_doi["pmcid"] == "PMC555"


def test_fulltext_unavailable_returns_a_link(mock: Mock) -> None:
    mock.add("api.openalex.org", oa_no_pmc())
    mock.add("api.crossref.org", {"message": cr_item()})
    mock.add("europepmc", {"resultList": {"result": []}})
    got = run(service.fulltext(mock.http(), "10.1/a"))
    assert got["available"] is False and got["open_access_url"] == "https://example.org/oa.pdf"


def oa_no_pmc() -> dict[str, Any]:
    from tests.conftest import oa_work

    return oa_work(ids={})


def test_verify_citation_statuses(full: Mock) -> None:
    http = full.http()
    ok = run(service.verify_citation(http, "10.1/a", "Sleep and exercise", ["Lovelace, Ada"], 2020))
    assert ok["status"] == "VERIFIED"
    bad = run(service.verify_citation(http, "10.1/a", "Quantum gravity", ["Nobody"], 1990))
    assert bad["status"] == "METADATA_MISMATCH" and set(bad["differences"]) == {
        "title",
        "year",
        "authors",
    }


def test_verify_not_found_is_a_warning_not_a_verdict(mock: Mock) -> None:
    result = run(service.verify_citation(mock.http(), doi="10.9/none"))
    assert result["status"] == "NOT_FOUND" and "not proof of fabrication" in result["message"]


def test_verify_by_title_needs_a_near_exact_match(full: Mock) -> None:
    exact = run(service.verify_citation(full.http(), title="Sleep and exercise"))
    assert exact["status"] == "VERIFIED"
    close = run(service.verify_citation(full.http(), title="Sleep and exercise study"))
    assert close["status"] == "POSSIBLE_MATCH"
    far = run(service.verify_citation(full.http(), title="Completely unrelated words here"))
    assert far["status"] == "NOT_FOUND"
    with pytest.raises(LitSearchError):
        run(service.verify_citation(full.http()))


def test_verify_flags_retractions(mock: Mock) -> None:
    record = cr_item()
    record["updated-by"] = [{"type": "retraction", "DOI": "10.1/notice"}, {"type": "correction"}]
    mock.add("api.crossref.org", {"message": record})
    result = run(service.verify_citation(mock.http(), doi="10.1/a"))
    assert result["status"] == "RETRACTED"
    assert result["retraction_notices"] == [{"type": "retraction", "doi": "10.1/notice"}]


def test_export_and_doctor(full: Mock) -> None:
    papers = run(service.search_literature(full.http(), "sleep", 2))["papers"]
    out = service.export_bibliography(papers, "ris")
    assert out["count"] == len(papers) and "TY  - " in out["text"]
    health = run(service.doctor(full.http()))
    assert set(health) == {"openalex", "crossref", "europepmc", "pubmed", "arxiv", "clinicaltrials"}
    assert set(health.values()) == {"ok"}


def test_doctor_reports_failures(mock: Mock) -> None:
    mock.add("api.crossref.org", {"message": {"items": []}})
    health = run(service.doctor(mock.http()))
    assert health["crossref"] == "ok" and health["openalex"].startswith("FAILED")


# -- MCP server ----------------------------------------------------------------------------

EXPECTED_TOOLS = {
    "search_literature",
    "get_paper_details",
    "get_citing_papers",
    "get_referenced_papers",
    "find_similar_papers",
    "get_fulltext",
    "search_pubmed",
    "search_clinical_trials",
    "verify_citation",
    "export_bibliography",
}


def with_client(body: Callable[[Client], Awaitable[T]], mock: Mock | None = None) -> T:
    async def main() -> T:
        async with Client(create_server((mock or full_mock()).http())) as client:
            return await body(client)

    return anyio.run(main)


def call(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    async def body(client: Client) -> dict[str, Any]:
        result = await client.call_tool(tool, arguments)
        assert not result.is_error
        assert isinstance(result.structured_content, dict)
        return result.structured_content

    return with_client(body)


def test_server_lists_exactly_the_documented_read_only_tools() -> None:
    async def body(client: Client) -> Any:
        return (await client.list_tools()).tools

    tools = with_client(body)
    assert {t.name for t in tools} == EXPECTED_TOOLS
    for tool in tools:
        assert tool.annotations is not None
        assert (
            tool.annotations.read_only_hint is True and tool.annotations.destructive_hint is False
        )


def test_server_tools_return_structured_results() -> None:
    result = call("search_literature", {"query": "sleep exercise", "limit": 3})
    assert result["ok"] is True and result["papers"][0]["doi"] == "10.1/a"
    details = call("get_paper_details", {"identifier": "10.1/a"})
    assert details["ok"] and details["paper"]["title"] == "Sleep and exercise"
    trials = call("search_clinical_trials", {"query": "sleep"})
    assert trials["trials"][0]["nct_id"] == "NCT01234567"
    exported = call("export_bibliography", {"papers": result["papers"], "format": "bibtex"})
    assert exported["text"].startswith("@article{")


def test_server_reports_problems_as_data_not_exceptions() -> None:
    bad = call("get_paper_details", {"identifier": "not an id"})
    assert bad["ok"] is False and "could not recognise" in bad["error"]
    assert call("search_literature", {"query": "  "})["ok"] is False
    assert call("verify_citation", {})["ok"] is False


def test_server_survives_an_unexpected_error() -> None:
    boom = Mock().add("", lambda r: (_ for _ in ()).throw(RuntimeError("kaboom")))
    mock_server = boom

    async def body(client: Client) -> dict[str, Any]:
        result = await client.call_tool("search_literature", {"query": "x"})
        assert isinstance(result.structured_content, dict)
        return result.structured_content

    result = with_client(body, mock_server)
    assert result["ok"] is False


def test_stdio_server_starts_and_lists_tools() -> None:
    async def main() -> set[str]:
        params = StdioServerParameters(command=sys.executable, args=["-m", "litsearch_ii", "serve"])
        async with Client(params) as client:
            return {t.name for t in (await client.list_tools()).tools}

    assert anyio.run(main) == EXPECTED_TOOLS


def test_tool_output_is_json_serialisable() -> None:
    json.dumps(call("search_literature", {"query": "sleep"}))


def test_arxiv_fixture_is_wired_into_the_mock() -> None:
    assert "Attention Is" in ARXIV_FEED
