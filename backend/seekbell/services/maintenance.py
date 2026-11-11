"""Read-only maintenance views."""

import shutil
import time

from sqlalchemy import exists, func, or_, select, tuple_

from seekbell.db.models import (
    AlertDelivery,
    DeliveryAttempt,
    ManualDelivery,
    Outbox,
    Post,
    RuleHit,
    SourceRun,
    SystemEvent,
    TargetTestAttempt,
)
from seekbell.services.history import read_session
from seekbell.services.retention import TERMINAL, excess_posts


def regular_size(path):
    # No symlink traversal or arbitrary filesystem paths in these views.
    try:
        return path.lstat().st_size if path.is_file() and not path.is_symlink() else 0
    except OSError:
        return 0


def storage_view(settings):
    from seekbell.services.backups import usage as backup_usage

    root = settings.data_dir.resolve()
    usage = shutil.disk_usage(root)
    kept = backup_usage(settings)
    return {
        # The write-ahead log is part of the live database.
        "database_bytes": regular_size(settings.database_path)
        + regular_size(root / "seekbell.sqlite3-wal"),
        "backup_bytes": kept["bytes"],
        "backup_count": kept["count"],
        "filesystem_total_bytes": usage.total,
        "filesystem_free_bytes": usage.free,
        "checked_at": time.time(),
    }


def retention_preview(engine, days, max_posts=None, *, at=None):
    """Estimate what the cleaner would remove under a draft policy; reads only."""
    at = time.time() if at is None else at
    cutoff = at - days * 86400
    recent_attempt = exists(
        select(DeliveryAttempt.id).where(
            DeliveryAttempt.event_id == Outbox.id,
            or_(
                DeliveryAttempt.finished_at.is_(None),
                DeliveryAttempt.started_at >= cutoff,
                DeliveryAttempt.finished_at >= cutoff,
                DeliveryAttempt.late_finished_at >= cutoff,
            ),
        )
    )
    eligible_deliveries = (
        select(Outbox.id)
        .where(
            Outbox.status.in_(TERMINAL),
            Outbox.created_at < cutoff,
            Outbox.completed_at < cutoff,
            ~recent_attempt,
        )
        .correlate(None)
    )
    retained_delivery = exists(
        select(Outbox.id).where(
            Outbox.website_id == Post.website_id,
            Outbox.external_post_id == Post.external_post_id,
            Outbox.id.not_in(eligible_deliveries),
        )
    )
    expired = Post.first_seen_at < cutoff
    if max_posts is not None:
        excess = excess_posts(max_posts)
        expired = or_(
            expired,
            tuple_(Post.website_id, Post.external_post_id).in_(
                select(excess.c.website_id, excess.c.external_post_id)
            ),
        )
    retained_alert = exists(
        select(AlertDelivery.id).where(
            AlertDelivery.event_id == SystemEvent.id,
            or_(
                AlertDelivery.result == "pending",
                AlertDelivery.finished_at.is_(None),
                AlertDelivery.finished_at >= cutoff,
            ),
        )
    )
    with read_session(engine) as session:

        def count(model, *conditions):
            return session.scalar(select(func.count()).select_from(model).where(*conditions))

        posts = count(Post, expired, ~retained_delivery)
        records = {
            "deliveries": session.scalar(
                select(func.count()).select_from(eligible_deliveries.subquery())
            ),
            "tests": count(TargetTestAttempt, TargetTestAttempt.finished_at < cutoff),
            "manual": count(ManualDelivery, ManualDelivery.finished_at < cutoff),
            "source_runs": count(SourceRun, SourceRun.at < cutoff),
            "system_events": count(SystemEvent, SystemEvent.at < cutoff, ~retained_alert),
        }
        return {
            "days": days,
            "max_posts": max_posts,
            "checked_at": at,
            "posts": posts,
            "records": sum(records.values()),
            "counts": {"posts": posts, **records},
        }


def data_overview(engine):
    """What history is kept right now: the counts a retention change visibly affects."""
    with read_session(engine) as session:

        def count(statement):
            return session.scalar(select(func.count()).select_from(statement.subquery()))

        return {
            "posts": count(select(Post.website_id)),
            "matched_posts": count(select(RuleHit.website_id, RuleHit.external_post_id).distinct()),
            "deliveries": count(select(Outbox.id)),
            "problems": count(select(SystemEvent.id).where(SystemEvent.phase == "fault")),
            "earliest_at": session.scalar(select(func.min(Post.first_seen_at))),
        }
