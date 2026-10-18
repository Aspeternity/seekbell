"""Explicit safe projections; credentials and wire snapshots never leave the server."""

import re

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from seekbell.db.models import (
    DeliveryAttempt,
    ManualDeliveryAttempt,
    NotificationTarget,
    Outbox,
    TargetTestAttempt,
)
from seekbell.services.explicit_sending import SendNotFound
from seekbell.sites.nodeseek import NodeSeekAdapter

MODELS = {"automatic": Outbox, "manual": ManualDeliveryAttempt, "test": TargetTestAttempt}


class DeliveryRecords:
    def __init__(self, engine: Engine):
        self.engine = engine

    @staticmethod
    def view(row, kind):
        auto = kind == "automatic"
        snapshot = row.target_snapshot
        post = row.payload.get("post", {}) if kind != "test" else {}
        key = str(post.get("external_post_id", ""))
        return {
            "id": row.id,
            "kind": kind,
            "target_id": row.target_id,
            "target_name": snapshot.get("name", ""),
            "channel": snapshot.get("kind", ""),
            "target_revision": snapshot.get("revision"),
            "status": row.status if auto else row.result,
            "result": row.last_result if auto else row.result,
            "code": row.last_error_code if auto else row.error_code,
            "uncertain": row.uncertain if auto else row.result == "unknown",
            "started_at": row.created_at if auto else row.started_at,
            "finished_at": None if auto else row.finished_at,
            "attempt_count": row.attempt_count if auto else 1,
            "next_attempt_at": row.available_at
            if auto and row.status in ("pending", "retry")
            else None,
            "lease_until": row.lease_until if auto else None,
            "original_event_id": row.original_event_id if kind == "manual" else None,
            "title": str(post.get("title", "SeekBell 通知测试"))[:8192],
            "url": NodeSeekAdapter.canonical_url(key)
            if re.fullmatch(r"[1-9][0-9]{0,19}", key)
            else None,
        }

    def list(
        self, *, kind: str, target_id: str | None, status: str | None, offset: int, limit: int
    ):
        model = MODELS[kind]
        statement = select(model)
        if target_id:
            statement = statement.where(model.target_id == target_id)
        if status:
            statement = statement.where(
                (model.status if kind == "automatic" else model.result) == status
            )
        at = model.created_at if kind == "automatic" else model.started_at
        with Session(self.engine) as session:
            total = session.scalar(select(func.count()).select_from(statement.subquery()))
            rows = session.scalars(
                statement.order_by(at.desc(), model.id).offset(offset).limit(limit)
            ).all()
            return {
                "items": [self.view(row, kind) for row in rows],
                "total": total,
                "offset": offset,
                "limit": limit,
            }

    def detail(self, key: str, kind: str):
        with Session(self.engine) as session:
            row = session.get(MODELS[kind], key)
            if row is None:
                raise SendNotFound
            result = self.view(row, kind)
            target = session.get(NotificationTarget, row.target_id)
            result["current_target"] = {
                "id": target.id,
                "name": target.name,
                "kind": target.kind,
                "revision": target.revision,
                "enabled": target.enabled,
            }
            result["matched_tasks"] = (
                [
                    {
                        "id": task.get("id"),
                        "version": task.get("version"),
                        "name": str(task.get("name", ""))[:200],
                    }
                    for task in row.payload.get("matched_tasks", [])
                ]
                if kind != "test"
                else []
            )
            result["attempts"] = (
                [
                    {
                        "sequence": attempt.sequence,
                        "started_at": attempt.started_at,
                        "finished_at": attempt.finished_at,
                        "result": attempt.result,
                        "code": attempt.error_code,
                        "late_result": attempt.late_result,
                        "late_finished_at": attempt.late_finished_at,
                    }
                    for attempt in session.scalars(
                        select(DeliveryAttempt)
                        .where(DeliveryAttempt.event_id == key)
                        .order_by(DeliveryAttempt.sequence)
                    )
                ]
                if kind == "automatic"
                else []
            )
            return result
