"""One process owns one source loop and one delivery loop."""

import asyncio
import inspect
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import httpx
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from seekbell.collectors.rss import RssCollector
from seekbell.db.models import ApplicationSettings, NotificationTarget, SourceState
from seekbell.notifiers.credentials import CredentialVault
from seekbell.notifiers.registry import NotifierRegistry
from seekbell.services.async_tools import storage_call, wait_for_signal
from seekbell.services.collection import PollOutcome, SourceRunner
from seekbell.services.configuration import identifier, target_snapshot
from seekbell.services.delivery import DeliveryWorker
from seekbell.services.explicit_sending import SendConflict, send_once
from seekbell.services.manual_delivery import ManualDelivery
from seekbell.services.settings import SystemSettings
from seekbell.services.target_testing import TargetTesting

logger = logging.getLogger(__name__)


class ApplicationRuntime:
    def __init__(
        self,
        engine: Engine,
        vault: CredentialVault,
        *,
        enabled: bool = True,
        rss_transport: httpx.AsyncBaseTransport | None = None,
        notification_transport: httpx.AsyncBaseTransport | None = None,
        shutdown_grace: float = 15,
        recovery_backoff: float = 5,
    ):
        self.engine, self.enabled = engine, enabled
        self.shutdown_grace = shutdown_grace
        self.recovery_backoff = recovery_backoff
        self.stop = asyncio.Event()
        self.wake = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._explicit_tasks: set[asyncio.Task] = set()
        self._explicit_lock = asyncio.Lock()
        self._components = {
            "collector": "disabled",
            "delivery": "disabled",
            "maintenance": "disabled",
        }
        self._restarts = {"collector": 0, "delivery": 0, "maintenance": 0}
        self._source_alerted = False
        self._closed = False
        self._started = False
        self.rss_client = httpx.AsyncClient(
            trust_env=False,
            follow_redirects=False,
            transport=rss_transport,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
        )
        self.registry = NotifierRegistry(vault, http_transport=notification_transport)
        self.collector = RssCollector(self.rss_client)
        self.source = SourceRunner(engine, self.collector)
        self.worker = DeliveryWorker(engine, self.registry.notifiers)
        self.settings = SystemSettings(engine)
        self.target_testing = TargetTesting(engine, self.registry.notifiers)
        self.manual_delivery = ManualDelivery(engine, self.registry.notifiers)

    def _alert_target_snapshot(self) -> dict | None:
        with Session(self.engine) as session:
            settings = session.get(ApplicationSettings, 1)
            if settings is None or not settings.alert_target_id:
                return None
            target = session.get(NotificationTarget, settings.alert_target_id)
            if target is None or not target.enabled:
                return None
            return target_snapshot(target)

    async def _send_system_alert(self, title: str, summary: str, category: str) -> None:
        try:
            snapshot = await storage_call(self._alert_target_snapshot)
            if snapshot is None:
                return
            now = time.time()
            payload = {
                "schema_version": 1,
                "event_id": identifier(),
                "post": {
                    "website_id": "nodeseek",
                    "external_post_id": "system-alert",
                    "title": title,
                    "summary": summary,
                    "url": "https://www.nodeseek.com/",
                    "author": "SeekBell",
                    "category": category,
                    "published_at": None,
                    "first_seen_at": datetime.fromtimestamp(now, UTC).isoformat(),
                },
                "matched_tasks": [{"id": "system-alert", "version": 1, "name": category}],
            }
            await send_once(self.registry.notifiers, snapshot, payload, timeout=10)
        except Exception:
            logger.error("system_alert_send_failed")

    def _source_failure_state(self) -> tuple[int, str | None]:
        with Session(self.engine) as session:
            state = session.get(SourceState, self.source.source_id)
            return (state.failures, state.last_error_code) if state is not None else (0, None)

    async def _on_collector_cycle(self, outcome: PollOutcome) -> None:
        self._components["collector"] = "running"
        if outcome.status == "failure":
            failures, code = await storage_call(self._source_failure_state)
            if failures >= 5 and not self._source_alerted:
                self._source_alerted = True
                await self._send_system_alert(
                    "【系统告警】RSS 采集连续失败",
                    f"NodeSeek RSS 连续失败 {failures} 次（错误码：{code or 'unknown'}）。",
                    "系统故障告警",
                )
        elif outcome.status == "success":
            if self._source_alerted:
                self._source_alerted = False
                await self._send_system_alert(
                    "【系统恢复】RSS 采集已恢复",
                    "NodeSeek RSS 采集已恢复正常。",
                    "系统恢复通知",
                )
            if outcome.report and outcome.report.possible_gap:
                await self._send_system_alert(
                    "【系统提示】检测到可能的 RSS 窗口缺口",
                    "前后两次采集窗口无交集，停机或退避期间可能有帖子移出 RSS 窗口。",
                    "系统告警",
                )

    async def _guard(self, component: str, runner: Callable[[], Awaitable[None]]) -> None:
        self._components[component] = "running"
        consecutive_failures = 0
        while not self.stop.is_set():
            try:
                await runner()
            except asyncio.CancelledError:
                if not self.stop.is_set():
                    self._components[component] = "failed"
                    logger.error("background_%s_cancelled", component)
                raise
            except Exception:
                consecutive_failures += 1
                self._restarts[component] += 1
                self._components[component] = "failed"
                # Exception strings/tracebacks may contain credentials or SQL parameters.
                logger.error("background_%s_failed", component)
                if consecutive_failures == 1:
                    await self._send_system_alert(
                        f"【系统告警】后台组件 {component} 异常",
                        f"后台组件 {component} 发生异常，正在自动退避恢复。",
                        "系统故障告警",
                    )
                delay = min(300.0, self.recovery_backoff * (2 ** (consecutive_failures - 1)))
                await wait_for_signal(self.stop, None, delay)
            else:
                if self.stop.is_set():
                    self._components[component] = "stopped"
                    return
                consecutive_failures += 1
                self._restarts[component] += 1
                self._components[component] = "failed"
                logger.error("background_%s_stopped_unexpectedly", component)
                delay = min(300.0, self.recovery_backoff * (2 ** (consecutive_failures - 1)))
                await wait_for_signal(self.stop, None, delay)

    async def _run_collector(self) -> None:
        signature = inspect.signature(self.source.run)
        if "on_cycle" in signature.parameters:
            await self.source.run(
                self.stop,
                wake=self.wake,
                on_cycle=lambda outcome: asyncio.create_task(self._on_collector_cycle(outcome)),
            )
        else:
            await self.source.run(self.stop, wake=self.wake)

    async def _run_delivery(self) -> None:
        signature = inspect.signature(self.worker.run)
        if "on_cycle" in signature.parameters:
            await self.worker.run(
                self.stop,
                on_cycle=lambda: self._components.__setitem__("delivery", "running"),
            )
        else:
            await self.worker.run(self.stop)

    async def start(self) -> None:
        if self._started or self._closed:
            raise RuntimeError("Runtime cannot be started twice")
        self._started = True
        if self.enabled:
            self._tasks = [
                asyncio.create_task(
                    self._guard("collector", self._run_collector),
                    name="seekbell-collector",
                ),
                asyncio.create_task(
                    self._guard("delivery", self._run_delivery),
                    name="seekbell-delivery",
                ),
                asyncio.create_task(
                    self._guard("maintenance", self._maintenance), name="seekbell-maintenance"
                ),
            ]
            await asyncio.sleep(0)

    def notify_configuration(self) -> None:
        self.wake.set()

    def snapshot(self) -> dict:
        return {
            "enabled": self.enabled,
            "healthy": "failed" not in self._components.values(),
            "stopping": self.stop.is_set(),
            "components": dict(self._components),
            "restarts": dict(self._restarts),
        }

    async def aclose(self) -> None:
        if self._closed:
            return
        self.stop.set()
        self.wake.set()
        try:
            tasks = [*self._tasks, *self._explicit_tasks]
            if tasks:
                _, pending = await asyncio.wait(tasks, timeout=self.shutdown_grace)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            try:
                await self.registry.aclose()
            finally:
                await self.rss_client.aclose()
                self._closed = True

    async def check_source(self) -> dict:
        return await self.source.check_connection()

    async def send_explicit(
        self, kind: str, resource_id: str, *, key: str, expected_revision: int
    ) -> dict:
        if self.stop.is_set() or self._closed or self._explicit_lock.locked():
            raise SendConflict
        async with self._explicit_lock:
            service = self.target_testing if kind == "test" else self.manual_delivery

            async def operation():
                result_key = await service.run(
                    resource_id, key=key, expected_revision=expected_revision
                )
                return await storage_call(service.get_result, result_key)

            running = asyncio.create_task(operation())
            self._explicit_tasks.add(running)
            try:
                return await running
            finally:
                self._explicit_tasks.discard(running)

    async def _maintenance(self):
        while not self.stop.is_set():
            await storage_call(self.settings.cleanup, at=time.time())
            self._components["maintenance"] = "running"
            await wait_for_signal(self.stop, None, 60)
