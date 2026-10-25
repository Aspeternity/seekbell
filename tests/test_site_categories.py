"""Per-site category identity, immutable legacy upgrade and read-only diagnosis."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from seekbell.config import Settings
from seekbell.db.models import Outbox, Task, TaskVersion
from seekbell.db.runtime import create_database_engine, migrate, schema_revision
from seekbell.domain.posts import PostBatch, PostFields
from seekbell.domain.rules import Rule, evaluate
from seekbell.main import create_app
from seekbell.services.configuration import Configuration
from seekbell.services.history import post_key
from seekbell.services.post_diagnosis import PostDiagnosis
from seekbell.services.rule_trial import trial_history
from seekbell.services.rule_values import normalized_rule
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from tests.core_helpers import batch
from tests.test_management import authenticate, target, task_values
from tests.test_management_operations import tables
from tests.test_task_websites import enable_linux


def scoped(node=("trade",), linux=()):
    return Rule(
        site_categories={
            key: {"mode": "specific" if values else "all", "values": list(values)}
            for key, values in (("nodeseek", node), ("linuxdo", linux))
        }
    )


@pytest.mark.parametrize(
    ("site", "category", "expected"),
    [
        ("nodeseek", "trade", "match"),
        ("linuxdo", "trade", "no_match"),
        ("linuxdo", "tech", "match"),
        ("nodeseek", "tech", "no_match"),
        ("nodeseek", None, "insufficient_data"),
    ],
)
def test_category_identity_and_missing_values_are_site_specific(site, category, expected):
    assert (
        evaluate(scoped(linux=("tech",)), PostFields(category=category), website_id=site).status
        == expected
    )


def test_all_scope_and_three_valued_decisions_keep_existing_semantics():
    rule = scoped()
    assert evaluate(rule, PostFields(), website_id="linuxdo").status == "match"
    assert evaluate(rule, PostFields(), website_id="linuxdo").warnings == ("all_new_posts",)
    denied = rule.model_copy(update={"groups": Rule(groups=[{"all_of": ["VPS"]}]).groups})
    assert evaluate(denied, PostFields(title="other"), website_id="nodeseek").status == "no_match"
    for site in (None, "other"):
        with pytest.raises(ValueError):
            evaluate(rule, PostFields(), website_id=site)


@pytest.mark.parametrize(
    "scope",
    [
        {"mode": "specific", "values": []},
        {"mode": "specific", "values": [" "]},
        {"mode": "all", "values": ["trade"]},
        {"mode": "excluded", "values": ["trade"]},
    ],
)
def test_invalid_scope_never_degrades_to_all(scope):
    with pytest.raises(ValidationError):
        Rule(site_categories={"nodeseek": scope})


def test_one_writable_representation_and_per_site_normalization():
    with pytest.raises(ValidationError):
        Rule(categories=["trade"], site_categories={"nodeseek": {"mode": "all"}})
    with pytest.raises(ValidationError):
        Rule(site_categories={})
    rule = scoped(node=("交易",), linux=("交易",))
    normalized = normalized_rule(rule, ["nodeseek", "linuxdo"])
    assert normalized.categories_for("nodeseek") == ("trade",)
    assert normalized.categories_for("linuxdo") == ("交易",)
    assert rule.categories_for("nodeseek") == ("交易",)
    for sites in (["nodeseek"], ["nodeseek", "linuxdo", "unknown"]):
        with pytest.raises(ValueError):
            normalized_rule(rule, sites)


def test_new_scopes_validate_transactionally_and_legacy_rules_stay_shared(core):
    original = core.one(Task).current_version
    for scopes in (
        {"linuxdo": {"mode": "all"}},
        {"nodeseek": {"mode": "all"}, "linuxdo": {"mode": "all"}},
        {"unknown": {"mode": "all"}},
    ):
        with pytest.raises(ValueError):
            core.config.update_task(
                core.task,
                "Invalid",
                Rule(site_categories=scopes),
                [core.target],
                at=5,
                website_ids=["nodeseek"],
            )
    assert core.one(Task).current_version == original
    legacy = Rule(categories=["trade", "unseen-old-value"])
    assert legacy.categories_for("nodeseek") == legacy.categories_for("linuxdo")
    assert legacy.categories_for(None) == ("trade", "unseen-old-value")


def test_ingestion_trials_and_saved_diagnosis_use_the_same_site_scope(core):
    enable_linux(core)

    def linux(*ids, at):
        raw = batch(*ids, category="trade")
        posts = tuple(
            post.model_copy(
                update={
                    "website_id": "linuxdo",
                    "url": "https://linux.do/t/topic/" + post.external_post_id,
                }
            )
            for post in raw.posts
        )
        return core.ingestion.ingest("linuxdo-rss", PostBatch(posts, raw.raw_count, ()), at=at)

    core.ingest(9001, at=10, category="trade")
    linux(9001, at=11)
    version = core.config.update_task(
        core.task,
        "Independent",
        scoped(linux=("tech",)),
        [core.target],
        at=12,
        website_ids=["nodeseek", "linuxdo"],
    )
    assert core.ingest(9001, 9002, at=20, category="trade").hits == 1
    assert linux(9001, 9002, at=21).hits == 0
    assert core.count(Outbox) == 1
    diagnosis = PostDiagnosis(core.engine)
    key = post_key("linuxdo", "9002")
    old = diagnosis.detail(key, core.task, version)
    assert old["result"]["status"] == "no_match"
    assert old["category"]["expected"] == [{"value": "tech", "label": "tech"}]
    before = tables(core.engine)
    trial = trial_history(core.engine, ["nodeseek", "linuxdo"], scoped(linux=("tech",)), 4)
    statuses = {
        (row["website_id"], row["sample"]["category"]): row["result"]["status"]
        for row in trial["items"]
    }
    assert statuses == {("nodeseek", "trade"): "match", ("linuxdo", "trade"): "no_match"}
    assert diagnosis.trial(key, core.task)["result"]["status"] == "no_match"
    assert tables(core.engine) == before
    current = core.config.update_task(
        core.task, "Linux all", scoped(), [core.target], at=30, website_ids=["nodeseek", "linuxdo"]
    )
    unchanged = tables(core.engine)
    assert diagnosis.trial(key, core.task)["version"] == current
    assert diagnosis.trial(key, core.task)["result"]["status"] == "match"
    assert diagnosis.detail(key, core.task, version) == old
    assert tables(core.engine) == unchanged
    assert linux(9001, 9002, at=31).hits == 0


def test_schema_marker_preserves_every_existing_table_row_and_scope(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0015_category_values")
        config = Configuration(engine)
        target_id = config.create_target("Synthetic target")
        key = config.create_task(
            "Legacy mixed",
            Rule(categories=["trade", "unknown"]),
            [target_id],
            at=1,
            website_ids=["nodeseek", "linuxdo"],
        )

        def snapshot():
            result = {}
            with engine.connect() as connection:
                for name in inspect(engine).get_table_names():
                    if name == "alembic_version":
                        continue
                    result[name] = connection.exec_driver_sql('SELECT * FROM "' + name + '"').all()
            return result

        before = snapshot()
        migrate(engine)
        assert schema_revision(engine) == "0017_hotlist_settings"
        assert snapshot() == before
        migrate(engine)
        assert snapshot() == before
        with Session(engine) as session:
            assert session.get(Task, key).current_version == 1
            rule = Rule.model_validate(session.get(TaskVersion, (key, 1)).rule)
            assert rule.site_categories is None
            assert (
                rule.categories_for("nodeseek")
                == rule.categories_for("linuxdo")
                == ("trade", "unknown")
            )
    finally:
        engine.dispose()


def test_api_rejects_incomplete_scopes_and_uses_sample_website(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        authenticate(client)
        for site in ("nodeseek", "linuxdo"):
            assert client.post("/api/manage/websites", json={"adapter_id": site}).status_code == 201
        values = task_values(target(client))
        values.pop("website_id")
        values["website_ids"] = ["nodeseek", "linuxdo"]
        values["rule"] = scoped(node=("交易",), linux=("tech",)).model_dump(mode="json")
        created = client.post("/api/manage/tasks", json=values)
        assert created.status_code == 201
        key = created.json()["id"]
        row = client.get("/api/manage/workspace").json()["tasks"][0]
        assert row["rule"]["site_categories"]["nodeseek"]["values"] == ["trade"]
        assert row["rule"]["site_categories"]["linuxdo"]["values"] == ["tech"]
        before = client.get("/api/manage/workspace").json()
        invalid = {**values, "rule": {"site_categories": {"nodeseek": {"mode": "all"}}}}
        assert client.put("/api/manage/tasks/" + key, json=invalid).status_code == 422
        assert (
            client.post(
                "/api/manage/rules/history",
                json={"website_ids": values["website_ids"], "rule": invalid["rule"]},
            ).status_code
            == 422
        )
        for site, expected in (("nodeseek", "match"), ("linuxdo", "no_match")):
            response = client.post(
                "/api/manage/rules/evaluate",
                json={"rule": row["rule"], "post": {"category": "trade"}, "website_id": site},
            )
            assert response.status_code == 200
            assert response.json()["status"] == expected
        assert (
            client.post(
                "/api/manage/rules/evaluate",
                json={"rule": row["rule"], "post": {"category": "trade"}},
            ).status_code
            == 422
        )
        assert client.get("/api/manage/workspace").json() == before
