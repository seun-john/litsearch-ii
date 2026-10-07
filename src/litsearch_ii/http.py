"""A small, polite HTTP layer: host allow-list, retries, size cap, caching and rate limits.

Every request goes to a fixed list of public scholarly hosts. Identifiers and queries only
ever appear in the path or query string, never as a host, so tool input cannot redirect a
request to another server.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any
from urllib.parse import urlparse

import httpx

from . import __version__
from .models import LitSearchError

ALLOWED_HOSTS = {
    "api.openalex.org",
    "api.crossref.org",
    "www.ebi.ac.uk",
    "eutils.ncbi.nlm.nih.gov",
    "export.arxiv.org",
    "clinicaltrials.gov",
}
USER_AGENT = f"litsearch-ii/{__version__} (+https://github.com/seun-john/litsearch-ii)"
MAX_BYTES = 8 * 1024 * 1024
# Minimum seconds between requests to one host (NCBI allows 3 per second without a key).
MIN_INTERVAL = {"eutils.ncbi.nlm.nih.gov": 0.4, "export.arxiv.org": 3.0, "api.openalex.org": 0.1}
RETRY_STATUS = {429, 500, 502, 503, 504}


class Http:
    """Async GET with caching. Pass `client` in tests to use a mock transport."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        cache_size: int = 256,
        cache_seconds: float = 900.0,
        retries: int = 2,
        timeout: float = 20.0,
    ) -> None:
        self._client = client
        self._owns_client = client is None
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._cache_size = cache_size
        self._cache_seconds = cache_seconds
        self._retries = retries
        self._timeout = timeout
        self._last_call: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/xml, */*"},
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def _pace(self, host: str) -> None:
        gap = MIN_INTERVAL.get(host, 0.0)
        if not gap:
            return
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            wait = self._last_call.get(host, 0.0) + gap - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call[host] = time.monotonic()

    async def get(
        self, url: str, params: dict[str, Any] | None = None, *, as_json: bool = True
    ) -> Any:
        host = urlparse(url).hostname or ""
        if host not in ALLOWED_HOSTS:
            raise LitSearchError(f"refusing to contact {host!r}: not a supported source")
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        key = f"{as_json}|{url}|{sorted(clean.items())}"
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < self._cache_seconds:
            self._cache.move_to_end(key)
            return hit[1]
        last_problem = "no response"
        for attempt in range(self._retries + 1):
            await self._pace(host)
            try:
                response = await self._http().get(url, params=clean)
            except httpx.TimeoutException:
                last_problem = "timed out"
            except httpx.HTTPError as exc:
                last_problem = f"network error ({type(exc).__name__})"
            else:
                if response.status_code in RETRY_STATUS and attempt < self._retries:
                    last_problem = f"HTTP {response.status_code}"
                    delay = response.headers.get("Retry-After", "")
                    await asyncio.sleep(
                        min(float(delay) if delay.isdigit() else 0.5 * 2**attempt, 8)
                    )
                    continue
                if response.status_code == 404:
                    raise LitSearchError(f"{host}: not found")
                if response.status_code >= 400:
                    raise LitSearchError(f"{host}: HTTP {response.status_code}")
                if len(response.content) > MAX_BYTES:
                    raise LitSearchError(
                        f"{host}: response larger than {MAX_BYTES // 1024 // 1024} MiB"
                    )
                try:
                    value = response.json() if as_json else response.text
                except ValueError:
                    raise LitSearchError(f"{host}: the response was not valid JSON") from None
                self._cache[key] = (time.monotonic(), value)
                while len(self._cache) > self._cache_size:
                    self._cache.popitem(last=False)
                return value
            if attempt < self._retries:
                await asyncio.sleep(0.5 * 2**attempt)
        raise LitSearchError(f"{host}: {last_problem}")
