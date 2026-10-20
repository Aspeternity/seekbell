"""Connection checks must get a due slot without bypassing the shared RSS throttle."""

import asyncio
import time

import httpx
import pytest
from seekbell.collectors.rss import RssCollector
from seekbell.db.models import Source, SourceProbe, WebsiteInstallation
from seekbell.db.transactions import write_session
from seekbell.services.collection import SourceRunner
from seekbell.services.source_probe import ProbeConflict, check
from sqlalchemy.orm import Session

from tests.rss_samples import Chunks, rss
from tests.test_management_operations import tables


def prepare(core):
    core.ingest(9001, at=100)
    with write_session(core.engine) as session:
        session.add(WebsiteInstallation(website_id="nodeseek"))


@pytest.mark.parametrize("backoff", [False, True])
def test_enabled_check_waits_for_shared_due_slot_and_does_not_ingest(core, backoff):
    prepare(core)
    due = 110
    if backoff:
        core.ingestion.record_failure("nodeseek-rss", "http_429", at=100, retry_after=60)
        due = 160
    before = tables(core.engine)
    calls = []

    async def exercise():
        start = time.monotonic()

        def clock():
            return due - 0.2 + time.monotonic() - start

        def handler(request):
            assert clock() >= due
            calls.append(request)
            return httpx.Response(
                200,
                headers={"content-type": "application/rss+xml"},
                stream=Chunks(rss([{"id": 9002}])),
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            runner = SourceRunner(core.engine, RssCollector(client), clock=clock)
            pending = asyncio.create_task(check(runner))
            async with asyncio.timeout(2):
                while not runner._lock.locked():
                    await asyncio.sleep(0)
            assert not calls
            assert (await runner.run_once()).status == "overlap"
            with pytest.raises(ProbeConflict):
                await check(runner)
            result = await pending
            assert result["status"] == "success" and result["item_count"] == 1, result
            assert (await runner.run_once()).status == "backoff"

    asyncio.run(exercise())
    assert len(calls) == 1
    assert tables(core.engine) == before


def test_saved_interval_is_rechecked_after_waiting(core):
    prepare(core)

    async def exercise():
        start = time.monotonic()

        def handler(request):
            raise AssertionError("Changed interval must prevent the request")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            runner = SourceRunner(
                core.engine,
                RssCollector(client),
                clock=lambda: 109.8 + time.monotonic() - start,
            )
            pending = asyncio.create_task(check(runner))
            async with asyncio.timeout(2):
                while not runner._lock.locked():
                    await asyncio.sleep(0)
                # Let the reservation read finish and enter its bounded wait.
                await asyncio.sleep(0.05)
            with write_session(core.engine) as session:
                session.get(Source, "nodeseek-rss").interval_seconds = 20
            with pytest.raises(ProbeConflict):
                await pending
            assert not runner._lock.locked()

    asyncio.run(exercise())
    with Session(core.engine) as session:
        assert session.get(SourceProbe, "nodeseek-rss") is None


def test_cancelled_wait_releases_slot_without_request_or_probe(core):
    prepare(core)

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: None)) as client:
            runner = SourceRunner(core.engine, RssCollector(client), clock=lambda: 105)
            pending = asyncio.create_task(check(runner))
            async with asyncio.timeout(2):
                while not runner._lock.locked():
                    await asyncio.sleep(0)
                await asyncio.sleep(0.02)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
            assert not runner._lock.locked()

    asyncio.run(exercise())
    with Session(core.engine) as session:
        assert session.get(SourceProbe, "nodeseek-rss") is None


def test_real_collection_backoff_reports_cause_and_remaining_wait(core):
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


def test_paused_check_does_not_wait_or_bypass_the_interval(core):
    prepare(core)
    with write_session(core.engine) as session:
        session.get(Source, "nodeseek-rss").enabled = False

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: None)) as client:
            runner = SourceRunner(core.engine, RssCollector(client), clock=lambda: 105)
            with pytest.raises(ProbeConflict) as error:
                await check(runner)
            assert error.value.retry_after == 5

    asyncio.run(exercise())


def test_long_saved_interval_returns_remaining_time_without_holding_slot(core):
    prepare(core)
    with write_session(core.engine) as session:
        session.get(Source, "nodeseek-rss").interval_seconds = 3600

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: None)) as client:
            runner = SourceRunner(core.engine, RssCollector(client), clock=lambda: 105)
            with pytest.raises(ProbeConflict) as error:
                await check(runner)
            assert error.value.retry_after == 3595
            assert "3595" in str(error.value)
            assert not runner._lock.locked()

    asyncio.run(exercise())
