"""Turn a background loop that stops completing into a recorded, alerted fault."""

import asyncio
import logging
import time
from contextlib import suppress

from seekbell.db.models import Administrator
from seekbell.db.transactions import database_call, write_session
from seekbell.services.alerts import observe

logger = logging.getLogger(__name__)

LOOP_STALL_SECONDS = 120
CODE = "loop_stalled"
# Kept apart from `runtime:<name>`, which a crash raises and only a restart clears.
PREFIX = "runtime:stall_"
LABELS = {
    "collection": "采集服务",
    "delivery": "投递服务",
    "retention": "历史清理服务",
    "alerts": "系统告警服务",
}


def stalled(actor, started_at, at):
    last = actor["last_loop_at"] or started_at
    return actor["alive"] and last is not None and at - last > LOOP_STALL_SECONDS


class StallWatch:
    """Reads the runtime's in-memory loop times; writes only when a verdict changes."""

    def __init__(self, engine, observation, *, interval=15, clock=time.time):
        self.engine, self.observation = engine, observation
        self.interval, self.clock = interval, clock
        # Unknown until the first check, which also clears stalls left by a previous process.
        self.known = {}

    def _record(self, changes, at):
        with write_session(self.engine) as session:
            if session.get(Administrator, 1) is None:
                return False
            for name, fault in changes.items():
                observe(
                    session,
                    PREFIX + name,
                    fault,
                    label=LABELS.get(name, name),
                    code=CODE if fault else None,
                    at=at,
                )
            return True

    async def check(self):
        at = self.clock()
        observed = self.observation()
        verdicts = {
            name: stalled(actor, observed["started_at"], at)
            for name, actor in observed["actors"].items()
        }
        changes = {name: fault for name, fault in verdicts.items() if self.known.get(name) != fault}
        if changes and await database_call(self._record, changes, at):
            self.known.update(changes)

    async def run(self, stop: asyncio.Event):
        while not stop.is_set():
            try:
                await self.check()
            except Exception:
                logger.error("SeekBell stall check could not be recorded")
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), self.interval)
