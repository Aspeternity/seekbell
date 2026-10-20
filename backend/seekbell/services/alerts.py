"""Durable fault/recovery transitions and one-shot, independent alert deliveries."""

import asyncio
import re
import time
from contextlib import suppress

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seekbell.db.models import (
    Administrator,
    AlertDelivery,
    AlertSettings,
    NotificationTarget,
    SystemEvent,
    SystemState,
)
from seekbell.db.transactions import database_call, write_session
from seekbell.domain.delivery import SendResult
from seekbell.services.configuration import identifier, target_snapshot
from seekbell.services.history import read_session


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
    if settings.enabled:
        for key in settings.target_ids:
            target = session.get(NotificationTarget, key)
            ready = (
                target and target.deleted_at is None and target.enabled and target.config_ciphertext
            )
            if target is None:
                continue
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
    return event.id


def get_settings(engine):
    with Session(engine) as session:
        settings = session.get(AlertSettings, 1)
        return {
            "enabled": settings.enabled,
            "target_ids": settings.target_ids,
            "revision": settings.revision,
        }


def update_settings(engine, enabled, target_ids, revision, *, at=None):
    at = time.time() if at is None else at
    target_ids = list(dict.fromkeys(target_ids))
    with write_session(engine) as session:
        settings = session.get(AlertSettings, 1)
        if settings.revision != revision:
            raise AlertConflict("告警设置已在其他页面改变，请重新读取后保存。")
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
        if settings.enabled != enabled or settings.target_ids != target_ids:
            settings.enabled, settings.target_ids = enabled, target_ids
            settings.revision += 1
            for delivery in session.scalars(
                select(AlertDelivery).where(AlertDelivery.result == "pending")
            ):
                if not enabled or delivery.target_id not in target_ids:
                    delivery.result, delivery.error_code = "cancelled", "alerts_disabled"
                    delivery.finished_at = at
        return {
            "enabled": settings.enabled,
            "target_ids": settings.target_ids,
            "revision": settings.revision,
        }


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


def payload(event, key):
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
        },
    }


class AlertWorker:
    def __init__(self, engine, notifiers, *, clock=time.time, tick=1, timeout=10):
        if not 0 < timeout <= 10:
            raise ValueError("Invalid alert timeout")
        self.engine, self.notifiers = engine, notifiers
        self.clock, self.tick, self.timeout = clock, tick, timeout

    def _claim(self):
        with write_session(self.engine) as session:
            if session.get(Administrator, 1) is None:
                return None
            settings = session.get(AlertSettings, 1)
            # Select one candidate at a time, so a disabled backlog does not
            # create an unbounded loop/transaction.
            item = session.scalar(
                select(AlertDelivery)
                .join(SystemEvent)
                .where(AlertDelivery.result == "pending")
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
                payload(session.get(SystemEvent, item.event_id), item.id),
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
            await self.run_once()
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), self.tick)
