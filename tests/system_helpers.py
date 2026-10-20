"""System settings browser fixture: real collectors/alerts, synthetic network only."""

import time
from datetime import UTC, datetime

import httpx
from seekbell.db.models import Post, SeenPost, SourceState, WebsiteInstallation
from seekbell.db.transactions import write_session
from seekbell.domain.delivery import SendResult
from seekbell.services.alerts import observe
from seekbell.services.runtime import Runtime
from sqlalchemy.orm import Session

from tests.rss_samples import Chunks, rss

NOW = datetime(2026, 10, 20, tzinfo=UTC).timestamp()


def seed_system(engine):
    with write_session(engine) as session:
        session.add(WebsiteInstallation(website_id="nodeseek"))
        for key, hour, label in (("7601", 0.5, "时区边界夜帖"), ("7602", 12.5, "时区边界日帖")):
            at = NOW - 86400 + hour * 3600
            session.add(SeenPost(website_id="nodeseek", external_post_id=key, first_seen_at=at))
            session.flush()
            session.add(
                Post(
                    website_id="nodeseek",
                    external_post_id=key,
                    first_seen_at=at,
                    title=label,
                    summary="本地时区样本",
                    url=f"https://www.nodeseek.com/post-{key}-1",
                )
            )
        for index in range(26):
            observe(
                session,
                "runtime:history_fixture",
                index % 2 == 0,
                label="合成历史事件",
                code="synthetic_history" if index % 2 == 0 else None,
                at=NOW - 500 + index,
            )


def system_runtime_factory(engine, notifiers):
    began = time.monotonic()
    started_at = time.time()
    calls = [0]

    async def feed(request):
        with Session(engine) as session:
            state = session.get(SourceState, "nodeseek-rss")
            if state.needs_baseline and state.failures == 0:
                calls[0] = 0
        calls[0] += 1
        if calls[0] <= 2:
            return httpx.Response(503, headers={"Retry-After": "20"})
        return httpx.Response(
            200,
            headers={"content-type": "application/rss+xml"},
            stream=Chunks(rss([{"id": 9001, "title": "Synthetic baseline"}])),
        )

    class SyntheticNotifier:
        async def send(self, snapshot, message):
            if "合成未知" in snapshot["name"]:
                return SendResult(status="unknown", code="synthetic_timeout")
            if "合成失败" in snapshot["name"]:
                return SendResult(status="permanent_error", code="synthetic_rejected")
            return SendResult(status="success")

    runtime = Runtime(
        engine,
        {kind: SyntheticNotifier() for kind in ("telegram", "bark", "smtp", "webhook")},
        http_transport=httpx.MockTransport(feed),
        tick=0.03,
    )
    runtime.source.clock = runtime.worker.clock = runtime.alerts.clock = lambda: (
        started_at + (time.monotonic() - began) * 50
    )
    return runtime
