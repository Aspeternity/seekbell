"""Bounded, transactional history pruning. Identity and receipt ledgers are never deleted."""

import asyncio
import time
from contextlib import suppress

from sqlalchemy import delete, exists, or_, select, tuple_
from sqlalchemy.orm import Session

from seekbell.db.models import (
    Administrator,
    DeliveryAttempt,
    ManualDelivery,
    Outbox,
    OutboxContribution,
    Post,
    RetentionPolicy,
    RuleHit,
    SourceRun,
    TargetTestAttempt,
    TaskEvaluation,
)
from seekbell.db.transactions import database_call, write_session

TERMINAL = ("sent", "failed", "cancelled")


class PolicyConflict(ValueError):
    pass


def policy_view(policy):
    return {
        "days": policy.days,
        "revision": policy.revision,
        "last_run_at": policy.last_run_at,
        "next_run_at": policy.next_run_at,
        "last_counts": policy.last_counts,
    }


def get_policy(engine):
    with Session(engine) as session:
        return policy_view(session.get(RetentionPolicy, 1))


def update_policy(engine, days, revision):
    if type(days) is not int or not 1 <= days <= 365:
        raise ValueError("Invalid history retention")
    with write_session(engine) as session:
        policy = session.get(RetentionPolicy, 1)
        if policy.revision != revision:
            raise PolicyConflict("保留策略已在其他页面改变，请重新读取后保存。")
        if policy.days != days:
            policy.days = days
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


class HistoryRetention:
    def __init__(self, engine, *, clock=time.time, tick=1, batch_size=100, interval=3600):
        if not 1 <= batch_size <= 100 or interval <= 0 or tick <= 0:
            raise ValueError("Invalid cleanup limits")
        self.engine, self.clock, self.tick = engine, clock, tick
        self.batch_size, self.interval = batch_size, interval

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
            if posts:
                counts["evaluations"] += remove(
                    session,
                    TaskEvaluation,
                    tuple_(TaskEvaluation.website_id, TaskEvaluation.external_post_id).in_(posts),
                )
                counts["hits"] += remove(
                    session,
                    RuleHit,
                    tuple_(RuleHit.website_id, RuleHit.external_post_id).in_(posts),
                )
                counts["posts"] = remove(
                    session, Post, tuple_(Post.website_id, Post.external_post_id).in_(posts)
                )
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

            policy.last_run_at, policy.last_counts = at, counts
            policy.next_run_at = at + (self.tick if full else self.interval)
            return {"status": "cleaned", "counts": counts, "more": full}

    async def run(self, stop: asyncio.Event):
        while not stop.is_set():
            await database_call(self.run_once)
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.tick)
