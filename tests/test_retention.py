import copy
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from seekbell.config import Settings
from seekbell.db.models import (
    Administrator,
    DeliveredPost,
    DeliveryAttempt,
    ManualDelivery,
    NotificationTarget,
    Outbox,
    OutboxContribution,
    Post,
    RetentionPolicy,
    RuleHit,
    SeenPost,
    SourceItem,
    SourceRun,
    SourceState,
    TargetTestAttempt,
    TaskEvaluation,
    TaskVersion,
)
from seekbell.db.runtime import create_database_engine, migrate, schema_revision
from seekbell.db.transactions import write_session
from seekbell.domain.delivery import SendResult
from seekbell.domain.rules import Rule
from seekbell.main import create_app
from seekbell.services.configuration import Configuration
from seekbell.services.delivery import DeliveryWorker
from seekbell.services.history import History
from seekbell.services.ingestion import Ingestion
from seekbell.services.retention import HistoryRetention
from sqlalchemy import event, inspect, select, text
from sqlalchemy.orm import Session

from tests.core_helpers import batch
from tests.history_helpers import seed_history
from tests.runtime_helpers import SyntheticScenario
from tests.test_management import authenticate
from tests.test_runtime import until


@pytest.fixture
def history(tmp_path):
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        authenticate(client)
        ids = seed_history(app.state.engine, app.state.vault)
        yield app, client, ids, Configuration(app.state.engine, app.state.vault)


def rows(engine, *models):
    with engine.connect() as connection:
        return {model.__tablename__: connection.execute(select(model)).all() for model in models}


LEDGERS = (SeenPost, DeliveredPost, SourceItem)
HISTORY = (
    Post,
    RuleHit,
    TaskEvaluation,
    Outbox,
    OutboxContribution,
    DeliveryAttempt,
    TargetTestAttempt,
    ManualDelivery,
    SourceRun,
)


def test_cleanup_removes_only_expired_readable_history_and_keeps_identity_and_queue(history):
    app, client, ids, config = history
    at = ids["base"] + 40 * 86400
    ledger = rows(app.state.engine, *LEDGERS)
    configuration = rows(
        app.state.engine, TaskVersion, NotificationTarget, SourceState, Administrator
    )
    cleaner = HistoryRetention(app.state.engine)
    result = cleaner.run_once(at=at)
    assert result["status"] == "cleaned"
    assert result["counts"]["deliveries"] == 3
    assert result["counts"]["posts"] == 6
    assert result["counts"]["tests"] == 1 and result["counts"]["source_runs"] == 27
    assert rows(app.state.engine, *LEDGERS) == ledger
    assert (
        rows(app.state.engine, TaskVersion, NotificationTarget, SourceState, Administrator)
        == configuration
    )
    with Session(app.state.engine) as session:
        assert len(session.scalars(select(Outbox)).all()) == 21
        assert session.get(Outbox, ids["leased"]).status == "leased"
        assert session.get(TargetTestAttempt, "history-test-unknown").finished_at is None
        assert (
            session.scalars(
                select(DeliveryAttempt).where(DeliveryAttempt.event_id == ids["sent"])
            ).all()
            == []
        )
    assert client.get("/api/manage/history/posts").json()["total"] == 21
    assert client.get("/api/manage/history/deliveries/" + ids["sent"]).status_code == 404
    assert cleaner.run_once(at=at + 1)["status"] == "backoff"
    with app.state.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    # Even new rules/targets cannot resurrect a previously observed post.
    fresh = config.create_target("New target")
    config.create_task("New rule", Rule(), [fresh], at=at)
    report = Ingestion(app.state.engine).ingest("nodeseek-rss", batch(8000, 8001, 8002), at=at + 2)
    # The seeded source is paused; re-enable only the internal synthetic source.
    assert report.status == "paused"
    config.set_source_enabled("nodeseek-rss", True, at=at + 3)
    config.set_website_enabled("nodeseek", True, at=at + 3)
    report = Ingestion(app.state.engine).ingest("nodeseek-rss", batch(8000, 8001, 8002), at=at + 4)
    assert report.new_posts == report.hits == report.queued == 0
    assert rows(app.state.engine, *LEDGERS) == ledger


def test_recent_cancellation_and_late_results_start_a_new_retention_window(history):
    app, _, ids, config = history
    at = ids["base"] + 40 * 86400
    worker = DeliveryWorker(app.state.engine, {})
    claim = worker.claim(at=ids["base"] + 400)
    config.set_target_enabled(ids["target"], False, at=at)
    worker.finish(claim, SendResult(status="success"), at=at + 1)
    with Session(app.state.engine) as session:
        active = session.get(Outbox, claim.event_id)
        assert active.completed_at == at + 1
        cancelled = session.scalars(select(Outbox).where(Outbox.status == "cancelled")).all()
        assert cancelled and all(item.completed_at == at for item in cancelled)
    HistoryRetention(app.state.engine).run_once(at=at + 2)
    with Session(app.state.engine) as session:
        assert session.get(Outbox, claim.event_id).status == "sent"
        assert session.scalars(select(Outbox).where(Outbox.status == "cancelled")).all()


def test_inflight_explicit_operations_survive_and_retained_manual_history_can_outlive_source(
    history,
):
    app, _, ids, _ = history
    at = ids["base"] + 40 * 86400
    with write_session(app.state.engine) as session:
        source = session.get(Outbox, ids["sent"])
        for key, finish in (
            ("old-manual", ids["base"] + 10),
            ("new-manual", at - 1),
            ("open-manual", None),
        ):
            session.add(
                ManualDelivery(
                    id=key,
                    source_event_id=source.id,
                    target_id=source.target_id,
                    target_snapshot=copy.deepcopy(source.target_snapshot),
                    payload=copy.deepcopy(source.payload),
                    started_at=ids["base"],
                    finished_at=finish,
                    result="unknown" if finish is None else "success",
                )
            )
        # An unfinished attempt protects a terminal event even if metadata is old.
        session.get(DeliveryAttempt, 1).finished_at = None
    HistoryRetention(app.state.engine).run_once(at=at)
    reader = History(app.state.engine)
    with Session(app.state.engine) as session:
        assert session.get(ManualDelivery, "old-manual") is None
        assert session.get(ManualDelivery, "open-manual")
        assert session.get(Outbox, ids["sent"])  # unfinished attempt protection
    with write_session(app.state.engine) as session:
        session.get(DeliveryAttempt, 1).finished_at = ids["base"] + 61
        session.get(RetentionPolicy, 1).next_run_at = 0
    HistoryRetention(app.state.engine).run_once(at=at + 1)
    detail = reader.get_manual("new-manual")
    assert detail["source_event_id"] == ids["sent"]
    assert not detail["source_exists"]
    assert detail["result"] == "success"


def test_expiry_boundary_batches_and_restart_continue_without_touching_new_rows(history):
    app, _, ids, _ = history
    at = ids["base"] + 30 * 86400
    # Exactly-at-cutoff rows remain. Then advance one day and prune in tiny batches.
    cleaner = HistoryRetention(app.state.engine, batch_size=2)
    first = cleaner.run_once(at=at)
    assert first["counts"]["posts"] == first["counts"]["deliveries"] == 0
    totals = dict.fromkeys(first["counts"], 0)
    for i in range(100):
        cleaner = HistoryRetention(app.state.engine, batch_size=2)
        result = cleaner.run_once(at=at + 86400 + i)
        assert result["status"] == "cleaned"
        assert result["counts"]["posts"] <= 2 and result["counts"]["deliveries"] <= 2
        for key, value in result["counts"].items():
            totals[key] += value
        if not result["more"]:
            break
    else:
        raise AssertionError("Cleanup did not finish")
    assert totals["posts"] == 6 and totals["deliveries"] == 3
    assert cleaner.run_once(at=at + 86400 + 101)["status"] == "backoff"


def test_cleanup_failure_rolls_back_children_parents_and_checkpoint(history):
    app, _, ids, _ = history
    before = rows(app.state.engine, *HISTORY, RetentionPolicy, *LEDGERS)

    def fail(_c, _cursor, statement, _params, _context, _many):
        if statement.startswith("DELETE FROM posts"):
            raise RuntimeError("synthetic cleanup failure")

    event.listen(app.state.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="synthetic cleanup failure"):
            HistoryRetention(app.state.engine).run_once(at=ids["base"] + 40 * 86400)
    finally:
        event.remove(app.state.engine, "before_cursor_execute", fail)
    assert rows(app.state.engine, *HISTORY, RetentionPolicy, *LEDGERS) == before
    assert (
        HistoryRetention(app.state.engine).run_once(at=ids["base"] + 40 * 86400)["status"]
        == "cleaned"
    )


def test_cleanup_and_queue_claim_are_serialized_without_deleting_pending(history):
    app, _, ids, _ = history
    ledger = rows(app.state.engine, *LEDGERS)
    worker = DeliveryWorker(app.state.engine, {})
    at = ids["base"] + 40 * 86400
    with ThreadPoolExecutor(max_workers=2) as pool:
        cleanup = pool.submit(HistoryRetention(app.state.engine).run_once, at=at)
        delivery = pool.submit(worker.claim, at=at)
        assert cleanup.result()["status"] == "cleaned"
        claim = delivery.result()
    assert claim is not None
    assert worker.finish(claim, SendResult(status="success"), at=at + 1)
    with Session(app.state.engine) as session:
        assert session.get(Outbox, claim.event_id).status == "sent"
    assert rows(app.state.engine, SeenPost, SourceItem) == {
        k: v for k, v in ledger.items() if k != "delivered_posts"
    }


def test_retention_policy_auth_revision_validation_persistence_and_no_cleanup_on_api_read(tmp_path):
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/manage/retention").status_code == 401
        authenticate(client)
        initial = client.get("/api/manage/retention")
        assert initial.headers["cache-control"] == "no-store"
        assert initial.json()["days"] == 30 and initial.json()["last_run_at"] is None
        revision = initial.json()["revision"]
        for bad in (0, 366, 1.5, True, "30"):
            assert (
                client.put(
                    "/api/manage/retention", json={"days": bad, "revision": revision}
                ).status_code
                == 422
            )
        csrf = client.headers.pop("X-CSRF-Token")
        assert (
            client.put("/api/manage/retention", json={"days": 1, "revision": revision}).status_code
            == 403
        )
        client.headers["X-CSRF-Token"] = csrf
        assert (
            client.put("/api/manage/retention", json={"days": 90, "revision": revision}).status_code
            == 200
        )
        assert client.get("/api/manage/workspace").json()["settings"]["retention"] == 90
        assert (
            client.put("/api/manage/retention", json={"days": 1, "revision": revision}).status_code
            == 409
        )
        assert client.get("/api/manage/retention").json()["last_run_at"] is None
    with TestClient(create_app(settings)) as client:
        authenticate(client, setup=False)
        assert client.get("/api/manage/retention").json()["days"] == 90


def test_new_installation_does_not_clean_before_initialization_and_runtime_runs_without_browser(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path)
    scenario = SyntheticScenario()

    def factory(engine, notifiers):
        runtime = scenario.factory(engine, notifiers)
        runtime.retention.clock = lambda: 2000000000

        async def idle(stop):
            await stop.wait()

        runtime.source.run = idle
        runtime.worker.run = idle
        return runtime

    app = create_app(settings, runtime_factory=factory)
    with TestClient(app) as client:
        time.sleep(0.1)
        with Session(app.state.engine) as session:
            assert session.get(RetentionPolicy, 1).last_run_at is None
        authenticate(client)
        seed_history(app.state.engine, app.state.vault)
        with write_session(app.state.engine) as session:
            session.get(RetentionPolicy, 1).next_run_at = 0
        # No API request is needed to trigger cleanup.
        until(lambda: History(app.state.engine).list_posts()["total"] < 27)
        assert not scenario.fetches
        assert "retention" in app.state.runtime.tasks
    assert all(task.done() for task in app.state.runtime.tasks.values())


def test_retention_migration_preserves_existing_data_and_rolls_back_atomically(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0007_management_operations")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO notification_targets(id,name,kind,revision,enabled) "
                    "VALUES('old','Old','mock',1,0)"
                )
            )
            connection.execute(text("INSERT INTO seen_posts VALUES('nodeseek','1',1)"))
            for status in ("sent", "pending"):
                connection.execute(
                    text("INSERT INTO seen_posts VALUES('nodeseek',:id,1)"), {"id": status}
                )
                connection.execute(
                    text(
                        "INSERT INTO outbox(id,website_id,external_post_id,"
                        "target_id,target_snapshot,payload,status,attempt_count,"
                        "available_at,cancel_requested,uncertain,created_at) "
                        "VALUES(:id,'nodeseek',:id,'old','{}','{}',:status,0,1,0,0,1)"
                    ),
                    {"id": status, "status": status},
                )

        def fail(_c, _cursor, statement, _params, _context, _many):
            if "CREATE TABLE retention_policy" in statement:
                raise RuntimeError("synthetic retention migration fault")

        event.listen(engine, "before_cursor_execute", fail)
        try:
            with pytest.raises(RuntimeError):
                migrate(engine)
        finally:
            event.remove(engine, "before_cursor_execute", fail)
        assert schema_revision(engine) == "0007_management_operations"
        assert "completed_at" not in {c["name"] for c in inspect(engine).get_columns("outbox")}
        before = time.time() - 1
        migrate(engine)
        migrate(engine)
        with Session(engine) as session:
            assert session.get(RetentionPolicy, 1).days == 30
            assert session.get(Outbox, "sent").completed_at >= before
            assert session.get(Outbox, "pending").completed_at is None
    finally:
        engine.dispose()
