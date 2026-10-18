"""Display settings and bounded history cleanup, independent of identity ledgers."""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from sqlalchemy import Engine, delete, or_, select, tuple_
from sqlalchemy.orm import Session

from seekbell.db.models import (
    ApplicationSettings,
    DeliveryAttempt,
    ManualDeliveryAttempt,
    Outbox,
    OutboxContribution,
    Post,
    RuleHit,
    SourceRun,
    TargetTestAttempt,
)
from seekbell.db.transactions import write_session
from seekbell.services.configuration import ConfigurationConflict


class SystemSettings:
    def __init__(self, engine: Engine):
        self.engine = engine

    def get(self) -> dict:
        with Session(self.engine) as session:
            row = session.get(ApplicationSettings, 1)
            return {
                "revision": row.revision,
                "timezone": row.timezone,
                "retention_days": row.retention_days,
                "last_cleanup_at": row.last_cleanup_at,
                "last_cleanup_counts": row.last_cleanup_counts,
            }

    @staticmethod
    def timezones():
        return sorted(available_timezones() - {"Factory", "localtime", "posixrules"})

    def update(self, *, expected_revision: int, timezone: str, retention_days: int):
        if timezone not in self.timezones() or not 1 <= retention_days <= 3650:
            raise ValueError("Invalid settings")
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Invalid timezone") from None
        with write_session(self.engine) as session:
            row = session.get(ApplicationSettings, 1)
            if row.revision != expected_revision:
                raise ConfigurationConflict
            if row.timezone != timezone or row.retention_days != retention_days:
                row.revision += 1
            row.timezone, row.retention_days = timezone, retention_days

    def cleanup(self, *, at: float, expected_revision: int | None = None, limit: int = 200) -> dict:
        if not 1 <= limit <= 1000:
            raise ValueError("Cleanup batch out of range")
        with write_session(self.engine) as session:
            settings = session.get(ApplicationSettings, 1)
            if expected_revision is not None and settings.revision != expected_revision:
                raise ConfigurationConflict
            cutoff = at - settings.retention_days * 86400
            counts = {}
            for model in (TargetTestAttempt, ManualDeliveryAttempt):
                ids = session.scalars(
                    select(model.id)
                    .where(model.finished_at < cutoff, model.result != "unknown")
                    .order_by(model.finished_at, model.id)
                    .limit(limit)
                ).all()
                if ids:
                    session.execute(delete(model).where(model.id.in_(ids)))
                counts[model.__tablename__] = len(ids)
            pending_attempt = (
                select(DeliveryAttempt.id)
                .where(
                    DeliveryAttempt.event_id == Outbox.id,
                    or_(
                        DeliveryAttempt.finished_at.is_(None),
                        DeliveryAttempt.finished_at >= cutoff,
                        DeliveryAttempt.late_finished_at >= cutoff,
                        DeliveryAttempt.result == "in_progress",
                    ),
                )
                .exists()
            )
            manual_reference = (
                select(ManualDeliveryAttempt.id)
                .where(ManualDeliveryAttempt.original_event_id == Outbox.id)
                .exists()
            )
            ids = session.scalars(
                select(Outbox.id)
                .where(
                    Outbox.created_at < cutoff,
                    Outbox.status.in_(("sent", "failed", "cancelled")),
                    Outbox.uncertain.is_(False),
                    ~pending_attempt,
                    ~manual_reference,
                )
                .order_by(Outbox.created_at, Outbox.id)
                .limit(limit)
            ).all()
            if ids:
                session.execute(
                    delete(OutboxContribution).where(OutboxContribution.event_id.in_(ids))
                )
                session.execute(delete(DeliveryAttempt).where(DeliveryAttempt.event_id.in_(ids)))
                session.execute(delete(Outbox).where(Outbox.id.in_(ids)))
            counts["outbox"] = len(ids)
            protected_hit = (
                select(OutboxContribution.event_id)
                .where(OutboxContribution.hit_id == RuleHit.id)
                .exists()
            )
            ids = session.scalars(
                select(RuleHit.id)
                .where(RuleHit.matched_at < cutoff, ~protected_hit)
                .order_by(RuleHit.matched_at, RuleHit.id)
                .limit(limit)
            ).all()
            if ids:
                session.execute(delete(RuleHit).where(RuleHit.id.in_(ids)))
            counts["rule_hits"] = len(ids)
            protected_post = (
                select(Outbox.id)
                .where(
                    Outbox.website_id == Post.website_id,
                    Outbox.external_post_id == Post.external_post_id,
                )
                .exists()
            )
            posts = session.execute(
                select(Post.website_id, Post.external_post_id)
                .where(Post.first_seen_at < cutoff, ~protected_post)
                .order_by(Post.first_seen_at, Post.external_post_id)
                .limit(limit)
            ).all()
            if posts:
                session.execute(
                    delete(Post).where(tuple_(Post.website_id, Post.external_post_id).in_(posts))
                )
            counts["posts"] = len(posts)
            ids = session.scalars(
                select(SourceRun.id)
                .where(SourceRun.at < cutoff)
                .order_by(SourceRun.at, SourceRun.id)
                .limit(limit)
            ).all()
            if ids:
                session.execute(delete(SourceRun).where(SourceRun.id.in_(ids)))
            counts["source_runs"] = len(ids)
            settings.last_cleanup_at, settings.last_cleanup_counts = at, counts
            return {"at": at, "cutoff": cutoff, "counts": counts, "batch_limit": limit}
