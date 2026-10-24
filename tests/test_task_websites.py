import json

import pytest
from fastapi.testclient import TestClient
from seekbell.collectors.rss import parse_rss
from seekbell.config import Settings
from seekbell.db.models import (
    Outbox,
    RuleHit,
    Source,
    Task,
    TaskEvaluation,
    TaskVersion,
    Website,
)
from seekbell.db.runtime import create_database_engine, migrate, schema_revision
from seekbell.db.transactions import write_session
from seekbell.domain.rules import Rule
from seekbell.main import create_app
from seekbell.services.rule_trial import trial_history
from seekbell.sites.linuxdo import LinuxDoAdapter
from sqlalchemy import event, inspect, select, text
from sqlalchemy.orm import Session

from tests.linuxdo_helpers import linuxdo_rss
from tests.test_management import authenticate, target, task_values


def linux_ingest(core, *ids, at):
    return core.ingestion.ingest(
        "linuxdo-rss", LinuxDoAdapter().normalize(parse_rss(linuxdo_rss(*ids))), at=at
    )


def enable_linux(core):
    with write_session(core.engine) as session:
        session.get(Website, "linuxdo").enabled = True
        session.get(Source, "linuxdo-rss").enabled = True


def test_one_task_can_add_remove_and_restore_sites_without_replaying_or_rewriting_history(core):
    core.queued()
    old_event = core.one(Outbox)
    old_payload = json.dumps(old_event.payload, sort_keys=True)
    enable_linux(core)
    assert linux_ingest(core, 8000, at=25).baseline

    version = core.config.update_task(
        core.task,
        "Same purpose",
        Rule(),
        [core.target],
        at=30,
        website_ids=["nodeseek", "linuxdo"],
    )
    assert version == 2
    assert core.ingest(9002, 9003, at=35).hits == 1
    # The same numeric ID from another site is a different post.
    assert linux_ingest(core, 8000, 9002, at=40).hits == 1
    with Session(core.engine) as session:
        assert session.get(TaskVersion, (core.task, 1)).website_ids == ["nodeseek"]
        assert session.get(TaskVersion, (core.task, 2)).website_ids == ["nodeseek", "linuxdo"]
        assert session.get(Task, core.task).origin_website_id == "nodeseek"
        event = session.get(Outbox, old_event.id)
        assert json.dumps(event.payload, sort_keys=True) == old_payload
        assert event.payload["matched_tasks"][0]["version"] == 1
        hits = session.scalars(select(RuleHit).where(RuleHit.task_version == 2)).all()
        assert {(hit.website_id, hit.external_post_id) for hit in hits} == {
            ("nodeseek", "9003"),
            ("linuxdo", "9002"),
        }
    core.config.update_task(
        core.task, "Same purpose", Rule(), [core.target], at=45, website_ids=["linuxdo"]
    )
    assert core.ingest(9004, at=50).hits == 0
    assert linux_ingest(core, 9003, at=55).hits == 1
    core.config.update_task(
        core.task,
        "Same purpose",
        Rule(),
        [core.target],
        at=60,
        website_ids=["nodeseek", "linuxdo"],
    )
    assert core.ingest(9002, 9003, 9004, at=65).hits == 0
    assert core.count(Outbox) == 4
    assert core.count(Task) == 1
    assert core.count(TaskEvaluation) == 4


def test_multisite_scope_is_validated_without_silently_dropping_existing_author_rules(core):
    before = core.one(Task).current_version
    for sites in ([], ["unknown"], ["nodeseek", "linuxdo"]):
        rule = Rule(authors_include=["synthetic-user"]) if len(sites) == 2 else Rule()
        with pytest.raises(ValueError):
            core.config.update_task(
                core.task, "Existing", rule, [core.target], at=30, website_ids=sites
            )
    assert core.one(Task).current_version == before


def test_multisite_history_trial_has_one_limit_labels_sites_and_never_writes(core):
    core.queued()
    enable_linux(core)
    linux_ingest(core, 9002, at=25)
    linux_ingest(core, 9003, at=30)
    before = {model: core.count(model) for model in (TaskVersion, Outbox, RuleHit, TaskEvaluation)}
    result = trial_history(core.engine, ["nodeseek", "linuxdo"], Rule(), 3)
    assert result["website_ids"] == ["nodeseek", "linuxdo"] and result["website_id"] is None
    assert result["available"] == 4 and result["sample_count"] == 3
    assert [item["website_id"] for item in result["items"]] == ["linuxdo", "linuxdo", "nodeseek"]
    assert {model: core.count(model) for model in before} == before


def test_api_edits_existing_task_sites_preserves_identity_and_checks_current_dependencies(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        authenticate(client)
        assert (
            client.post("/api/manage/websites", json={"adapter_id": "nodeseek"}).status_code == 201
        )
        target_id = target(client)
        original = task_values(target_id)
        created = client.post("/api/manage/tasks", json=original)
        assert created.status_code == 201
        key = created.json()["id"]
        multi = {k: v for k, v in original.items() if k != "website_id"}
        multi["website_ids"] = ["nodeseek", "linuxdo"]
        assert client.put("/api/manage/tasks/" + key, json=multi).status_code == 409
        assert (
            client.post("/api/manage/websites", json={"adapter_id": "linuxdo"}).status_code == 201
        )
        assert client.put("/api/manage/tasks/" + key, json=multi).json() == {"version": 2}
        row = client.get("/api/manage/workspace").json()["tasks"][0]
        assert row["id"] == key and row["website_ids"] == ["nodeseek", "linuxdo"]
        for field in ("name", "description", "rule", "target_ids", "enabled"):
            assert row[field] == original[field]
        assert client.delete("/api/manage/websites/linuxdo").status_code == 409
        trial = client.post(
            "/api/manage/rules/history",
            json={"website_ids": multi["website_ids"], "rule": {}, "limit": 2},
        )
        assert trial.status_code == 200 and trial.json()["website_ids"] == multi["website_ids"]
        # Target deletion also creates a version; it must carry the full website scope.
        preview = client.get("/api/manage/targets/" + target_id + "/delete-preview").json()
        assert (
            client.request(
                "DELETE",
                "/api/manage/targets/" + target_id,
                json={"confirmation": preview["confirmation"]},
            ).status_code
            == 200
        )
        row = client.get("/api/manage/workspace").json()["tasks"][0]
        assert row["website_ids"] == multi["website_ids"] and not row["enabled"]
        assert row["target_ids"] == [] and row["version"] == 3
        replacement = target(client, name="Replacement")
        single = {**multi, "website_ids": ["nodeseek"], "target_ids": [replacement]}
        assert client.put("/api/manage/tasks/" + key, json=single).status_code == 200
        assert client.delete("/api/manage/websites/linuxdo").status_code == 200
        with Session(app.state.engine) as session:
            assert session.get(TaskVersion, (key, 2)).website_ids == ["nodeseek", "linuxdo"]


@pytest.mark.parametrize(
    "selection",
    [
        {},
        {"website_ids": []},
        {"website_ids": ["nodeseek", "nodeseek"]},
        {"website_ids": ["unknown"]},
        {"website_ids": ["nodeseek"], "website_id": "linuxdo"},
    ],
)
def test_api_rejects_empty_unknown_duplicate_or_ambiguous_scope_without_writes(tmp_path, selection):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        authenticate(client)
        assert (
            client.post("/api/manage/websites", json={"adapter_id": "nodeseek"}).status_code == 201
        )
        values = task_values(target(client))
        values.pop("website_id")
        response = client.post("/api/manage/tasks", json={**values, **selection})
        assert response.status_code == 422
        assert client.get("/api/manage/workspace").json()["tasks"] == []


def seed_legacy_tasks(engine):
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO tasks(id,website_id,current_version,enabled,deleted_at,created_at) "
                "VALUES('node-task','nodeseek',2,1,NULL,10),('linux-task','linuxdo',1,0,20,11)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO task_versions(task_id,version,name,description,"
                "rule,target_ids,created_at) "
                "VALUES('node-task',1,'Old','note','{}','[]',10),"
                "('node-task',2,'Current','note','{}','[]',12),"
                "('linux-task',1,'Removed','note','{}','[]',11)"
            )
        )


def test_upgrade_backfills_all_historical_and_deleted_task_versions_without_changing_old_columns(
    tmp_path,
):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0013_site_order")
        seed_legacy_tasks(engine)
        with engine.connect() as connection:
            tasks = connection.execute(text("SELECT * FROM tasks ORDER BY id")).all()
            versions = connection.execute(
                text("SELECT * FROM task_versions ORDER BY task_id,version")
            ).all()
        migrate(engine)
        assert schema_revision(engine) == "0014_task_websites"
        with engine.connect() as connection:
            assert connection.execute(text("SELECT * FROM tasks ORDER BY id")).all() == tasks
            assert [
                row[:-1]
                for row in connection.execute(
                    text("SELECT * FROM task_versions ORDER BY task_id,version")
                )
            ] == versions
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
        with Session(engine) as session:
            assert session.get(TaskVersion, ("node-task", 1)).website_ids == ["nodeseek"]
            assert session.get(TaskVersion, ("node-task", 2)).website_ids == ["nodeseek"]
            assert session.get(TaskVersion, ("linux-task", 1)).website_ids == ["linuxdo"]
    finally:
        engine.dispose()


def test_failed_task_scope_migration_rolls_back_data_column_and_revision(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0013_site_order")
        seed_legacy_tasks(engine)

        def fail(_connection, _cursor, statement, _parameters, _context, _many):
            if "UPDATE task_versions SET website_ids" in statement:
                raise RuntimeError("synthetic task scope fault")

        event.listen(engine, "before_cursor_execute", fail)
        with pytest.raises(RuntimeError, match="task scope fault"):
            migrate(engine)
        event.remove(engine, "before_cursor_execute", fail)
        assert schema_revision(engine) == "0013_site_order"
        assert "website_ids" not in {
            c["name"] for c in inspect(engine).get_columns("task_versions")
        }
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM task_versions")).scalar() == 3
        migrate(engine)
    finally:
        engine.dispose()
