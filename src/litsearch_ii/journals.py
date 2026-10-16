"""Decide whether a cited journal name is an abbreviation of a record's journal name."""

from __future__ import annotations

import re

FILLER = frozenset(
    {"of", "the", "and", "for", "in", "on", "de", "la", "le", "du", "des", "und", "der", "di", "et"}
)
# Standard abbreviations that drop letters from the middle of the word, so are not prefixes.
# Kept short on purpose: matching on letter subsequences alone would accept 'Nat Med' for
# 'Nature Methods'.
NON_PREFIX = {
    "natl": "national",
    "intl": "international",
    "mgmt": "management",
    "govt": "government",
    "engrg": "engineering",
}
NOTICE_PREFIX = re.compile(r"^\s*(?:retracted|retraction|withdrawn)\s*[:\-–—]\s*", re.I)


def norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.casefold()).strip()


def strip_notice(title: str) -> str:
    """Publishers prefix a retracted paper's title with 'RETRACTED:'; the citation does not."""
    return NOTICE_PREFIX.sub("", title)


def _tokens(name: str) -> list[str]:
    return [t for t in norm(name).split() if t not in FILLER]


def abbreviates(short: str, full: str) -> bool:
    """True when `short` reads as a standard abbreviation of `full`.

    'Nat Prod Rep' abbreviates 'Natural Product Reports'; 'N Engl J Med' abbreviates 'New
    England Journal of Medicine'. Every word must be the same word, a prefix of it, or one of a
    few standard forms such as 'Natl', and the word count must match once filler words (of,
    the, and) are dropped, so 'Nature' does not match 'Nature Medicine'. A one-letter word
    counts as 'J' for Journal, anywhere before the end, or inside a closing run of at least two
    letters ('U S A'). A single closing letter must match exactly, so 'Phys Rev A' does not
    match 'Physical Review Applied'. A subtitle after a colon in `full` may be left out.
    """
    return any(_match(_tokens(short), _tokens(c)) for c in (full, full.split(":", 1)[0]))


def same_journal(a: str, b: str) -> bool:
    return norm(a) == norm(b) or abbreviates(a, b) or abbreviates(b, a)


def _match(a: list[str], b: list[str]) -> bool:
    if not a or not b:
        return False
    while len(a) > len(b) and len(a[-1]) == 1:
        a.pop()
    if len(a) != len(b):
        return False
    run_start = len(a)  # start of the closing run of one-letter words
    while run_start > 0 and len(a[run_start - 1]) == 1:
        run_start -= 1
    for i, (x, y) in enumerate(zip(a, b, strict=True)):
        if x == y:
            continue
        if not y.startswith(x) and NON_PREFIX.get(x) != y:
            return False
        if len(x) == 1:
            in_closing_run = i >= run_start and len(a) - run_start >= 2
            if not (in_closing_run or i < len(a) - 1 or (x == "j" and y == "journal")):
                return False
    return True
