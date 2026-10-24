import asyncio

import httpx
from seekbell.collectors.rss import RssCollector
from seekbell.db.models import Outbox, Source, SourceState
from seekbell.services.collection import SourceRunner
from sqlalchemy.orm import Session

from tests.rss_samples import Chunks, rss


def test_default_source_is_disabled_and_does_not_make_requests(core):
    with Session(core.engine) as session:
        source = session.get(Source, "nodeseek-rss")
        source.enabled = False
        session.commit()

    async def exercise():
        def handler(request):
            raise AssertionError("Disabled source must not fetch")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            outcome = await SourceRunner(core.engine, RssCollector(client)).run_once()
            assert outcome.status == "paused"

    asyncio.run(exercise())


def test_shared_collection_baseline_failure_backoff_and_restart(core):
    now = [0]
    requests = []

    async def exercise():
        def handler(request):
            requests.append(request)
            if len(requests) == 1:
                return httpx.Response(429, headers={"Retry-After": "60"})
            ids = [9001] if len(requests) == 2 else [9001, 9002]
            return httpx.Response(
                200,
                headers={"content-type": "application/xml"},
                stream=Chunks(rss([{"id": key} for key in ids])),
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:

            def runner():
                return SourceRunner(
                    core.engine, RssCollector(client), clock=lambda: now[0], jitter=lambda: 0
                )

            assert (await runner().run_once()).status == "failure"
            assert not core.one(SourceState, SourceState.source_id == "nodeseek-rss").initialized
            now[0] = 59
            assert (await runner().run_once()).status == "backoff"
            assert len(requests) == 1
            now[0] = 60
            assert (await runner().run_once()).report.baseline
            now[0] = 70
            result = await runner().run_once()
            assert result.report.new_posts == 1 and result.report.queued == 1

    asyncio.run(exercise())
    assert (
        core.count(Outbox) == 1
        and core.one(SourceState, SourceState.source_id == "nodeseek-rss").failures == 0
    )


def test_overlapping_polls_are_skipped_and_one_shared_fetch_serves_tasks(core):
    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []

        async def handler(request):
            calls.append(request)
            entered.set()
            await release.wait()
            return httpx.Response(
                200, headers={"content-type": "application/xml"}, stream=Chunks(rss([{"id": 9001}]))
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            runner = SourceRunner(core.engine, RssCollector(client), clock=lambda: 100)
            first = asyncio.create_task(runner.run_once())
            await entered.wait()
            assert (await runner.run_once()).status == "overlap"
            release.set()
            assert (await first).report.baseline
            assert len(calls) == 1

    asyncio.run(exercise())


def test_all_invalid_feed_cannot_establish_baseline_and_url_changes_do_not_fetch(core):
    calls = []

    async def exercise():
        def handler(request):
            calls.append(request)
            return httpx.Response(
                200,
                headers={"content-type": "application/xml"},
                stream=Chunks(
                    rss(
                        [
                            {"id": 9001, "guid": "9002"},
                        ]
                    )
                ),
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            runner = SourceRunner(core.engine, RssCollector(client), clock=lambda: 100)
            assert (await runner.run_once()).status == "failure"
            assert not core.one(SourceState, SourceState.source_id == "nodeseek-rss").initialized
            with Session(core.engine) as session:
                session.get(Source, "nodeseek-rss").url = "https://synthetic.invalid/feed"
                session.get(SourceState, "nodeseek-rss").next_attempt_at = 0
                session.commit()
            assert (await runner.run_once()).code == "unsupported_source"
            assert len(calls) == 1

    asyncio.run(exercise())
