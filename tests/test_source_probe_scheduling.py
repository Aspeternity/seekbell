"""Manual RSS diagnostics have their own cooldown and preserve automatic scheduling."""

import asyncio

import httpx
import pytest
from seekbell.collectors.rss import RssCollector
from seekbell.db.models import Source, SourceProbe, SourceState, WebsiteInstallation
from seekbell.db.transactions import write_session
from seekbell.services.collection import SourceRunner
from seekbell.services.source_probe import ProbeConflict, check, get_probe

from tests.rss_samples import Chunks, rss
from tests.test_management_operations import tables


def prepare(core):
    core.ingest(9001, at=100)
    with write_session(core.engine) as session:
        session.add(WebsiteInstallation(website_id="nodeseek"))


def response():
    return httpx.Response(
        200,
        headers={"content-type": "application/rss+xml"},
        stream=Chunks(rss([{"id": 9002}])),
    )


@pytest.mark.parametrize("interval", [10, 37, 3600])
def test_recent_successful_collection_does_not_block_manual_check_or_get_rescheduled(
    core, interval
):
    prepare(core)
    with write_session(core.engine) as session:
        session.get(Source, "nodeseek-rss").interval_seconds = interval
        session.get(SourceState, "nodeseek-rss").next_attempt_at = 100 + interval
    before, calls = tables(core.engine), []

    async def exercise():
        def handler(request):
            calls.append(request)
            return response()

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            runner = SourceRunner(core.engine, RssCollector(client), clock=lambda: 100.1)
            result = await check(runner)
            assert result["status"] == "success" and result["started_at"] == 100.1
            assert result["next_attempt_at"] == 102.1
            assert runner._snapshot()["next_attempt_at"] == 100 + interval

    asyncio.run(exercise())
    assert len(calls) == 1 and tables(core.engine) == before


def test_successful_probe_own_cooldown_does_not_delay_a_due_collection(core):
    prepare(core)
    calls = []

    async def exercise():
        now = [109.9]

        def handler(request):
            calls.append(now[0])
            return response()

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            runner = SourceRunner(core.engine, RssCollector(client), clock=lambda: now[0])
            result = await check(runner)
            assert result["next_attempt_at"] > 110
            now[0] = 110
            assert (await runner.run_once()).status == "success"

    asyncio.run(exercise())
    assert calls == [109.9, 110]


def test_manual_checks_have_their_own_persistent_double_click_cooldown(core):
    prepare(core)
    with write_session(core.engine) as session:
        session.get(Source, "nodeseek-rss").enabled = False

    async def exercise():
        now = [100.1]
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response())) as client:

            def runner():
                return SourceRunner(core.engine, RssCollector(client), clock=lambda: now[0])

            await check(runner())
            with pytest.raises(ProbeConflict) as error:
                await check(runner())
            assert error.value.retry_after == 2
            assert "2" in str(error.value)
            now[0] = 102.2
            assert (await check(runner()))["status"] == "success"

    asyncio.run(exercise())


def test_real_collection_backoff_still_reports_cause_and_remaining_wait(core):
    prepare(core)
    core.ingestion.record_failure("nodeseek-rss", "http_429", at=100, retry_after=60)
    before = tables(core.engine)

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: None)) as client:
            runner = SourceRunner(core.engine, RssCollector(client), clock=lambda: 110)
            with pytest.raises(ProbeConflict) as error:
                await check(runner)
            assert error.value.retry_after == 50
            assert "http_429" in str(error.value) and "50" in str(error.value)

    asyncio.run(exercise())
    assert tables(core.engine) == before


def test_successful_check_does_not_clear_formal_collection_failure(core):
    prepare(core)
    core.ingestion.record_failure("nodeseek-rss", "http_503", at=90)
    before = tables(core.engine)

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response())) as client:
            runner = SourceRunner(core.engine, RssCollector(client), clock=lambda: 101)
            assert (await check(runner))["status"] == "success"
            assert runner._snapshot()["next_attempt_at"] == 100

    asyncio.run(exercise())
    assert tables(core.engine) == before


def test_legacy_successful_probe_does_not_retain_the_old_collection_interval(core):
    prepare(core)
    with write_session(core.engine) as session:
        session.add(
            SourceProbe(
                source_id="nodeseek-rss",
                started_at=100,
                finished_at=100,
                next_attempt_at=3700,
                status="success",
                code=None,
                item_count=1,
            )
        )
    assert get_probe(core.engine, "nodeseek")["next_attempt_at"] == 102

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response())) as client:
            runner = SourceRunner(core.engine, RssCollector(client), clock=lambda: 103)
            assert runner._snapshot()["next_attempt_at"] == 110
            assert (await check(runner))["status"] == "success"

    asyncio.run(exercise())


def test_probe_retry_after_still_blocks_automatic_collection(core):
    prepare(core)
    before = tables(core.engine)

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(429, headers={"Retry-After": "60"})
            )
        ) as client:
            runner = SourceRunner(core.engine, RssCollector(client), clock=lambda: 101)
            result = await check(runner)
            assert result["code"] == "http_429" and result["next_attempt_at"] == 161
            assert runner._snapshot()["next_attempt_at"] == 161
            assert (await runner.run_once()).status == "backoff"

    asyncio.run(exercise())
    assert tables(core.engine) == before
