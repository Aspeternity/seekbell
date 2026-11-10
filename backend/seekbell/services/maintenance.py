"""Read-only maintenance views and bounded non-secret backup receipts."""

import os
import re
import shutil
import time
import uuid
from datetime import UTC, datetime
from importlib.metadata import version

from sqlalchemy import delete, exists, func, or_, select

from seekbell.db.models import (
    BackupRecord,
    DeliveryAttempt,
    ManualDelivery,
    Outbox,
    Post,
    SourceRun,
    TargetTestAttempt,
)
from seekbell.db.transactions import write_session
from seekbell.services.history import read_session
from seekbell.services.retention import TERMINAL


def record_backup(engine, kind, result, *, archive_bytes=None, manifest=None):
    from seekbell.backup import expected_revision

    manifest = manifest or {}
    with write_session(engine) as session:
        session.add(
            BackupRecord(
                id=str(uuid.uuid4()),
                kind=kind,
                result=result,
                at=time.time(),
                archive_bytes=archive_bytes,
                application_version=manifest.get("application_version", version("seekbell")),
                database_revision=manifest.get("database_revision", expected_revision()),
            )
        )
        session.flush()
        keep = select(BackupRecord.id).order_by(BackupRecord.at.desc(), BackupRecord.id).limit(50)
        session.execute(delete(BackupRecord).where(BackupRecord.id.not_in(keep)))


def backup_records(engine):
    with read_session(engine) as session:
        return [
            {
                name: getattr(row, name)
                for name in (
                    "id",
                    "kind",
                    "result",
                    "at",
                    "archive_bytes",
                    "application_version",
                    "database_revision",
                )
            }
            for row in session.scalars(
                select(BackupRecord).order_by(BackupRecord.at.desc(), BackupRecord.id).limit(50)
            )
        ]


def regular_size(path):
    # No symlink traversal or arbitrary filesystem paths in these views.
    try:
        return path.lstat().st_size if path.is_file() and not path.is_symlink() else 0
    except OSError:
        return 0


CANDIDATE = "web-restore"
# `tempfile.mkdtemp` suffix after the UTC stamp written by a web restore.
PREVIOUS = re.compile(r"before-restore-(\d{8}T\d{6})Z-[A-Za-z0-9_]{8}")
LEFTOVER_FILES = (
    "seekbell.sqlite3",
    "seekbell.sqlite3-wal",
    "seekbell.sqlite3-shm",
    "credentials.key",
)


def leftover_path(root, name):
    """The directory a restore left behind under this fixed name, or None for anything else."""
    if name != CANDIDATE and not PREVIOUS.fullmatch(name):
        return None
    path = root / name
    return path if os.path.lexists(path) else None


def leftovers(root):
    """Data a restore set aside: the replaced workspace, or a verification-only copy."""
    rows = []
    try:
        names = sorted(entry.name for entry in os.scandir(root))
    except OSError:
        return rows
    for name in names:
        path = leftover_path(root, name)
        if path is None:
            continue
        stamp = PREVIOUS.fullmatch(name)
        try:
            at = (
                datetime.strptime(stamp[1], "%Y%m%dT%H%M%S").replace(tzinfo=UTC).timestamp()
                if stamp
                else path.lstat().st_mtime
            )
        except (OSError, ValueError):
            continue
        rows.append(
            {
                "id": name,
                "kind": "previous" if stamp else "candidate",
                "at": at,
                "bytes": 0
                if path.is_symlink()
                else sum(regular_size(path / file) for file in LEFTOVER_FILES),
            }
        )
    return sorted(rows, key=lambda row: -row["at"])


def storage_view(settings):
    root = settings.data_dir.resolve()
    usage = shutil.disk_usage(root)
    kept = leftovers(root)
    return {
        # The write-ahead log is part of the live database.
        "database_bytes": regular_size(settings.database_path)
        + regular_size(root / "seekbell.sqlite3-wal"),
        "leftover_bytes": sum(row["bytes"] for row in kept),
        "leftover_count": len(kept),
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
