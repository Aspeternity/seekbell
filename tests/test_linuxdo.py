import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from seekbell.collectors.rss import parse_rss
from seekbell.config import Settings
from seekbell.db.models import (
    HotlistSnapshot,
    Outbox,
    Post,
    SeenPost,
    Source,
    SourceState,
    Website,
    WebsiteInstallation,
)
from seekbell.db.runtime import create_database_engine, migrate, schema_revision
from seekbell.db.transactions import write_session
from seekbell.domain.errors import SourceFailure
from seekbell.domain.rules import Rule, evaluate
from seekbell.main import create_app
from seekbell.services.history import History, post_key
from seekbell.services.hotlists import HotlistService
from seekbell.sites.hotlists import HOTLIST_SOURCES, parse_linuxdo_snapshot
from seekbell.sites.linuxdo import LinuxDoAdapter
from sqlalchemy import event, inspect, select, text
from sqlalchemy.orm import Session

from tests.hotlist_helpers import snapshot, synthetic_hotlists
from tests.linuxdo_helpers import linuxdo_rss
from tests.rss_samples import Chunks, rss
from tests.test_management import authenticate, target, task_values


def test_linuxdo_upgrade_preserves_old_data_and_never_installs_or_enables(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0010_overview_preferences")
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE sources SET interval_seconds=31 WHERE id='nodeseek-rss'")
            )
            connection.execute(text("INSERT INTO website_installations VALUES ('nodeseek')"))
        migrate(engine, "0011_linuxdo")
        migrate(engine, "0011_linuxdo")
        assert schema_revision(engine) == "0011_linuxdo"
        with Session(engine) as session:
            assert session.get(Source, "nodeseek-rss").interval_seconds == 31
            assert session.get(WebsiteInstallation, "nodeseek")
            assert not session.get(WebsiteInstallation, "linuxdo")
            assert not session.get(Website, "linuxdo").enabled
            source = session.get(Source, "linuxdo-rss")
            assert source.url == LinuxDoAdapter.rss_url and source.interval_seconds == 60
            assert not source.enabled and not session.get(SourceState, source.id).initialized
    finally:
        engine.dispose()


def test_linuxdo_failed_migration_rolls_back_column_seed_and_revision(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0010_overview_preferences")

        def fail(_connection, _cursor, statement, _parameters, _context, _many):
            if "CREATE TABLE website_request_states" in statement:
                raise RuntimeError("synthetic linuxdo migration fault")

        event.listen(engine, "before_cursor_execute", fail)
        with pytest.raises(RuntimeError, match="migration fault"):
            migrate(engine)
        event.remove(engine, "before_cursor_execute", fail)
        assert schema_revision(engine) == "0010_overview_preferences"
        assert "author_display_name" not in {
            c["name"] for c in inspect(engine).get_columns("posts")
        }
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM websites WHERE id='linuxdo'")) == 0
        migrate(engine)
    finally:
        engine.dispose()


def test_discordance_between_display_name_username_and_footer_is_preserved():
    post = LinuxDoAdapter().normalize(parse_rss(linuxdo_rss(9001))).posts[0]
    assert post.author is None and post.author_display_name == "Synthetic Display Name"
    assert post.summary == "Synthetic topic summary"
    assert post.category == "合成技术"
    assert post.url == "https://linux.do/t/topic/9001"
    assert (
        evaluate(Rule(groups=[{"all_of": ["参与者"]}], scope="summary"), post).status == "no_match"
    )
    assert (
        evaluate(Rule(authors_include=["Synthetic Display Name"]), post).status
        == "insufficient_data"
    )
    assert (
        LinuxDoAdapter().normalize(parse_rss(linuxdo_rss(9001, summary=None))).posts[0].summary
        is None
    )
    assert (
        LinuxDoAdapter().normalize(parse_rss(linuxdo_rss(9001, summary=""))).posts[0].summary == ""
    )
    body = "<p>参与者、阅读完整话题是正文关键词</p>"
    assert (
        LinuxDoAdapter().normalize(parse_rss(linuxdo_rss(9001, summary=body))).posts[0].summary
        == "参与者、阅读完整话题是正文关键词"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://linux.do/t/topic/9001",
        "https://linux.do/t/9001",
        "https://linux.do/t/some-slug/9001/3",
        "https://linux.do/t/9001/3",
    ],
)
def test_linuxdo_topic_identity_accepts_canonical_forms(url):
    assert LinuxDoAdapter.post_id(url) == "9001"


@pytest.mark.parametrize(
    "url",
    [
        "http://linux.do/t/topic/9001",
        "https://linux.do.evil.test/t/topic/9001",
        "https://" + "fixture@" + "linux.do/t/topic/9001",
        "https://linux.do:8443/t/topic/9001",
        "javascript:9001",
        "https://linux.do/t/topic/0",
        "https://linux.do/t/topic/x",
        "https://linux.do/u/9001",
    ],
)
def test_linuxdo_topic_identity_rejects_external_or_ambiguous_urls(url):
    assert LinuxDoAdapter.post_id(url) is None


def test_linuxdo_conflicting_identity_fails_and_guid_can_supply_canonical_link():
    with pytest.raises(SourceFailure, match="no_valid_entries"):
        LinuxDoAdapter().normalize(parse_rss(linuxdo_rss(9001, guid="linux.do-topic-9002")))
    post = (
        LinuxDoAdapter()
        .normalize(parse_rss(linuxdo_rss(9001, link="https://bad.example.test/")))
        .posts[0]
    )
    assert post.url == "https://linux.do/t/topic/9001"
    assert LinuxDoAdapter().normalize(parse_rss(rss())).posts == ()


def test_rss_hotlist_uses_source_order_and_has_no_fabricated_metrics_or_update_time():
    data = parse_linuxdo_snapshot(linuxdo_rss(9002, 9001, 9002), 2000)
    assert data["source_updated_at"] is None and data["fetched_at"] == 2000
    assert [i["id"] for i in data["items"]] == ["9002", "9001"]
    assert all(i["views"] is None and i["comments"] is None for i in data["items"])
    metadata = HOTLIST_SOURCES["linuxdo"].metadata()
    assert metadata["default_period"] == "hot"
    assert metadata["periods"] == [
        {"id": "hot", "label": "热门"},
        {"id": "daily", "label": "每日"},
        {"id": "weekly", "label": "每周"},
    ]


def test_linuxdo_api_installation_capabilities_periods_and_task_isolation(tmp_path):
    app = create_app(Settings(data_dir=tmp_path), hotlist_factory=synthetic_hotlists)
    with TestClient(app) as client:
        authenticate(client)
        assert client.get("/api/manage/hotlists/linuxdo").status_code == 409
        assert (
            client.post("/api/manage/websites", json={"adapter_id": "linuxdo"}).status_code == 201
        )
        assert (
            client.post("/api/manage/websites", json={"adapter_id": "linuxdo"}).status_code == 409
        )
        site = client.get("/api/manage/workspace").json()["websites"][0]
        assert site["interval"] == 60 and not site["enabled"]
        assert (
            client.put(
                "/api/manage/websites/linuxdo", json={"enabled": True, "interval": 10}
            ).status_code
            == 422
        )
        key = target(client)
        values = {**task_values(key), "website_id": "linuxdo"}
        values["rule"]["authors_include"] = ["Synthetic Display Name"]
        assert client.post("/api/manage/tasks", json=values).status_code == 422
        values["rule"]["authors_include"] = []
        response = client.post("/api/manage/tasks", json=values)
        assert response.status_code == 201
        task_id = response.json()["id"]
        assert (
            client.post(
                "/api/manage/rules/history",
                json={"website_id": "linuxdo", "rule": values["rule"], "limit": 20},
            ).status_code
            == 200
        )
        assert client.get("/api/manage/hotlists/linuxdo?period=realtime").status_code == 404
        assert client.get("/api/manage/hotlists/linuxdo").json()["period"] == "hot"
        assert client.delete("/api/manage/websites/linuxdo").status_code == 409
        assert client.delete("/api/manage/tasks/" + task_id).status_code == 200
        assert client.delete("/api/manage/websites/linuxdo").status_code == 200
        assert client.get("/api/manage/hotlists/linuxdo").status_code == 409


def test_readable_linuxdo_history_links_and_author_search_do_not_affect_rule_username(core):
    with write_session(core.engine) as session:
        session.get(Website, "linuxdo").enabled = True
        session.get(Source, "linuxdo-rss").enabled = True
    report = core.ingestion.ingest(
        "linuxdo-rss", LinuxDoAdapter().normalize(parse_rss(linuxdo_rss(9001))), at=10
    )
    assert report.baseline
    item = History(core.engine).get_post(post_key("linuxdo", "9001"))
    assert item["original_url"] == "https://linux.do/t/topic/9001"
    assert item["author"] is None and item["author_display_name"] == "Synthetic Display Name"
    assert History(core.engine).list_posts(q="Display Name")["total"] == 1


@pytest.mark.parametrize("website_id,period", [("nodeseek", "daily"), ("linuxdo", "hot")])
def test_persisted_hotlist_is_available_after_restart_and_expired_refresh_does_not_block(
    core, website_id, period
):
    async def run():
        now = [2000]
        calls = []

        async def handler(request):
            calls.append(str(request.url))
            data = (
                linuxdo_rss(9002, 9001)
                if website_id == "linuxdo"
                else json.dumps(snapshot(now=1900)).encode()
            )
            return httpx.Response(
                200,
                headers={"Content-Type": "application/rss+xml"} if website_id == "linuxdo" else {},
                stream=Chunks(data),
            )

        first = HotlistService(
            engine=core.engine, transport=httpx.MockTransport(handler), clock=lambda: now[0]
        )
        original = await first.get(website_id, period)
        await first.aclose()
        assert original["status"] == "ready" and len(calls) == 1
        started, release = asyncio.Event(), asyncio.Event()

        async def held(request):
            calls.append(str(request.url))
            started.set()
            await release.wait()
            return httpx.Response(403)

        restored = HotlistService(
            engine=core.engine, transport=httpx.MockTransport(held), clock=lambda: now[0]
        )
        try:
            assert (await restored.get(website_id, period))["items"] == original["items"]
            assert len(calls) == 1
            now[0] += 601
            cached = await asyncio.wait_for(restored.get(website_id, period), 0.5)
            assert cached["refreshing"] and cached["items"] == original["items"]
            await started.wait()
            release.set()
            await asyncio.gather(*restored.pending.values())
            stale = await restored.get(website_id, period)
            assert stale["status"] == "stale" and stale["items"] == original["items"]
            assert stale["fetched_at"] == 2000
            with Session(core.engine) as session:
                assert session.scalar(select(HotlistSnapshot)).fetched_at == 2000
        finally:
            release.set()
            await restored.aclose()
        assert core.count(Outbox) == core.count(Post) == core.count(SeenPost) == 0

    asyncio.run(run())


@pytest.mark.parametrize("invalid", ["expired", "invalid_identity", "too_many_items"])
def test_invalid_or_expired_disk_snapshot_is_not_used_as_current_content(core, invalid):
    async def run():
        now = 100000
        data = parse_linuxdo_snapshot(linuxdo_rss(9001), now - 10)
        if invalid == "invalid_identity":
            data["items"][0]["id"] = "../9001"
        elif invalid == "too_many_items":
            data["items"] *= 101
        else:
            data["fetched_at"] = now - 86401
        with write_session(core.engine) as session:
            session.add(
                HotlistSnapshot(
                    website_id="linuxdo",
                    provider_id="linuxdo-rss",
                    period="hot",
                    **data,
                )
            )
        calls = []

        async def handler(request):
            calls.append(request)
            return httpx.Response(
                200,
                headers={"Content-Type": "application/rss+xml"},
                stream=Chunks(linuxdo_rss(9002)),
            )

        service = HotlistService(
            engine=core.engine, transport=httpx.MockTransport(handler), clock=lambda: now
        )
        try:
            current = await service.get("linuxdo", "hot")
            assert current["status"] == "ready"
            assert [item["id"] for item in current["items"]] == ["9002"]
            assert len(calls) == 1
        finally:
            await service.aclose()

    asyncio.run(run())
