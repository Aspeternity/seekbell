"""Synthetic persisted history shared by API/browser checks, never production startup."""

from datetime import UTC, datetime

from seekbell.db.models import (
    NotificationTarget,
    Source,
    TargetTestAttempt,
    Website,
    WebsiteInstallation,
)
from seekbell.db.transactions import write_session
from seekbell.domain.delivery import SendResult
from seekbell.domain.posts import NormalizedPost, PostBatch
from seekbell.domain.rules import Rule
from seekbell.services.configuration import Configuration, target_snapshot
from seekbell.services.delivery import DeliveryWorker
from seekbell.services.history import post_key
from seekbell.services.ingestion import Ingestion
from sqlalchemy.orm import Session

PRIVATE = "synthetic-private-history-value"


def seed_history(engine, vault):
    config = Configuration(engine, vault)
    base = datetime(2026, 10, 19, 0, tzinfo=UTC).timestamp()
    target = config.create_target(
        "历史 Webhook 名称",
        kind="webhook",
        enabled=True,
        config={
            "url": "https://receiver.example.test/" + PRIVATE,
            "headers": {"X-Test": PRIVATE},
        },
    )
    primary = config.create_task(
        "摘要关注", Rule(scope="summary", groups=[{"all_of": ["VPS"]}]), [target], at=base - 10
    )
    secondary = config.create_task(
        "特别标题关注", Rule(groups=[{"all_of": ["特别"]}]), [target], at=base - 9
    )
    with write_session(engine) as session:
        if session.get(WebsiteInstallation, "nodeseek") is None:
            session.add(WebsiteInstallation(website_id="nodeseek"))
        session.get(Website, "nodeseek").enabled = True
        session.get(Source, "nodeseek-rss").enabled = True
    ingestion = Ingestion(engine)
    batch = []
    keys = {}
    for i in range(27):
        key = str(8000 + i)
        title = (
            "特别结果"
            if i == 2
            else "<img src=x onerror=window.historyInjected=true> %_ 样本"
            if i == 5
            else f"读取样本 {i:02}"
        )
        post = NormalizedPost(
            website_id="nodeseek",
            external_post_id=key,
            source_item_id=key,
            url=f"https://www.nodeseek.com/post-{key}-1",
            title=title,
            summary=None if i == 3 else "" if i == 4 else "普通信息" if i == 2 else "VPS 合成摘要",
            author=None if i == 3 else "fixture_author",
            category="技术" if i % 2 else "优惠",
        )
        batch.append(post)
        ingestion.ingest("nodeseek-rss", PostBatch(tuple(batch), len(batch)), at=base + i * 60)
        keys[i] = post_key("nodeseek", key)
    worker = DeliveryWorker(engine, {})
    sent = worker.claim(at=base + 60)
    worker.finish(sent, SendResult(status="unknown", code="send_timeout"), at=base + 61)
    retry = worker.claim(at=base + 70)
    assert retry.event_id == sent.event_id
    worker.finish(retry, SendResult(status="success"), at=base + 71)
    failed = worker.claim(at=base + 120)
    worker.finish(failed, SendResult(status="permanent_error", code="http_403"), at=base + 121)
    old = worker.claim(at=base + 300)
    replacement = worker.claim(at=base + 340)
    assert old.event_id == replacement.event_id
    worker.finish(old, SendResult(status="success"), at=base + 341)
    worker.finish(replacement, SendResult(status="transient_error", code="http_503"), at=base + 342)
    leased = worker.claim(at=base + 360)
    with Session(engine) as session:
        snapshot = target_snapshot(session.get(NotificationTarget, target))
    with write_session(engine) as session:
        session.add_all(
            [
                TargetTestAttempt(
                    id="history-test-success",
                    target_id=target,
                    target_snapshot=snapshot,
                    started_at=base + 5,
                    finished_at=base + 6,
                    result="success",
                ),
                TargetTestAttempt(
                    id="history-test-unknown",
                    target_id=target,
                    target_snapshot=snapshot,
                    started_at=base + 7,
                    result="unknown",
                    error_code="test_not_completed",
                ),
            ]
        )
    config.update_task(primary, "当前任务名称", Rule(), [target], at=base + 2000)
    config.delete_task(secondary, at=base + 2001)
    config.update_target(target, name="当前目标名称", config={})
    config.set_source_enabled("nodeseek-rss", False, at=base + 2002)
    config.set_website_enabled("nodeseek", False, at=base + 2002)
    return {
        "posts": keys,
        "primary": primary,
        "secondary": secondary,
        "target": target,
        "base": base,
        "sent": sent.event_id,
        "failed": failed.event_id,
        "late": old.event_id,
        "leased": leased.event_id,
    }
