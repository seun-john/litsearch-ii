# Changelog

## Unreleased

- `verify_citation` / `verify --journal`: the journal is compared with the record's. An abbreviation of the record's journal name is accepted (`accepted_equivalences`); a different journal is a `METADATA_MISMATCH`. The parameter is optional.
- A `RETRACTED:`, `Retraction:` or `Withdrawn:` prefix on the record's title is ignored when comparing titles.
- Title-only verification: a `METADATA_MISMATCH` with a year more than two years away, or authors that do not match, now carries `identity_doubts` and a note. The status is unchanged.

## 0.1.0

First release.

- Multi-source search with de-duplication and rank fusion across OpenAlex, Crossref, Europe PMC, PubMed and arXiv.
- Paper details, citing and referenced papers, similar papers, open-access full text, clinical trials, citation verification and BibTeX / RIS / CSL-JSON export.
- Works with no accounts and no API keys.
