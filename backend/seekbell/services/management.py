"""Safe read projections and side-effect-free rule previews for authenticated management."""

import re
from pathlib import Path

from sqlalchemy import Engine, func, or_, select
from sqlalchemy.orm import Session

from seekbell.db.models import (
    NotificationTarget,
    Outbox,
    Post,
    TargetTestAttempt,
    Task,
    TaskVersion,
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
        for model in (Outbox, TargetTestAttempt):
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
