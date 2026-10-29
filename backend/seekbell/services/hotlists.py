"""Bounded hotlists kept warm only while someone views them; snapshots survive restart."""

import asyncio
import copy
import hashlib
import json
import logging
import time
from contextlib import asynccontextmanager, suppress

import httpx
from sqlalchemy.orm import Session

from seekbell.collectors.http import public_client, public_response, source_failure
from seekbell.db.models import (
    HotlistSnapshot,
    Source,
    SourceState,
    Website,
    WebsiteInstallation,
)
from seekbell.db.transactions import database_call, write_session
from seekbell.domain.errors import SourceDeferred, SourceFailure
from seekbell.services.hotlist_settings import configuration
from seekbell.sites.hotlists import HOTLIST_SOURCES, number, text
from seekbell.sites.registry import BUILTIN_ADAPTERS

MAX_BYTES = 1024 * 1024
SNAPSHOT_MAX_AGE = 86400
logger = logging.getLogger(__name__)
WAITING_CODES = ("source_busy", "source_cooldown", "collection_priority")
# Keep every visible list warm while viewed and for this long after the last viewer left.
VIEW_GRACE = 900
WARM_TICK = 60


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
        # [(website_id, periods)] in warm order; the application binds it to the database.
        self.catalog = list
        self.viewed_at = None
        self.warmer = None
        self.wait_seconds = 25
        self.changed, self.nudge = asyncio.Event(), asyncio.Event()

    def _notify(self):
        self.changed.set()
        self.changed = asyncio.Event()

    def wake(self):
        """Release waiting board reads so they re-check their stop condition."""
        self._notify()

    async def aclose(self):
        self.closed = True
        self._notify()
        tasks = [*self.pending.values(), *([self.warmer] if self.warmer else [])]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.client.aclose()

    @asynccontextmanager
    async def _budget(self, website_id):
        if self.request_budget is None:
            yield
        else:
            async with self.request_budget.request(website_id, auxiliary=True):
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
            failure = source_failure(response, self.clock())
            if failure is not None:
                raise failure
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
            state.update(next_attempt_at=0, failures=0, error_code=None, deferred=False)
            return
        except SourceDeferred as error:
            state.update(
                next_attempt_at=error.next_attempt_at, error_code=error.code, deferred=True
            )
            return
        except SourceFailure as error:
            retry_after = error.retry_after
            if error.code in ("http_403", "http_429", "access_challenge"):
                code = error.code
        except (TimeoutError, httpx.HTTPError, ValueError, OverflowError):
            pass
        state["deferred"] = False
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
        self._notify()

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

    async def _prepare(self, website_id, period, collection_active=False):
        if self.closed:
            raise RuntimeError("Hotlist service is closed")
        source = HOTLIST_SOURCES[website_id]
        key = website_id, source.provider_id, period
        state = self.states.setdefault(
            key, {"next_attempt_at": 0, "failures": 0, "error_code": None, "deferred": False}
        )
        interval, priority = await database_call(
            self._policy, website_id, period, collection_active
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
        return source, key, state, interval, priority

    def _due(self, key, state, interval):
        # Successful freshness and failed-attempt backoff are independent. A new
        # configured interval takes effect without clearing failures or snapshots.
        snapshot = self.cache.get(key)
        return max(snapshot["fetched_at"] + interval if snapshot else 0, state["next_attempt_at"])

    async def _ensure(self, website_id, period):
        """Start the shared refresh when this list is due; returns it, if any."""
        source, key, state, interval, priority = await self._prepare(
            website_id, period, self.collection_active()
        )
        before = dict(state)
        task = self.pending.get(key)
        if task is None and state["deferred"] and self.request_budget is not None:
            until, code = await database_call(self.request_budget.view, website_id)
            if until <= self.clock():
                state.update(next_attempt_at=0, error_code=None, deferred=False)
            else:
                state.update(next_attempt_at=until, error_code=code or "source_cooldown")
            task = self.pending.get(key)
        if task is None and self.clock() >= self._due(key, state, interval):
            until, code = 0, None
            if self.request_budget is not None:
                until, code = await database_call(self.request_budget.view, website_id)
                if website_id == "linuxdo" and self.request_budget.lock.locked():
                    until = max(until, self.clock() + 2)
                    code = code or "source_busy"
            task = self.pending.get(key)
            # Budget/database reads may yield until another reader has already
            # completed a refresh. Recheck both the task and successful freshness.
            if task is None and self.clock() >= self._due(key, state, interval):
                if until > self.clock():
                    state.update(
                        next_attempt_at=until, error_code=code or "source_cooldown", deferred=True
                    )
                elif priority:
                    state.update(
                        next_attempt_at=self.clock() + 2,
                        error_code="collection_priority",
                        deferred=True,
                    )
                else:
                    task = asyncio.create_task(self._refresh(source, period, key, state))
                    self.pending[key] = task
                    task.add_done_callback(lambda finished: self._finished(key, finished))
                    self._notify()
        if state != before:
            self._notify()
        return key, interval, task

    def _render(self, website_id, period, key, interval):
        source, state, snapshot = HOTLIST_SOURCES[website_id], self.states[key], self.cache.get(key)
        task = self.pending.get(key)
        return {
            **source.metadata(),
            "period": period,
            "status": "waiting"
            if state["deferred"] or state["error_code"] in WAITING_CODES
            else "stale"
            if snapshot and state["error_code"]
            else "ready"
            if snapshot
            else "unavailable",
            "refreshing": task is not None and not task.done(),
            "error_code": state["error_code"],
            "next_attempt_at": self._due(key, state, interval),
            "refresh_interval": interval,
            "source_updated_at": snapshot["source_updated_at"] if snapshot else None,
            "fetched_at": snapshot["fetched_at"] if snapshot else None,
            "items": copy.deepcopy(snapshot["items"]) if snapshot else [],
        }

    async def get(self, website_id, period):
        """One list; a cold read waits for its first fetch. Does not start warming."""
        key, interval, task = await self._ensure(website_id, period)
        if key not in self.cache and task is not None:
            await asyncio.shield(task)
        return self._render(website_id, period, key, interval)

    async def _warm_site(self, website_id, periods):
        # One list at a time per site, so a shared request budget is never contended.
        due = []
        for period in periods:
            key, interval, task = await self._ensure(website_id, period)
            if task is not None:
                await asyncio.shield(task)
            due.append((key, interval))
        return min(self._due(key, self.states[key], interval) for key, interval in due)

    async def warm_once(self):
        """Refresh due visible lists; returns when to look again, or None to stop."""
        if self.closed or self.viewed_at is None:
            return None
        until = self.viewed_at + VIEW_GRACE
        catalog = await database_call(self.catalog)
        if not catalog or self.clock() > until:
            return None
        return min(
            until,
            *await asyncio.gather(*(self._warm_site(site, periods) for site, periods in catalog)),
        )

    async def _warm(self):
        try:
            while True:
                # Cleared before the pass, so a viewer arriving mid-pass triggers another.
                self.nudge.clear()
                if (wake := await self.warm_once()) is None:
                    break
                with suppress(TimeoutError):
                    await asyncio.wait_for(
                        self.nudge.wait(), min(WARM_TICK, max(1, wake - self.clock()))
                    )
        except Exception as error:
            # The next viewer restarts warming; reads keep serving stored snapshots.
            if not self.closed:
                logger.warning("Hotlist warming stopped: %s", type(error).__name__)

    def touch(self, nudge=False):
        """A viewer read extends the grace period; a fresh view also checks due lists now.

        Continuing long polls never nudge: a change would answer the poll and its
        follow-up would start another pass, turning moving retry times into a loop.
        """
        self.viewed_at = self.clock()
        if self.warmer is None or self.warmer.done():
            self.warmer = asyncio.create_task(self._warm())
        elif nudge:
            self.nudge.set()

    async def _board(self):
        lists = []
        for website_id, periods in await database_call(self.catalog):
            for period in periods:
                _, key, _, interval, _ = await self._prepare(website_id, period)
                lists.append(self._render(website_id, period, key, interval))
        tag = hashlib.sha256(json.dumps(lists, sort_keys=True).encode()).hexdigest()[:32]
        return {"tag": tag, "lists": lists}

    async def board(self, after=None, stop=lambda: False):
        """Every visible list; with the caller's tag, wait until something changes."""
        self.touch(nudge=after is None)
        if after is None:
            # The selected list leads the catalog: start it now so the reply shows it.
            catalog = await database_call(self.catalog)
            if catalog:
                await self._ensure(catalog[0][0], catalog[0][1][0])
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.wait_seconds
        while True:
            changed = self.changed
            board = await self._board()
            if board["tag"] != after or stop() or loop.time() >= deadline:
                return board
            with suppress(TimeoutError):
                await asyncio.wait_for(changed.wait(), deadline - loop.time())
            if self.closed:
                raise RuntimeError("Hotlist service is closed")
