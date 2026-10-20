"""Own the single-process background actors and stop them before closing resources."""

import asyncio
import logging

import httpx

from seekbell.collectors.rss import RssCollector
from seekbell.services.collection import SourceRunner
from seekbell.services.delivery import DeliveryWorker
from seekbell.services.retention import HistoryRetention
from seekbell.services.source_probe import ProbeConflict, check

logger = logging.getLogger(__name__)


class Runtime:
    def __init__(
        self,
        engine,
        notifiers,
        *,
        http_transport=None,
        tick=1,
        shutdown_grace=16,
        collector_timeout=15,
    ):
        self.client = httpx.AsyncClient(
            transport=http_transport,
            trust_env=False,
            follow_redirects=False,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
        )
        self.source = SourceRunner(
            engine,
            RssCollector(self.client),
            managed=True,
            tick=tick,
            fetch_timeout=collector_timeout,
        )
        self.worker = DeliveryWorker(engine, notifiers, managed=True, tick=tick)
        self.retention = HistoryRetention(engine, tick=tick)
        self.stop = asyncio.Event()
        self.tasks = {}
        self.probes = set()
        self.status = "starting"
        self.code = None
        self.shutdown_grace = shutdown_grace

    @property
    def active(self):
        return (
            self.status == "running"
            and bool(self.tasks)
            and all(not task.done() for task in self.tasks.values())
        )

    @property
    def healthy(self):
        return self.active

    def snapshot(self):
        return {"active": self.active, "status": self.status, "code": self.code}

    def _failed(self, name):
        if self.status not in ("stopping", "stopped", "failed"):
            self.status, self.code = "failed", name + "_stopped"
            self.stop.set()
            # No exception text, request URLs, configuration or SQL parameters.
            logger.error("SeekBell background actor stopped: %s", name)

    async def _actor(self, name, run):
        try:
            await run(self.stop)
        except asyncio.CancelledError:
            if self.status != "stopping":
                self._failed(name)
        except Exception:
            self._failed(name)
        finally:
            if not self.stop.is_set():
                self._failed(name)

    async def start(self):
        if self.tasks:
            raise RuntimeError("Runtime already started")
        self.tasks = {
            name: asyncio.create_task(self._actor(name, actor.run), name="seekbell-" + name)
            for name, actor in (
                ("collection", self.source),
                ("delivery", self.worker),
                ("retention", self.retention),
            )
        }
        self.status = "running"
        await asyncio.sleep(0)

    async def check_source(self):
        if not self.active:
            raise ProbeConflict("后台未运行，请先检查概览。")
        task = asyncio.current_task()
        self.probes.add(task)
        try:
            return await check(self.source)
        finally:
            self.probes.discard(task)

    async def aclose(self):
        self.status = "stopping"
        self.stop.set()
        try:
            tasks = {*self.tasks.values(), *self.probes}
            if tasks:
                _, pending = await asyncio.wait(
                    tasks,
                    timeout=self.shutdown_grace,
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            # Actors have joined, including any shielded database work.
            await self.client.aclose()
            self.status = "stopped"


def status(request):
    return request.app.state.runtime.snapshot()
