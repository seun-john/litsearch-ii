"""Opt-in checks against the real services: LITSEARCH_LIVE=1 pytest tests/test_live.py"""

from __future__ import annotations

import asyncio
import os

import pytest

from litsearch_ii import service
from litsearch_ii.http import Http

pytestmark = pytest.mark.skipif(
    os.environ.get("LITSEARCH_LIVE") != "1", reason="set LITSEARCH_LIVE=1 to call the real services"
)


def test_every_source_answers() -> None:
    async def main() -> dict[str, str]:
        http = Http()
        try:
            return await service.doctor(http)
        finally:
            await http.aclose()

    health = asyncio.run(main())
    assert all(v == "ok" for v in health.values()), health


def test_a_known_paper_verifies() -> None:
    async def main() -> str:
        http = Http()
        try:
            result = await service.verify_citation(
                http, doi="10.1038/nature14539", title="Deep learning", year=2015
            )
            return str(result["status"])
        finally:
            await http.aclose()

    assert asyncio.run(main()) == "VERIFIED"
