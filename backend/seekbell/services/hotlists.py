"""Bounded on-demand hotlists; snapshots survive restart without background polling."""

import asyncio
import copy
import time
from contextlib import asynccontextmanager

import httpx
from sqlalchemy.orm import Session

from seekbell.collectors.http import public_client, public_response
from seekbell.db.models import (
    HotlistSnapshot,
    Source,
    SourceState,
    Website,
    WebsiteInstallation,
)
from seekbell.db.transactions import database_call, write_session
from seekbell.domain.errors import SourceDeferred, SourceFailure
from seekbell.domain.http import retry_after_seconds
from seekbell.services.hotlist_settings import configuration
from seekbell.sites.hotlists import HOTLIST_SOURCES, number, text
from seekbell.sites.registry import BUILTIN_ADAPTERS

MAX_BYTES = 1024 * 1024
SNAPSHOT_MAX_AGE = 86400
WAITING_CODES = ("source_busy", "source_cooldown", "collection_priority")


class HotlistService:
    def __init__(
        self,
        *,
        transport=None,
        clock=time.time,
        engine=None,
        request_budget=None,
        collection_active=None,
    ):
        self.clock, self.engine, self.request_budget = clock, engine, request_budget
        self.collection_active = collection_active or (lambda: False)
        self.client = public_client(
            transport=transport,
            timeout=httpx.Timeout(8, connect=3),
            limits=httpx.Limits(max_connections=3),
            headers={
                "Accept-Encoding": "identity",
                "User-Agent": "SeekBell/0.1",
            },
        )
        self.cache, self.states, self.pending = {}, {}, {}
        self.loaded = set()
        self.closed = False

    async def aclose(self):
        self.closed = True
        tasks = list(self.pending.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.client.aclose()

    @asynccontextmanager
    async def _budget(self, website_id):
        if self.request_budget is None:
            yield
        else:
            async with self.request_budget.request(website_id):
                yield

    def _load(self, key):
        with Session(self.engine) as session:
            row = session.get(HotlistSnapshot, key)
            if row is None:
                return None
            fetched, updated = number(row.fetched_at), number(row.source_updated_at)
            now = self.clock()
            if (
                fetched is None
                or not now - SNAPSHOT_MAX_AGE <= fetched <= now + 300
                or (updated is not None and updated > now + 300)
                or (key[0] != "linuxdo" and not updated)
                or not isinstance(row.items, list)
                or len(row.items) > 100
            ):
                return None
            items, seen = [], set()
            for entry in row.items:
                if not isinstance(entry, dict):
                    return None
                identifier = entry.get("id")
                title = text(entry.get("title"), 1000)
                rank = entry.get("rank")
                if (
                    not isinstance(identifier, str)
                    or not identifier.isascii()
                    or not identifier.isdigit()
                    or not 1 <= len(identifier) <= 20
                    or int(identifier) < 1
                    or identifier in seen
                    or not title
                    or type(rank) is not int
                    or not 1 <= rank <= 500
                ):
                    return None
                seen.add(identifier)
                items.append(
                    {
                        "id": identifier,
                        "rank": rank,
                        "title": title,
                        "url": BUILTIN_ADAPTERS[key[0]].canonical_url(identifier),
                        "author": text(entry.get("author"), 100),
                        "category": text(entry.get("category"), 80),
                        "views": number(entry.get("views")),
                        "comments": number(entry.get("comments")),
                    }
                )
            return {"fetched_at": fetched, "source_updated_at": updated, "items": items}

    def _save(self, key, snapshot):
        with write_session(self.engine) as session:
            row = session.get(HotlistSnapshot, key)
            if row is None:
                row = HotlistSnapshot(website_id=key[0], provider_id=key[1], period=key[2])
                session.add(row)
            row.fetched_at = snapshot["fetched_at"]
            row.source_updated_at = snapshot["source_updated_at"]
            row.items = snapshot["items"]

    async def _fetch(self, source, period):
        accept = (
            "application/rss+xml, application/xml, text/xml"
            if source.format == "rss"
            else "application/json"
        )
        async with (
            self._budget(source.website_id),
            public_response(
                self.client, source.endpoints[period], headers={"Accept": accept}
            ) as response,
        ):
            if response.status_code != 200:
                code = (
                    "access_challenge"
                    if response.status_code == 403
                    and response.headers.get("cf-mitigated") == "challenge"
                    else f"http_{response.status_code}"
                )
                raise SourceFailure(
                    code,
                    retry_after=retry_after_seconds(
                        response.headers.get("retry-after"), self.clock()
                    ),
                )
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                raise ValueError("invalid_snapshot")
            if source.format == "rss" and (
                response.headers.get("content-type", "").split(";")[0].lower()
                not in ("application/rss+xml", "application/xml", "text/xml")
            ):
                raise ValueError("invalid_snapshot")
            raw = bytearray()
            async for chunk in response.aiter_raw():
                raw.extend(chunk)
                if len(raw) > MAX_BYTES:
                    raise ValueError("invalid_snapshot")
        return raw

    async def _refresh(self, source, period, key, state):
        retry_after = None
        code = "source_unavailable"
        try:
            async with asyncio.timeout(10):
                raw = await self._fetch(source, period)
                snapshot = await asyncio.to_thread(source.parse, raw, self.clock())
            old = self.cache.get(key)
            updated = snapshot["source_updated_at"]
            if (
                old
                and updated is not None
                and old["source_updated_at"] is not None
                and updated < old["source_updated_at"]
            ):
                raise ValueError("invalid_snapshot")
            if self.engine is not None:
                await database_call(self._save, key, snapshot)
            self.cache[key] = snapshot
            state.update(next_attempt_at=0, failures=0, error_code=None)
            return
        except SourceDeferred as error:
            state.update(next_attempt_at=error.next_attempt_at, error_code=error.code)
            return
        except SourceFailure as error:
            retry_after = error.retry_after
            if error.code in ("http_403", "http_429", "access_challenge"):
                code = error.code
        except TimeoutError:
            if self.request_budget is not None and source.website_id == "linuxdo":
                await database_call(
                    self.request_budget.failed, SourceFailure("timeout"), self.clock()
                )
        except (httpx.HTTPError, ValueError, OverflowError):
            pass
        state["failures"] = min(6, state["failures"] + 1)
        state["error_code"] = code
        state["next_attempt_at"] = self.clock() + max(
            min(300 if source.website_id == "linuxdo" else 600, 30 * 2 ** (state["failures"] - 1)),
            min(86400, retry_after or 0),
        )
        if self.request_budget is not None:
            until, _ = await database_call(self.request_budget.view, source.website_id)
            state["next_attempt_at"] = max(state["next_attempt_at"], until)

    def _finished(self, key, task):
        if self.pending.get(key) is task:
            del self.pending[key]
        if not task.cancelled():
            task.exception()

    def _policy(self, website_id, period, collection_active):
        source = HOTLIST_SOURCES[website_id]
        interval, priority = source.recommended_interval(period), False
        if self.engine is not None:
            with Session(self.engine) as session:
                installation = session.get(WebsiteInstallation, website_id)
                if installation is not None:
                    policy = configuration(website_id, installation.hotlist_settings)
                    interval = next(
                        row["interval_seconds"] for row in policy["periods"] if row["id"] == period
                    )
                    if collection_active and website_id == "linuxdo":
                        rss = session.get(Source, BUILTIN_ADAPTERS[website_id].source_id)
                        state = session.get(SourceState, rss.id)
                        website = session.get(Website, website_id)
                        priority = (
                            rss.enabled
                            and website.enabled
                            and state.next_attempt_at <= self.clock() + 2
                        )
        return interval, priority

    async def get(self, website_id, period):
        if self.closed:
            raise RuntimeError("Hotlist service is closed")
        source = HOTLIST_SOURCES[website_id]
        key = website_id, source.provider_id, period
        state = self.states.setdefault(
            key, {"next_attempt_at": 0, "failures": 0, "error_code": None}
        )
        interval, priority = await database_call(
            self._policy, website_id, period, self.collection_active()
        )
        if self.engine is not None and key not in self.loaded:
            stored = await database_call(self._load, key)
            self.loaded.add(key)
            if stored:
                self.cache.setdefault(key, stored)
        if self.closed:
            raise RuntimeError("Hotlist service is closed")
        if key in self.cache and self.cache[key]["fetched_at"] < self.clock() - SNAPSHOT_MAX_AGE:
            del self.cache[key]
        snapshot = self.cache.get(key)
        # Successful freshness and failed-attempt backoff are independent. A new
        # configured interval takes effect without clearing failures or snapshots.
        fresh_until = snapshot["fetched_at"] + interval if snapshot else 0
        next_attempt = max(fresh_until, state["next_attempt_at"])
        task = self.pending.get(key)
        if task is None and self.clock() >= next_attempt:
            until, code = 0, None
            if self.request_budget is not None:
                until, code = await database_call(self.request_budget.view, website_id)
                if website_id == "linuxdo" and self.request_budget.lock.locked():
                    until = max(until, self.clock() + 2)
                    code = code or "source_busy"
            task = self.pending.get(key)
            latest = self.cache.get(key)
            due = max(latest["fetched_at"] + interval if latest else 0, state["next_attempt_at"])
            # Budget/database reads may yield until another reader has already
            # completed a refresh. Recheck both the task and successful freshness.
            if task is None and self.clock() >= due:
                if until > self.clock():
                    state.update(next_attempt_at=until, error_code=code or "source_cooldown")
                elif priority:
                    state.update(next_attempt_at=self.clock() + 2, error_code="collection_priority")
                else:
                    task = asyncio.create_task(self._refresh(source, period, key, state))
                    self.pending[key] = task
                    task.add_done_callback(lambda finished: self._finished(key, finished))
        if key not in self.cache and task is not None:
            await asyncio.shield(task)
        snapshot = self.cache.get(key)
        refreshing = task is not None and not task.done()
        next_attempt = max(
            snapshot["fetched_at"] + interval if snapshot else 0, state["next_attempt_at"]
        )
        return {
            **source.metadata(),
            "period": period,
            "status": "waiting"
            if state["error_code"] in WAITING_CODES
            else "stale"
            if snapshot and state["error_code"]
            else "ready"
            if snapshot
            else "unavailable",
            "refreshing": refreshing,
            "error_code": state["error_code"],
            "next_attempt_at": self.clock() + 2 if refreshing else next_attempt,
            "refresh_interval": interval,
            "source_updated_at": snapshot["source_updated_at"] if snapshot else None,
            "fetched_at": snapshot["fetched_at"] if snapshot else None,
            "items": copy.deepcopy(snapshot["items"]) if snapshot else [],
        }
