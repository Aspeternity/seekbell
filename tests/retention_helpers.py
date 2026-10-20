"""Disposable retention fixtures; only the cleanup actor runs."""

from datetime import UTC, datetime

from seekbell.db.models import Post, SeenPost, SourceItem
from seekbell.db.transactions import write_session

from tests.runtime_helpers import SyntheticScenario

NOW = datetime(2026, 10, 20, 12, tzinfo=UTC).timestamp()


def seed_retention(engine):
    with write_session(engine) as session:
        for key, age in (("7501", 20 * 86400), ("7502", 10 * 86400), ("7503", 3600)):
            at = NOW - age
            session.add(SeenPost(website_id="nodeseek", external_post_id=key, first_seen_at=at))
            session.flush()
            session.add(
                Post(
                    website_id="nodeseek",
                    external_post_id=key,
                    first_seen_at=at,
                    title="近期合成历史" if key == "7503" else "过期合成历史 " + key,
                    url="https://www.nodeseek.com/post-" + key + "-1",
                    summary="本地清理夹具",
                )
            )
            session.add(
                SourceItem(
                    source_id="nodeseek-rss",
                    source_item_id=key,
                    website_id="nodeseek",
                    external_post_id=key,
                    first_seen_at=at,
                )
            )


def retention_runtime_factory(engine, notifiers):
    runtime = SyntheticScenario().factory(engine, notifiers)

    async def idle(stop):
        await stop.wait()

    runtime.source.run = idle
    runtime.worker.run = idle
    runtime.retention.clock = lambda: NOW
    return runtime
