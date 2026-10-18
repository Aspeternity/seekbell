import asyncio
import random
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from seekbell.collectors.rss import RssCollector
from seekbell.db.models import Source, SourceState, Website
from seekbell.domain.errors import SourceFailure
from seekbell.services.ingestion import Ingestion, IngestReport
from seekbell.sites.nodeseek import BUILTIN_ADAPTERS


@dataclass(frozen=True)
class PollOutcome:
    status: str
    code: str | None = None
    report: IngestReport | None = None


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
                "interval_seconds": source.interval_seconds,
            }

    async def run_once(self) -> PollOutcome:
        if self._lock.locked():
            return PollOutcome("overlap")
        async with self._lock:
            snapshot = await asyncio.to_thread(self._snapshot)
            self._interval = snapshot["interval_seconds"]
            if not snapshot["enabled"]:
                return PollOutcome("paused")
            if self.clock() < snapshot["next_attempt_at"]:
                return PollOutcome("backoff")
            try:
                adapter = BUILTIN_ADAPTERS.get(snapshot["website_id"])
                if adapter is None or snapshot["url"] != adapter.rss_url:
                    raise SourceFailure("unsupported_source")
                feed = await self.collector.fetch(adapter.rss_url)
                batch = await asyncio.to_thread(adapter.normalize, feed)
            except SourceFailure as exc:
                await asyncio.to_thread(
                    self.ingestion.record_failure,
                    self.source_id,
                    exc.code,
                    at=self.clock(),
                    retry_after=exc.retry_after,
                    jitter=self.jitter(),
                )
                return PollOutcome("failure", exc.code)
            report = await asyncio.to_thread(
                self.ingestion.ingest, self.source_id, batch, at=self.clock()
            )
            return PollOutcome(report.status, report=report)

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            started = time.monotonic()
            await self.run_once()
            delay = started + self._interval - time.monotonic()
            if delay <= 0:
                delay = self._interval  # Skip missed ticks rather than replaying them.
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=delay + self.jitter())
