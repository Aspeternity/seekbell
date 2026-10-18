"""Safe read projections and side-effect-free rule previews for authenticated management."""

import re
from pathlib import Path

from sqlalchemy import Engine, func, or_, select
from sqlalchemy.orm import Session

from seekbell.db.models import (
    ManualDeliveryAttempt,
    NotificationTarget,
    Outbox,
    Post,
    RuleHit,
    Source,
    SourceState,
    TargetTestAttempt,
    Task,
    TaskVersion,
    Website,
)
from seekbell.domain.posts import PostFields
from seekbell.domain.rules import Rule, evaluate, explain
from seekbell.notifiers.configs import validate_config
from seekbell.notifiers.credentials import CredentialError, CredentialVault
from seekbell.services.configuration import Configuration
from seekbell.sites.nodeseek import NodeSeekAdapter


def application_configuration(engine: Engine, data_dir: Path) -> Configuration:
    path = data_dir / "credentials.key"
    with Session(engine) as session:
        encrypted = session.scalar(
            select(NotificationTarget.id)
            .where(
                or_(
                    NotificationTarget.config_ciphertext.is_not(None),
                    NotificationTarget.kind != "mock",
                )
            )
            .limit(1)
        )
        for model in (Outbox, TargetTestAttempt, ManualDeliveryAttempt):
            encrypted = encrypted or session.scalar(
                select(model.id)
                .where(model.target_snapshot["config_ciphertext"].as_string().is_not(None))
                .limit(1)
            )
        if not path.exists() and not path.is_symlink() and encrypted:
            raise CredentialError("Credential key unavailable; restore the original key")
        vault = CredentialVault.open(data_dir, create=not path.exists() and not path.is_symlink())
        for target in session.scalars(
            select(NotificationTarget).where(NotificationTarget.kind != "mock")
        ):
            values = vault.unseal(target.id, target.kind, target.config_ciphertext)
            validate_config(target.kind, values)
    return Configuration(engine, vault)


def task_view(task: Task, version: TaskVersion) -> dict:
    rule = Rule.model_validate(version.rule)
    return {
        "id": task.id,
        "website_id": task.website_id,
        "enabled": task.enabled,
        "version": version.version,
        "name": version.name,
        "rule": rule.model_dump(mode="json"),
        "target_ids": version.target_ids,
        "explanation": explain(rule),
    }


class Management:
    def __init__(self, engine: Engine):
        self.engine = engine

    def tasks(self) -> list[dict]:
        with Session(self.engine) as session:
            return [
                task_view(task, version)
                for task, version in session.execute(
                    select(Task, TaskVersion)
                    .join(
                        TaskVersion,
                        (TaskVersion.task_id == Task.id)
                        & (TaskVersion.version == Task.current_version),
                    )
                    .where(Task.deleted_at.is_(None))
                    .order_by(Task.created_at.desc(), Task.id)
                )
            ]

    def task(self, key: str) -> dict | None:
        with Session(self.engine) as session:
            task = session.get(Task, key)
            if task is None or task.deleted_at is not None:
                return None
            return task_view(task, session.get(TaskVersion, (key, task.current_version)))

    def history(self, rule: Rule, limit: int) -> dict:
        with Session(self.engine) as session:
            posts = session.scalars(
                select(Post)
                .where(Post.website_id == "nodeseek")
                .order_by(Post.first_seen_at.desc(), Post.external_post_id)
                .limit(limit)
            ).all()
            total = session.scalar(
                select(func.count()).select_from(Post).where(Post.website_id == "nodeseek")
            )
            items = []
            for post in posts:
                result = evaluate(
                    rule,
                    PostFields(
                        title=post.title,
                        summary=post.summary,
                        author=post.author,
                        category=post.category,
                    ),
                )
                items.append(
                    {
                        "external_post_id": post.external_post_id,
                        "title": post.title,
                        "first_seen_at": post.first_seen_at,
                        "url": NodeSeekAdapter.canonical_url(post.external_post_id)
                        if re.fullmatch(r"[0-9]{1,20}", post.external_post_id)
                        else None,
                        "result": result.model_dump(mode="json"),
                    }
                )
            return {
                "items": items,
                "sample_count": len(items),
                "total": total,
                "oldest_at": min((p.first_seen_at for p in posts), default=None),
                "newest_at": max((p.first_seen_at for p in posts), default=None),
                "explanation": explain(rule),
            }

    def site(self) -> dict:
        with Session(self.engine) as session:
            website = session.get(Website, "nodeseek")
            source = session.get(Source, "nodeseek-rss")
            state = session.get(SourceState, source.id)
            return {
                "website_id": website.id,
                "name": website.name,
                "enabled": website.enabled and source.enabled,
                "interval_seconds": source.interval_seconds,
                "revision": source.revision,
                "url": NodeSeekAdapter.rss_url,
                "configuration_valid": source.url == NodeSeekAdapter.rss_url,
                "capabilities": sorted(NodeSeekAdapter.capabilities),
                "initialized": state.initialized,
                "needs_baseline": state.needs_baseline,
                "last_attempt_at": state.last_attempt_at,
                "last_success_at": state.last_success_at,
                "last_error_code": state.last_error_code,
                "failures": state.failures,
                "next_attempt_at": state.next_attempt_at,
                "window_count": state.window_count,
                "possible_gap": state.possible_gap,
                "last_gap_at": state.last_gap_at,
            }

    def overview(self) -> dict:
        with Session(self.engine) as session:
            tasks = select(func.count()).select_from(Task).where(Task.deleted_at.is_(None))
            deliveries = dict(
                session.execute(select(Outbox.status, func.count()).group_by(Outbox.status)).all()
            )
            return {
                "tasks": session.scalar(tasks),
                "enabled_tasks": session.scalar(tasks.where(Task.enabled.is_(True))),
                "targets": session.scalar(select(func.count()).select_from(NotificationTarget)),
                "posts": session.scalar(select(func.count()).select_from(Post)),
                "hits": session.scalar(select(func.count()).select_from(RuleHit)),
                "deliveries": {
                    key: deliveries.get(key, 0)
                    for key in ("pending", "retry", "leased", "sent", "failed", "cancelled")
                },
                "uncertain": session.scalar(
                    select(func.count()).select_from(Outbox).where(Outbox.uncertain.is_(True))
                ),
            }

    def content_options(self) -> list[dict]:
        with Session(self.engine) as session:
            return [
                {"id": task.id, "name": version.name, "deleted": task.deleted_at is not None}
                for task, version in session.execute(
                    select(Task, TaskVersion)
                    .join(
                        TaskVersion,
                        (TaskVersion.task_id == Task.id)
                        & (TaskVersion.version == Task.current_version),
                    )
                    .order_by(Task.created_at.desc(), Task.id)
                )
            ]

    def content(
        self,
        *,
        offset: int,
        limit: int,
        query: str,
        author: str,
        category: str,
        task_id: str | None,
        matched_only: bool,
    ) -> dict:
        statement = select(Post).where(Post.website_id == "nodeseek")
        if query:
            statement = statement.where(Post.title.contains(query, autoescape=True))
        if author:
            statement = statement.where(Post.author == author)
        if category:
            statement = statement.where(Post.category == category)
        matching_hit = select(RuleHit.id).where(
            RuleHit.website_id == Post.website_id,
            RuleHit.external_post_id == Post.external_post_id,
        )
        if task_id:
            matching_hit = matching_hit.where(RuleHit.task_id == task_id)
        if matched_only or task_id:
            statement = statement.where(matching_hit.exists())
        with Session(self.engine) as session:
            total = session.scalar(select(func.count()).select_from(statement.subquery()))
            posts = session.scalars(
                statement.order_by(Post.first_seen_at.desc(), Post.external_post_id)
                .offset(offset)
                .limit(limit)
            ).all()
            ids = [post.external_post_id for post in posts]
            hits: dict[str, list] = {key: [] for key in ids}
            if ids:
                for hit, version, task in session.execute(
                    select(RuleHit, TaskVersion, Task)
                    .join(
                        TaskVersion,
                        (TaskVersion.task_id == RuleHit.task_id)
                        & (TaskVersion.version == RuleHit.task_version),
                    )
                    .join(Task, Task.id == RuleHit.task_id)
                    .where(RuleHit.website_id == "nodeseek", RuleHit.external_post_id.in_(ids))
                    .order_by(RuleHit.matched_at, RuleHit.task_id, RuleHit.task_version)
                ):
                    hits[hit.external_post_id].append(
                        {
                            "task_id": hit.task_id,
                            "version": hit.task_version,
                            "name": version.name,
                            "deleted": task.deleted_at is not None,
                            "matched_at": hit.matched_at,
                            "reason": hit.reason,
                        }
                    )
            items = []
            for post in posts:
                items.append(
                    {
                        "external_post_id": post.external_post_id,
                        "title": post.title[:8192],
                        "summary": post.summary[:65536] if post.summary is not None else None,
                        "author": post.author[:500] if post.author is not None else None,
                        "category": post.category[:500] if post.category is not None else None,
                        "display_truncated": len(post.title) > 8192
                        or len(post.summary or "") > 65536
                        or len(post.author or "") > 500
                        or len(post.category or "") > 500,
                        "published_at": post.published_at,
                        "first_seen_at": post.first_seen_at,
                        "url": NodeSeekAdapter.canonical_url(post.external_post_id)
                        if re.fullmatch(r"[1-9][0-9]{0,19}", post.external_post_id)
                        else None,
                        "hits": hits[post.external_post_id],
                    }
                )
            return {"items": items, "total": total, "offset": offset, "limit": limit}
