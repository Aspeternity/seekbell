import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from seekbell.config import Settings
from seekbell.db.models import Outbox, Post, RuleHit, TaskEvaluation
from seekbell.db.runtime import create_database_engine, migrate, schema_revision
from seekbell.db.transactions import write_session
from seekbell.main import create_app
from seekbell.services.history import History, date_window, post_key
from sqlalchemy import event, inspect, select, text
from sqlalchemy.orm import Session

from tests.history_helpers import PRIVATE, seed_history
from tests.test_management import authenticate


@pytest.fixture
def history_client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, static_dir=tmp_path / "static"))
    with TestClient(app) as client:
        authenticate(client)
        ids = seed_history(app.state.engine, app.state.vault)
        yield client, app, ids


def test_filtering_uses_saved_three_state_decisions_not_current_rule(history_client):
    client, app, ids = history_client
    response = client.get("/api/manage/history/posts")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 27 and len(data["items"]) == 20
    assert data["summary"]["not_evaluated"] == 1
    for index, expected in (
        (0, "not_evaluated"),
        (1, "match"),
        (2, "match"),
        (3, "insufficient_data"),
        (4, "no_match"),
    ):
        value = client.get("/api/manage/history/posts/" + ids["posts"][index]).json()
        assert value["status"] == expected
    # Task was renamed and its current rule now matches everything. History stays no_match.
    data = client.get(
        "/api/manage/history/posts", params={"task_id": ids["primary"], "status": "no_match"}
    ).json()
    assert {p["id"] for p in data["items"]} == {ids["posts"][2], ids["posts"][4]}
    result = client.get("/api/manage/history/posts/" + ids["posts"][2] + "/evaluations").json()
    assert result["total"] == 2
    assert {r["name"] for r in result["items"]} == {"摘要关注", "特别标题关注"}
    assert all(r["version"] == 1 for r in result["items"])
    assert any(r["deleted"] for r in result["items"])
    with Session(app.state.engine) as session:
        assert len(session.scalars(select(TaskEvaluation)).all()) == 52


def test_stable_server_pagination_literal_search_and_filters(history_client):
    client, _, ids = history_client
    url = "/api/manage/history/posts"
    first = client.get(url, params={"page_size": 5}).json()
    second = client.get(url, params={"page_size": 5, "page": 2}).json()
    assert first["total"] == second["total"] == 27
    assert not {x["id"] for x in first["items"]} & {x["id"] for x in second["items"]}
    assert client.get(url, params={"q": "%_"}).json()["total"] == 1
    assert client.get(url, params={"q": "READING-absent"}).json()["total"] == 0
    assert client.get(url, params={"category": "优惠"}).json()["total"] == 14
    assert client.get(url, params={"website_id": "absent"}).json()["total"] == 0
    assert (
        client.get(url, params={"discovered_on": "2026-10-19", "timezone": "Asia/Shanghai"}).json()[
            "total"
        ]
        == 27
    )
    assert (
        client.get(
            url, params={"discovered_on": "2026-10-18", "timezone": "America/Los_Angeles"}
        ).json()["total"]
        == 27
    )
    assert client.get(url, params={"page": 100}).json()["items"] == []
    options = client.get("/api/manage/history/options").json()
    assert any(t["id"] == ids["secondary"] and t["deleted"] for t in options["tasks"])


def test_delivery_status_uncertainty_snapshot_and_attempt_pages(history_client):
    client, _, ids = history_client
    url = "/api/manage/history/deliveries"
    item = client.get(url + "/" + ids["late"]).json()
    assert item["status"] == "sent" and item["uncertain"]
    assert item["target_name"] == "历史 Webhook 名称"
    assert item["tasks"]["items"][0]["name"] == "摘要关注"
    assert item["attempts"]["total"] == 2 and item["receipt_at"] == ids["base"] + 341
    assert item["attempts"]["items"][0]["result"] == "unknown"
    assert item["attempts"]["items"][0]["late_result"] == "success"
    data = client.get(url + "/" + ids["late"], params={"page_size": 1, "attempt_page": 2}).json()
    assert data["attempts"]["items"][0]["sequence"] == 2
    data = client.get(url, params={"status": "sent", "uncertain": True}).json()
    assert data["total"] == 2 and all(
        r["status"] == "sent" and r["uncertain"] for r in data["items"]
    )
    assert client.get(url, params={"status": "failed"}).json()["total"] == 1
    assert client.get(url, params={"q": "历史 Webhook 名称"}).json()["total"] == 24
    assert client.get(url, params={"q": "当前目标名称"}).json()["total"] == 0
    assert (
        client.get(url, params={"post_id": ids["posts"][2]}).json()["items"][0]["id"]
        == ids["failed"]
    )


def test_history_is_readonly_and_never_serializes_credentials_or_leases(history_client):
    client, app, ids = history_client
    with app.state.engine.connect() as connection:
        before = "\n".join(connection.connection.driver_connection.iterdump())
    urls = [
        "/api/manage/history/options",
        "/api/manage/history/posts",
        "/api/manage/history/posts/" + ids["posts"][1],
        "/api/manage/history/posts/" + ids["posts"][1] + "/evaluations",
        "/api/manage/history/deliveries",
        "/api/manage/history/deliveries/" + ids["leased"],
        "/api/manage/history/tests",
        "/api/manage/history/tests/history-test-unknown",
    ]
    with Session(app.state.engine) as session:
        leased = session.get(Outbox, ids["leased"]).lease_token
    for url in urls:
        response = client.get(url)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        assert PRIVATE not in response.text and leased not in response.text
        assert not any(
            key in response.text for key in ("config_ciphertext", "lease_token", "csrf", "headers")
        )
    with app.state.engine.connect() as connection:
        after = "\n".join(connection.connection.driver_connection.iterdump())
    assert before == after
    assert client.post("/api/manage/history/posts", json={}).status_code == 405
    client.post("/api/auth/logout")
    assert client.get("/api/manage/history/posts").status_code == 401


def test_independent_test_records_and_pruned_post_snapshot(history_client):
    client, app, ids = history_client
    tests = client.get("/api/manage/history/tests").json()
    assert tests["total"] == 2
    pending = client.get("/api/manage/history/tests/history-test-unknown").json()
    assert pending["result"] == "unknown" and pending["finished_at"] is None
    assert (
        client.get("/api/manage/history/tests", params={"status": "success"}).json()["total"] == 1
    )
    with write_session(app.state.engine) as session:
        session.delete(session.get(Post, ("nodeseek", "8001")))
    assert client.get("/api/manage/history/posts/" + ids["posts"][1]).status_code == 404
    delivery = client.get("/api/manage/history/deliveries/" + ids["sent"]).json()
    assert delivery["post_id"] is None and delivery["title"] == "读取样本 01"
    assert delivery["post"]["original_url"] == "https://www.nodeseek.com/post-8001-1"


def test_invalid_filters_and_unknown_records_are_distinct_from_empty_results(history_client):
    client, _, _ = history_client
    url = "/api/manage/history/posts"
    for params in (
        {"page": 0},
        {"page_size": 101},
        {"status": "made-up"},
        {"q": "x" * 201},
        {"timezone": "Unknown/Zone"},
        {"discovered_on": "invalid"},
        {"discovered_on": "9999-12-31"},
    ):
        assert client.get(url, params=params).status_code == 422
    for suffix in ("not-base64", "%%%", post_key("nodeseek", "absent")):
        assert client.get(url + "/" + suffix).status_code == 404
    assert client.get("/api/manage/history/deliveries/missing").status_code == 404
    assert client.get("/api/manage/history/tests/missing").status_code == 404
    assert client.get(url, params={"q": "no-such-content"}).json()["total"] == 0


def test_date_window_uses_iana_timezone_including_dst():
    start, end = date_window(date(2026, 11, 1), "America/Los_Angeles")
    assert end - start == 25 * 3600
    assert (
        date_window(date(2026, 3, 8), "America/Los_Angeles")[1]
        - date_window(date(2026, 3, 8), "America/Los_Angeles")[0]
        == 23 * 3600
    )


def test_legacy_migration_preserves_known_hits_and_unknown_missing_decisions(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0004_management")
        from seekbell.domain.rules import Rule

        # Seed the historical schema directly; current ORM includes later columns.
        task = "legacy-task"
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO notification_targets(id,name,kind,revision,enabled) "
                    "VALUES ('legacy-target','legacy mock','mock',1,1)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO tasks(id,website_id,current_version,enabled,created_at) "
                    "VALUES (:id,'nodeseek',1,1,1)"
                ),
                {"id": task},
            )
            connection.execute(
                text(
                    "INSERT INTO task_versions(task_id,version,name,rule,target_ids,created_at) "
                    "VALUES (:id,1,'Old version name',:rule,:targets,1)"
                ),
                {"id": task, "rule": Rule().model_dump_json(), "targets": '["legacy-target"]'},
            )
            for key in ("7001", "7002"):
                connection.execute(
                    text("INSERT INTO seen_posts VALUES ('nodeseek',:id,1)"), {"id": key}
                )
                connection.execute(
                    text(
                        "INSERT INTO posts (website_id,external_post_id,title,url,first_seen_at) "
                        "VALUES ('nodeseek',:id,'legacy','javascript:private',1)"
                    ),
                    {"id": key},
                )
            connection.execute(
                text(
                    "INSERT INTO rule_hits VALUES ('old-hit',:task,1,'nodeseek','7001',:reason,1)"
                ),
                {"task": task, "reason": json.dumps({"status": "match", "reasons": []})},
            )
        migrate(engine)
        migrate(engine)
        reader = History(engine)
        known = reader.get_post(post_key("nodeseek", "7001"))
        absent = reader.get_post(post_key("nodeseek", "7002"))
        assert known["status"] == "match" and known["baseline"] is None
        assert absent["status"] == "unrecorded" and absent["original_url"] is None
        assert reader.evaluations(known["id"])["total"] == 1
        with Session(engine) as session:
            assert session.scalars(select(TaskEvaluation)).all() == []
            assert len(session.scalars(select(RuleHit)).all()) == 1
    finally:
        engine.dispose()


def test_history_migration_failure_rolls_back_columns_and_revision(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0004_management")

        def fail(_c, _cursor, statement, _p, _ctx, _many):
            if "CREATE TABLE task_evaluations" in statement:
                raise RuntimeError("synthetic history fault")

        event.listen(engine, "before_cursor_execute", fail)
        with pytest.raises(RuntimeError, match="history fault"):
            migrate(engine)
        event.remove(engine, "before_cursor_execute", fail)
        assert schema_revision(engine) == "0004_management"
        assert "baseline" not in {c["name"] for c in inspect(engine).get_columns("posts")}
        migrate(engine)
        assert schema_revision(engine) == "0007_management_operations"
    finally:
        engine.dispose()


def test_decision_ledger_rolls_back_with_outbox_and_duplicate_ingestion_does_not_rewrite(core):
    core.ingest(9001, at=10)

    def fail(_c, _cursor, statement, _p, _ctx, _many):
        if "INSERT INTO outbox " in statement:
            raise RuntimeError("synthetic outbox fault")

    event.listen(core.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="outbox fault"):
            core.ingest(9001, 9002, at=20)
    finally:
        event.remove(core.engine, "before_cursor_execute", fail)
    assert core.count(TaskEvaluation) == 0
    core.ingest(9001, 9002, at=20)
    assert core.count(TaskEvaluation) == 1
    with Session(core.engine) as session:
        before = session.scalars(select(TaskEvaluation)).one().result
    core.ingest(9002, 9001, at=30)
    with Session(core.engine) as session:
        rows = session.scalars(select(TaskEvaluation)).all()
        assert len(rows) == 1 and rows[0].result == before


def test_read_snapshot_does_not_block_ingestion_or_change_mid_page(core):
    from concurrent.futures import ThreadPoolExecutor

    from seekbell.services.history import read_session
    from sqlalchemy import func

    core.queued()
    with read_session(core.engine) as session:
        count = select(func.count()).select_from(Post)
        assert session.scalar(count) == 2
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(core.ingest, 9001, 9002, 9003, at=30).result(timeout=5)
        assert session.scalar(count) == 2
    assert History(core.engine).list_posts()["total"] == 3
