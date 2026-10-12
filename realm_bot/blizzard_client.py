from __future__ import annotations

import asyncio
import base64
import time
from typing import Any, Dict, List, Optional, cast

import httpx
from .metrics import blizzard_request_seconds, blizzard_requests_total


class BlizzardClient:
    """Battle.net / WoW Game Data API client.

    - Auth: OAuth2 Client Credentials against https://oauth.battle.net/token (global)
    - Region host: https://{region}.api.blizzard.com
    - Namespace: dynamic-{region}
    """

    def __init__(self, *, region: str, locale: str, client_id: str, client_secret: str, timeout: float = 20.0):
        self.region = region
        self.locale = locale
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = f"https://{region}.api.blizzard.com"
        self.namespace = f"dynamic-{region}"
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0
        # HTTP client for API calls
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout, http2=True)
        # Simple concurrency limiter for per-id fetches
        self._sem = asyncio.Semaphore(6)

    async def aclose(self):
        await self._client.aclose()

    async def _get_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expiry - 60:
            return self._token
        # Fetch token
        auth_bytes = f"{self.client_id}:{self.client_secret}".encode()
        basic = base64.b64encode(auth_bytes).decode()
        async with httpx.AsyncClient(timeout=15.0) as c:
            endpoint = "/oauth/token"
            method = "POST"
            start = time.perf_counter()
            status = "error"
            outcome = "error"
            try:
                r = await c.post(
                    "https://oauth.battle.net/token",
                    headers={
                        "Authorization": f"Basic {basic}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={"grant_type": "client_credentials"},
                )
                r.raise_for_status()
                status = str(r.status_code)
                outcome = "success"
                data = r.json()
                token = str(data["access_token"])  # ensure non-None string
                self._token = token
                self._token_expiry = now + float(data.get("expires_in", 0))
                return token
            finally:
                dur = time.perf_counter() - start
                blizzard_requests_total.labels(endpoint=endpoint, method=method, status=status, outcome=outcome).inc()
                blizzard_request_seconds.labels(endpoint=endpoint, method=method, status=status, outcome=outcome).observe(dur)

    async def _auth_headers(self) -> Dict[str, str]:
        token = await self._get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Battlenet-Namespace": self.namespace,
        }

    async def fetch_connected_realm_index(self) -> List[int]:
        """Return a list of connected realm IDs."""
        headers = await self._auth_headers()
        params = {"namespace": self.namespace, "locale": self.locale}
        endpoint = "/data/wow/connected-realm/index"
        method = "GET"
        start = time.perf_counter()
        status = "error"
        outcome = "error"
        r = None
        try:
            r = await self._client.get(endpoint, headers=headers, params=params)
            r.raise_for_status()
            status = str(r.status_code)
            outcome = "success"
        finally:
            dur = time.perf_counter() - start
            blizzard_requests_total.labels(endpoint=endpoint, method=method, status=status, outcome=outcome).inc()
            blizzard_request_seconds.labels(endpoint=endpoint, method=method, status=status, outcome=outcome).observe(dur)
        data = r.json()
        ids: List[int] = []
        for cr in data.get("connected_realms", []):
            href: str = cr.get("href")
            # Expect href like https://us.api.blizzard.com/data/wow/connected-realm/{id}?namespace=...
            if href:
                try:
                    id_str = href.split("/connected-realm/")[1].split("?")[0]
                    ids.append(int(id_str))
                except Exception:
                    continue
        return ids

    async def fetch_connected_realms_search(self, max_pages: int = 50) -> List[Dict[str, Any]]:
        """Placeholder for Search API; return [] to force fallback to index+detail.

        This keeps v1 simple and robust. We can implement search-based pagination later.
        """
        return []

    async def fetch_connected_realm_detail(self, cr_id: int) -> Dict[str, Any]:
        headers = await self._auth_headers()
        params = {"namespace": self.namespace, "locale": self.locale}
        endpoint = f"/data/wow/connected-realm/{cr_id}"
        method = "GET"
        start = time.perf_counter()
        status = "error"
        outcome = "error"
        r = None
        try:
            r = await self._client.get(endpoint, headers=headers, params=params)
            r.raise_for_status()
            status = str(r.status_code)
            outcome = "success"
            return r.json()
        finally:
            dur = time.perf_counter() - start
            blizzard_requests_total.labels(endpoint=endpoint, method=method, status=status, outcome=outcome).inc()
            blizzard_request_seconds.labels(endpoint=endpoint, method=method, status=status, outcome=outcome).observe(dur)

    async def fetch_realm_detail_by_href(self, href: str) -> Dict[str, Any]:
        headers = await self._auth_headers()
        endpoint = "/data/wow/realm/by-href"
        method = "GET"
        start = time.perf_counter()
        status = "error"
        outcome = "error"
        r = None
        try:
            r = await self._client.get(href, headers=headers)
            r.raise_for_status()
            status = str(r.status_code)
            outcome = "success"
            return r.json()
        finally:
            dur = time.perf_counter() - start
            blizzard_requests_total.labels(endpoint=endpoint, method=method, status=status, outcome=outcome).inc()
            blizzard_request_seconds.labels(endpoint=endpoint, method=method, status=status, outcome=outcome).observe(dur)

    async def fetch_all_connected_realms(self) -> List[Dict[str, Any]]:
        """Fetch connected realm data, preferring Search API and falling back to index+detail."""
        # Try search first to minimize calls
        try:
            search_res = await self.fetch_connected_realms_search()
            if search_res:
                return search_res
        except httpx.HTTPError:
            # Fall back on any HTTP error
            pass

        # Fallback: index + detail with bounded concurrency
        ids = await self.fetch_connected_realm_index()

        async def _fetch_one(cid: int):
            async with self._sem:
                return await self.fetch_connected_realm_detail(cid)

        results = await asyncio.gather(*[_fetch_one(cid) for cid in ids], return_exceptions=True)
        out: List[Dict[str, Any]] = []
        for res in results:
            if isinstance(res, Exception):
                continue
            out.append(cast(Dict[str, Any], res))
        return out
