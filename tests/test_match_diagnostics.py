import pytest
from fastapi.testclient import TestClient
from seekbell.config import Settings
from seekbell.db.models import Outbox, Source, Task, TaskVersion
from seekbell.db.runtime import create_database_engine, migrate, schema_revision
from seekbell.db.transactions import write_session
from seekbell.domain.posts import PostFields
from seekbell.domain.rules import Rule, evaluate
from seekbell.main import create_app
from seekbell.services.configuration import Configuration
from seekbell.services.diagnosis import summarize
from seekbell.services.history import post_key
from seekbell.services.ingestion import Ingestion
from seekbell.services.post_diagnosis import PostDiagnosis
from seekbell.sites.categories import category_options, normalize_categories
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from tests.core_helpers import batch
from tests.test_management import authenticate, target, task_values
from tests.test_management_operations import tables


@pytest.mark.parametrize(
    ("sites", "values", "expected"),
    [
        (["nodeseek"], ["交易", "trade", "技术"], ["trade", "tech"]),
        (["nodeseek", "linuxdo"], ["交易"], ["交易", "trade"]),
        (["linuxdo"], ["交易"], ["交易"]),
        (["nodeseek"], ["优惠", "unknown"], ["优惠", "unknown"]),
    ],
)
def test_category_mapping_is_exact_and_does_not_guess(sites, values, expected):
    assert normalize_categories(values, sites) == expected
    assert (
        len([item for item in category_options("nodeseek", ["技术"]) if item["label"] == "技术"])
        == 1
    )


def legacy_engine(tmp_path, sites=None, deleted=False):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    migrate(engine, "0014_task_websites")
    config = Configuration(engine)
    target_id = config.create_target("Synthetic target")
    key = config.create_task(
        "Legacy category", Rule(), [target_id], at=1, website_ids=sites or ["nodeseek"]
    )
    old = Rule(categories=["交易"], groups=[{"all_of": ["VPS"]}]).model_dump(mode="json")
    with write_session(engine) as session:
        session.get(TaskVersion, (key, 1)).rule = old
        session.get(Source, "nodeseek-rss").enabled = True
        if deleted:
            session.get(Task, key).deleted_at = 2
    return engine, key, old


def test_repair_new_version_preserves_history_and_never_replays(tmp_path):
    engine, key, old = legacy_engine(tmp_path)
    try:
        ingestion = Ingestion(engine)
        ingestion.ingest("nodeseek-rss", batch(9001, category="trade"), at=10)
        ingestion.ingest("nodeseek-rss", batch(9001, 9002, category="trade"), at=20)
        before = tables(engine)
        migrate(engine)
        assert schema_revision(engine) == "0017_hotlist_settings"
        after = tables(engine)
        assert {k: v for k, v in after.items() if k != "task_versions"} == {
            k: v for k, v in before.items() if k != "task_versions"
        }
        with Session(engine) as session:
            assert session.get(Task, key).current_version == 2
            original = session.get(TaskVersion, (key, 1))
            assert original.rule == old
            fixed = session.get(TaskVersion, (key, 2))
            assert fixed.rule == {**old, "categories": ["trade"]}
            for field in ("name", "description", "target_ids", "website_ids"):
                assert getattr(fixed, field) == getattr(original, field)
            assert not session.scalars(select(Outbox)).all()
        diagnosis = PostDiagnosis(engine)
        saved = diagnosis.detail(post_key("nodeseek", "9002"), key, 1)
        assert saved["result"]["status"] == "no_match"
        assert saved["category"]["legacy_mismatch"]
        assert "标识不一致" in saved["explanation"]["headline"]
        readonly = tables(engine)
        current = diagnosis.trial(post_key("nodeseek", "9002"), key)
        assert current["version"] == 2 and current["result"]["status"] == "match"
        assert tables(engine) == readonly
        assert (
            ingestion.ingest("nodeseek-rss", batch(9001, 9002, category="trade"), at=30).hits == 0
        )
        assert (
            ingestion.ingest("nodeseek-rss", batch(9002, 9003, category="trade"), at=40).hits == 1
        )
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("sites", "deleted", "categories", "version"),
    [
        (["nodeseek", "linuxdo"], False, ["交易", "trade"], 2),
        (["linuxdo"], False, ["交易"], 1),
        (["nodeseek"], True, ["交易"], 1),
    ],
)
def test_migration_keeps_other_site_literals_deleted_tasks_and_status(
    tmp_path, sites, deleted, categories, version
):
    engine, key, _ = legacy_engine(tmp_path, sites, deleted)
    try:
        migrate(engine)
        with Session(engine) as session:
            task = session.get(Task, key)
            assert task.current_version == version and task.enabled
            assert session.get(TaskVersion, (key, version)).rule["categories"] == categories
    finally:
        engine.dispose()


def test_repair_rolls_back_atomically_and_is_idempotent(tmp_path):
    engine, key, old = legacy_engine(tmp_path)
    try:

        def fail(_connection, _cursor, statement, _parameters, _context, _many):
            if "UPDATE tasks SET current_version" in statement:
                raise RuntimeError("synthetic category repair fault")

        event.listen(engine, "before_cursor_execute", fail)
        with pytest.raises(RuntimeError, match="category repair fault"):
            migrate(engine)
        event.remove(engine, "before_cursor_execute", fail)
        assert schema_revision(engine) == "0014_task_websites"
        with Session(engine) as session:
            assert session.get(Task, key).current_version == 1
            assert session.get(TaskVersion, (key, 1)).rule == old
            assert session.get(TaskVersion, (key, 2)) is None
        migrate(engine)
        migrate(engine)
        with Session(engine) as session:
            assert session.get(Task, key).current_version == 2
    finally:
        engine.dispose()


def test_explanation_respects_or_groups_and_negative_conditions():
    rule = Rule(
        groups=[{"all_of": ["vmiss", "tri"]}, {"any_of": ["VPS", "CPU"]}],
        exclude=["求购"],
        authors_exclude=["blocked"],
        categories=["trade"],
    )
    result = evaluate(rule, PostFields(title="VPS offer", author="allowed", category="trade"))
    data = summarize(result.model_dump(mode="json"))
    assert result.status == "match" and not data["blockers"]
    assert all(check["state"] == "passed" for check in data["checks"])
    result = evaluate(rule, PostFields(title="求购 VPS", author="allowed", category="trade"))
    data = summarize(result.model_dump(mode="json"))
    assert data["blockers"] == ["触发排除词「求购」"]
    assert next(c for c in data["checks"] if c["code"] == "keywords")["state"] == "passed"


def test_picker_is_bounded_and_only_counts_saved_decisions(core):
    missing = Rule(groups=[{"all_of": ["absent"]}])
    core.config.update_task(core.task, "Task 000", missing, [core.target], at=2)
    core.ingest(9001, at=10)
    keys = [core.task]
    for index in range(1, 101):
        keys.append(core.config.create_task(f"Task {index:03}", missing, [core.target], at=11))
    core.ingest(9001, 9002, at=20)
    core.config.create_task("Later task", Rule(), [core.target], at=30)
    diagnosis = PostDiagnosis(core.engine)
    key = post_key("nodeseek", "9002")
    before = tables(core.engine)
    options = diagnosis.options(key, page_size=20, preferred_task_id=keys[-1])
    assert options["recorded_total"] == options["total"] == 101
    assert len(options["items"]) == 20 and options["preferred"]["task_id"] == keys[-1]
    assert all("result" not in row and "rule" not in row for row in options["items"])
    assert len(diagnosis.options(key, page=6, page_size=20)["items"]) == 1
    found = diagnosis.options(key, q="Task 100")
    assert found["total"] == 1 and found["items"][0]["task_id"] == keys[-1]
    assert diagnosis.options(key, q="%")["total"] == 0
    selected = diagnosis.detail(key, keys[-1], 1)
    assert selected["explanation"]["headline"] == "没有条件组满足关键词要求"
    assert tables(core.engine) == before
    with pytest.raises(LookupError):
        diagnosis.detail(post_key("nodeseek", "9001"), keys[-1], 1)


def test_trial_reports_removed_site_without_replacing_history(core):
    core.queued()
    core.config.update_task(
        core.task, "Changed scope", Rule(), [core.target], at=30, website_ids=["linuxdo"]
    )
    before = tables(core.engine)
    diagnosis = PostDiagnosis(core.engine)
    result = diagnosis.trial(post_key("nodeseek", "9002"), core.task)
    assert not result["applicable"] and result["result"] is None
    assert (
        diagnosis.detail(post_key("nodeseek", "9002"), core.task, 1)["result"]["status"] == "match"
    )
    assert tables(core.engine) == before


def test_api_catalog_and_diagnosis_authentication_and_csrf(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        assert client.get("/api/manage/history/posts/missing/evaluation-options").status_code == 401
        authenticate(client)
        client.post("/api/manage/websites", json={"adapter_id": "nodeseek"})
        site = client.get("/api/manage/workspace").json()["websites"][0]
        assert {"value": "trade", "label": "交易"} in site["categoryOptions"]
        values = task_values(target(client))
        values["rule"]["categories"] = ["交易"]
        key = client.post("/api/manage/tasks", json=values).json()["id"]
        saved = client.get("/api/manage/workspace").json()["tasks"][0]
        assert saved["rule"]["categories"] == ["trade"]
        response = client.post(
            "/api/manage/rules/evaluate",
            json={
                "website_id": "nodeseek",
                "rule": values["rule"],
                "post": {"title": "VPS offer", "category": "交易"},
            },
        )
        assert response.status_code == 200 and response.json()["status"] == "match"
        token = client.headers.pop("X-CSRF-Token")
        assert (
            client.post(
                "/api/manage/history/posts/missing/current-rule-trial", json={"task_id": key}
            ).status_code
            == 403
        )
        client.headers["X-CSRF-Token"] = token
        assert client.get("/api/manage/history/posts/missing/evaluation-options").status_code == 404
