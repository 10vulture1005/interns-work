"""Async HTTP with retry/backoff and per-host concurrency limits.

Connectors talk to the network only through `Net`, which keeps request policy
(retries, backoff, politeness) in one place.
"""

from __future__ import annotations

import asyncio
import random

import httpx

_RETRYABLE = {429, 500, 502, 503, 504}


class HostLimiter:
    """Caps how many requests run concurrently against any single host."""

    def __init__(self, per_host: int = 8) -> None:
        self._per_host = per_host
        self._sems: dict[str, asyncio.Semaphore] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, host: str) -> asyncio.Semaphore:
        async with self._lock:
            sem = self._sems.get(host)
            if sem is None:
                sem = asyncio.Semaphore(self._per_host)
                self._sems[host] = sem
            return sem


def _backoff(attempt: int, response: httpx.Response | None = None) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After", "")
        if retry_after.isdigit():
            return min(float(retry_after), 30.0)
    return min(2**attempt + random.random(), 20.0)


class Net:
    """A thin client wrapper bound to one httpx session + host limiter."""

    def __init__(self, client: httpx.AsyncClient, limiter: HostLimiter) -> None:
        self._client = client
        self._limiter = limiter

    async def get_json(self, url: str, **kwargs):
        return await self._request("GET", url, **kwargs)

    async def post_json(self, url: str, **kwargs):
        return await self._request("POST", url, **kwargs)

    async def _request(self, method: str, url: str, *, retries: int = 3, **kwargs):
        host = httpx.URL(url).host
        sem = await self._limiter.acquire(host)
        last_error: Exception | None = None

        for attempt in range(retries + 1):
            try:
                async with sem:
                    response = await self._client.request(method, url, **kwargs)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_error = exc
                if attempt == retries:
                    raise
                await asyncio.sleep(_backoff(attempt))
                continue

            if response.status_code in _RETRYABLE and attempt < retries:
                await asyncio.sleep(_backoff(attempt, response))
                continue

            response.raise_for_status()
            return response.json()

        raise last_error or httpx.HTTPError(f"request to {url} failed after retries")

    async def fetch_html(self, url: str, *, needs_interaction: bool = False, check_robots: bool = False):
        """Fetch HTML, escalating from Tier 1 (httpx/Fetcher) to Tier 2/3 (Scrapling)."""
        host = httpx.URL(url).host
        sem = await self._limiter.acquire(host)

        def _do_fetch():
            from scrapling.fetchers import Fetcher, StealthyFetcher, DynamicFetcher
            
            if needs_interaction:
                try:
                    return DynamicFetcher.fetch(url, headless=True)
                except Exception as e:
                    print(f"Tier 3 fetch failed for {url}: {e}")
                    return None
                
            try:
                page = Fetcher.get(url, timeout=15)
                if page.status == 200:
                    return page
            except Exception as e:
                print(f"Tier 1 fetch failed for {url}: {e}")

            # Tier 1 failed — escalate
            try:
                print(f"Escalating to Tier 2 for {url}")
                return StealthyFetcher.fetch(url, headless=True)
            except Exception as e:
                print(f"Tier 2 fetch failed for {url}: {e}")
                return None
                
        async with sem:
            return await asyncio.to_thread(_do_fetch)
