import asyncio
import copy
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass

from sqlalchemy import Engine, and_, or_, select

from seekbell.db.models import (
    Administrator,
    DeliveredPost,
    DeliveryAttempt,
    NotificationTarget,
    Outbox,
    OutboxContribution,
    RuleHit,
    Task,
    TaskVersion,
)
from seekbell.db.transactions import database_call, write_session
from seekbell.domain.delivery import DeliveryPolicy, SendResult
from seekbell.notifiers.base import Notifier
from seekbell.services.configuration import identifier


@dataclass(frozen=True)
class Claim:
    event_id: str
    token: str
    sequence: int
    payload: dict
    target_snapshot: dict


class DeliveryWorker:
    def __init__(
        self,
        engine: Engine,
        notifiers: dict[str, Notifier],
        *,
        policy: DeliveryPolicy | None = None,
        clock: Callable[[], float] = time.time,
        managed: bool = False,
        tick: float = 1,
    ):
        self.engine = engine
        self.notifiers = notifiers
        self.policy = policy or DeliveryPolicy()
        self.clock = clock
        self.managed, self.tick = managed, tick

    @staticmethod
    def _active_tasks(session, event_id: str) -> list[dict]:
        rows = session.execute(
            select(RuleHit, TaskVersion)
            .join(OutboxContribution, OutboxContribution.hit_id == RuleHit.id)
            .join(Task, Task.id == RuleHit.task_id)
            .join(
                TaskVersion,
                (TaskVersion.task_id == RuleHit.task_id)
                & (TaskVersion.version == RuleHit.task_version),
            )
            .where(
                OutboxContribution.event_id == event_id,
                OutboxContribution.active.is_(True),
                Task.enabled.is_(True),
                Task.deleted_at.is_(None),
            )
            .order_by(RuleHit.task_id, RuleHit.task_version)
        ).all()
        return [
            {"id": hit.task_id, "version": hit.task_version, "name": version.name}
            for hit, version in rows
        ]

    @staticmethod
    def _release(event: Outbox) -> None:
        event.lease_token = None
        event.lease_until = None

    def claim(self, *, at: float) -> Claim | None:
        with write_session(self.engine) as session:
            if self.managed and session.get(Administrator, 1) is None:
                return None
            events = session.scalars(
                select(Outbox)
                .where(
                    or_(
                        and_(Outbox.status.in_(("pending", "retry")), Outbox.available_at <= at),
                        and_(Outbox.status == "leased", Outbox.lease_until <= at),
                    )
                )
                .order_by(Outbox.available_at, Outbox.created_at, Outbox.id)
            ).all()
            for event in events:
                if event.status == "leased":
                    previous = session.scalar(
                        select(DeliveryAttempt).where(
                            DeliveryAttempt.lease_token == event.lease_token
                        )
                    )
                    if previous is not None and previous.result == "in_progress":
                        previous.result = "unknown"
                        previous.error_code = "lease_expired"
                        previous.finished_at = at
                    event.uncertain = True
                    event.last_result = "unknown"
                    event.last_error_code = "lease_expired"

                receipt_key = (event.website_id, event.external_post_id, event.target_id)
                if session.get(DeliveredPost, receipt_key) is not None:
                    event.status = "sent"
                    event.last_result = "success"
                    event.last_error_code = None
                    self._release(event)
                    continue
                target = session.get(NotificationTarget, event.target_id)
                tasks = self._active_tasks(session, event.id)
                if event.cancel_requested or not target.enabled or not tasks:
                    event.status = "cancelled"
                    event.last_error_code = "delivery_cancelled"
                    self._release(event)
                    continue
                if event.attempt_count >= self.policy.max_attempts:
                    event.status = "failed"
                    event.last_error_code = "attempts_exhausted"
                    self._release(event)
                    continue

                token = identifier()
                event.payload = {**copy.deepcopy(event.payload), "matched_tasks": tasks}
                event.status = "leased"
                event.lease_token = token
                event.lease_until = at + self.policy.lease_seconds
                event.attempt_count += 1
                session.add(
                    DeliveryAttempt(
                        event_id=event.id,
                        sequence=event.attempt_count,
                        lease_token=token,
                        started_at=at,
                        result="in_progress",
                    )
                )
                return Claim(
                    event.id,
                    token,
                    event.attempt_count,
                    copy.deepcopy(event.payload),
                    copy.deepcopy(event.target_snapshot),
                )
        return None

    def finish(self, claim: Claim, result: SendResult, *, at: float) -> bool:
        with write_session(self.engine) as session:
            event = session.get(Outbox, claim.event_id)
            attempt = session.scalar(
                select(DeliveryAttempt).where(DeliveryAttempt.lease_token == claim.token)
            )
            if event is None or attempt is None:
                return False
            key = (event.website_id, event.external_post_id, event.target_id)
            if result.status == "success" and session.get(DeliveredPost, key) is None:
                session.add(
                    DeliveredPost(
                        website_id=event.website_id,
                        external_post_id=event.external_post_id,
                        target_id=event.target_id,
                        event_id=event.id,
                        delivered_at=at,
                    )
                )
            if event.status != "leased" or event.lease_token != claim.token:
                # An old worker cannot overwrite a newer lease. Preserve late evidence.
                attempt.late_result = result.status
                attempt.late_finished_at = at
                if result.status == "success" and event.status != "leased":
                    # No newer worker owns the event; reflect the proven late receipt.
                    event.status = "sent"
                    event.last_result = "success"
                    event.last_error_code = None
                return False

            attempt.result = result.status
            attempt.error_code = result.code
            attempt.finished_at = at
            event.last_result = result.status
            event.last_error_code = result.code
            if result.status == "unknown":
                event.uncertain = True
            target = session.get(NotificationTarget, event.target_id)
            known_success = (
                result.status == "success" or session.get(DeliveredPost, key) is not None
            )
            if known_success:
                event.status = "sent"
                event.last_result = "success"
                event.last_error_code = None
            elif (
                event.cancel_requested
                or not target.enabled
                or not self._active_tasks(session, event.id)
            ):
                event.status = "cancelled"
                event.last_error_code = result.code or "delivery_cancelled"
            elif (
                result.status == "permanent_error"
                or event.attempt_count >= self.policy.max_attempts
            ):
                event.status = "failed"
                event.last_error_code = result.code or "attempts_exhausted"
            else:
                event.status = "retry"
                event.available_at = at + self.policy.retry_delay(
                    event.attempt_count, result.retry_after
                )
            self._release(event)
            return True

    async def run_once(self) -> str | None:
        claim = await database_call(self.claim, at=self.clock())
        if claim is None:
            return None
        notifier = self.notifiers.get(claim.target_snapshot["kind"])
        if notifier is None:
            result = SendResult(status="permanent_error", code="unsupported_notifier")
        else:
            try:
                result = await asyncio.wait_for(
                    notifier.send(claim.target_snapshot, claim.payload),
                    timeout=self.policy.send_timeout_seconds,
                )
                if not isinstance(result, SendResult):
                    result = SendResult(status="unknown", code="invalid_notifier_result")
            except TimeoutError:
                result = SendResult(status="unknown", code="send_timeout")
            except Exception:
                result = SendResult(status="unknown", code="send_exception")
        await database_call(self.finish, claim, result, at=self.clock())
        return claim.event_id

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            event_id = await self.run_once()
            if event_id is None:
                with suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=self.tick)
