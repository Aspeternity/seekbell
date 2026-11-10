"""Read-only maintenance views."""

import shutil
import time

from sqlalchemy import exists, func, or_, select

from seekbell.db.models import (
    DeliveryAttempt,
    ManualDelivery,
    Outbox,
    Post,
    SourceRun,
    TargetTestAttempt,
)
from seekbell.services.history import read_session
from seekbell.services.retention import TERMINAL


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


def retention_preview(engine, days, *, at=None):
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
    with read_session(engine) as session:

        def count(model, *conditions):
            return session.scalar(select(func.count()).select_from(model).where(*conditions))

        old_posts = count(Post, Post.first_seen_at < cutoff)
        posts = count(Post, Post.first_seen_at < cutoff, ~retained_delivery)
        counts = {
            "posts": posts,
            "deliveries": session.scalar(
                select(func.count()).select_from(eligible_deliveries.subquery())
            ),
            "tests": count(TargetTestAttempt, TargetTestAttempt.finished_at < cutoff),
            "manual": count(ManualDelivery, ManualDelivery.finished_at < cutoff),
            "source_runs": count(SourceRun, SourceRun.at < cutoff),
        }
        return {
            "days": days,
            "cutoff": cutoff,
            "checked_at": at,
            "counts": counts,
            "protected_posts": old_posts - posts,
        }
