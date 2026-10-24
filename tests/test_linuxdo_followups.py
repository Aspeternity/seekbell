import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient
from seekbell.collectors.rss import RssCollector
from seekbell.config import Settings
from seekbell.db.models import WebsiteRequestState
from seekbell.db.runtime import create_database_engine, migrate, schema_revision
from seekbell.domain.errors import SourceFailure
from seekbell.main import create_app
from seekbell.services.collection import SourceRunner
from seekbell.services.hotlists import HotlistService
from seekbell.services.request_budget import WebsiteRequestBudget
from seekbell.services.source_probe import ProbeConflict, check
from sqlalchemy import event, inspect, text
from sqlalchemy.orm import Session

from tests.test_management import authenticate
from tests.test_retry_controls import install, response


def test_automatic_failures_do_not_claim_or_extend_manual_quota(core):
    install(core, failure=True)
    now, calls = [2000], []
    budget = WebsiteRequestBudget(core.engine, clock=lambda: now[0])

    async def exercise():
        async with budget.request("linuxdo"):
            pass
        budget.failed(SourceFailure("access_challenge"), 2000)
        with Session(core.engine) as session:
            assert session.get(WebsiteRequestState, "linuxdo").next_manual_at == 0

        async def handler(request):
            calls.append(now[0])
            return response()

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            runner = SourceRunner(
                core.engine,
                RssCollector(client, request_budget=budget, website_id="linuxdo"),
                source_id="linuxdo-rss",
                clock=lambda: now[0],
            )
            now[0] = 2001
            with pytest.raises(ProbeConflict) as error:
                await check(runner)
            assert error.value.retry_after == 1 and "60" not in str(error.value)
            now[0] = 2002
            assert (await check(runner))["status"] == "success"
            now[0] = 2050
            budget.failed(SourceFailure("http_503"), now[0])
            with Session(core.engine) as session:
                assert session.get(WebsiteRequestState, "linuxdo").next_manual_at == 2062
            with pytest.raises(ProbeConflict):
                await check(runner)
            now[0] = 2062
            assert (await check(runner))["status"] == "success"

    asyncio.run(exercise())
    assert calls == [2002, 2062]


def test_busy_manual_check_can_retry_after_short_gap_without_a_one_minute_penalty(core):
    install(core)
    now, calls = [2000], []
    budget = WebsiteRequestBudget(core.engine, clock=lambda: now[0])

    async def exercise():
        def handler(request):
            calls.append(now[0])
            return response()

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            runner = SourceRunner(
                core.engine,
                RssCollector(client, request_budget=budget, website_id="linuxdo"),
                source_id="linuxdo-rss",
                clock=lambda: now[0],
            )
            await budget.lock.acquire()
            try:
                first = await check(runner)
            finally:
                budget.lock.release()
            assert first["status"] == "deferred" and first["next_attempt_at"] == 2002
            assert not calls
            with Session(core.engine) as session:
                assert session.get(WebsiteRequestState, "linuxdo").next_manual_at == 0
            now[0] = 2002
            assert (await check(runner))["status"] == "success"
            with pytest.raises(ProbeConflict):
                await check(runner)

    asyncio.run(exercise())
    assert calls == [2002]


def test_daily_hotlist_short_deferral_is_waiting_then_recovers_without_a_failure(core):
    now, calls = [2000], []
    budget = WebsiteRequestBudget(core.engine, clock=lambda: now[0])

    async def exercise():
        def handler(request):
            calls.append(str(request.url))
            return response()

        service = HotlistService(
            transport=httpx.MockTransport(handler), request_budget=budget, clock=lambda: now[0]
        )
        try:
            async with budget.request("linuxdo"):
                pass
            data = await service.get("linuxdo", "daily")
            assert data["status"] == "waiting" and data["error_code"] == "source_cooldown"
            assert data["next_attempt_at"] == 2002 and not calls
            with Session(core.engine) as session:
                assert session.get(WebsiteRequestState, "linuxdo").failures == 0
            now[0] = 2002
            data = await service.get("linuxdo", "daily")
            assert data["status"] == "ready" and len(data["items"]) == 1
        finally:
            await service.aclose()

    asyncio.run(exercise())
    assert calls == ["https://linux.do/top.rss?period=daily"]


@pytest.mark.parametrize("order", [("nodeseek", "linuxdo"), ("linuxdo", "nodeseek")])
def test_installation_order_is_shared_and_survives_restart_and_readd(tmp_path, order):
    settings = Settings(data_dir=tmp_path)
    with TestClient(create_app(settings)) as client:
        authenticate(client)
        for key in order:
            assert client.post("/api/manage/websites", json={"adapter_id": key}).status_code == 201
        assert [w["id"] for w in client.get("/api/manage/workspace").json()["websites"]] == list(
            order
        )
        assert [
            w["website_id"] for w in client.get("/api/manage/overview").json()["sources"]
        ] == list(order)
        assert [
            w["website_id"]
            for w in client.get("/api/manage/overview-preferences").json()["sources"]
        ] == list(order)
        assert client.post("/api/manage/websites", json={"adapter_id": order[0]}).status_code == 409
    with TestClient(create_app(settings)) as client:
        authenticate(client, setup=False)
        assert [w["id"] for w in client.get("/api/manage/workspace").json()["websites"]] == list(
            order
        )
        assert client.delete("/api/manage/websites/" + order[0]).status_code == 200
        assert client.post("/api/manage/websites", json={"adapter_id": order[0]}).status_code == 201
        assert [w["id"] for w in client.get("/api/manage/workspace").json()["websites"]] == [
            order[1],
            order[0],
        ]


@pytest.mark.parametrize(
    ("status", "deadline"),
    [
        (None, 0),
        ("success", 2070),
        ("failure", 2070),
        ("unknown", 2060),
        ("deferred", 0),
    ],
)
def test_site_order_migration_uses_row_insertion_order_and_only_actual_manual_evidence(
    tmp_path, status, deadline
):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0012_retry_controls")
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO website_installations(website_id) VALUES('nodeseek'),('linuxdo')")
            )
            connection.execute(
                text(
                    "UPDATE website_request_states SET next_manual_at=9999,retry_after_until=12345"
                )
            )
            if status:
                connection.execute(
                    text(
                        "INSERT INTO source_probes("
                        "source_id,started_at,finished_at,next_attempt_at,status) "
                        "VALUES('linuxdo-rss',2000,:finished,9000,:status)"
                    ),
                    {"finished": None if status == "unknown" else 2010, "status": status},
                )
        migrate(engine, "0013_site_order")
        assert schema_revision(engine) == "0013_site_order"
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT website_id,position FROM website_installations ORDER BY position")
            ).all() == [("nodeseek", 1), ("linuxdo", 2)]
            assert connection.execute(
                text("SELECT next_manual_at,retry_after_until FROM website_request_states")
            ).one() == (deadline, 12345)
    finally:
        engine.dispose()


def test_site_order_migration_rolls_back_order_column_and_quota_on_error(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0012_retry_controls")
        with engine.begin() as connection:
            connection.execute(text("UPDATE website_request_states SET next_manual_at=9999"))

        def fail(_connection, _cursor, statement, _parameters, _context, _many):
            if "SET next_manual_at" in statement:
                raise RuntimeError("synthetic site-order migration fault")

        event.listen(engine, "before_cursor_execute", fail)
        with pytest.raises(RuntimeError, match="site-order migration fault"):
            migrate(engine)
        event.remove(engine, "before_cursor_execute", fail)
        assert schema_revision(engine) == "0012_retry_controls"
        assert "position" not in {
            c["name"] for c in inspect(engine).get_columns("website_installations")
        }
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT next_manual_at FROM website_request_states")
                ).scalar()
                == 9999
            )
        migrate(engine)
    finally:
        engine.dispose()
