"""Durable fault/recovery transitions and one-shot, independent alert deliveries."""

import asyncio
import re
import time
from contextlib import suppress

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from seekbell.db.models import (
    Administrator,
    AlertDelivery,
    AlertSettings,
    NotificationTarget,
    Source,
    SystemEvent,
    SystemState,
    Website,
    WebsiteInstallation,
)
from seekbell.db.transactions import database_call, write_session
from seekbell.domain.delivery import SendResult
from seekbell.services.configuration import identifier, target_snapshot
from seekbell.services.display import notification_context
from seekbell.services.fault_guide import delivery_guide, guide_for
from seekbell.services.history import read_session

# A fault is announced once it has lasted this long: whole minutes, at most a day.
MAX_DELAY_SECONDS = 86400
# Repeat an unresolved fault to those who were told about it: never, every 6 h or every day.
REMINDERS = (0, 21600, 86400)
REMIND_CHECK_SECONDS = 60
RECOVERED_EARLY = "recovered_within_delay"
# Events that tell a target a fault exists; a recovery goes to whoever heard one of them.
ANNOUNCING = ("fault", "reminder")


class AlertConflict(ValueError):
    pass


def observe(session, component, fault, *, label, code=None, at):
    """Called inside the domain writer's transaction, never performs network IO."""
    state = session.get(SystemState, component)
    code = code if isinstance(code, str) and re.fullmatch(r"[a-z0-9_]{1,80}", code) else None
    if state is None:
        if not fault:
            return None
        state = SystemState(
            component=component, fault=False, generation=0, label=label[:200], updated_at=at
        )
        session.add(state)
    if state.fault == fault:
        if fault:
            state.code, state.label = code, label[:200]
        return None
    state.fault, state.updated_at, state.label = fault, at, label[:200]
    state.code = code if fault else None
    if fault:
        state.generation += 1
    session.flush()
    event = SystemEvent(
        id=identifier(),
        component=component,
        generation=state.generation,
        phase="fault" if fault else "recovery",
        label=label[:200],
        code=code,
        at=at,
    )
    session.add(event)
    session.flush()
    settings = session.get(AlertSettings, 1)
    if fault:
        recipients = set(settings.target_ids)
    else:
        _withdraw_brief_fault(session, state, settings, at)
        # Never a recovery for a fault the target did not hear about (alerts were off then,
        # the target was paused or added later, or the fault cleared inside the delay).
        recipients = _announced(session, component, state.generation)
    if settings.enabled:
        _queue(session, settings, event, recipients, at)
    return event.id


def _queue(session, settings, event, recipients, at):
    for key in settings.target_ids:
        if key not in recipients:
            continue
        target = session.get(NotificationTarget, key)
        if target is None:
            continue
        ready = target.deleted_at is None and target.enabled and target.config_ciphertext
        session.add(
            AlertDelivery(
                id=identifier(),
                event_id=event.id,
                target_id=target.id,
                target_snapshot=target_snapshot(target),
                result="pending" if ready else "cancelled",
                error_code=None if ready else "target_unavailable",
                finished_at=None if ready else at,
            )
        )


def _announced(session, component, generation):
    return set(
        session.scalars(
            select(AlertDelivery.target_id)
            .join(SystemEvent)
            .where(
                SystemEvent.component == component,
                SystemEvent.generation == generation,
                SystemEvent.phase.in_(ANNOUNCING),
                AlertDelivery.result != "cancelled",
            )
        )
    )


def object_active(session, kind, key):
    """Whether the faulty object is still in use; a paused source or target cannot recover."""
    if kind == "source":
        source = session.get(Source, key)
        if source is None:
            return False
        website = session.get(Website, source.website_id)
        return bool(
            source.enabled and website.enabled and session.get(WebsiteInstallation, website.id)
        )
    if kind == "delivery":
        target = session.get(NotificationTarget, key)
        return bool(target and target.deleted_at is None and target.enabled)
    return True


def queue_reminders(session, at):
    """Add a reminder for each fault unresolved for a whole reminder interval since last told."""
    settings = session.get(AlertSettings, 1)
    if not settings.enabled or not settings.remind_seconds:
        return 0
    created = 0
    for state in session.scalars(select(SystemState).where(SystemState.fault.is_(True))).all():
        kind, _, key = state.component.partition(":")
        if not object_active(session, kind, key):
            continue
        told = (
            SystemEvent.component == state.component,
            SystemEvent.generation == state.generation,
            SystemEvent.phase.in_(ANNOUNCING),
        )
        last = session.scalar(select(func.max(SystemEvent.at)).where(*told))
        if last is None or at - last < settings.remind_seconds:
            continue
        recipients = _announced(session, state.component, state.generation)
        if not recipients:
            continue
        event = SystemEvent(
            id=identifier(),
            component=state.component,
            generation=state.generation,
            phase="reminder",
            label=state.label,
            code=state.code,
            at=at,
        )
        session.add(event)
        session.flush()
        _queue(session, settings, event, recipients, at)
        created += 1
    return created


def _withdraw_brief_fault(session, state, settings, at):
    """A fault that clears inside the delay was never announced, so its recovery is not either."""
    if not settings.delay_seconds:
        return
    fault = session.scalar(
        select(SystemEvent).where(
            SystemEvent.component == state.component,
            SystemEvent.generation == state.generation,
            SystemEvent.phase == "fault",
        )
    )
    if fault is None or at - fault.at >= settings.delay_seconds:
        return
    for delivery in session.scalars(
        select(AlertDelivery).where(
            AlertDelivery.event_id == fault.id, AlertDelivery.result == "pending"
        )
    ):
        delivery.result, delivery.error_code = "cancelled", RECOVERED_EARLY
        delivery.finished_at = at
    session.flush()


def settings_view(settings):
    return {
        "enabled": settings.enabled,
        "target_ids": settings.target_ids,
        "delay_seconds": settings.delay_seconds,
        "remind_seconds": settings.remind_seconds,
        "revision": settings.revision,
    }


def get_settings(engine):
    with Session(engine) as session:
        return settings_view(session.get(AlertSettings, 1))


def update_settings(
    engine, enabled, target_ids, revision, *, delay_seconds=None, remind_seconds=None, at=None
):
    at = time.time() if at is None else at
    target_ids = list(dict.fromkeys(target_ids))
    with write_session(engine) as session:
        settings = session.get(AlertSettings, 1)
        if settings.revision != revision:
            raise AlertConflict("告警设置已在其他页面改变，请重新读取后保存。")
        if delay_seconds is None:
            delay_seconds = settings.delay_seconds
        if not 0 <= delay_seconds <= MAX_DELAY_SECONDS or delay_seconds % 60:
            raise ValueError("Unsupported alert delay")
        if remind_seconds is None:
            remind_seconds = settings.remind_seconds
        if remind_seconds not in REMINDERS:
            raise ValueError("Unsupported alert reminder")
        if len(target_ids) > 64 or (enabled and not target_ids):
            raise ValueError("Select configured alert targets")
        for key in target_ids:
            target = session.get(NotificationTarget, key)
            if (
                target is None
                or target.deleted_at is not None
                or target.kind == "mock"
                or not target.config_ciphertext
            ):
                raise ValueError("Unknown configured alert target")
        wanted = (enabled, target_ids, delay_seconds, remind_seconds)
        if (
            settings.enabled,
            settings.target_ids,
            settings.delay_seconds,
            settings.remind_seconds,
        ) != wanted:
            settings.enabled, settings.target_ids = enabled, target_ids
            settings.delay_seconds, settings.remind_seconds = delay_seconds, remind_seconds
            settings.revision += 1
            for delivery in session.scalars(
                select(AlertDelivery).where(AlertDelivery.result == "pending")
            ):
                if not enabled or delivery.target_id not in target_ids:
                    delivery.result, delivery.error_code = "cancelled", "alerts_disabled"
                    delivery.finished_at = at
        session.flush()
        return settings_view(settings)


def event_view(event):
    return {
        "id": event.id,
        "component": event.component,
        "generation": event.generation,
        "phase": event.phase,
        "label": event.label,
        "code": event.code,
        "at": event.at,
    }


def history(engine, *, page=1, page_size=20):
    with read_session(engine) as session:
        events = session.scalars(
            select(SystemEvent)
            .order_by(SystemEvent.at.desc(), SystemEvent.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        keys = [event.id for event in events]
        counts = (
            session.execute(
                select(AlertDelivery.event_id, AlertDelivery.result, func.count())
                .where(AlertDelivery.event_id.in_(keys))
                .group_by(AlertDelivery.event_id, AlertDelivery.result)
            ).all()
            if keys
            else []
        )
        results = {key: {} for key in keys}
        for key, result, count in counts:
            results[key][result] = count
        return {
            "total": session.scalar(select(func.count()).select_from(SystemEvent)),
            "page": page,
            "page_size": page_size,
            "items": [{**event_view(event), "deliveries": results[event.id]} for event in events],
        }


def states(engine, *, page=1, page_size=20):
    with read_session(engine) as session:
        query = select(SystemState).where(SystemState.fault.is_(True))
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        items = session.scalars(
            query.order_by(SystemState.updated_at.desc(), SystemState.component)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "component": item.component,
                    "label": item.label,
                    "code": item.code,
                    "since": item.updated_at,
                }
                for item in items
            ],
        }


def detail(engine, key, *, page=1, page_size=20):
    with read_session(engine) as session:
        event = session.get(SystemEvent, key)
        if event is None:
            raise LookupError("系统事件不存在或已清理。")
        query = select(AlertDelivery).where(AlertDelivery.event_id == key)
        items = session.scalars(
            query.order_by(AlertDelivery.id).offset((page - 1) * page_size).limit(page_size)
        )
        return {
            **event_view(event),
            "total": session.scalar(select(func.count()).select_from(query.subquery())),
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "id": item.id,
                    "target_name": item.target_snapshot.get("name", ""),
                    "kind": item.target_snapshot.get("kind"),
                    "result": item.result,
                    "error_code": item.error_code,
                    "started_at": item.started_at,
                    "finished_at": item.finished_at,
                }
                for item in items
            ],
        }


def _summary(component, code):
    kind = component.partition(":")[0]
    if kind not in ("source", "delivery", "runtime"):
        return None
    guide = guide_for(kind, code)
    return guide.summary if guide.known else None


def _fault_start(session, event):
    if event.phase == "fault":
        return event.at
    start = session.scalar(
        select(SystemEvent.at).where(
            SystemEvent.component == event.component,
            SystemEvent.generation == event.generation,
            SystemEvent.phase == "fault",
        )
    )
    if start is None:
        # Event history may be pruned during a long fault; the state still holds its start.
        state = session.get(SystemState, event.component)
        if state is not None and state.fault and state.generation == event.generation:
            start = state.updated_at
    return start


def payload(session, event, key):
    start = _fault_start(session, event)
    return {
        "schema_version": 2,
        "event_id": key,
        "type": "system_alert",
        "alert": {
            "id": event.id,
            "component": event.component,
            "phase": event.phase,
            "label": event.label,
            "code": event.code,
            "at": event.at,
            "summary": _summary(event.component, event.code) if event.phase in ANNOUNCING else None,
            "started_at": start,
            "duration_seconds": None
            if event.phase == "fault" or start is None
            else max(0, event.at - start),
        },
    }


class AlertWorker:
    def __init__(self, engine, notifiers, *, clock=time.time, tick=1, timeout=10):
        if not 0 < timeout <= 10:
            raise ValueError("Invalid alert timeout")
        self.engine, self.notifiers = engine, notifiers
        self.clock, self.tick, self.timeout = clock, tick, timeout
        self.last_loop_at = None
        self.reminded_at = None

    def _remind(self, at):
        with write_session(self.engine) as session:
            if session.get(Administrator, 1) is None:
                return 0
            return queue_reminders(session, at)

    async def remind(self):
        """Look for due reminders at most once a minute; they are queued like any other alert."""
        at = self.clock()
        if self.reminded_at is not None and at - self.reminded_at < REMIND_CHECK_SECONDS:
            return 0
        self.reminded_at = at
        return await database_call(self._remind, at)

    def _claim(self):
        with write_session(self.engine) as session:
            if session.get(Administrator, 1) is None:
                return None
            settings = session.get(AlertSettings, 1)
            # Select one candidate at a time, so a disabled backlog does not
            # create an unbounded loop/transaction.
            due = [AlertDelivery.result == "pending"]
            if settings.delay_seconds:
                # A fault waits out the delay; `observe` withdraws it if it clears first.
                due.append(
                    or_(
                        SystemEvent.phase != "fault",
                        SystemEvent.at <= self.clock() - settings.delay_seconds,
                    )
                )
            item = session.scalar(
                select(AlertDelivery)
                .join(SystemEvent)
                .where(*due)
                .order_by(
                    SystemEvent.at, SystemEvent.generation, SystemEvent.phase, AlertDelivery.id
                )
                .limit(1)
            )
            if item is None:
                return None
            target = session.get(NotificationTarget, item.target_id)
            if (
                not settings.enabled
                or item.target_id not in settings.target_ids
                or target.deleted_at is not None
                or not target.enabled
            ):
                item.result, item.error_code, item.finished_at = (
                    "cancelled",
                    "target_unavailable",
                    self.clock(),
                )
                return None
            item.result, item.error_code, item.started_at = (
                "unknown",
                "alert_not_completed",
                self.clock(),
            )
            return (
                item.id,
                dict(item.target_snapshot),
                notification_context(
                    session, payload(session, session.get(SystemEvent, item.event_id), item.id)
                ),
            )

    def _finish(self, key, result):
        with write_session(self.engine) as session:
            item = session.get(AlertDelivery, key)
            item.result, item.error_code, item.finished_at = (
                result.status,
                result.code,
                self.clock(),
            )

    async def run_once(self):
        claim = await database_call(self._claim)
        if claim is None:
            return False
        key, snapshot, message = claim
        result = SendResult(status="permanent_error", code="unsupported_notifier")
        notifier = self.notifiers.get(snapshot["kind"])
        if notifier:
            try:
                result = await asyncio.wait_for(notifier.send(snapshot, message), self.timeout)
                if not isinstance(result, SendResult):
                    result = SendResult(status="unknown", code="invalid_notifier_result")
            except TimeoutError:
                result = SendResult(status="unknown", code="send_timeout")
            except Exception:
                result = SendResult(status="unknown", code="notifier_exception")
        await database_call(self._finish, key, result)
        return True

    async def run(self, stop: asyncio.Event):
        while not stop.is_set():
            await self.remind()
            await self.run_once()
            self.last_loop_at = self.clock()
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), self.tick)


async def send_test(engine, notifiers, target_ids, *, at=None, timeout=10):
    """Send one clearly marked message to each chosen target; nothing is queued or recorded."""
    at = time.time() if at is None else at
    key = identifier()

    def prepare():
        with Session(engine) as session:
            message = notification_context(
                session,
                {
                    "schema_version": 2,
                    "event_id": key,
                    "type": "system_alert",
                    "alert": {
                        "id": key,
                        "component": "test",
                        "phase": "test",
                        "label": "通知目标可以接收系统告警",
                        "code": "test_alert",
                        "at": at,
                        "summary": None,
                        "started_at": None,
                        "duration_seconds": None,
                    },
                },
            )
            rows = []
            for target_id in dict.fromkeys(target_ids):
                target = session.get(NotificationTarget, target_id)
                if (
                    target is None
                    or target.deleted_at is not None
                    or target.kind == "mock"
                    or not target.config_ciphertext
                ):
                    raise ValueError("Unknown configured alert target")
                rows.append((target.enabled, target_snapshot(target)))
            return message, rows

    message, rows = await database_call(prepare)

    async def send(enabled, snapshot):
        if not enabled:
            return "cancelled", "target_unavailable"
        notifier = notifiers.get(snapshot["kind"])
        if notifier is None:
            return "permanent_error", "unsupported_notifier"
        try:
            result = await asyncio.wait_for(notifier.send(snapshot, dict(message)), timeout)
        except TimeoutError:
            return "unknown", "send_timeout"
        except Exception:
            return "unknown", "notifier_exception"
        if not isinstance(result, SendResult):
            return "unknown", "invalid_notifier_result"
        return result.status, result.code

    results = await asyncio.gather(*(send(enabled, snapshot) for enabled, snapshot in rows))
    return [
        {
            "target_id": snapshot["id"],
            "target_name": snapshot.get("name", ""),
            "kind": snapshot.get("kind"),
            "result": status,
            "error_code": code,
            "summary": _failure_summary(status, code),
        }
        for (_, snapshot), (status, code) in zip(rows, results, strict=True)
    ]


def _failure_summary(status, code):
    if status in ("success", "cancelled") or not code:
        return None
    guide = delivery_guide(code)
    return guide.summary if guide.known else None
