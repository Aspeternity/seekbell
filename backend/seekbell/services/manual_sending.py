"""Explicit one-shot sends, using original messages and current target credentials."""

import copy

from sqlalchemy.orm import Session

from seekbell.db.models import ManualDelivery, NotificationTarget, Outbox
from seekbell.db.transactions import write_session
from seekbell.services.configuration import identifier, target_snapshot
from seekbell.services.display import notification_context
from seekbell.services.target_testing import OperationConflict, TargetTesting


class MissingSend(LookupError):
    pass


def validate_target(target, revision=None, *, enabled=False):
    if (
        target is None
        or target.deleted_at is not None
        or target.kind == "mock"
        or not target.config_ciphertext
    ):
        raise MissingSend("通知目标不存在或未配置。")
    if enabled and not target.enabled:
        raise OperationConflict("请先启用对应通知目标。")
    if revision is not None and target.revision != revision:
        raise OperationConflict("目标配置已改变，请重新打开确认。")


def preview(engine, key, *, manual=False):
    with Session(engine) as session:
        event = session.get(Outbox, key) if manual else None
        if manual and event is None:
            raise MissingSend("原投递记录不存在或已清理。")
        target = session.get(NotificationTarget, event.target_id if manual else key)
        validate_target(target, enabled=manual)
        if event and event.status in ("pending", "retry", "leased"):
            raise OperationConflict("原通知仍在等待、重试或发送中，请先处理原投递。")
        return {
            "target_id": target.id,
            "target_name": target.name,
            "kind": target.kind,
            "revision": target.revision,
            "enabled": target.enabled,
            "source_event_id": event.id if event else None,
            "title": event.payload.get("post", {}).get("title", "原消息")
            if event
            else "SeekBell 通知测试",
            "uncertain": event.uncertain if event else False,
        }


class ManualSending(TargetTesting):
    record_type = ManualDelivery

    def _start(self, event_id, key=None, revision=None):
        key, at = key or identifier(), self.clock()
        with write_session(self.engine) as session:
            existing = session.get(ManualDelivery, key)
            if existing:
                if existing.source_event_id != event_id:
                    raise OperationConflict("操作标识已用于另一条通知。")
                return key, None, None
            event = session.get(Outbox, event_id)
            if event is None:
                raise MissingSend("原投递记录不存在或已清理。")
            target = session.get(NotificationTarget, event.target_id)
            validate_target(target, revision, enabled=True)
            if event.status in ("pending", "retry", "leased"):
                raise OperationConflict("原通知仍在等待、重试或发送中，请先处理原投递。")
            snapshot = target_snapshot(target)
            payload = copy.deepcopy(event.payload)
            payload["event_id"] = key
            message = notification_context(session, payload)
            session.add(
                ManualDelivery(
                    id=key,
                    source_event_id=event.id,
                    target_id=target.id,
                    target_snapshot=snapshot,
                    payload=payload,
                    started_at=at,
                    result="unknown",
                    error_code="send_not_completed",
                )
            )
        return key, snapshot, message


class ConfiguredTargetTesting(TargetTesting):
    def validate(self, target, revision):
        validate_target(target, revision)
