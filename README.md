<p align="center">
  <img src="assets/logo.png" alt="LitSearch II logo" width="420">
</p>

# LitSearch II

A literature-search MCP server that needs **no accounts and no API keys**.

It searches OpenAlex, Crossref, Europe PMC, PubMed and arXiv at once, merges and ranks the results, follows citations, reads open-access full text, looks up clinical trials, checks that a citation is real, and exports BibTeX, RIS or CSL-JSON. Every source is a public service that answers anonymous requests, so there is nothing to sign up for, log in to, or paste into a config file.

Everything it does is read-only.

## Install

Requires Python 3.10 or newer.

```bash
pip install git+https://github.com/seun-john/litsearch-ii.git
```

### Add it to Claude Code

```bash
claude mcp add litsearch-ii -- litsearch-ii serve
```

### Add it to Claude Desktop or any MCP client

```json
{
  "mcpServers": {
    "litsearch-ii": { "command": "litsearch-ii", "args": ["serve"] }
  }
}
```

If the command is not on your `PATH`, use `python -m litsearch_ii serve` or the full path to the script. For a network client, `litsearch-ii serve --transport streamable-http --port 8000` serves `http://127.0.0.1:8000/mcp`.

## Tools

| Tool | What it does |
| --- | --- |
| `search_literature` | Search all five sources, merge duplicates by DOI or title, rank by agreement between sources. Filters: `year_from`, `year_to`, `open_access_only`, `sources`, and `country` (a two-letter code such as `NG`, to keep papers with an author affiliated in that country; OpenAlex only). |
| `get_paper_details` | One paper's full record from a DOI, PMID, PMCID, arXiv id (or URL) or OpenAlex id, merged across sources. |
| `get_citing_papers` | Papers that cite it, most cited first. |
| `get_referenced_papers` | Papers it cites. |
| `find_similar_papers` | Related papers, as OpenAlex sees them. |
| `get_fulltext` | Open-access full text as plain text when PubMed Central has it; otherwise an open-access link if one is known. |
| `search_pubmed` | PubMed alone, with abstracts and PubMed syntax such as `malaria[MeSH Terms] AND Nigeria`. |
| `search_clinical_trials` | ClinicalTrials.gov, optionally by status (`RECRUITING`, `COMPLETED`, ...). |
| `verify_citation` | Is this citation real, and do its details match? Returns `VERIFIED`, `METADATA_MISMATCH`, `RETRACTED`, `POSSIBLE_MATCH` or `NOT_FOUND`. |
| `export_bibliography` | Format papers returned by the search tools as `bibtex`, `ris` or `csl-json`. |

Each result says which sources found it (`sources`). If a source is down, the others still answer and the failure is listed under `warnings`. Search results are limited to 50 per call.

### Coverage

`search_literature` and `verify_citation` add a `coverage` object to their result (the layout shared by the Trust Tools). For a search the items are the sources asked: one that answered is decided and one that failed is undecided (`source_failed`), with its name in `notes`; the failure is also listed under `warnings`, as before. For a verification there is one item: `VERIFIED`, `METADATA_MISMATCH` and `RETRACTED` are decided; `NOT_FOUND` and `POSSIBLE_MATCH` are undecided, because neither is proof that the citation is real or invented. Existing fields are unchanged.

### Checking citations

`verify_citation` is built for catching references an AI invented:

- With a DOI it looks the record up in Crossref, then OpenAlex, and compares title, year, authors and, if you give `--journal`, the journal with what you cited. An abbreviated journal (`N Engl J Med`) matches its full name, and a `RETRACTED:` prefix on the record's title is ignored; both are listed in `accepted_equivalences`. It also reads Crossref's retraction, withdrawal and removal notices.
- With only a title it needs a near-exact match to report `VERIFIED`; a weaker match comes back as `POSSIBLE_MATCH` with the record it found, never as a verdict.
- With only a title, a close match whose details disagree is still `METADATA_MISMATCH`, but if the year is more than two years away or the authors do not match, the result also carries `identity_doubts` and a note: without a DOI the record is only the closest title match and may be another edition of the work rather than this citation with wrong details.
- `NOT_FOUND` is a warning, not proof. A DOI can be new, mistyped, or from a source these services do not index.

## Try it from a terminal

```bash
litsearch-ii search "exercise sleep quality" --limit 5 --from 2020 --open-access
litsearch-ii search "malaria vaccine" --country NG
litsearch-ii details 10.1038/nature14539
litsearch-ii verify --doi 10.1038/nature14539 --title "Deep learning" --year 2015
litsearch-ii doctor          # which sources are reachable right now
```

## How it behaves

- **Sources are fixed.** Requests only ever go to `api.openalex.org`, `api.crossref.org`, `www.ebi.ac.uk` (Europe PMC), `eutils.ncbi.nlm.nih.gov` (PubMed), `export.arxiv.org` and `clinicaltrials.gov`. Tool input appears only in a query string or path, never as a host.
- **Polite.** Responses are cached for 15 minutes, failed requests are retried with backoff, and requests to PubMed and arXiv are spaced out to respect their rate guidance. Heavy use of one source (OpenAlex in particular meters anonymous traffic) can still be slowed or refused; the tool then reports that source in `warnings`.
- **Safe parsing.** XML from the internet is refused if it declares entities, and responses over 8 MiB are rejected.
- **Untrusted text.** Titles, abstracts and full text are written by third parties. The server tells the model to treat them as data to read, never as instructions.
- **Nothing is stored or sent anywhere else.** There is no account, telemetry, or database.

## Limits

- Coverage depends on the public services. A paper missing from them may still exist.
- Ranking is rank fusion across sources with a small citation boost. It is not a relevance model, and it will not match what a publisher's own search returns.
- Citation counts differ between OpenAlex and Crossref; the larger is kept.
- Full text is returned only for PubMed Central open-access articles. Other open-access versions are given as links, because reading PDFs is out of scope.
- `country` uses author affiliations as OpenAlex records them, which is incomplete for some institutions.
- PubMed is queried without a key, at about three requests a second.

## Develop

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && pytest -q
LITSEARCH_LIVE=1 pytest tests/test_live.py      # optional: calls the real services
```

The tests use mocked HTTP, so they run offline.

MIT licence.


## Research paper

This tool was evaluated, with and without each tool, in an open preprint: Oluwawalemi, O. J. (2026). Do Verification Tools Improve on an AI Reader? A With-and-Without Evaluation of Fifteen Open-Source Tools for AI-Assisted Research. Zenodo. https://doi.org/10.5281/zenodo.23404947

The test corpora, truth labels, verdicts and scripts are in the same Zenodo record. Independent replication and testing are welcome. Please open an issue to share results.
