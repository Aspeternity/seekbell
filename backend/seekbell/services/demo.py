"""Run the M1 closed loop with synthetic data, mock HTTP and a temporary database."""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seekbell.collectors.rss import RssCollector
from seekbell.config import Settings
from seekbell.db.models import DeliveredPost, DeliveryAttempt, Outbox, RuleHit
from seekbell.db.runtime import create_database_engine, migrate, schema_revision
from seekbell.domain.delivery import DeliveryPolicy, SendResult
from seekbell.domain.rules import Rule
from seekbell.services.collection import SourceRunner
from seekbell.services.configuration import Configuration
from seekbell.services.delivery import DeliveryWorker


class SyntheticStream(httpx.AsyncByteStream):
    def __init__(self, ids):
        self.body = (
            '<rss version="2.0"><channel><title>Synthetic SeekBell</title>'
            "<link>https://www.nodeseek.com/</link><description>Offline demo</description>"
            + "".join(
                f'<item><guid isPermaLink="false">{key}</guid>'
                f"<link>https://www.nodeseek.com/post-{key}-1</link>"
                "<title>Synthetic VPS offer</title><category>fixture-section</category></item>"
                for key in ids
            )
            + "</channel></rss>"
        ).encode()

    async def __aiter__(self):
        yield self.body


class SyntheticNotifier:
    def __init__(self):
        self.calls = []

    async def send(self, target, payload):
        self.calls.append(payload)
        if len(self.calls) == 1:
            return SendResult(status="transient_error", code="mock_unavailable", retry_after=5)
        return SendResult(status="success")


async def exercise(directory: Path) -> dict:
    engine = create_database_engine(Settings(data_dir=directory))
    try:
        migrate(engine)
        config = Configuration(engine)
        target = config.create_target("Offline demo target")
        for name in ("Synthetic first rule", "Synthetic second rule"):
            config.create_task(name, Rule(), [target], at=1)
        config.set_source_enabled("nodeseek-rss", True, at=100)
        clock = [100]
        polls = []

        def handle(request):
            polls.append(request)
            return httpx.Response(
                200,
                headers={"content-type": "application/rss+xml"},
                stream=SyntheticStream([9001] if len(polls) == 1 else [9001, 9002]),
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            runner = SourceRunner(
                engine,
                RssCollector(client),
                clock=lambda: clock[0],
                jitter=lambda: 0,
            )
            first = (await runner.run_once()).report
            assert first.baseline and first.queued == 0
            clock[0] = 110
            new = (await runner.run_once()).report
            assert (new.hits, new.queued) == (2, 1)
            notifier = SyntheticNotifier()
            worker = DeliveryWorker(
                engine,
                {"mock": notifier},
                policy=DeliveryPolicy(lease_seconds=10),
                clock=lambda: clock[0],
            )
            abandoned = await asyncio.to_thread(worker.claim, at=110)
            assert abandoned is not None
            clock[0] = 120
            assert await worker.run_once() == abandoned.event_id
            clock[0] = 130
            assert await worker.run_once() == abandoned.event_id
            clock[0] = 140
            repeated = (await runner.run_once()).report
            assert repeated.queued == 0 and await worker.run_once() is None
            assert all(call["event_id"] == abandoned.event_id for call in notifier.calls)

        with Session(engine) as session:

            def count(model):
                return session.scalar(select(func.count()).select_from(model))

            event = session.get(Outbox, abandoned.event_id)
            assert event.status == "sent" and event.uncertain
            return {
                "mode": "offline_synthetic",
                "database_revision": schema_revision(engine),
                "baseline_posts": first.new_posts,
                "new_posts": new.new_posts,
                "rule_hits": count(RuleHit),
                "merged_outbox_events": count(Outbox),
                "attempts_including_expired_lease": count(DeliveryAttempt),
                "mock_send_calls": len(notifier.calls),
                "delivered_receipts": count(DeliveredPost),
                "final_status": event.status,
                "uncertainty_retained": event.uncertain,
                "duplicate_poll_queued": repeated.queued,
            }
    finally:
        engine.dispose()


def main():
    # No production directory, account, URL override or credential can enter this demo.
    with TemporaryDirectory(prefix="seekbell-demo-") as directory:
        result = asyncio.run(exercise(Path(directory)))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
