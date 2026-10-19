"""Explicit target tests have separate history and never change automatic deduplication."""

import time
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from seekbell.db.models import ManualDeliveryAttempt, NotificationTarget, Outbox, TargetTestAttempt
from seekbell.db.transactions import write_session
from seekbell.domain.delivery import SendResult
from seekbell.notifiers.base import Notifier
from seekbell.services.async_tools import storage_call
from seekbell.services.configuration import identifier, target_snapshot
from seekbell.services.explicit_sending import SendConflict, SendNotFound, send_once


class TargetTesting:
    def __init__(
        self,
        engine: Engine,
        notifiers: dict[str, Notifier],
        *,
        timeout: float = 10,
        clock: Callable[[], float] = time.time,
    ):
        self.engine, self.notifiers, self.clock = engine, notifiers, clock
        if not 0 < timeout <= 10:
            raise ValueError("Target test timeout must be between 0 and 10 seconds")
        self.timeout = timeout

    def _start(self, target_id: str, key: str | None = None, expected_revision: int | None = None):
        key, at = key or identifier(), self.clock()
        with write_session(self.engine) as session:
            existing = session.get(TargetTestAttempt, key)
            if existing is not None:
                if existing.target_id != target_id or (
                    expected_revision is not None
                    and existing.target_snapshot["revision"] != expected_revision
                ):
                    raise SendConflict
                return key, None, None
            if session.get(ManualDeliveryAttempt, key) or session.get(Outbox, key):
                raise SendConflict
            target = session.get(NotificationTarget, target_id)
            if target is None:
                raise SendNotFound
            if expected_revision is not None and target.revision != expected_revision:
                raise SendConflict
            snapshot = target_snapshot(target)
            session.add(
                TargetTestAttempt(
                    id=key,
                    target_id=target_id,
                    target_snapshot=snapshot,
                    started_at=at,
                    result="unknown",
                    error_code="test_not_completed",
                )
            )
        payload = {
            "schema_version": 1,
            "event_id": key,
            "post": {
                "website_id": "nodeseek",
                "external_post_id": "test",
                "title": "SeekBell 通知测试",
                "summary": "这是手动目标测试。",
                "url": "https://www.nodeseek.com/",
                "author": "SeekBell",
                "category": "通知测试",
                "published_at": None,
                "first_seen_at": datetime.fromtimestamp(at, UTC).isoformat(),
            },
            "matched_tasks": [{"id": "test", "version": 1, "name": "手动通知测试"}],
        }
        return key, snapshot, payload

    def _finish(self, key: str, result: SendResult):
        with write_session(self.engine) as session:
            attempt = session.get(TargetTestAttempt, key)
            attempt.result, attempt.error_code = result.status, result.code
            attempt.finished_at = self.clock()

    async def run(
        self, target_id: str, *, key: str | None = None, expected_revision: int | None = None
    ) -> str:
        key, snapshot, payload = await storage_call(self._start, target_id, key, expected_revision)
        if payload is not None:
            result = await send_once(self.notifiers, snapshot, payload, timeout=self.timeout)
            await storage_call(self._finish, key, result)
        return key

    def get_result(self, key: str) -> dict:
        with Session(self.engine) as session:
            attempt = session.get(TargetTestAttempt, key)
            if attempt is None:
                raise ValueError("Unknown target test")
            return {
                "id": key,
                "target_id": attempt.target_id,
                "result": attempt.result,
                "code": attempt.error_code,
                "started_at": attempt.started_at,
                "finished_at": attempt.finished_at,
            }
