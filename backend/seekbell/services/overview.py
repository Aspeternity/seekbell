"""Snapshot statistics from persisted records; never collect, evaluate or send."""

import time
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Integer, and_, cast, func, or_, select

from seekbell.db.models import (
    DeliveredPost,
    NotificationTarget,
    Outbox,
    Post,
    SeenPost,
    Source,
    SourceProbe,
    SourceRun,
    SourceState,
    Task,
    TaskVersion,
    Website,
    WebsiteInstallation,
    WorkspacePreferences,
)
from seekbell.services.history import date_window, decisions, error_code, post_key, read_session
from seekbell.services.request_budget import request_state
from seekbell.services.source_probe import probe_backoff


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
        preferences = session.get(WorkspacePreferences, 1)
        timezone = preferences.timezone if preferences else "UTC"
        local_day = datetime.fromtimestamp(end, ZoneInfo(timezone)).date()
        day_start, _ = date_window(local_day, timezone)
        today_posts = dict(
            session.execute(
                select(SeenPost.website_id, func.count())
                .where(SeenPost.first_seen_at >= day_start, SeenPost.first_seen_at < end)
                .group_by(SeenPost.website_id)
            ).all()
        )
        sources = []
        for website, source, state in session.execute(
            select(Website, Source, SourceState)
            .join(WebsiteInstallation, WebsiteInstallation.website_id == Website.id)
            .join(Source, Source.website_id == Website.id)
            .join(SourceState, SourceState.source_id == Source.id)
            .order_by(WebsiteInstallation.position, Website.id, Source.id)
        ):
            # Source identity index includes the integer row ID in SQLite. Read
            # the last persisted attempts without sorting all retained history.
            recent_runs = list(
                session.scalars(
                    select(SourceRun)
                    .where(SourceRun.source_id == source.id, SourceRun.at < end)
                    .order_by(SourceRun.id.desc())
                    .limit(30)
                )
            )
            sources.append(
                {
                    "website_id": website.id,
                    "name": website.name,
                    "source_id": source.id,
                    "enabled": website.enabled and source.enabled,
                    "interval_seconds": source.interval_seconds,
                    "today_posts": today_posts.get(website.id, 0),
                    "recent_runs": [
                        {
                            "id": run.id,
                            "at": run.at,
                            "status": run.status
                            if run.status in ("success", "failure")
                            else "unknown",
                        }
                        for run in reversed(recent_runs)
                    ],
                    "last_attempt_at": state.last_attempt_at,
                    "last_success_at": state.last_success_at,
                    "next_attempt_at": max(
                        state.next_attempt_at,
                        probe_backoff(session.get(SourceProbe, source.id)),
                        request_state(session, website.id, end)[0],
                    ),
                    "failures": state.failures,
                    "error_code": error_code(
                        state.last_error_code or request_state(session, website.id, end)[1]
                    ),
                    "possible_gap": state.possible_gap,
                    "last_gap_at": state.last_gap_at,
                }
            )
        task_counts = dict(
            session.execute(
                select(matches.c.task_id, func.count()).group_by(matches.c.task_id)
            ).all()
        )
        task_last = dict(
            session.execute(
                select(d.task_id, func.max(d.at))
                .where(d.status == "match", d.at < end)
                .group_by(d.task_id)
            ).all()
        )
        task_stats = [
            {
                "id": task_id,
                "matches": task_counts.get(task_id, 0),
                "last_match_at": task_last.get(task_id),
            }
            for task_id in session.scalars(
                select(Task.id).where(Task.deleted_at.is_(None)).order_by(Task.id)
            )
        ]
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
            # Database-only view; API adds the in-process actor status.
            "runtime_active": False,
            "today": {"start": day_start, "end": end, "timezone": timezone},
            "configuration": {
                "websites": total(WebsiteInstallation),
                "tasks": total(Task, Task.deleted_at.is_(None)),
                "enabled_tasks": total(Task, Task.deleted_at.is_(None), Task.enabled.is_(True)),
                "targets": total(NotificationTarget, NotificationTarget.deleted_at.is_(None)),
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
            "tasks": task_stats,
            "sources": sources,
            "recent_matches": recent,
        }
