import asyncio
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from seekbell.collectors.rss import RssCollector
from seekbell.db.models import Source, SourceState, Website
from seekbell.domain.errors import SourceFailure
from seekbell.services.async_tools import storage_call, wait_for_signal
from seekbell.services.ingestion import Ingestion, IngestReport
from seekbell.sites.nodeseek import BUILTIN_ADAPTERS


@dataclass(frozen=True)
class PollOutcome:
    status: str
    code: str | None = None
    report: IngestReport | None = None


class SourceBusy(Exception):
    pass


class SourceRunner:
    """One shared source, no overlap or catch-up queue. Construct explicitly; no auto-start."""

    def __init__(
        self,
        engine: Engine,
        collector: RssCollector,
        *,
        source_id: str = "nodeseek-rss",
        clock: Callable[[], float] = time.time,
        jitter: Callable[[], float] | None = None,
    ):
        self.engine = engine
        self.collector = collector
        self.source_id = source_id
        self.ingestion = Ingestion(engine)
        self.clock = clock
        self.jitter = jitter or (lambda: random.uniform(0, 0.5))
        self._lock = asyncio.Lock()
        self._interval = 10

    def _snapshot(self) -> dict:
        with Session(self.engine) as session:
            source = session.get(Source, self.source_id)
            state = session.get(SourceState, self.source_id)
            if source is None or state is None:
                raise ValueError("Unknown source")
            website = session.get(Website, source.website_id)
            return {
                "enabled": source.enabled and website.enabled,
                "website_id": source.website_id,
                "url": source.url,
                "next_attempt_at": state.next_attempt_at,
                "last_error_code": state.last_error_code,
                "interval_seconds": source.interval_seconds,
                "revision": source.revision,
            }

    async def _fetch(self, snapshot: dict):
        adapter = BUILTIN_ADAPTERS.get(snapshot["website_id"])
        if adapter is None or snapshot["url"] != adapter.rss_url:
            raise SourceFailure("unsupported_source")
        feed = await self.collector.fetch(adapter.rss_url)
        return await asyncio.to_thread(adapter.normalize, feed)

    async def check_connection(self) -> dict:
        if self._lock.locked():
            raise SourceBusy
        async with self._lock:
            snapshot = await storage_call(self._snapshot)
            if snapshot["last_error_code"] and self.clock() < snapshot["next_attempt_at"]:
                return {
                    "status": "backoff",
                    "code": snapshot["last_error_code"],
                    "next_attempt_at": snapshot["next_attempt_at"],
                    "at": self.clock(),
                }
            try:
                batch = await asyncio.wait_for(self._fetch(snapshot), timeout=15)
            except (SourceFailure, TimeoutError) as error:
                code = error.code if isinstance(error, SourceFailure) else "timeout"
                if re.fullmatch(r"[a-z0-9_]{1,80}", code) is None:
                    code = "source_error"
                next_at = await storage_call(
                    self.ingestion.record_failure,
                    self.source_id,
                    code,
                    at=self.clock(),
                    retry_after=error.retry_after if isinstance(error, SourceFailure) else None,
                    jitter=self.jitter(),
                )
                return {
                    "status": "failure",
                    "code": code,
                    "at": self.clock(),
                    "next_attempt_at": next_at,
                }
            return {
                "status": "success",
                "code": None,
                "at": self.clock(),
                "raw_count": batch.raw_count,
                "valid_count": len(batch.posts),
                "diagnostics": [item.code for item in batch.diagnostics],
            }

    async def run_once(self) -> PollOutcome:
        if self._lock.locked():
            return PollOutcome("overlap")
        async with self._lock:
            snapshot = await storage_call(self._snapshot)
            self._interval = snapshot["interval_seconds"]
            if not snapshot["enabled"]:
                return PollOutcome("paused")
            if self.clock() < snapshot["next_attempt_at"]:
                return PollOutcome("backoff")
            try:
                batch = await self._fetch(snapshot)
            except SourceFailure as exc:
                await storage_call(
                    self.ingestion.record_failure,
                    self.source_id,
                    exc.code,
                    at=self.clock(),
                    retry_after=exc.retry_after,
                    jitter=self.jitter(),
                )
                return PollOutcome("failure", exc.code)
            report = await storage_call(
                self.ingestion.ingest,
                self.source_id,
                batch,
                at=self.clock(),
                expected_source_revision=snapshot["revision"],
            )
            return PollOutcome(report.status, report=report)

    async def run(self, stop: asyncio.Event, *, wake: asyncio.Event | None = None) -> None:
        while not stop.is_set():
            if wake is not None:
                wake.clear()
            started = time.monotonic()
            await self.run_once()
            delay = started + self._interval - time.monotonic()
            if delay <= 0:
                delay = self._interval  # Skip missed ticks rather than replaying them.
            await wait_for_signal(stop, wake, delay + self.jitter())
