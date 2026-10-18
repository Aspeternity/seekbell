"""Explicit target tests have separate history and never change automatic deduplication."""

import asyncio
import time
from collections.abc import Callable

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from seekbell.db.models import NotificationTarget, TargetTestAttempt
from seekbell.db.transactions import write_session
from seekbell.domain.delivery import SendResult
from seekbell.notifiers.base import Notifier
from seekbell.services.configuration import identifier, target_snapshot


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

    def _start(self, target_id: str):
        key, at = identifier(), self.clock()
        with write_session(self.engine) as session:
            target = session.get(NotificationTarget, target_id)
            if target is None:
                raise ValueError("Unknown target")
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
                "first_seen_at": at,
            },
            "matched_tasks": [{"id": "test", "version": 1, "name": "手动通知测试"}],
        }
        return key, snapshot, payload

    def _finish(self, key: str, result: SendResult):
        with write_session(self.engine) as session:
            attempt = session.get(TargetTestAttempt, key)
            attempt.result, attempt.error_code = result.status, result.code
            attempt.finished_at = self.clock()

    async def run(self, target_id: str) -> str:
        key, snapshot, payload = await asyncio.to_thread(self._start, target_id)
        notifier = self.notifiers.get(snapshot["kind"])
        result = SendResult(status="permanent_error", code="unsupported_notifier")
        if notifier:
            try:
                result = await asyncio.wait_for(
                    notifier.send(snapshot, payload), timeout=self.timeout
                )
                if not isinstance(result, SendResult):
                    result = SendResult(status="unknown", code="invalid_notifier_result")
            except TimeoutError:
                result = SendResult(status="unknown", code="send_timeout")
            except Exception:
                result = SendResult(status="unknown", code="send_exception")
        await asyncio.to_thread(self._finish, key, result)
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
