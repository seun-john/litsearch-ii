"""Mock transport and small payloads shaped like the real services (no network in tests)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from litsearch_ii.http import Http

Route = Callable[[httpx.Request], httpx.Response] | dict[str, Any] | str


class Mock:
    """Routes are matched by `host` + substring of the path/query; first match wins."""

    def __init__(self) -> None:
        self.routes: list[tuple[str, Route]] = []
        self.calls: list[httpx.Request] = []

    def add(self, needle: str, response: Route) -> Mock:
        self.routes.append((needle, response))
        return self

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        target = f"{request.url.host}{request.url.path}?{request.url.query.decode()}"
        for needle, response in self.routes:
            if needle in target:
                if callable(response):
                    return response(request)
                if isinstance(response, str):
                    return httpx.Response(200, text=response)
                return httpx.Response(200, json=response)
        return httpx.Response(404, json={"error": "no route", "target": target})

    def http(self, **kw: Any) -> Http:
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(self.handler), follow_redirects=True
        )
        kw.setdefault("retries", 0)
        return Http(client=client, **kw)


@pytest.fixture()
def mock() -> Mock:
    return Mock()


def oa_work(
    n: int = 1, title: str = "Sleep and exercise", doi: str | None = "10.1/a", **kw: Any
) -> dict[str, Any]:
    work = {
        "id": f"https://openalex.org/W{n}",
        "doi": f"https://doi.org/{doi}" if doi else None,
        "title": title,
        "publication_year": 2020,
        "cited_by_count": 12,
        "open_access": {"is_oa": True, "oa_url": "https://example.org/oa.pdf"},
        "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
        "primary_location": {
            "source": {"display_name": "J Things"},
            "landing_page_url": "https://example.org/a",
        },
        "abstract_inverted_index": {"Exercise": [0], "helps": [1], "sleep.": [2]},
        "type": "article",
        "ids": {"pmid": "https://pubmed.ncbi.nlm.nih.gov/123/"},
        "referenced_works": ["https://openalex.org/W7", "https://openalex.org/W8"],
        "related_works": ["https://openalex.org/W9"],
    }
    work.update(kw)
    return work


def cr_item(title: str = "Sleep and exercise", doi: str = "10.1/a", **kw: Any) -> dict[str, Any]:
    item = {
        "DOI": doi.upper(),
        "title": [title],
        "author": [{"given": "Ada", "family": "Lovelace"}],
        "issued": {"date-parts": [[2020, 5]]},
        "container-title": ["J Things"],
        "is-referenced-by-count": 30,
        "type": "journal-article",
        "abstract": "<jats:p>Exercise helps sleep.</jats:p>",
        "URL": f"https://doi.org/{doi}",
    }
    item.update(kw)
    return item


EPMC = {
    "resultList": {
        "result": [
            {
                "id": "123",
                "source": "MED",
                "pmid": "123",
                "pmcid": "PMC555",
                "doi": "10.1/a",
                "title": "Sleep and exercise.",
                "authorList": {"author": [{"fullName": "Lovelace A"}]},
                "journalInfo": {"journal": {"title": "J Things"}},
                "pubYear": "2020",
                "abstractText": "<h4>Background</h4> Exercise helps sleep.",
                "citedByCount": 5,
                "isOpenAccess": "Y",
                "fullTextUrlList": {
                    "fullTextUrl": [{"availabilityCode": "OA", "url": "https://europepmc.org/x"}]
                },
            }
        ]
    }
}

ARXIV_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <published>2017-06-12T17:57:34Z</published>
    <title>Attention Is
      All You Need</title>
    <summary>The dominant sequence transduction models.</summary>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
    <link title="pdf" href="http://arxiv.org/pdf/1706.03762v7" rel="related" type="application/pdf"/>
  </entry>
</feed>"""

ARXIV_ERROR = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><id>http://arxiv.org/api/errors#bad</id><title>Error</title><summary>bad</summary></entry></feed>"""

PUBMED_SEARCH = {"esearchresult": {"idlist": ["123"]}}
PUBMED_SUMMARY = {
    "result": {
        "uids": ["123"],
        "123": {
            "uid": "123",
            "title": "Sleep and exercise.",
            "authors": [{"name": "Lovelace A"}],
            "pubdate": "2020 May",
            "fulljournalname": "J Things",
            "source": "J Things",
            "articleids": [
                {"idtype": "doi", "value": "10.1/A"},
                {"idtype": "pmc", "value": "PMC555"},
            ],
            "pubtype": ["Journal Article"],
        },
    }
}
PUBMED_EFETCH = """<?xml version="1.0"?>
<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2019//EN" "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_190101.dtd">
<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID Version="1">123</PMID>
<Article><Abstract>
<AbstractText Label="BACKGROUND">Sleep matters.</AbstractText>
<AbstractText Label="RESULTS">Exercise <i>helped</i>.</AbstractText>
</Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"""

TRIALS = {
    "studies": [
        {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT01234567",
                    "briefTitle": "Exercise for sleep",
                },
                "statusModule": {
                    "overallStatus": "COMPLETED",
                    "startDateStruct": {"date": "2020-01"},
                },
                "designModule": {
                    "studyType": "INTERVENTIONAL",
                    "phases": ["NA"],
                    "enrollmentInfo": {"count": 80},
                },
                "conditionsModule": {"conditions": ["Insomnia"]},
                "sponsorCollaboratorsModule": {"leadSponsor": {"name": "University X"}},
                "descriptionModule": {"briefSummary": "A <b>trial</b>."},
                "contactsLocationsModule": {"locations": [{}, {}]},
            },
            "hasResults": False,
        }
    ]
}

PMC_XML = """<?xml version="1.0"?><article><front><article-meta/></front><body>
<sec><title>Introduction</title><p>First paragraph.</p><p>Second   paragraph.</p></sec>
<sec><title>Methods</title><p>We did things.</p></sec></body></article>"""


def full_mock() -> Mock:
    m = Mock()
    m.add("api.openalex.org/works/doi:10.1/a", oa_work())
    m.add(
        "api.openalex.org/works", {"results": [oa_work(1), oa_work(2, "Another study", "10.1/b")]}
    )
    m.add("api.crossref.org/works/10.1/a", {"message": cr_item()})
    m.add(
        "api.crossref.org/works",
        {"message": {"items": [cr_item(), cr_item("Third study", "10.1/c")]}},
    )
    m.add("europepmc/webservices/rest/PMC555/fullTextXML", PMC_XML)
    m.add("europepmc/webservices/rest/search", EPMC)
    m.add("esearch.fcgi", PUBMED_SEARCH)
    m.add("esummary.fcgi", PUBMED_SUMMARY)
    m.add("efetch.fcgi", PUBMED_EFETCH)
    m.add("export.arxiv.org", ARXIV_FEED)
    m.add("clinicaltrials.gov", TRIALS)
    return m


@pytest.fixture()
def full() -> Mock:
    return full_mock()


def json_body(request: httpx.Request) -> Any:
    return json.loads(request.content)
