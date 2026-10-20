import json

import pytest
from fastapi.testclient import TestClient
from seekbell.api.overview import snapshot_time
from seekbell.config import Settings
from seekbell.db.models import (
    DeliveredPost,
    Outbox,
    Post,
    RuleHit,
    SourceRun,
    SourceState,
    TaskEvaluation,
)
from seekbell.db.transactions import write_session
from seekbell.main import create_app
from seekbell.services.overview import overview
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from tests.history_helpers import PRIVATE, seed_history
from tests.test_management import authenticate


@pytest.fixture
def records(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, static_dir=tmp_path / "static"))
    with TestClient(app) as client:
        authenticate(client)
        ids = seed_history(app.state.engine, app.state.vault)
        app.dependency_overrides[snapshot_time] = lambda: ids["base"] + 86400
        yield app, client, ids


def test_overview_aggregates_persisted_records_without_duplicate_attempts_or_test_sends(records):
    app, client, ids = records
    with Session(app.state.engine) as session:
        before = "\n".join(session.connection().connection.driver_connection.iterdump())
        source = session.get(SourceState, "nodeseek-rss")
        last_success = source.last_success_at
    response = client.get("/api/manage/overview")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["configuration"] == {"websites": 1, "tasks": 1, "enabled_tasks": 1, "targets": 1}
    assert data["window"] == {
        "posts": 27,
        "matches": 24,
        "insufficient_data": 1,
        "delivered": 2,
        "source_failures": 0,
    }
    assert data["current"]["attention"] == 3
    assert data["current"]["uncertain"] == 2
    assert data["current"]["queue"] == {"sent": 2, "failed": 1, "leased": 1, "pending": 20}
    assert not data["runtime_active"]
    assert len(data["buckets"]) == 24
    assert sum(b["matches"] for b in data["buckets"]) == 24
    assert data["buckets"][0]["matches"] == 24
    assert len(data["recent_matches"]) == 5
    assert all(r["task_name"] == "摘要关注" for r in data["recent_matches"])
    assert data["sources"][0]["last_success_at"] == last_success
    assert not data["sources"][0]["enabled"]
    assert PRIVATE not in response.text and "ciphertext" not in response.text
    assert "lease_token" not in response.text and "result" not in data["recent_matches"][0]
    with Session(app.state.engine) as session:
        assert "\n".join(session.connection().connection.driver_connection.iterdump()) == before


def test_time_windows_are_half_open_and_buckets_sum_to_match_count(records):
    app, client, ids = records
    end = ids["base"] + 86400
    with write_session(app.state.engine) as session:
        session.execute(update(TaskEvaluation).values(evaluated_at=ids["base"] - 2))
        session.execute(update(RuleHit).values(matched_at=ids["base"] - 2))
        matches = session.scalars(
            select(TaskEvaluation).where(TaskEvaluation.status == "match").limit(4)
        ).all()
        for row, at in zip(
            matches, [ids["base"] - 1, ids["base"], ids["base"] + 3600, end], strict=True
        ):
            row.evaluated_at = at
        receipts = session.scalars(select(DeliveredPost)).all()
        receipts[0].delivered_at = ids["base"]
        receipts[1].delivered_at = end
        session.add_all(
            [
                SourceRun(source_id="nodeseek-rss", at=ids["base"], status="failure"),
                SourceRun(source_id="nodeseek-rss", at=end, status="failure"),
            ]
        )
    data = client.get("/api/manage/overview").json()
    assert data["window"]["matches"] == 2
    assert [b["matches"] for b in data["buckets"][:2]] == [1, 1]
    assert sum(b["matches"] for b in data["buckets"]) == 2
    assert data["window"]["delivered"] == 1
    assert data["window"]["source_failures"] == 1
    week = client.get("/api/manage/overview?range=7d").json()
    assert len(week["buckets"]) == 7
    assert week["window"]["matches"] == 23
    assert sum(b["matches"] for b in week["buckets"]) == 23
    # Current attention covers all retained events, independently of selected window.
    assert data["current"] == week["current"]


def test_legacy_matches_and_pruned_content_keep_statistics_and_snapshot_names(records):
    app, client, ids = records
    with write_session(app.state.engine) as session:
        session.execute(
            delete(TaskEvaluation).where(
                TaskEvaluation.task_id == ids["primary"], TaskEvaluation.external_post_id == "8026"
            )
        )
        session.execute(delete(Post).where(Post.external_post_id == "8026"))
        session.get(SourceState, "nodeseek-rss").last_error_code = PRIVATE + "/url"
        session.get(SourceState, "nodeseek-rss").failures = 2
        session.get(SourceState, "nodeseek-rss").possible_gap = True
    data = client.get("/api/manage/overview").json()
    assert data["window"]["matches"] == 24
    assert data["window"]["posts"] == 26
    assert data["recent_matches"][0]["title"] is None
    assert data["recent_matches"][0]["post_id"] is None
    assert data["recent_matches"][0]["task_name"] == "摘要关注"
    assert data["sources"][0]["error_code"] is None
    assert data["sources"][0]["possible_gap"]
    assert PRIVATE not in json.dumps(data)


def test_empty_database_is_zero_and_api_is_protected_and_validated(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, static_dir=tmp_path / "static"))
    with TestClient(app) as client:
        assert client.get("/api/manage/overview").status_code == 401
        authenticate(client)
        assert client.get("/api/manage/overview?range=invalid").status_code == 422
        data = client.get("/api/manage/overview").json()
        assert not any(data["window"].values())
        assert not any(data["configuration"].values())
        assert data["recent_matches"] == [] and data["sources"] == []
        assert all(b["matches"] == 0 for b in data["buckets"])


def test_overview_has_one_read_snapshot_during_concurrent_ingestion(records):
    from sqlalchemy import event

    app, client, ids = records
    engine = app.state.engine
    changed = False

    def insert_after_first_read(connection, cursor, statement, parameters, context, many):
        nonlocal changed
        if not changed and statement.lstrip().startswith("SELECT"):
            changed = True
            with write_session(engine) as session:
                session.execute(update(TaskEvaluation).values(status="no_match"))
                session.execute(update(Outbox).values(uncertain=False))

    event.listen(engine, "after_cursor_execute", insert_after_first_read)
    try:
        data = overview(engine, at=ids["base"] + 86400)
    finally:
        event.remove(engine, "after_cursor_execute", insert_after_first_read)
    assert changed
    assert data["window"]["matches"] == sum(b["matches"] for b in data["buckets"]) == 24
    assert data["current"]["uncertain"] == 2
    assert overview(engine, at=ids["base"] + 86400)["window"]["matches"] == 0
