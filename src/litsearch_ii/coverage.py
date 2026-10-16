"""The shared coverage block: how much a call could judge, and why not."""

from __future__ import annotations

from typing import Any


def coverage(
    unit: str,
    items: int,
    decided: int,
    reasons: dict[str, int] | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    """`decided + undecided == items` and the reasons add up to `undecided`; a caller that
    breaks that has a bug, so this raises instead of reporting numbers that do not add up."""
    kept = {k: v for k, v in sorted((reasons or {}).items()) if v}
    undecided = items - decided
    if not 0 <= decided <= items or sum(kept.values()) != undecided:
        raise RuntimeError(f"inconsistent coverage: {items} items, {decided} decided, {kept}")
    return {
        "unit": unit,
        "items": items,
        "decided": decided,
        "undecided": undecided,
        "reasons": kept,
        "suppressed": 0,
        "notes": list(notes or []),
    }


DECIDED_VERIFY_STATUSES = frozenset({"VERIFIED", "METADATA_MISMATCH", "RETRACTED"})


def for_verification(result: dict[str, Any]) -> dict[str, Any]:
    """One citation: decided if a record was found and compared, undecided otherwise.

    NOT_FOUND and POSSIBLE_MATCH are warnings, never proof either way, so they are undecided.
    """
    status = str(result.get("status", ""))
    if status in DECIDED_VERIFY_STATUSES:
        return coverage("citations", 1, 1)
    notes = []
    if status == "NOT_FOUND":
        notes.append("not found is a warning, not proof that the citation was invented")
    return coverage("citations", 1, 0, {status.lower() or "unknown": 1}, notes)


def for_search(
    chosen: list[str], answered: list[str], failed: list[dict[str, str]]
) -> dict[str, Any]:
    """A search: a source is decided if it answered; one that raised an error is undecided."""
    broke = [w["source"] for w in failed if w["source"] in chosen and w["source"] not in answered]
    notes = [f"no answer from: {', '.join(sorted(broke))}"] if broke else []
    return coverage(
        "sources", len(chosen), len(answered), {"source_failed": len(chosen) - len(answered)}, notes
    )
