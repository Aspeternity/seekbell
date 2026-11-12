"""Bounded, transactional history pruning. Identity and receipt ledgers are never deleted."""

import asyncio
import time
from contextlib import suppress

from sqlalchemy import delete, exists, or_, select, tuple_
from sqlalchemy.orm import Session

from seekbell.db.models import (
    Administrator,
    AlertDelivery,
    DeliveryAttempt,
    ManualDelivery,
    Outbox,
    OutboxContribution,
    Post,
    RetentionPolicy,
    RuleHit,
    SourceRun,
    SystemEvent,
    TargetTestAttempt,
    TaskEvaluation,
)
from seekbell.db.transactions import database_call, write_session

TERMINAL = ("sent", "failed", "cancelled")


class PolicyConflict(ValueError):
    pass


MAX_POSTS = 1_000_000


def policy_view(policy):
    return {"days": policy.days, "max_posts": policy.max_posts, "revision": policy.revision}


def get_policy(engine):
    with Session(engine) as session:
        return policy_view(session.get(RetentionPolicy, 1))


def update_policy(engine, days, max_posts, revision):
    if type(days) is not int or not 1 <= days <= 365:
        raise ValueError("Invalid history retention")
    if max_posts is not None and (type(max_posts) is not int or not 1 <= max_posts <= MAX_POSTS):
        raise ValueError("Invalid content limit")
    with write_session(engine) as session:
        policy = session.get(RetentionPolicy, 1)
        if policy.revision != revision:
            raise PolicyConflict("保留策略已在其他页面改变，请重新读取后保存。")
        if (policy.days, policy.max_posts) != (days, max_posts):
            policy.days, policy.max_posts = days, max_posts
            policy.revision += 1
            policy.next_run_at = 0
        return policy_view(policy)


def no_delivery(model):
    return ~exists(
        select(Outbox.id).where(
            Outbox.website_id == model.website_id,
            Outbox.external_post_id == model.external_post_id,
        )
    )


def no_post(model):
    return ~exists(
        select(Post.website_id).where(
            Post.website_id == model.website_id,
            Post.external_post_id == model.external_post_id,
        )
    )


def remove(session, model, *conditions):
    return session.execute(
        delete(model).where(*conditions).execution_options(synchronize_session=False)
    ).rowcount


def excess_posts(max_posts):
    """Unmatched content beyond the newest ``max_posts``; matched content is never counted."""
    return (
        select(Post.website_id, Post.external_post_id, Post.first_seen_at)
        .where(
            ~exists(
                select(RuleHit.id).where(
                    RuleHit.website_id == Post.website_id,
                    RuleHit.external_post_id == Post.external_post_id,
                )
            )
        )
        .order_by(Post.first_seen_at.desc(), Post.website_id.desc(), Post.external_post_id.desc())
        .offset(max_posts)
        .subquery()
    )


def excess_batch(max_posts, limit):
    """The oldest excess content that can go now: none of it still has a delivery."""
    excess = excess_posts(max_posts)
    return (
        select(excess.c.website_id, excess.c.external_post_id)
        .where(
            ~exists(
                select(Outbox.id).where(
                    Outbox.website_id == excess.c.website_id,
                    Outbox.external_post_id == excess.c.external_post_id,
                )
            )
        )
        .order_by(excess.c.first_seen_at, excess.c.website_id, excess.c.external_post_id)
        .limit(limit)
    )


def remove_posts(session, posts, counts):
    """A readable post goes together with its decisions."""
    if not posts:
        return
    counts["evaluations"] += remove(
        session,
        TaskEvaluation,
        tuple_(TaskEvaluation.website_id, TaskEvaluation.external_post_id).in_(posts),
    )
    counts["hits"] += remove(
        session, RuleHit, tuple_(RuleHit.website_id, RuleHit.external_post_id).in_(posts)
    )
    counts["posts"] += remove(
        session, Post, tuple_(Post.website_id, Post.external_post_id).in_(posts)
    )


def reclaim(engine):
    """Return the pages freed by a finished cleanup to the filesystem (incremental mode)."""
    with engine.connect() as connection:
        # Usually nothing is free: stay read-only and leave the write lock to others.
        if not connection.exec_driver_sql("PRAGMA freelist_count").scalar():
            return
    with write_session(engine) as session:
        # Each step frees one page: drain the raw cursor (SQLAlchemy would close it early).
        cursor = session.connection().connection.cursor()
        try:
            cursor.execute("PRAGMA incremental_vacuum").fetchall()
        finally:
            cursor.close()


# A backlog (a tightened limit, a shortened period) is worked off batch after batch
# without waiting a full tick; the short pause lets collection and delivery take the
# write lock between batches.
BACKLOG_PAUSE = 0.05


class HistoryRetention:
    def __init__(
        self, engine, *, clock=time.time, tick=1, batch_size=100, interval=3600, disk=None
    ):
        if not 1 <= batch_size <= 100 or interval <= 0 or tick <= 0:
            raise ValueError("Invalid cleanup limits")
        self.engine, self.clock, self.tick = engine, clock, tick
        self.batch_size, self.interval = batch_size, interval
        # Storage upkeep shares this actor: an optional watch on free disk space.
        self.disk = disk
        self.last_loop_at = None
        # Set by collection when new content was stored: the content limit is then
        # enforced within a tick instead of at the next hourly run.
        self.content_arrived = False

    def content_added(self):
        self.content_arrived = True

    def trim_once(self):
        """Only the content limit, between full runs."""
        with Session(self.engine) as session:
            if session.get(Administrator, 1) is None:
                return {"status": "uninitialized"}
            limit = session.get(RetentionPolicy, 1).max_posts
            # Nothing beyond the limit is the usual case: stay read-only.
            if limit is None or not session.execute(excess_batch(limit, 1)).first():
                return {"status": "within_limit"}
        counts = {"posts": 0, "evaluations": 0, "hits": 0}
        with write_session(self.engine) as session:
            limit = session.get(RetentionPolicy, 1).max_posts
            if limit is not None:
                posts = session.execute(excess_batch(limit, self.batch_size)).all()
                remove_posts(session, posts, counts)
        full = counts["posts"] == self.batch_size
        if not full:
            reclaim(self.engine)
        return {"status": "trimmed", "counts": counts, "more": full}

    def run_once(self, *, at=None):
        at = self.clock() if at is None else at
        # Most wakes are read-only; configuration and queue writers need no
        # write-lock competition while cleanup is waiting for its next run.
        with Session(self.engine) as session:
            if session.get(Administrator, 1) is None:
                return {"status": "uninitialized"}
            if at < session.get(RetentionPolicy, 1).next_run_at:
                return {"status": "backoff"}
        with write_session(self.engine) as session:
            if session.get(Administrator, 1) is None:
                return {"status": "uninitialized"}
            policy = session.get(RetentionPolicy, 1)
            if at < policy.next_run_at:
                return {"status": "backoff"}
            cutoff = at - policy.days * 86400
            counts = dict.fromkeys(
                (
                    "deliveries",
                    "attempts",
                    "contributions",
                    "posts",
                    "evaluations",
                    "hits",
                    "tests",
                    "manual",
                    "source_runs",
                    "system_events",
                    "alerts",
                ),
                0,
            )
            full = False

            # Retain queues, leases, recent results and unfinished attempts.
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
            keys = list(
                session.scalars(
                    select(Outbox.id)
                    .where(
                        Outbox.status.in_(TERMINAL),
                        Outbox.created_at < cutoff,
                        Outbox.completed_at < cutoff,
                        ~recent_attempt,
                    )
                    .order_by(Outbox.completed_at, Outbox.id)
                    .limit(self.batch_size)
                )
            )
            if keys:
                counts["attempts"] = remove(
                    session, DeliveryAttempt, DeliveryAttempt.event_id.in_(keys)
                )
                counts["contributions"] = remove(
                    session, OutboxContribution, OutboxContribution.event_id.in_(keys)
                )
                counts["deliveries"] = remove(session, Outbox, Outbox.id.in_(keys))
            full |= len(keys) == self.batch_size

            # Remove the readable post and its decisions together. Retain all
            # of them while ANY delivery for that post is still retained.
            posts = session.execute(
                select(Post.website_id, Post.external_post_id)
                .where(
                    Post.first_seen_at < cutoff,
                    no_delivery(Post),
                )
                .order_by(Post.first_seen_at, Post.website_id, Post.external_post_id)
                .limit(self.batch_size)
            ).all()
            remove_posts(session, posts, counts)
            full |= len(posts) == self.batch_size

            # The content limit: oldest unmatched content beyond the newest N goes first.
            if policy.max_posts is not None:
                posts = session.execute(excess_batch(policy.max_posts, self.batch_size)).all()
                remove_posts(session, posts, counts)
                full |= len(posts) == self.batch_size

            # Also handle ordinary decisions whose readable post was pruned by
            # an earlier version/maintenance operation.
            evals = session.execute(
                select(
                    TaskEvaluation.task_id,
                    TaskEvaluation.task_version,
                    TaskEvaluation.website_id,
                    TaskEvaluation.external_post_id,
                )
                .where(
                    TaskEvaluation.evaluated_at < cutoff,
                    no_post(TaskEvaluation),
                    no_delivery(TaskEvaluation),
                )
                .order_by(TaskEvaluation.evaluated_at)
                .limit(self.batch_size)
            ).all()
            if evals:
                counts["evaluations"] += remove(
                    session,
                    TaskEvaluation,
                    tuple_(
                        TaskEvaluation.task_id,
                        TaskEvaluation.task_version,
                        TaskEvaluation.website_id,
                        TaskEvaluation.external_post_id,
                    ).in_(evals),
                )
            full |= len(evals) == self.batch_size
            hits = list(
                session.scalars(
                    select(RuleHit.id)
                    .where(
                        RuleHit.matched_at < cutoff,
                        no_post(RuleHit),
                        no_delivery(RuleHit),
                        ~exists(
                            select(OutboxContribution.event_id).where(
                                OutboxContribution.hit_id == RuleHit.id
                            )
                        ),
                    )
                    .order_by(RuleHit.matched_at, RuleHit.id)
                    .limit(self.batch_size)
                )
            )
            counts["hits"] += remove(session, RuleHit, RuleHit.id.in_(hits)) if hits else 0
            full |= len(hits) == self.batch_size

            for model, field, label in (
                (TargetTestAttempt, TargetTestAttempt.finished_at, "tests"),
                (ManualDelivery, ManualDelivery.finished_at, "manual"),
                (SourceRun, SourceRun.at, "source_runs"),
            ):
                keys = list(
                    session.scalars(
                        select(model.id)
                        .where(field < cutoff)
                        .order_by(field, model.id)
                        .limit(self.batch_size)
                    )
                )
                counts[label] = remove(session, model, model.id.in_(keys)) if keys else 0
                full |= len(keys) == self.batch_size

            keys = list(
                session.scalars(
                    select(SystemEvent.id)
                    .where(
                        SystemEvent.at < cutoff,
                        ~exists(
                            select(AlertDelivery.id).where(
                                AlertDelivery.event_id == SystemEvent.id,
                                or_(
                                    AlertDelivery.result == "pending",
                                    AlertDelivery.finished_at.is_(None),
                                    AlertDelivery.finished_at >= cutoff,
                                ),
                            )
                        ),
                    )
                    .order_by(SystemEvent.at, SystemEvent.id)
                    .limit(self.batch_size)
                )
            )
            if keys:
                counts["alerts"] = remove(session, AlertDelivery, AlertDelivery.event_id.in_(keys))
                counts["system_events"] = remove(session, SystemEvent, SystemEvent.id.in_(keys))
            full |= len(keys) == self.batch_size

            policy.next_run_at = at if full else at + self.interval
        if not full:
            reclaim(self.engine)
        return {"status": "cleaned", "counts": counts, "more": full}

    async def run(self, stop: asyncio.Event):
        while not stop.is_set():
            # Content stored after this point sets the flag again for the next wake.
            arrived, self.content_arrived = self.content_arrived, False
            result = await database_call(self.run_once)
            # A full run already applied the limit; otherwise only the limit is checked.
            if arrived and result.get("status") == "backoff":
                result = await database_call(self.trim_once)
                if result.get("more"):
                    self.content_arrived = True
            if self.disk is not None:
                await database_call(self.disk.run_once)
            self.last_loop_at = self.clock()
            pause = BACKLOG_PAUSE if result.get("more") else self.tick
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=pause)
