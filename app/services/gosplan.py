"""Async GosPlan client: bounded concurrency, retries with exponential backoff + jitter."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any
from urllib.parse import quote

import httpx

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}


class GosplanError(Exception):
    """kind: not_found | timeout | unavailable | bad_response | http_error"""

    def __init__(self, kind: str, message: str, status: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.status = status


class GosplanClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 20.0,
        retries: int = 3,
        backoff: float = 0.5,
        concurrency: int = 8,
        client: httpx.AsyncClient | None = None,
        api_key: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key.strip()
        self.retries = max(0, retries)
        self.backoff = backoff
        self._sem = asyncio.Semaphore(concurrency)
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers={"Accept": "application/json", "User-Agent": "tender-price-predictor/1.0"},
            limits=httpx.Limits(max_connections=max(concurrency, 4) * 2),
        )
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # -- low level ---------------------------------------------------------------------
    async def _get(self, path: str) -> httpx.Response:
        url = f"{self.base_url}{path}"
        last: GosplanError | None = None
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["apikey"] = self._api_key  # production server (v2.gosplan.info) header
        for attempt in range(self.retries + 1):
            try:
                async with self._sem:  # slot is released while we back off
                    resp = await self._client.get(url, headers=headers)
            except httpx.TimeoutException:
                last = GosplanError("timeout", "GosPlan did not answer in time")
            except httpx.TransportError as exc:
                last = GosplanError("unavailable", f"Could not reach GosPlan ({type(exc).__name__})")
            else:
                if resp.status_code == 404:
                    raise GosplanError("not_found", "Not found in GosPlan (HTTP 404)", 404)
                if resp.status_code in RETRY_STATUS:
                    last = GosplanError("unavailable", f"GosPlan is unavailable (HTTP {resp.status_code})", resp.status_code)
                    delay = self._retry_after(resp)
                    if delay is not None and attempt < self.retries:
                        await asyncio.sleep(min(delay, 20.0))
                        continue
                elif resp.status_code >= 400:
                    raise GosplanError("http_error", f"GosPlan returned HTTP {resp.status_code}", resp.status_code)
                else:
                    return resp
            if attempt < self.retries:
                delay = self.backoff * (2**attempt) * (0.75 + random.random() / 2)  # noqa: S311 - jitter only
                log.warning("GET %s failed (%s); retry %d/%d in %.1fs", url, last.message if last else "?", attempt + 1, self.retries, delay)
                await asyncio.sleep(delay)
        assert last is not None
        raise last

    @staticmethod
    def _retry_after(resp: httpx.Response) -> float | None:
        v = resp.headers.get("Retry-After")
        try:
            return float(v) if v is not None else None
        except ValueError:
            return None

    @staticmethod
    def _json(resp: httpx.Response) -> Any:
        try:
            return resp.json()
        except ValueError as exc:
            raise GosplanError("bad_response", "GosPlan returned a response that is not valid JSON") from exc

    # -- API ----------------------------------------------------------------------------
    async def get_purchase(self, purchase_number: str) -> dict[str, Any]:
        resp = await self._get(f"/fz44/purchases/{quote(purchase_number, safe='')}")
        data = self._json(resp)
        if not isinstance(data, dict) or not data.get("purchase_number"):
            raise GosplanError("bad_response", "GosPlan response has no purchase_number")
        return data

    async def get_protocols(self, purchase_number: str) -> list[Any]:
        resp = await self._get(f"/fz44/purchases/{quote(purchase_number, safe='')}/protocols")
        data = self._json(resp)
        if not isinstance(data, list):
            raise GosplanError("bad_response", "Protocols response is not a list")
        return data

    async def download_purchase(self, purchase_number: str) -> bytes:
        """Raw JSON body, returned untouched for the download button."""
        resp = await self._get(f"/fz44/purchases/{quote(purchase_number, safe='')}")
        return resp.content
