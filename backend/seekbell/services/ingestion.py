import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from seekbell.db.models import (
    NotificationTarget,
    Outbox,
    OutboxContribution,
    Post,
    RuleHit,
    SeenPost,
    Source,
    SourceItem,
    SourceRun,
    SourceState,
    Task,
    TaskVersion,
    Website,
)
from seekbell.db.transactions import write_session
from seekbell.domain.delivery import SourcePolicy
from seekbell.domain.posts import Diagnostic, PostBatch, PostFields
from seekbell.domain.rules import Rule, evaluate
from seekbell.services.configuration import identifier, target_snapshot


@dataclass(frozen=True)
class IngestReport:
    status: str
    baseline: bool = False
    new_posts: int = 0
    hits: int = 0
    queued: int = 0
    insufficient: int = 0
    possible_gap: bool = False
    diagnostics: tuple[Diagnostic, ...] = ()


class Ingestion:
    def __init__(self, engine: Engine, *, source_policy: SourcePolicy | None = None):
        self.engine = engine
        self.source_policy = source_policy or SourcePolicy()

    def record_failure(
        self,
        source_id: str,
        code: str,
        *,
        at: float,
        retry_after: float | None = None,
        jitter: float = 0,
    ) -> float:
        if re.fullmatch(r"[a-z0-9_]{1,80}", code) is None:
            code = "source_error"
        with write_session(self.engine) as session:
            source = session.get(Source, source_id)
            state = session.get(SourceState, source_id)
            if source is None or state is None:
                raise ValueError("Unknown source")
            state.failures += 1
            state.last_attempt_at = at
            state.last_error_code = code
            state.next_attempt_at = at + max(
                source.interval_seconds,
                self.source_policy.retry_delay(state.failures, retry_after) + max(0, jitter),
            )
            session.add(SourceRun(source_id=source_id, at=at, status="failure", code=code))
            return state.next_attempt_at

    def ingest(
        self,
        source_id: str,
        batch: PostBatch,
        *,
        at: float,
        expected_source_revision: int | None = None,
    ) -> IngestReport:
        with write_session(self.engine) as session:
            source = session.get(Source, source_id)
            state = session.get(SourceState, source_id)
            if source is None or state is None:
                raise ValueError("Unknown source")
            if expected_source_revision is not None and source.revision != expected_source_revision:
                return IngestReport("configuration_changed")
            website = session.get(Website, source.website_id)
            if not source.enabled or not website.enabled:
                return IngestReport("paused")
            if any(post.website_id != source.website_id for post in batch.posts):
                raise ValueError("Normalized website does not match source")

            baseline = not state.initialized or state.needs_baseline
            window = list(dict.fromkeys(post.external_post_id for post in batch.posts))
            gap = bool(
                not baseline
                and state.previous_window
                and window
                and not set(window).intersection(state.previous_window)
            )
            if gap:
                state.possible_gap = True
                state.last_gap_at = at
            diagnostics = list(batch.diagnostics)
            versions = session.execute(
                select(Task, TaskVersion)
                .join(
                    TaskVersion,
                    (TaskVersion.task_id == Task.id)
                    & (TaskVersion.version == Task.current_version),
                )
                .where(
                    Task.website_id == source.website_id,
                    Task.enabled.is_(True),
                    Task.deleted_at.is_(None),
                )
                .order_by(Task.id)
            ).all()
            new_posts = hit_count = queued = insufficient = 0
            encountered = set()
            for post in batch.posts:
                key = (post.website_id, post.external_post_id)
                is_new = key not in encountered and session.get(SeenPost, key) is None
                encountered.add(key)
                if is_new:
                    session.add(
                        SeenPost(
                            website_id=post.website_id,
                            external_post_id=post.external_post_id,
                            first_seen_at=at,
                        )
                    )
                    session.flush()
                source_item = session.get(SourceItem, (source_id, post.source_item_id))
                if source_item is None:
                    session.add(
                        SourceItem(
                            source_id=source_id,
                            source_item_id=post.source_item_id,
                            website_id=post.website_id,
                            external_post_id=post.external_post_id,
                            first_seen_at=at,
                        )
                    )
                elif (source_item.website_id, source_item.external_post_id) != key:
                    diagnostics.append(Diagnostic("source_item_id_reused"))
                if not is_new:
                    continue

                new_posts += 1
                session.add(
                    Post(
                        website_id=post.website_id,
                        external_post_id=post.external_post_id,
                        title=post.title,
                        summary=post.summary,
                        author=post.author,
                        category=post.category,
                        url=post.url,
                        published_at=post.published_at.timestamp() if post.published_at else None,
                        first_seen_at=at,
                    )
                )
                if baseline:
                    continue

                target_hits: dict[str, list[tuple[RuleHit, TaskVersion]]] = {}
                for task, version in versions:
                    decision = evaluate(Rule.model_validate(version.rule), post)
                    if decision.status == "insufficient_data":
                        insufficient += 1
                    if decision.status != "match":
                        continue
                    hit = RuleHit(
                        id=identifier(),
                        task_id=task.id,
                        task_version=version.version,
                        website_id=post.website_id,
                        external_post_id=post.external_post_id,
                        reason=decision.model_dump(mode="json"),
                        matched_at=at,
                    )
                    session.add(hit)
                    hit_count += 1
                    for target_id in version.target_ids:
                        target = session.get(NotificationTarget, target_id)
                        if target is not None and target.enabled:
                            target_hits.setdefault(target_id, []).append((hit, version))

                for target_id, hits in target_hits.items():
                    target = session.get(NotificationTarget, target_id)
                    event_id = identifier()
                    payload = {
                        "schema_version": 1,
                        "event_id": event_id,
                        "post": {
                            "website_id": post.website_id,
                            "external_post_id": post.external_post_id,
                            "title": post.title,
                            "summary": post.summary,
                            "author": post.author,
                            "category": post.category,
                            "url": post.url,
                            "published_at": post.published_at.isoformat()
                            if post.published_at
                            else None,
                            "first_seen_at": at,
                        },
                        "matched_tasks": [
                            {"id": hit.task_id, "version": hit.task_version, "name": version.name}
                            for hit, version in hits
                        ],
                    }
                    session.add(
                        Outbox(
                            id=event_id,
                            website_id=post.website_id,
                            external_post_id=post.external_post_id,
                            target_id=target_id,
                            target_snapshot=target_snapshot(target),
                            payload=payload,
                            available_at=at,
                            created_at=at,
                        )
                    )
                    session.flush()
                    for hit, _ in hits:
                        session.add(OutboxContribution(event_id=event_id, hit_id=hit.id))
                    queued += 1

            state.initialized = True
            state.needs_baseline = False
            state.last_attempt_at = state.last_success_at = at
            state.last_error_code = None
            state.failures = 0
            state.next_attempt_at = at + source.interval_seconds
            if window:
                state.previous_window = window
            state.window_count = batch.raw_count
            session.add(
                SourceRun(
                    source_id=source_id,
                    at=at,
                    status="success",
                    code="baseline" if baseline else None,
                    raw_count=batch.raw_count,
                    new_posts=new_posts,
                    hit_count=hit_count,
                    queued_count=queued,
                    insufficient_count=insufficient,
                    possible_gap=gap,
                    diagnostics=[asdict(item) for item in diagnostics],
                )
            )
            return IngestReport(
                "success",
                baseline,
                new_posts,
                hit_count,
                queued,
                insufficient,
                gap,
                tuple(diagnostics),
            )

    def preview(self, rule: Rule, *, website_id: str = "nodeseek", limit: int = 100) -> dict:
        """Read-only history matching. It never calls ingest or creates outbox intents."""
        if not 1 <= limit <= 1000:
            raise ValueError("Preview sample limit must be between 1 and 1000")
        with Session(self.engine) as session:
            rows = session.scalars(
                select(Post)
                .where(Post.website_id == website_id)
                .order_by(Post.first_seen_at.desc(), Post.external_post_id)
                .limit(limit)
            ).all()
            results = []
            for row in rows:
                decision = evaluate(
                    rule,
                    PostFields(
                        title=row.title,
                        summary=row.summary,
                        author=row.author,
                        category=row.category,
                    ),
                )
                results.append(
                    {
                        "website_id": row.website_id,
                        "external_post_id": row.external_post_id,
                        "result": decision.model_dump(mode="json"),
                    }
                )
            times = [row.first_seen_at for row in rows]
            return {
                "sample_count": len(rows),
                "first_seen_from": datetime.fromtimestamp(min(times), UTC).isoformat()
                if times
                else None,
                "first_seen_until": datetime.fromtimestamp(max(times), UTC).isoformat()
                if times
                else None,
                "results": results,
            }
