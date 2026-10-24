"""Bounded read-only historical diagnosis and explicit current-rule trials."""

import json

from pydantic import ValidationError
from sqlalchemy import and_, func, select

from seekbell.db.models import Post, Task, TaskVersion
from seekbell.domain.posts import PostFields
from seekbell.domain.rules import Rule, evaluate
from seekbell.services.diagnosis import summarize
from seekbell.services.history import (
    MissingHistory,
    decisions,
    decode_post_key,
    read_session,
    result_snapshot,
)
from seekbell.sites.categories import NODESEEK_ALIASES
from seekbell.sites.labels import category_label


class PostDiagnosis:
    def __init__(self, engine):
        self.engine = engine
        self.decisions = decisions()

    def _rows(self, website, external):
        d = self.decisions.c
        return (
            select(
                d.task_id,
                d.task_version,
                d.status,
                d.result,
                d.at,
                TaskVersion.name,
                Task.deleted_at,
                TaskVersion.rule,
            )
            .select_from(self.decisions)
            .join(
                TaskVersion,
                and_(TaskVersion.task_id == d.task_id, TaskVersion.version == d.task_version),
            )
            .join(Task, Task.id == d.task_id)
            .where(d.website_id == website, d.external_post_id == external)
        )

    @staticmethod
    def _option(row):
        return {
            "key": json.dumps([row.task_id, row.task_version], separators=(",", ":")),
            "task_id": row.task_id,
            "version": row.task_version,
            "name": row.name,
            "deleted": row.deleted_at is not None,
            "status": row.status,
            "at": row.at,
        }

    def options(self, key, *, group="other", q="", page=1, page_size=20, preferred_task_id=""):
        website, external = decode_post_key(key)
        d = self.decisions.c
        with read_session(self.engine) as session:
            if session.get(Post, (website, external)) is None:
                raise MissingHistory("内容不存在或已清理。")
            base = self._rows(website, external)
            source = base.subquery()
            counts = dict(
                session.execute(
                    select(source.c.status, func.count()).group_by(source.c.status)
                ).all()
            )
            if group == "other":
                base = base.where(d.status != "match")
            elif group == "matched":
                base = base.where(d.status == "match")
            ordered = base.order_by(TaskVersion.name, d.task_id, d.task_version.desc())
            preferred = (
                session.execute(ordered.where(d.task_id == preferred_task_id).limit(1)).first()
                if preferred_task_id
                else None
            )
            if preferred is None:
                preferred = session.execute(ordered.limit(1)).first()
            filtered = base.where(TaskVersion.name.icontains(q, autoescape=True)) if q else base
            total = session.scalar(select(func.count()).select_from(filtered.subquery()))
            # Select only metadata for the picker, not rules or reason arrays.
            listing = filtered.with_only_columns(
                d.task_id, d.task_version, d.status, d.at, TaskVersion.name, Task.deleted_at
            ).order_by(TaskVersion.name, d.task_id, d.task_version.desc())
            rows = session.execute(listing.offset((page - 1) * page_size).limit(page_size)).all()
            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "counts": counts,
                "recorded_total": sum(counts.values()),
                "preferred": self._option(preferred) if preferred else None,
                "items": [self._option(row) for row in rows],
            }

    @staticmethod
    def _detail(row, post):
        result = result_snapshot(row.result, row.status)
        try:
            rule = Rule.model_validate(row.rule).model_dump(mode="json")
        except (ValidationError, TypeError):
            rule = None
        expected = rule["categories"] if rule else []
        legacy = bool(
            post.website_id == "nodeseek"
            and any(
                NODESEEK_ALIASES.get(value) == post.category and value != post.category
                for value in expected
            )
            and any(r["code"] == "category" and r["truth"] == "false" for r in result["reasons"])
        )
        explanation = summarize(result)
        if legacy and row.status == "no_match":
            explanation["headline"] = "历史版块保存值与来源标识不一致"
        return {
            **PostDiagnosis._option(row),
            "result": result,
            "rule": rule,
            "explanation": explanation,
            "category": {
                "actual": post.category,
                "label": category_label(post.website_id, post.category),
                "expected": [
                    {"value": value, "label": category_label(post.website_id, value)}
                    for value in expected
                ],
                "legacy_mismatch": legacy,
            },
            "author": post.author,
        }

    def detail(self, key, task_id, version):
        website, external = decode_post_key(key)
        with read_session(self.engine) as session:
            post = session.get(Post, (website, external))
            if post is None:
                raise MissingHistory("内容不存在或已清理。")
            d = self.decisions.c
            row = session.execute(
                self._rows(website, external).where(d.task_id == task_id, d.task_version == version)
            ).first()
            if row is None:
                raise MissingHistory("没有该任务对这条帖子的历史判定。")
            return self._detail(row, post)

    def trial(self, key, task_id):
        website, external = decode_post_key(key)
        with read_session(self.engine) as session:
            post = session.get(Post, (website, external))
            task = session.get(Task, task_id)
            if post is None:
                raise MissingHistory("内容不存在或已清理。")
            if task is None or task.deleted_at is not None:
                raise MissingHistory("当前任务已删除或不存在，历史判定仍可查看。")
            version = session.get(TaskVersion, (task_id, task.current_version))
            info = {
                "task_id": task_id,
                "version": version.version,
                "name": version.name,
                "historical": False,
                "applicable": website in version.website_ids,
            }
            if not info["applicable"]:
                return {
                    **info,
                    "result": None,
                    "explanation": None,
                    "message": "当前任务未选择该网站。",
                }
            result = evaluate(
                Rule.model_validate(version.rule),
                PostFields(
                    title=post.title,
                    summary=post.summary,
                    author=post.author,
                    category=post.category,
                ),
            ).model_dump(mode="json")
            return {
                **info,
                "result": result,
                "explanation": summarize(result),
                "message": "按当前已保存规则试算，不改变当时判定，不发送通知。",
            }
