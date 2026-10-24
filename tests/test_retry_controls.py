import asyncio

import httpx
import pytest
from seekbell.collectors.rss import RssCollector
from seekbell.config import Settings
from seekbell.db.models import (
    Source,
    SourceState,
    Website,
    WebsiteInstallation,
    WebsiteRequestState,
)
from seekbell.db.runtime import create_database_engine, migrate, schema_revision
from seekbell.db.transactions import write_session
from seekbell.domain.errors import SourceDeferred, SourceFailure
from seekbell.services.collection import SourceRunner
from seekbell.services.request_budget import WebsiteRequestBudget
from seekbell.services.source_probe import ProbeConflict, check, get_probe
from sqlalchemy import event, inspect, text
from sqlalchemy.orm import Session

from tests.linuxdo_helpers import linuxdo_rss
from tests.rss_samples import Chunks
from tests.test_management_operations import tables


def install(core, *, failure=False):
    with write_session(core.engine) as session:
        session.add(WebsiteInstallation(website_id="linuxdo"))
        session.get(Website, "linuxdo").enabled = True
        session.get(Source, "linuxdo-rss").enabled = True
        state = session.get(SourceState, "linuxdo-rss")
        state.next_attempt_at = 5000
        if failure:
            state.last_error_code, state.failures = "access_challenge", 5


def response():
    return httpx.Response(
        200, headers={"Content-Type": "application/rss+xml"}, stream=Chunks(linuxdo_rss(9001))
    )


@pytest.mark.parametrize(
    ("code", "delays"),
    [
        ("access_challenge", [300, 600, 600, 600, 600, 600]),
        ("http_403", [300, 600, 600, 600, 600, 600]),
        ("http_429", [60, 120, 240, 480, 600, 600]),
        ("timeout", [30, 60, 120, 240, 300, 300]),
    ],
)
def test_automatic_backoff_is_bounded_and_persisted(core, code, delays):
    now = [2000]
    for delay in delays:
        budget = WebsiteRequestBudget(core.engine, clock=lambda: now[0])
        budget.failed(SourceFailure(code), now[0])
        assert budget.view("linuxdo") == (now[0] + delay, code)
        now[0] += delay + 1


def test_manual_recovery_has_own_persistent_quota_and_schedules_real_collection(core):
    install(core, failure=True)
    now, calls = [2000], []
    budget = WebsiteRequestBudget(core.engine, clock=lambda: now[0])
    budget.failed(SourceFailure("access_challenge"), now[0])
    before = tables(core.engine)

    async def exercise():
        def handler(request):
            calls.append(now[0])
            return response()

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:

            def runner():
                return SourceRunner(
                    core.engine,
                    RssCollector(
                        client,
                        request_budget=WebsiteRequestBudget(core.engine, clock=lambda: now[0]),
                        website_id="linuxdo",
                    ),
                    source_id="linuxdo-rss",
                    clock=lambda: now[0],
                )

            now[0] = 2060
            assert (await check(runner()))["status"] == "success"
            after = tables(core.engine)
            assert {k: v for k, v in after.items() if k != "source_states"} == {
                k: v for k, v in before.items() if k != "source_states"
            }
            with Session(core.engine) as session:
                state = session.get(SourceState, "linuxdo-rss")
                assert state.next_attempt_at == 2062
                assert state.failures == 5 and state.last_success_at is None
                assert not state.initialized and not state.needs_baseline
            with pytest.raises(ProbeConflict) as error:
                await check(runner())
            assert error.value.retry_after == 60
            now[0] = 2062
            assert (await runner().run_once()).status == "success"
            with Session(core.engine) as session:
                state = session.get(SourceState, "linuxdo-rss")
                assert state.initialized and state.failures == 0 and state.last_success_at == 2062
            assert get_probe(core.engine, "linuxdo")["next_attempt_at"] == 2120

    asyncio.run(exercise())
    assert calls == [2060, 2062]


@pytest.mark.parametrize("code", ["http_429", "http_503", "access_challenge"])
def test_retry_after_cannot_be_overridden_by_manual_requests_after_restart(core, code):
    install(core, failure=True)
    now, calls = [2000], []
    budget = WebsiteRequestBudget(core.engine, clock=lambda: now[0])
    budget.failed(SourceFailure(code, retry_after=900), now[0])

    async def exercise():
        def handler(request):
            calls.append(request)
            return response()

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            restored = WebsiteRequestBudget(core.engine, clock=lambda: now[0])
            runner = SourceRunner(
                core.engine,
                RssCollector(client, request_budget=restored, website_id="linuxdo"),
                source_id="linuxdo-rss",
                clock=lambda: now[0],
            )
            now[0] = 2100
            with pytest.raises(ProbeConflict) as error:
                await check(runner)
            assert error.value.retry_after == 800 and "来源要求" in str(error.value)
            now[0] = 2899
            with pytest.raises(ProbeConflict):
                await check(runner)
            assert not calls
            now[0] = 2900
            assert (await check(runner))["status"] == "success"

    asyncio.run(exercise())
    assert len(calls) == 1


def test_failed_manual_probe_preserves_automatic_backoff_and_relimits_manual_requests(core):
    install(core, failure=True)
    now = [2000]
    budget = WebsiteRequestBudget(core.engine, clock=lambda: now[0])
    budget.failed(SourceFailure("access_challenge"), now[0])

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(403, headers={"cf-mitigated": "challenge"})
            )
        ) as client:
            runner = SourceRunner(
                core.engine,
                RssCollector(client, request_budget=budget, website_id="linuxdo"),
                source_id="linuxdo-rss",
                clock=lambda: now[0],
            )
            now[0] = 2060
            data = await check(runner)
            assert data["code"] == "access_challenge" and data["next_attempt_at"] == 2120
            assert budget.view("linuxdo") == (2660, "access_challenge")
            with pytest.raises(ProbeConflict):
                await check(runner)
            now[0] = 2120
            with pytest.raises(SourceDeferred):
                async with budget.request("linuxdo"):
                    raise AssertionError("Automatic request ignored the backoff")
            with Session(core.engine) as session:
                assert session.get(SourceState, "linuxdo-rss").next_attempt_at == 5000

    asyncio.run(exercise())


def test_cancelled_manual_request_keeps_quota_without_fabricating_failure(core):
    now = [2000]

    async def exercise():
        budget = WebsiteRequestBudget(core.engine, clock=lambda: now[0])
        entered = asyncio.Event()

        async def pending():
            async with budget.request("linuxdo", manual=True):
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(pending())
        await entered.wait()
        with pytest.raises(SourceDeferred, match="source_busy"):
            async with budget.request("linuxdo"):
                pass
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        restored = WebsiteRequestBudget(core.engine, clock=lambda: now[0])
        now[0] = 2003
        with pytest.raises(SourceDeferred, match="manual_cooldown"):
            async with restored.request("linuxdo", manual=True):
                pass
        with Session(core.engine) as session:
            assert session.get(WebsiteRequestState, "linuxdo").failures == 0
        async with restored.request("linuxdo"):
            pass
        with pytest.raises(SourceDeferred, match="manual_cooldown"):
            async with restored.request("linuxdo", manual=True):
                pass

    asyncio.run(exercise())


def test_busy_deferred_probe_keeps_truthful_evidence_and_does_not_delay_collection(core):
    install(core)
    now = [2000]
    budget = WebsiteRequestBudget(core.engine, clock=lambda: now[0])
    before = tables(core.engine)

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response())) as client:
            runner = SourceRunner(
                core.engine,
                RssCollector(client, request_budget=budget, website_id="linuxdo"),
                source_id="linuxdo-rss",
                clock=lambda: now[0],
            )
            await budget.lock.acquire()
            try:
                result = await check(runner)
            finally:
                budget.lock.release()
            assert result["status"] == "deferred" and result["next_attempt_at"] == 2002
            with pytest.raises(ProbeConflict):
                await check(runner)
            with Session(core.engine) as session:
                assert session.get(WebsiteRequestState, "linuxdo").failures == 0

    asyncio.run(exercise())
    assert tables(core.engine) == before


def test_successful_probe_keeps_healthy_automatic_schedule_unchanged(core):
    install(core)
    before = tables(core.engine)

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response())) as client:
            runner = SourceRunner(
                core.engine,
                RssCollector(
                    client,
                    request_budget=WebsiteRequestBudget(core.engine, clock=lambda: 2000),
                    website_id="linuxdo",
                ),
                source_id="linuxdo-rss",
                clock=lambda: 2000,
            )
            result = await check(runner)
            assert result["status"] == "success" and result["next_attempt_at"] == 2060

    asyncio.run(exercise())
    assert tables(core.engine) == before


def test_retry_after_remains_capped_at_one_day(core):
    budget = WebsiteRequestBudget(core.engine, clock=lambda: 2000)
    budget.failed(SourceFailure("http_429", retry_after=999999), 2000)
    assert budget.view("linuxdo")[0] == 88400
    with Session(core.engine) as session:
        assert session.get(WebsiteRequestState, "linuxdo").retry_after_until == 88400


def test_retry_migration_preserves_legacy_deadline_and_old_columns(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0011_linuxdo")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE website_request_states SET blocked_until=12345,failures=5,"
                    "error_code='access_challenge'"
                )
            )
            before = connection.execute(
                text(
                    "SELECT website_id,next_request_at,blocked_until,failures,error_code "
                    "FROM website_request_states"
                )
            ).all()
        migrate(engine, "0012_retry_controls")
        migrate(engine, "0012_retry_controls")
        assert schema_revision(engine) == "0012_retry_controls"
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT website_id,next_request_at,blocked_until,failures,error_code "
                        "FROM website_request_states"
                    )
                ).all()
                == before
            )
            assert connection.execute(
                text("SELECT retry_after_until,next_manual_at FROM website_request_states")
            ).one() == (12345, 0)
    finally:
        engine.dispose()


def test_retry_migration_failure_rolls_back_added_columns_and_version(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0011_linuxdo")

        def fail(_connection, _cursor, statement, _parameters, _context, _many):
            if "SET retry_after_until" in statement:
                raise RuntimeError("synthetic retry migration fault")

        event.listen(engine, "before_cursor_execute", fail)
        with pytest.raises(RuntimeError, match="retry migration fault"):
            migrate(engine)
        event.remove(engine, "before_cursor_execute", fail)
        assert schema_revision(engine) == "0011_linuxdo"
        assert "retry_after_until" not in {
            c["name"] for c in inspect(engine).get_columns("website_request_states")
        }
        migrate(engine)
    finally:
        engine.dispose()


def test_linuxdo_hotlist_does_not_keep_a_longer_inner_failure_backoff(core):
    from seekbell.services.hotlists import HotlistService

    now = [2000]

    async def exercise():
        service = HotlistService(
            transport=httpx.MockTransport(lambda _: httpx.Response(503)),
            request_budget=WebsiteRequestBudget(core.engine, clock=lambda: now[0]),
            clock=lambda: now[0],
        )
        try:
            for delay in (30, 60, 120, 240, 300, 300):
                result = await service.get("linuxdo", "hot")
                assert result["status"] == "unavailable"
                assert result["next_attempt_at"] == now[0] + delay
                now[0] += delay + 1
        finally:
            await service.aclose()

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("failed_source", "failed_probe", "deadline"),
    [
        (True, False, 20000),
        (False, True, 21000),
        (False, False, 12345),
    ],
)
def test_legacy_migration_protects_failure_deadlines_but_not_healthy_schedules(
    tmp_path, failed_source, failed_probe, deadline
):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0011_linuxdo")
        with engine.begin() as connection:
            connection.execute(text("UPDATE website_request_states SET blocked_until=12345"))
            connection.execute(
                text(
                    "UPDATE source_states SET next_attempt_at=20000,failures=:n "
                    "WHERE source_id='linuxdo-rss'"
                ),
                {"n": int(failed_source)},
            )
            connection.execute(
                text(
                    "INSERT INTO source_probes("
                    "source_id,started_at,finished_at,next_attempt_at,status) "
                    "VALUES('linuxdo-rss',2000,2000,21000,:status)"
                ),
                {"status": "failure" if failed_probe else "success"},
            )
        migrate(engine)
        with Session(engine) as session:
            assert session.get(WebsiteRequestState, "linuxdo").retry_after_until == deadline
    finally:
        engine.dispose()
