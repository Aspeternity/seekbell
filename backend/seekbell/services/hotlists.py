"""Bounded on-demand hotlists; cached reads never wait for a refresh."""

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
        self.pending = {}
        self.closed = False

    async def aclose(self):
        self.closed = True
        tasks = list(self.pending.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.client.aclose()

    async def _refresh(self, source, period, key, state):
        retry_after = None
        try:
            async with asyncio.timeout(10):
                async with self.client.stream("GET", source.endpoints[period]) as response:
                    if response.status_code != 200:
                        retry_after = retry_after_seconds(
                            response.headers.get("retry-after"), self.clock()
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
            if (
                key in self.cache
                and snapshot["source_updated_at"] < self.cache[key]["source_updated_at"]
            ):
                raise ValueError("invalid_snapshot")
            self.cache[key] = snapshot
            state.update(next_attempt_at=self.clock() + TTL, failures=0, error_code=None)
        except (httpx.HTTPError, TimeoutError, ValueError, OverflowError):
            state["failures"] = min(6, state["failures"] + 1)
            state["error_code"] = "source_unavailable"
            state["next_attempt_at"] = self.clock() + max(
                min(600, 30 * 2 ** (state["failures"] - 1)), min(86400, retry_after or 0)
            )

    def _finished(self, key, task):
        if self.pending.get(key) is task:
            del self.pending[key]
        if not task.cancelled():
            task.exception()

    async def get(self, website_id, period):
        if self.closed:
            raise RuntimeError("Hotlist service is closed")
        source = HOTLIST_SOURCES[website_id]
        key = (website_id, source.provider_id, period)
        state = self.states.setdefault(
            key, {"next_attempt_at": 0, "failures": 0, "error_code": None}
        )
        task = self.pending.get(key)
        if task is None and self.clock() >= state["next_attempt_at"]:
            task = asyncio.create_task(self._refresh(source, period, key, state))
            self.pending[key] = task
            task.add_done_callback(lambda finished: self._finished(key, finished))
        # A cold reader shares the fetch; canceling that reader must not cancel other readers.
        if key not in self.cache and task is not None:
            await asyncio.shield(task)
        snapshot = self.cache.get(key)
        refreshing = task is not None and not task.done()
        return {
            **source.metadata(),
            "period": period,
            "status": "stale"
            if snapshot and state["error_code"]
            else "ready"
            if snapshot
            else "unavailable",
            "refreshing": refreshing,
            "error_code": state["error_code"],
            "next_attempt_at": self.clock() + 2 if refreshing else state["next_attempt_at"],
            "source_updated_at": snapshot["source_updated_at"] if snapshot else None,
            "fetched_at": snapshot["fetched_at"] if snapshot else None,
            "items": copy.deepcopy(snapshot["items"]) if snapshot else [],
        }
