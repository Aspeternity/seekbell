"""Read-only, bounded views of stored history. Never re-evaluate or dispatch."""

import base64
import json
from contextlib import contextmanager
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, case, exists, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from seekbell.db.models import (
    DeliveredPost,
    DeliveryAttempt,
    ManualDelivery,
    NotificationTarget,
    Outbox,
    Post,
    RuleHit,
    TargetTestAttempt,
    Task,
    TaskEvaluation,
    TaskVersion,
    Website,
)
from seekbell.sites.labels import category_label
from seekbell.sites.nodeseek import NodeSeekAdapter


class MissingHistory(LookupError):
    pass


def post_key(website_id, external_post_id):
    return (
        base64.urlsafe_b64encode(
            json.dumps([website_id, external_post_id], separators=(",", ":")).encode()
        )
        .decode()
        .rstrip("=")
    )


def decode_post_key(key):
    try:
        values = json.loads(
            base64.b64decode(key + "=" * (-len(key) % 4), altchars=b"-_", validate=True)
        )
        if (
            not isinstance(values, list)
            or len(values) != 2
            or not all(isinstance(v, str) and v for v in values)
            or len(values[0]) > 80
            or len(values[1]) > 128
            or post_key(*values) != key
        ):
            raise ValueError
        return values
    except (ValueError, TypeError, UnicodeError):
        raise MissingHistory("内容不存在。") from None


@contextmanager
def read_session(engine):
    with Session(engine) as session:
        # SQLite's legacy driver does not BEGIN for SELECT. Pin count and page
        # to one WAL snapshot without acquiring the configuration write lock.
        session.connection().exec_driver_sql("BEGIN")
        yield session


def date_window(value: date | None, timezone: str):
    return date_range_window(value, value, timezone)


def date_range_window(start: date | None, end: date | None, timezone: str):
    try:
        zone = ZoneInfo(timezone)
    except (ValueError, ZoneInfoNotFoundError):
        raise ValueError("Unknown display timezone") from None
    if start is None and end is None:
        return None
    if start is None or end is None or start > end:
        raise ValueError("Invalid date range")
    return (
        datetime.combine(start, time.min, zone).astimezone(UTC).timestamp(),
        datetime.combine(end + timedelta(days=1), time.min, zone).astimezone(UTC).timestamp(),
    )


def bounded_date(statement, column, window):
    return statement if window is None else statement.where(column >= window[0], column < window[1])


def text(value, fallback=""):
    return value if isinstance(value, str) else fallback


def original_url(website_id, external_id, url):
    if website_id == "nodeseek" and NodeSeekAdapter.post_id(text(url)) == external_id:
        return NodeSeekAdapter.canonical_url(external_id)
    return None


def decisions():
    current = select(
        TaskEvaluation.task_id,
        TaskEvaluation.task_version,
        TaskEvaluation.website_id,
        TaskEvaluation.external_post_id,
        TaskEvaluation.status,
        TaskEvaluation.result,
        TaskEvaluation.evaluated_at.label("at"),
    )
    # M1-M3 matches are trustworthy even though old negative/unknown decisions
    # were not recorded. Include them only when the new ledger has no same row.
    legacy = select(
        RuleHit.task_id,
        RuleHit.task_version,
        RuleHit.website_id,
        RuleHit.external_post_id,
        literal("match").label("status"),
        RuleHit.reason.label("result"),
        RuleHit.matched_at.label("at"),
    ).where(
        ~exists(
            select(1).where(
                TaskEvaluation.task_id == RuleHit.task_id,
                TaskEvaluation.task_version == RuleHit.task_version,
                TaskEvaluation.website_id == RuleHit.website_id,
                TaskEvaluation.external_post_id == RuleHit.external_post_id,
            )
        )
    )
    return union_all(current, legacy).subquery("decisions")


def result_snapshot(result, status):
    allowed = {
        "all_of",
        "any_of",
        "exclude",
        "author_include",
        "author_exclude",
        "category",
        "missing_summary",
        "missing_author",
        "missing_category",
    }
    reasons = []
    for reason in result.get("reasons", []) if isinstance(result, dict) else []:
        if not isinstance(reason, dict):
            continue
        reasons.append(
            {
                "code": reason.get("code") if reason.get("code") in allowed else "unrecorded",
                "truth": reason.get("truth")
                if reason.get("truth") in ("true", "false", "unknown")
                else "unknown",
                "term": text(reason.get("term")) or None,
                "group": reason.get("group") if isinstance(reason.get("group"), int) else None,
            }
        )
    return {"status": status, "reasons": reasons}


def error_code(value):
    # Stored notifier errors are codes, never remote response text/URLs. Keep the
    # same boundary for imported/legacy rows; unknown values do not get echoed.
    import re

    return (
        value if isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,79}", value) else None
    )


class History:
    def __init__(self, engine):
        self.engine = engine
        self.decisions = decisions()

    def post_status(self, task_id=""):
        d = self.decisions.c
        predicates = [d.website_id == Post.website_id, d.external_post_id == Post.external_post_id]
        if task_id:
            predicates.append(d.task_id == task_id)

        def found(status):
            return exists(
                select(1).select_from(self.decisions).where(*predicates, d.status == status)
            ).correlate(Post)

        return case(
            (found("match"), "match"),
            (found("insufficient_data"), "insufficient_data"),
            (found("no_match"), "no_match"),
            (Post.baseline.is_not(None), "not_evaluated"),
            else_="unrecorded",
        )

    def post_item(self, session, post, status, *, detail=False):
        d = self.decisions.c
        hits = session.execute(
            select(d.task_id, d.task_version, TaskVersion.name, Task.deleted_at)
            .select_from(self.decisions)
            .join(
                TaskVersion,
                and_(TaskVersion.task_id == d.task_id, TaskVersion.version == d.task_version),
            )
            .join(Task, Task.id == d.task_id)
            .where(
                d.website_id == post.website_id,
                d.external_post_id == post.external_post_id,
                d.status == "match",
            )
            .order_by(d.task_id, d.task_version)
            .limit(3)
        ).all()
        return {
            "id": post_key(post.website_id, post.external_post_id),
            "website_id": post.website_id,
            "external_post_id": post.external_post_id,
            "title": post.title,
            "summary": post.summary if detail or post.summary is None else post.summary[:400],
            "author": post.author,
            "category": post.category,
            "category_label": category_label(post.website_id, post.category),
            "first_seen_at": post.first_seen_at,
            "published_at": post.published_at,
            "original_url": original_url(post.website_id, post.external_post_id, post.url),
            "status": status,
            "baseline": post.baseline,
            "hits": [
                {
                    "task_id": h.task_id,
                    "version": h.task_version,
                    "name": h.name,
                    "deleted": h.deleted_at is not None,
                }
                for h in hits
            ],
        }

    def list_posts(
        self,
        *,
        page=1,
        page_size=20,
        q="",
        status="all",
        task_id="",
        website_id="",
        category="",
        window=None,
    ):
        d = self.decisions.c
        matching_status = self.post_status(task_id)
        statement = select(Post, matching_status.label("matching_status"))
        if q:
            statement = statement.where(
                or_(
                    Post.title.icontains(q, autoescape=True),
                    Post.summary.icontains(q, autoescape=True),
                    Post.author.icontains(q, autoescape=True),
                )
            )
        if task_id:
            statement = statement.where(
                exists(
                    select(1)
                    .select_from(self.decisions)
                    .where(
                        d.website_id == Post.website_id,
                        d.external_post_id == Post.external_post_id,
                        d.task_id == task_id,
                    )
                ).correlate(Post)
            )
        if website_id:
            statement = statement.where(Post.website_id == website_id)
        if category:
            statement = statement.where(Post.category == category)
        if status != "all":
            statement = statement.where(matching_status == status)
        statement = bounded_date(statement, Post.first_seen_at, window)
        with read_session(self.engine) as session:
            filtered = statement.subquery()
            summary = dict(
                session.execute(
                    select(filtered.c.matching_status, func.count()).group_by(
                        filtered.c.matching_status
                    )
                ).all()
            )
            rows = session.execute(
                statement.order_by(
                    Post.first_seen_at.desc(),
                    Post.published_at.desc().nulls_last(),
                    Post.website_id,
                    Post.external_post_id,
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            return {
                "total": sum(summary.values()),
                "page": page,
                "page_size": page_size,
                "summary": summary,
                "items": [self.post_item(session, post, result) for post, result in rows],
            }

    def get_post(self, key):
        website, external = decode_post_key(key)
        with read_session(self.engine) as session:
            row = session.execute(
                select(Post, self.post_status()).where(
                    Post.website_id == website, Post.external_post_id == external
                )
            ).one_or_none()
            if row is None:
                raise MissingHistory("内容不存在或已清理。")
            return self.post_item(session, *row, detail=True)

    def evaluations(self, key, *, page=1, page_size=20, group="all"):
        if group not in {"all", "matched", "primary", "other"}:
            raise ValueError("Unknown evaluation group")
        website, external = decode_post_key(key)
        d = self.decisions.c
        with read_session(self.engine) as session:
            if session.get(Post, (website, external)) is None:
                raise MissingHistory("内容不存在或已清理。")
            statement = (
                select(
                    d.task_id,
                    d.task_version,
                    d.status,
                    d.result,
                    d.at,
                    TaskVersion.name,
                    Task.deleted_at,
                )
                .select_from(self.decisions)
                .join(
                    TaskVersion,
                    and_(TaskVersion.task_id == d.task_id, TaskVersion.version == d.task_version),
                )
                .join(Task, Task.id == d.task_id)
                .where(d.website_id == website, d.external_post_id == external)
            )
            all_rows = statement.subquery()
            counts = dict(
                session.execute(
                    select(all_rows.c.status, func.count()).group_by(all_rows.c.status)
                ).all()
            )
            matched_total = counts.get("match", 0)
            other_total = sum(counts.values()) - matched_total
            total = matched_total + other_total
            if group == "matched" or (group == "primary" and matched_total):
                statement = statement.where(d.status == "match")
                total = matched_total
            elif group == "other":
                statement = statement.where(d.status != "match")
                total = other_total
            rows = session.execute(
                statement.order_by(d.task_id, d.task_version)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            return {
                "matched_total": matched_total,
                "other_total": other_total,
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": [
                    {
                        "task_id": r.task_id,
                        "version": r.task_version,
                        "name": r.name,
                        "deleted": r.deleted_at is not None,
                        "at": r.at,
                        "result": result_snapshot(r.result, r.status),
                    }
                    for r in rows
                ],
            }

    def delivery_item(self, session, event):
        snapshot = event.target_snapshot
        payload_post = event.payload.get("post", {})
        post = session.get(Post, (event.website_id, event.external_post_id))
        return {
            "id": event.id,
            "post_id": post_key(event.website_id, event.external_post_id) if post else None,
            "website_id": event.website_id,
            "title": text(payload_post.get("title"), "内容快照缺失"),
            "target_id": event.target_id,
            "target_name": text(snapshot.get("name"), "历史目标名称未记录"),
            "kind": text(snapshot.get("kind"), "unknown"),
            "target_revision": snapshot.get("revision"),
            "status": event.status,
            "uncertain": event.uncertain,
            "attempt_count": event.attempt_count,
            "created_at": event.created_at,
            "available_at": event.available_at,
            "last_result": event.last_result,
            "error_code": error_code(event.last_error_code),
            "cancel_requested": event.cancel_requested,
        }

    def list_deliveries(
        self,
        *,
        page=1,
        page_size=20,
        q="",
        status="all",
        target_id="",
        website_id="",
        post_id="",
        uncertain=None,
        window=None,
    ):
        statement = select(Outbox)
        if q:
            statement = statement.where(
                or_(
                    Outbox.payload["post"]["title"].as_string().icontains(q, autoescape=True),
                    Outbox.target_snapshot["name"].as_string().icontains(q, autoescape=True),
                )
            )
        if status != "all":
            statement = statement.where(Outbox.status == status)
        if target_id:
            statement = statement.where(Outbox.target_id == target_id)
        if website_id:
            statement = statement.where(Outbox.website_id == website_id)
        if post_id:
            website, external = decode_post_key(post_id)
            statement = statement.where(
                Outbox.website_id == website, Outbox.external_post_id == external
            )
        if uncertain is not None:
            statement = statement.where(Outbox.uncertain == uncertain)
        statement = bounded_date(statement, Outbox.created_at, window)
        with read_session(self.engine) as session:
            total = session.scalar(select(func.count()).select_from(statement.subquery()))
            rows = session.scalars(
                statement.order_by(Outbox.created_at.desc(), Outbox.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": [self.delivery_item(session, event) for event in rows],
            }

    def get_delivery(self, key, *, attempt_page=1, task_page=1, page_size=20):
        with read_session(self.engine) as session:
            event = session.get(Outbox, key)
            if event is None:
                raise MissingHistory("投递记录不存在或已清理。")
            result = self.delivery_item(session, event)
            raw_post = event.payload.get("post", {})
            result["post"] = {
                field: raw_post.get(field)
                for field in (
                    "title",
                    "summary",
                    "author",
                    "category",
                    "published_at",
                    "first_seen_at",
                )
            }
            result["post"]["original_url"] = original_url(
                event.website_id, event.external_post_id, raw_post.get("url")
            )
            tasks = event.payload.get("matched_tasks", [])
            offset = (task_page - 1) * page_size
            result["tasks"] = {
                "total": len(tasks),
                "page": task_page,
                "page_size": page_size,
                "items": [],
            }
            for item in tasks[offset : offset + page_size]:
                task = session.get(Task, item.get("id"))
                result["tasks"]["items"].append(
                    {
                        "id": item.get("id"),
                        "name": text(item.get("name"), "历史任务"),
                        "version": item.get("version"),
                        "deleted": task is None or task.deleted_at is not None,
                    }
                )
            attempts = select(DeliveryAttempt).where(DeliveryAttempt.event_id == key)
            count = session.scalar(select(func.count()).select_from(attempts.subquery()))
            rows = session.scalars(
                attempts.order_by(DeliveryAttempt.sequence)
                .offset((attempt_page - 1) * page_size)
                .limit(page_size)
            ).all()
            result["attempts"] = {
                "total": count,
                "page": attempt_page,
                "page_size": page_size,
                "items": [
                    {
                        "sequence": a.sequence,
                        "started_at": a.started_at,
                        "finished_at": a.finished_at,
                        "result": a.result,
                        "error_code": error_code(a.error_code),
                        "late_result": a.late_result,
                        "late_finished_at": a.late_finished_at,
                    }
                    for a in rows
                ],
            }
            receipt = session.get(
                DeliveredPost, (event.website_id, event.external_post_id, event.target_id)
            )
            result["receipt_at"] = (
                receipt.delivered_at if receipt and receipt.event_id == key else None
            )
            return result

    def list_tests(self, **filters):
        return self._list_explicit(TargetTestAttempt, **filters)

    def list_manual(self, **filters):
        return self._list_explicit(ManualDelivery, **filters)

    def _list_explicit(
        self,
        model,
        *,
        page=1,
        page_size=20,
        q="",
        status="all",
        target_id="",
        window=None,
        source_event_id="",
    ):
        statement = select(model)
        if q:
            statement = statement.where(
                model.target_snapshot["name"].as_string().icontains(q, autoescape=True)
            )
        if status != "all":
            statement = statement.where(model.result == status)
        if target_id:
            statement = statement.where(model.target_id == target_id)
        if source_event_id and model is ManualDelivery:
            statement = statement.where(model.source_event_id == source_event_id)
        statement = bounded_date(statement, model.started_at, window)
        with read_session(self.engine) as session:
            total = session.scalar(select(func.count()).select_from(statement.subquery()))
            rows = session.scalars(
                statement.order_by(model.started_at.desc(), model.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": [
                    self.manual_item(row) if model is ManualDelivery else self.test_item(row)
                    for row in rows
                ],
            }

    @staticmethod
    def test_item(row):
        return {
            "id": row.id,
            "target_id": row.target_id,
            "target_name": text(row.target_snapshot.get("name"), "历史目标"),
            "kind": text(row.target_snapshot.get("kind"), "unknown"),
            "result": row.result,
            "error_code": error_code(row.error_code),
            "started_at": row.started_at,
            "finished_at": row.finished_at,
        }

    def get_test(self, key):
        with read_session(self.engine) as session:
            row = session.get(TargetTestAttempt, key)
            if row is None:
                raise MissingHistory("目标测试记录不存在或已清理。")
            return self.test_item(row)

    def counts(self):
        with read_session(self.engine) as session:
            return {
                name: session.scalar(select(func.count()).select_from(model))
                for name, model in (
                    ("deliveries", Outbox),
                    ("manual", ManualDelivery),
                    ("tests", TargetTestAttempt),
                )
            }

    def dates(self, scope, *, timezone="Asia/Shanghai", before=None, limit=100):
        # Seek one stored timestamp per local day, not every post or only the current page.
        # Local midnight boundaries preserve IANA/DST semantics used by the list filters.
        zone = ZoneInfo(timezone)
        column = {
            "posts": Post.first_seen_at,
            "deliveries": Outbox.created_at,
            "manual": ManualDelivery.started_at,
            "tests": TargetTestAttempt.started_at,
        }[scope]
        boundary = date_window(before, timezone)[0] if before else None
        values = []
        with read_session(self.engine) as session:
            for _ in range(limit + 1):
                statement = select(column)
                if boundary is not None:
                    statement = statement.where(column < boundary)
                latest = session.scalar(statement.order_by(column.desc()).limit(1))
                if latest is None:
                    break
                local_day = datetime.fromtimestamp(latest, zone).date()
                values.append(local_day.isoformat())
                boundary = date_window(local_day, timezone)[0]
        return {
            "items": values[:limit],
            "next_before": values[limit - 1] if len(values) > limit else None,
        }

    def options(self):
        with read_session(self.engine) as session:
            task_rows = session.execute(
                select(Task, TaskVersion)
                .join(
                    TaskVersion,
                    and_(
                        TaskVersion.task_id == Task.id, TaskVersion.version == Task.current_version
                    ),
                )
                .where(Task.deleted_at.is_(None))
                .order_by(Task.created_at.desc(), Task.id)
                .limit(201)
            ).all()
            category_rows = session.execute(
                select(Post.website_id, Post.category)
                .where(Post.category.is_not(None))
                .distinct()
                .order_by(Post.website_id, Post.category)
                .limit(201)
            ).all()
            categories = sorted({value for _, value in category_rows[:200]})
            targets = session.execute(
                select(NotificationTarget.id, NotificationTarget.name)
                .order_by(NotificationTarget.name, NotificationTarget.id)
                .limit(201)
            ).all()
            return {
                "tasks": [
                    {"id": task.id, "name": version.name, "deleted": task.deleted_at is not None}
                    for task, version in task_rows[:200]
                ],
                "categories": categories,
                "category_options": [
                    {
                        "website_id": website,
                        "value": value,
                        "label": category_label(website, value),
                    }
                    for website, value in category_rows[:200]
                ],
                "targets": [{"id": key, "name": name} for key, name in targets[:200]],
                "websites": [
                    {"id": key, "name": name}
                    for key, name in session.execute(select(Website.id, Website.name).limit(100))
                ],
                "truncated": len(task_rows) > 200 or len(category_rows) > 200 or len(targets) > 200,
            }

    @staticmethod
    def manual_item(row):
        return {
            **History.test_item(row),
            "source_event_id": row.source_event_id,
            "title": text(row.payload.get("post", {}).get("title"), "历史消息"),
            "target_revision": row.target_snapshot.get("revision"),
        }

    def get_manual(self, key, *, task_page=1, page_size=20):
        with read_session(self.engine) as session:
            row = session.get(ManualDelivery, key)
            if row is None:
                raise MissingHistory("手动重发记录不存在或已清理。")
            result = self.manual_item(row)
            result["source_exists"] = session.get(Outbox, row.source_event_id) is not None
            raw_post = row.payload.get("post", {})
            result["post"] = {
                field: raw_post.get(field)
                for field in (
                    "title",
                    "summary",
                    "author",
                    "category",
                    "published_at",
                    "first_seen_at",
                )
            }
            website_id = raw_post.get("website_id")
            external_id = raw_post.get("external_post_id")
            result["post"]["original_url"] = original_url(
                website_id, external_id, raw_post.get("url")
            )
            result["post_id"] = (
                post_key(website_id, external_id)
                if website_id and external_id and session.get(Post, (website_id, external_id))
                else None
            )
            tasks = row.payload.get("matched_tasks", [])
            offset = (task_page - 1) * page_size
            result["tasks"] = {
                "total": len(tasks),
                "page": task_page,
                "page_size": page_size,
                "items": [
                    {"name": text(item.get("name"), "历史任务"), "version": item.get("version")}
                    for item in tasks[offset : offset + page_size]
                ],
            }
            return result
