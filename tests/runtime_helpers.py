"""Runtime test adapters: no product switches and no external connections."""

import copy

import httpx
from seekbell.domain.delivery import SendResult
from seekbell.services.runtime import Runtime

from tests.rss_samples import Chunks, rss


class PassiveRuntime:
    """Isolate old CRUD/history checks from actors; never used by normal startup."""

    active = False
    healthy = True

    def __init__(self, engine, notifiers):
        self.status = "idle"

    def snapshot(self):
        return {"active": False, "status": self.status, "code": None}

    async def start(self):
        pass

    async def aclose(self):
        self.status = "stopped"


class SyntheticScenario:
    def __init__(self):
        self.fetches, self.sends = [], []
        self.items = [9001]
        self.failure = None
        self.block = None
        self.send_block = None

    async def feed(self, request):
        self.fetches.append(str(request.url))
        if self.block is not None:
            await self.block.wait()
        if self.failure:
            return httpx.Response(self.failure, headers={"Retry-After": "60"})
        return httpx.Response(
            200,
            headers={"content-type": "application/rss+xml"},
            stream=Chunks(
                rss([{"id": key, "title": "Synthetic VPS signal"} for key in self.items])
            ),
        )

    async def send(self, target, payload):
        self.sends.append(copy.deepcopy(payload))
        if self.send_block is not None:
            await self.send_block.wait()
        return SendResult(status="success")

    def factory(self, engine, notifiers):
        return Runtime(
            engine,
            {kind: self for kind in ("telegram", "bark", "smtp", "webhook")},
            http_transport=httpx.MockTransport(self.feed),
            tick=0.03,
            shutdown_grace=0.2,
        )


def synthetic_runtime_factory(engine, notifiers):
    scenario = SyntheticScenario()
    original = scenario.feed

    async def growing(request):
        scenario.items = list(range(9001, 9002 + len(scenario.fetches)))
        return await original(request)

    scenario.feed = growing
    return scenario.factory(engine, notifiers)


def operations_runtime_factory(engine, notifiers):
    # Seeded history stays immutable; explicit probes use the real lock/collector.
    scenario = SyntheticScenario()
    runtime = scenario.factory(engine, notifiers)

    async def idle(stop):
        await stop.wait()

    runtime.worker.run = idle
    return runtime
