"""Snapshot statistics from persisted records; never collect, evaluate or send."""

import time

from sqlalchemy import Integer, and_, cast, func, or_, select

from seekbell.db.models import (
    DeliveredPost,
    NotificationTarget,
    Outbox,
    Post,
    Source,
    SourceRun,
    SourceState,
    Task,
    TaskVersion,
    Website,
    WebsiteInstallation,
)
from seekbell.services.history import decisions, error_code, post_key, read_session


def overview(engine, range_name="24h", *, at=None):
    end = time.time() if at is None else at
    count, width = (24, 3600) if range_name == "24h" else (7, 86400)
    start = end - count * width
    ledger = decisions()
    d = ledger.c
    matches = select(ledger).where(d.status == "match", d.at >= start, d.at < end).subquery()
    with read_session(engine) as session:

        def total(model, *conditions):
            return session.scalar(select(func.count()).select_from(model).where(*conditions))

        by_bucket = dict(
            session.execute(
                select(cast((matches.c.at - start) / width, Integer), func.count()).group_by(
                    cast((matches.c.at - start) / width, Integer)
                )
            ).all()
        )
        decision_counts = dict(
            session.execute(
                select(d.status, func.count()).where(d.at >= start, d.at < end).group_by(d.status)
            ).all()
        )
        queue = dict(
            session.execute(select(Outbox.status, func.count()).group_by(Outbox.status)).all()
        )
        sources = []
        for website, source, state in session.execute(
            select(Website, Source, SourceState)
            .join(WebsiteInstallation, WebsiteInstallation.website_id == Website.id)
            .join(Source, Source.website_id == Website.id)
            .join(SourceState, SourceState.source_id == Source.id)
            .order_by(Website.id, Source.id)
        ):
            sources.append(
                {
                    "website_id": website.id,
                    "name": website.name,
                    "source_id": source.id,
                    "enabled": website.enabled and source.enabled,
                    "last_attempt_at": state.last_attempt_at,
                    "last_success_at": state.last_success_at,
                    "failures": state.failures,
                    "error_code": error_code(state.last_error_code),
                    "possible_gap": state.possible_gap,
                    "last_gap_at": state.last_gap_at,
                }
            )
        recent = []
        for row in session.execute(
            select(
                matches,
                TaskVersion.name,
                Task.deleted_at,
                Post.title,
                Post.external_post_id.label("retained_id"),
            )
            .join(
                TaskVersion,
                and_(
                    TaskVersion.task_id == matches.c.task_id,
                    TaskVersion.version == matches.c.task_version,
                ),
            )
            .join(Task, Task.id == matches.c.task_id)
            .outerjoin(
                Post,
                and_(
                    Post.website_id == matches.c.website_id,
                    Post.external_post_id == matches.c.external_post_id,
                ),
            )
            .order_by(matches.c.at.desc(), matches.c.task_id, matches.c.external_post_id)
            .limit(5)
        ).mappings():
            recent.append(
                {
                    "post_id": post_key(row["website_id"], row["external_post_id"])
                    if row["retained_id"] is not None
                    else None,
                    "title": row["title"],
                    "task_name": row["name"],
                    "task_version": row["task_version"],
                    "task_deleted": row["deleted_at"] is not None,
                    "at": row["at"],
                }
            )
        return {
            "range": range_name,
            "start": start,
            "end": end,
            # Lifespan does not start a collector or delivery worker in this stage.
            "runtime_active": False,
            "configuration": {
                "websites": total(WebsiteInstallation),
                "tasks": total(Task, Task.deleted_at.is_(None)),
                "enabled_tasks": total(Task, Task.deleted_at.is_(None), Task.enabled.is_(True)),
                "targets": total(NotificationTarget),
            },
            "window": {
                "posts": total(Post, Post.first_seen_at >= start, Post.first_seen_at < end),
                "matches": decision_counts.get("match", 0),
                "insufficient_data": decision_counts.get("insufficient_data", 0),
                # Receipts deduplicate retries/late results by post and target, and
                # exclude independent target tests. This is acceptance, not inbox arrival.
                "delivered": total(
                    DeliveredPost,
                    DeliveredPost.delivered_at >= start,
                    DeliveredPost.delivered_at < end,
                ),
                "source_failures": total(
                    SourceRun,
                    SourceRun.at >= start,
                    SourceRun.at < end,
                    SourceRun.status == "failure",
                ),
            },
            "current": {
                "queue": queue,
                "uncertain": total(Outbox, Outbox.uncertain.is_(True)),
                "attention": total(
                    Outbox,
                    or_(Outbox.status.in_(("failed", "retry")), Outbox.uncertain.is_(True)),
                ),
            },
            "buckets": [
                {
                    "start": start + i * width,
                    "end": start + (i + 1) * width,
                    "matches": by_bucket.get(i, 0),
                }
                for i in range(count)
            ],
            "sources": sources,
            "recent_matches": recent,
        }
