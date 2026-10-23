import asyncio
import random
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from seekbell.collectors.rss import RssCollector
from seekbell.db.models import (
    Administrator,
    Source,
    SourceProbe,
    SourceState,
    Website,
    WebsiteInstallation,
)
from seekbell.db.transactions import database_call
from seekbell.domain.errors import SourceDeferred, SourceFailure
from seekbell.services.ingestion import Ingestion, IngestReport
from seekbell.services.request_budget import request_state
from seekbell.services.source_probe import probe_backoff
from seekbell.sites.registry import BUILTIN_ADAPTERS


@dataclass(frozen=True)
class PollOutcome:
    status: str
    code: str | None = None
    report: IngestReport | None = None


class SourceRunner:
    """One shared source, no overlap or catch-up queue. One actor per service instance."""

    def __init__(
        self,
        engine: Engine,
        collector: RssCollector,
        *,
        source_id: str = "nodeseek-rss",
        clock: Callable[[], float] = time.time,
        jitter: Callable[[], float] | None = None,
        managed: bool = False,
        tick: float = 1,
        fetch_timeout: float = 15,
    ):
        self.engine = engine
        self.collector = collector
        self.source_id = source_id
        self.ingestion = Ingestion(engine)
        self.clock = clock
        self.jitter = jitter or (lambda: random.uniform(0, 0.5))
        self._lock = asyncio.Lock()
        self.managed, self.tick, self.fetch_timeout = managed, tick, fetch_timeout

    def _snapshot(self) -> dict:
        with Session(self.engine) as session:
            source = session.get(Source, self.source_id)
            state = session.get(SourceState, self.source_id)
            if source is None or state is None:
                raise ValueError("Unknown source")
            probe = session.get(SourceProbe, self.source_id)
            website = session.get(Website, source.website_id)
            return {
                "enabled": source.enabled
                and website.enabled
                and (
                    not self.managed
                    or (
                        session.get(Administrator, 1) is not None
                        and session.get(WebsiteInstallation, website.id) is not None
                    )
                ),
                "website_id": source.website_id,
                "url": source.url,
                "next_attempt_at": max(
                    state.next_attempt_at,
                    probe_backoff(probe),
                    request_state(session, source.website_id, self.clock())[0],
                ),
                "interval_seconds": source.interval_seconds,
            }

    async def fetch_batch(self, adapter):
        try:
            async with asyncio.timeout(self.fetch_timeout):
                feed = await self.collector.fetch(adapter.rss_url)
        except TimeoutError:
            budget = self.collector.request_budget
            if budget is not None and adapter.website_id == "linuxdo":
                await database_call(budget.failed, SourceFailure("timeout"), budget.clock())
            raise SourceFailure("timeout") from None
        return await asyncio.to_thread(adapter.normalize, feed)

    async def run_once(self) -> PollOutcome:
        if self._lock.locked():
            return PollOutcome("overlap")
        # Paused/backoff wakes do not occupy the network operation lock. A
        # second snapshot under the lock validates a due poll against changes.
        snapshot = await database_call(self._snapshot)
        if not snapshot["enabled"]:
            return PollOutcome("paused")
        if self.clock() < snapshot["next_attempt_at"]:
            return PollOutcome("backoff")
        if self._lock.locked():
            return PollOutcome("overlap")
        async with self._lock:
            snapshot = await database_call(self._snapshot)
            if not snapshot["enabled"]:
                return PollOutcome("paused")
            if self.clock() < snapshot["next_attempt_at"]:
                return PollOutcome("backoff")
            try:
                adapter = BUILTIN_ADAPTERS.get(snapshot["website_id"])
                if adapter is None or snapshot["url"] != adapter.rss_url:
                    raise SourceFailure("unsupported_source")
                batch = await self.fetch_batch(adapter)
            except SourceDeferred as exc:
                return PollOutcome("backoff", exc.code)
            except SourceFailure as exc:
                await database_call(
                    self.ingestion.record_failure,
                    self.source_id,
                    exc.code,
                    at=self.clock(),
                    retry_after=exc.retry_after,
                    jitter=self.jitter(),
                )
                return PollOutcome("failure", exc.code)
            report = await database_call(
                self.ingestion.ingest, self.source_id, batch, at=self.clock()
            )
            return PollOutcome(report.status, report=report)

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.run_once()
            # Persisted next_attempt_at controls network frequency. Short wakes
            # observe configuration changes without replaying missed polls.
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.tick)
