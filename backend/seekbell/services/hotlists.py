"""Bounded on-demand hotlist reads; never feed monitoring or notification actors."""

import asyncio
import copy
import time

import httpx

from seekbell.domain.http import retry_after_seconds
from seekbell.sites.hotlists import HOTLIST_SOURCES

TTL = 600
MAX_BYTES = 1024 * 1024


class HotlistService:
    def __init__(self, *, transport=None, clock=time.time):
        self.clock = clock
        self.client = httpx.AsyncClient(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(8, connect=3),
            limits=httpx.Limits(max_connections=3),
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "User-Agent": "SeekBell/0.1",
            },
        )
        self.cache = {}
        self.states = {}
        self.locks = {}

    async def aclose(self):
        await self.client.aclose()

    async def get(self, website_id, period):
        source = HOTLIST_SOURCES[website_id]
        key = (website_id, source.provider_id, period)
        lock = self.locks.setdefault(key, asyncio.Lock())
        async with lock:
            now = self.clock()
            state = self.states.setdefault(
                key, {"next_attempt_at": 0, "failures": 0, "error_code": None}
            )
            if now >= state["next_attempt_at"]:
                retry_after = None
                code = "source_unavailable"
                try:
                    async with asyncio.timeout(10):
                        async with self.client.stream("GET", source.endpoints[period]) as response:
                            if response.status_code != 200:
                                retry_after = retry_after_seconds(
                                    response.headers.get("retry-after"), now
                                )
                                raise ValueError("source_unavailable")
                            if response.headers.get("content-encoding", "identity") != "identity":
                                raise ValueError("invalid_snapshot")
                            raw = bytearray()
                            async for chunk in response.aiter_raw():
                                raw.extend(chunk)
                                if len(raw) > MAX_BYTES:
                                    raise ValueError("invalid_snapshot")
                        snapshot = source.parse(raw, self.clock())
                    # A regressing source timestamp must not replace a newer snapshot.
                    if (
                        key in self.cache
                        and snapshot["source_updated_at"] < self.cache[key]["source_updated_at"]
                    ):
                        raise ValueError("invalid_snapshot")
                    self.cache[key] = snapshot
                    state.update(next_attempt_at=self.clock() + TTL, failures=0, error_code=None)
                except (httpx.HTTPError, TimeoutError, ValueError, OverflowError):
                    state["failures"] = min(6, state["failures"] + 1)
                    state["error_code"] = code
                    state["next_attempt_at"] = self.clock() + max(
                        min(600, 30 * 2 ** (state["failures"] - 1)), min(86400, retry_after or 0)
                    )
            snapshot = self.cache.get(key)
            return {
                **source.metadata(),
                "period": period,
                "status": "stale"
                if snapshot and state["error_code"]
                else "ready"
                if snapshot
                else "unavailable",
                "error_code": state["error_code"],
                "next_attempt_at": state["next_attempt_at"],
                "source_updated_at": snapshot["source_updated_at"] if snapshot else None,
                "fetched_at": snapshot["fetched_at"] if snapshot else None,
                "items": copy.deepcopy(snapshot["items"]) if snapshot else [],
            }
