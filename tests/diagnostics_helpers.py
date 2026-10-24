"""Large, synthetic-only history for the diagnosis browser checks."""

from seekbell.db.models import NotificationTarget, Source, SourceState, Task, TaskVersion, Website
from seekbell.db.transactions import write_session
from seekbell.domain.posts import NormalizedPost, PostBatch
from seekbell.domain.rules import Rule
from seekbell.services.configuration import Configuration
from seekbell.services.ingestion import Ingestion
from sqlalchemy import select


def seed_diagnostics(engine, vault):
    config = Configuration(engine, vault)
    with write_session(engine) as session:
        for task in session.scalars(select(Task)):
            task.enabled = False
        target = session.scalar(
            select(NotificationTarget.id).where(
                NotificationTarget.kind != "mock", NotificationTarget.deleted_at.is_(None)
            )
        )
        session.get(Website, "nodeseek").enabled = True
        session.get(Source, "nodeseek-rss").enabled = True
        state = session.get(SourceState, "nodeseek-rss")
        state.initialized = True
        state.needs_baseline = False
    rule = Rule(
        scope="title_summary",
        groups=[{"all_of": ["vmiss", "tri"]}],
        categories=["trade"],
        exclude=["求购"],
    )
    legacy = config.create_task("000 版块值修复示例", rule, [target], at=1792368100)
    with write_session(engine) as session:
        session.get(TaskVersion, (legacy, 1)).rule = {
            **rule.model_dump(mode="json"),
            "categories": ["交易"],
        }
    for index in range(100):
        config.create_task(
            f"诊断任务 {index:03}",
            Rule(groups=[{"all_of": [f"absent-{index}"]}]),
            [target],
            at=1792368100 + index,
        )
    posts = tuple(
        NormalizedPost(
            website_id="nodeseek",
            external_post_id=str(99000 + index),
            source_item_id=str(99000 + index),
            title=f"诊断样本 {index:03} vmiss tri",
            summary="合成交易摘要",
            author="synthetic_author",
            category="trade",
            url=f"https://www.nodeseek.com/post-{99000 + index}-1",
        )
        for index in range(100)
    )
    Ingestion(engine).ingest("nodeseek-rss", PostBatch(posts, len(posts)), at=1792368400)
    # Current rules recover, while the old failed decisions remain immutable.
    config.update_task(legacy, "000 版块值修复示例", rule, [target], at=1792368500)
    with write_session(engine) as session:
        session.get(Source, "nodeseek-rss").enabled = False
        session.get(Website, "nodeseek").enabled = False
