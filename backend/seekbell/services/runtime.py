"""One process owns one source loop and one delivery loop."""

import asyncio
import logging
from collections.abc import Awaitable

import httpx
from sqlalchemy import Engine

from seekbell.collectors.rss import RssCollector
from seekbell.notifiers.credentials import CredentialVault
from seekbell.notifiers.registry import NotifierRegistry
from seekbell.services.async_tools import storage_call
from seekbell.services.collection import SourceRunner
from seekbell.services.delivery import DeliveryWorker
from seekbell.services.explicit_sending import SendConflict
from seekbell.services.manual_delivery import ManualDelivery
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
    ):
        self.engine, self.enabled = engine, enabled
        self.shutdown_grace = shutdown_grace
        self.stop = asyncio.Event()
        self.wake = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._explicit_tasks: set[asyncio.Task] = set()
        self._explicit_lock = asyncio.Lock()
        self._components = {"collector": "disabled", "delivery": "disabled"}
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
        self.target_testing = TargetTesting(engine, self.registry.notifiers)
        self.manual_delivery = ManualDelivery(engine, self.registry.notifiers)

    async def _guard(self, component: str, run: Awaitable[None]) -> None:
        self._components[component] = "running"
        try:
            await run
        except asyncio.CancelledError:
            if not self.stop.is_set():
                self._components[component] = "failed"
                logger.error("background_%s_cancelled", component)
            raise
        except Exception:
            self._components[component] = "failed"
            # Exception strings/tracebacks may contain credentials or SQL parameters.
            logger.error("background_%s_failed", component)
        else:
            self._components[component] = "stopped" if self.stop.is_set() else "failed"

    async def start(self) -> None:
        if self._started or self._closed:
            raise RuntimeError("Runtime cannot be started twice")
        self._started = True
        if self.enabled:
            self._tasks = [
                asyncio.create_task(
                    self._guard("collector", self.source.run(self.stop, wake=self.wake)),
                    name="seekbell-collector",
                ),
                asyncio.create_task(
                    self._guard("delivery", self.worker.run(self.stop)),
                    name="seekbell-delivery",
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
