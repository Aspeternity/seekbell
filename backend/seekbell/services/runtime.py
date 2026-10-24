"""Own the single-process background actors and stop them before closing resources."""

import asyncio
import logging

import httpx

from seekbell.collectors.http import public_client
from seekbell.collectors.rss import RssCollector
from seekbell.db.models import Administrator
from seekbell.db.transactions import database_call, write_session
from seekbell.services.alerts import AlertWorker, observe
from seekbell.services.collection import SourceRunner
from seekbell.services.delivery import DeliveryWorker
from seekbell.services.request_budget import WebsiteRequestBudget
from seekbell.services.retention import HistoryRetention
from seekbell.services.source_probe import ProbeConflict, check
from seekbell.sites.registry import BUILTIN_ADAPTERS

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
        request_budget=None,
    ):
        self.client = public_client(
            transport=http_transport,
            limits=httpx.Limits(
                max_connections=len(BUILTIN_ADAPTERS),
                max_keepalive_connections=len(BUILTIN_ADAPTERS),
            ),
        )
        self.request_budget = request_budget or WebsiteRequestBudget(engine)
        self.sources = {
            website_id: SourceRunner(
                engine,
                RssCollector(
                    self.client, request_budget=self.request_budget, website_id=website_id
                ),
                source_id=adapter.source_id,
                managed=True,
                tick=tick,
                fetch_timeout=collector_timeout,
            )
            for website_id, adapter in BUILTIN_ADAPTERS.items()
        }
        self.source = self.sources["nodeseek"]
        self.worker = DeliveryWorker(engine, notifiers, managed=True, tick=tick)
        self.retention = HistoryRetention(engine, tick=tick)
        self.alerts = AlertWorker(engine, notifiers, tick=tick)
        self.engine = engine
        self.alert_stop = asyncio.Event()
        self.reports = set()
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
        if self.status in ("stopping", "stopped"):
            return
        if self.status != "failed":
            self.status, self.code = "failed", name + "_stopped"
            self.stop.set()
        if name == "alerts":
            self.alert_stop.set()
        task = asyncio.create_task(self._report_failure(name))
        self.reports.add(task)
        task.add_done_callback(self.reports.discard)
        # Only fixed actor names, never exception text or configuration.
        logger.error("SeekBell background actor stopped: %s", name)

    async def _report_failure(self, name):
        try:
            await database_call(self._runtime_transition, name, True)
        except Exception:
            logger.error("SeekBell runtime incident could not be persisted")

    def _runtime_transition(self, name, fault):
        import time

        with write_session(self.engine) as session:
            if session.get(Administrator, 1) is not None:
                observe(
                    session,
                    "runtime:" + name,
                    fault,
                    label={
                        "collection": "采集服务",
                        "delivery": "自动投递服务",
                        "retention": "历史清理服务",
                        "alerts": "系统告警服务",
                    }[name],
                    code=name + "_stopped" if fault else None,
                    at=time.time(),
                )

    async def _actor(self, name, run):
        stop = self.alert_stop if name == "alerts" else self.stop
        try:
            await run(stop)
        except asyncio.CancelledError:
            if self.status != "stopping":
                self._failed(name)
        except Exception:
            self._failed(name)
        finally:
            if not stop.is_set():
                self._failed(name)

    async def collect(self, stop):
        # TaskGroup joins/cancels every source when the actor exits or fails.
        # Expected HTTP/parser failures are handled inside each SourceRunner.
        async with asyncio.TaskGroup() as group:
            for website_id, source in self.sources.items():
                group.create_task(source.run(stop), name="seekbell-source-" + website_id)

    async def start(self):
        if self.tasks:
            raise RuntimeError("Runtime already started")
        self.tasks = {
            name: asyncio.create_task(
                self._actor(name, self.collect if name == "collection" else actor.run),
                name="seekbell-" + name,
            )
            for name, actor in (
                ("collection", self),
                ("delivery", self.worker),
                ("retention", self.retention),
                ("alerts", self.alerts),
            )
        }
        self.status = "running"
        await asyncio.sleep(0)
        if self.active:
            for name in self.tasks:
                if self.active:
                    await database_call(self._runtime_transition, name, False)

    async def check_source(self, website_id="nodeseek"):
        if not self.active:
            raise ProbeConflict("后台未运行，请先检查概览。")
        source = self.sources.get(website_id)
        if source is None:
            raise ProbeConflict("该网站尚未支持。")
        task = asyncio.current_task()
        self.probes.add(task)
        try:
            return await check(source)
        finally:
            self.probes.discard(task)

    async def aclose(self):
        self.status = "stopping"
        self.stop.set()
        self.alert_stop.set()
        try:
            tasks = {*self.tasks.values(), *self.probes, *self.reports}
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
