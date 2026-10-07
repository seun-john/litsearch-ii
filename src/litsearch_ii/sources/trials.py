"""ClinicalTrials.gov (API v2): registered clinical studies. No key needed."""

from __future__ import annotations

from typing import Any

from ..http import Http
from ..models import LitSearchError, clean_text

BASE = "https://clinicaltrials.gov/api/v2/studies"
STATUSES = {
    "RECRUITING",
    "NOT_YET_RECRUITING",
    "ACTIVE_NOT_RECRUITING",
    "COMPLETED",
    "ENROLLING_BY_INVITATION",
    "SUSPENDED",
    "TERMINATED",
    "WITHDRAWN",
    "UNKNOWN",
}


def to_trial(study: dict[str, Any]) -> dict[str, Any]:
    p = study.get("protocolSection", {})
    ident = p.get("identificationModule", {})
    status = p.get("statusModule", {})
    design = p.get("designModule", {})
    nct = ident.get("nctId")
    trial = {
        "nct_id": nct,
        "title": ident.get("briefTitle"),
        "official_title": ident.get("officialTitle"),
        "status": status.get("overallStatus"),
        "start_date": (status.get("startDateStruct") or {}).get("date"),
        "completion_date": (status.get("completionDateStruct") or {}).get("date"),
        "study_type": design.get("studyType"),
        "phases": design.get("phases"),
        "enrollment": (design.get("enrollmentInfo") or {}).get("count"),
        "conditions": p.get("conditionsModule", {}).get("conditions"),
        "sponsor": p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name"),
        "summary": clean_text(p.get("descriptionModule", {}).get("briefSummary")),
        "locations": len(p.get("contactsLocationsModule", {}).get("locations", [])),
        "has_results": study.get("hasResults"),
        "url": f"https://clinicaltrials.gov/study/{nct}" if nct else None,
    }
    return {k: v for k, v in trial.items() if v not in (None, [], "")}


async def search(
    http: Http, query: str, limit: int, *, status: str | None = None
) -> list[dict[str, Any]]:
    if status and status.upper() not in STATUSES:
        raise LitSearchError("status must be one of: " + ", ".join(sorted(STATUSES)))
    data = await http.get(
        BASE,
        {
            "query.term": query,
            "pageSize": limit,
            "filter.overallStatus": status.upper() if status else None,
            "format": "json",
        },
    )
    return [to_trial(s) for s in data.get("studies", [])]
