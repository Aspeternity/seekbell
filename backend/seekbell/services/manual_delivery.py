"""One explicit resend attempt; automatic state and receipt tombstones remain untouched."""

import copy
import time

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from seekbell.db.models import ManualDeliveryAttempt, NotificationTarget, Outbox, TargetTestAttempt
from seekbell.db.transactions import write_session
from seekbell.services.async_tools import storage_call
from seekbell.services.configuration import target_snapshot
from seekbell.services.explicit_sending import SendConflict, SendNotFound, send_once


class ManualDelivery:
    def __init__(self, engine: Engine, notifiers: dict, *, clock=time.time):
        self.engine, self.notifiers, self.clock = engine, notifiers, clock

    def _start(self, event_id: str, key: str, expected_revision: int):
        with write_session(self.engine) as session:
            existing = session.get(ManualDeliveryAttempt, key)
            if existing is not None:
                if (
                    existing.original_event_id != event_id
                    or existing.target_snapshot["revision"] != expected_revision
                ):
                    raise SendConflict
                return None, None
            if session.get(TargetTestAttempt, key) or session.get(Outbox, key):
                raise SendConflict
            event = session.get(Outbox, event_id)
            if event is None:
                raise SendNotFound
            target = session.get(NotificationTarget, event.target_id)
            if (
                event.status not in ("sent", "failed", "cancelled")
                or not target.enabled
                or target.revision != expected_revision
            ):
                raise SendConflict
            payload = copy.deepcopy(event.payload)
            payload["event_id"] = key
            payload["post"]["title"] = "【手动重发】" + payload["post"]["title"]
            snapshot = target_snapshot(target)
            session.add(
                ManualDeliveryAttempt(
                    id=key,
                    original_event_id=event.id,
                    target_id=target.id,
                    target_snapshot=snapshot,
                    payload=payload,
                    started_at=self.clock(),
                    result="unknown",
                    error_code="manual_not_completed",
                )
            )
        return snapshot, payload

    def _finish(self, key, result):
        with write_session(self.engine) as session:
            attempt = session.get(ManualDeliveryAttempt, key)
            attempt.result, attempt.error_code = result.status, result.code
            attempt.finished_at = self.clock()

    async def run(self, event_id: str, *, key: str, expected_revision: int) -> str:
        snapshot, payload = await storage_call(self._start, event_id, key, expected_revision)
        if payload is not None:
            result = await send_once(self.notifiers, snapshot, payload, timeout=10)
            await storage_call(self._finish, key, result)
        return key

    def get_result(self, key: str) -> dict:
        with Session(self.engine) as session:
            attempt = session.get(ManualDeliveryAttempt, key)
            if attempt is None:
                raise SendNotFound
            return {
                "id": key,
                "original_event_id": attempt.original_event_id,
                "target_id": attempt.target_id,
                "result": attempt.result,
                "code": attempt.error_code,
                "started_at": attempt.started_at,
                "finished_at": attempt.finished_at,
            }
