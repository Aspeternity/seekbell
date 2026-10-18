import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from seekbell.config import Settings
from seekbell.db.models import (
    DeliveredPost,
    DeliveryAttempt,
    Outbox,
    OutboxContribution,
    Post,
    RuleHit,
    SeenPost,
    SourceItem,
    SourceState,
    TaskVersion,
    Website,
)
from seekbell.db.runtime import create_database_engine, migrate
from seekbell.db.transactions import write_session
from seekbell.domain.rules import ConditionGroup, Rule
from seekbell.services.delivery import DeliveryWorker
from seekbell.services.ingestion import Ingestion
from sqlalchemy import delete, event, select
from sqlalchemy.orm import Session

from tests.core_helpers import batch


def test_initial_failure_does_not_establish_baseline(core):
    core.ingestion.record_failure("nodeseek-rss", "http_503", at=1)
    assert not core.one(SourceState).initialized
    first = core.ingest(9001, 9002, at=10)
    assert first.baseline and first.new_posts == 2 and first.queued == 0
    assert core.one(SourceState).failures == 0
    assert core.one(SourceState).last_error_code is None
    next_poll = core.ingest(9002, 9003, at=20)
    assert (next_poll.new_posts, next_poll.hits, next_poll.queued) == (1, 1, 1)
    assert not next_poll.possible_gap


def test_duplicates_reordering_same_title_and_global_identity(core):
    core.queued()
    repeat = core.ingest(9002, 9001, 9002, at=30, guid="opaque-changed")
    assert repeat.new_posts == repeat.queued == 0
    assert core.ingest(9002, 9003, at=40).queued == 1
    assert core.count(SeenPost) == 3
    assert core.count(Outbox) == 2
    # Source entry identity is not the global post identity.
    assert core.count(SourceItem) >= 3
    with write_session(core.engine) as session:
        session.add(Website(id="synthetic-other", name="Synthetic", enabled=True))
        session.flush()
        session.add(
            SeenPost(
                website_id="synthetic-other",
                external_post_id="9002",
                first_seen_at=50,
            )
        )
    assert core.count(SeenPost) == 4


def test_window_gap_is_warning_and_does_not_invent_missing_count(core):
    core.ingest(9001)
    report = core.ingest(9010, 9011, at=110)
    assert report.possible_gap and report.new_posts == 2
    state = core.one(SourceState)
    assert state.possible_gap and state.window_count == 2 and state.last_gap_at == 110
    assert core.ingest(9011, 9012, at=120).possible_gap is False
    assert core.one(SourceState).possible_gap


def test_rule_versions_and_new_tasks_apply_only_to_future_posts(core):
    core.queued()
    other = core.config.create_task("Second", Rule(), [core.target], at=21)
    core.config.update_task(
        core.task,
        "Updated",
        Rule(groups=[ConditionGroup(all_of=["unmatched"])]),
        [core.target],
        at=22,
    )
    assert core.ingest(9002, at=30).queued == 0
    report = core.ingest(9002, 9003, at=40)
    assert report.hits == 1 and report.queued == 1
    with Session(core.engine) as session:
        events = session.scalars(select(Outbox).order_by(Outbox.created_at)).all()
        assert events[0].payload["matched_tasks"] == [
            {
                "id": core.task,
                "version": 1,
                "name": "Synthetic rule",
            }
        ]
        assert events[1].payload["matched_tasks"][0]["id"] == other
        assert session.get(TaskVersion, (core.task, 1)).name == "Synthetic rule"


def test_task_pause_keeps_ingesting_without_later_backfill(core):
    core.ingest(9001)
    core.config.set_task_enabled(core.task, False)
    assert core.ingest(9001, 9002, at=110).queued == 0
    core.config.set_task_enabled(core.task, True)
    assert core.ingest(9002, 9003, at=120).queued == 1
    assert core.one(Outbox).external_post_id == "9003"


@pytest.mark.parametrize("level", ["source", "website"])
def test_explicit_collection_pause_requires_new_baseline(core, level):
    core.ingest(9001)
    if level == "source":

        def toggle(enabled, at):
            core.config.set_source_enabled("nodeseek-rss", enabled, at=at)
    else:

        def toggle(enabled, at):
            core.config.set_website_enabled("nodeseek", enabled, at=at)

    toggle(False, 110)
    assert core.ingest(9002, at=120).status == "paused"
    toggle(True, 130)
    assert core.ingest(9002, at=140).baseline
    assert core.ingest(9002, 9003, at=150).queued == 1


def test_restart_preserves_seen_and_uncommitted_delivery_intent(core):
    core.queued()
    event_id = core.one(Outbox).id
    core.engine.dispose()
    engine = create_database_engine(Settings(data_dir=core.data_dir))
    try:
        migrate(engine)
        report = Ingestion(engine).ingest("nodeseek-rss", batch(9002, 9003), at=30)
        assert not report.baseline and report.queued == 1
        with Session(engine) as session:
            assert session.get(Outbox, event_id).status == "pending"
    finally:
        engine.dispose()


def test_atomic_ingestion_rolls_back_identity_hits_and_intents(core):
    core.ingest(9001)

    def fail(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("INSERT INTO outbox "):
            raise RuntimeError("synthetic transaction fault")

    event.listen(core.engine, "before_cursor_execute", fail)
    with pytest.raises(RuntimeError, match="synthetic transaction"):
        core.ingest(9002, at=110)
    event.remove(core.engine, "before_cursor_execute", fail)
    assert core.count(SeenPost) == core.count(Post) == 1
    assert core.count(RuleHit) == core.count(Outbox) == 0
    assert core.one(SourceState).last_success_at == 100
    assert core.ingest(9002, at=120).queued == 1


def test_process_death_before_commit_does_not_consume_post(core):
    core.ingest(9001)
    script = """
import os,sys
from pathlib import Path
from sqlalchemy import event
from seekbell.config import Settings
from seekbell.db.runtime import create_database_engine
from seekbell.services.ingestion import Ingestion
from tests.core_helpers import batch
e=create_database_engine(Settings(data_dir=Path(sys.argv[1])))
@event.listens_for(e, "before_cursor_execute")
def crash(c, cur, statement, params, ctx, many):
    if statement.startswith("INSERT INTO outbox "):
        os._exit(37)
Ingestion(e).ingest("nodeseek-rss",batch(9002),at=110)
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(core.data_dir)],
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 37, result.stderr
    assert core.count(SeenPost) == 1 and core.count(Outbox) == 0
    assert core.ingest(9002, at=120).queued == 1


def test_concurrent_poll_transactions_produce_one_intent(core):
    core.ingest(9001)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reports = list(pool.map(lambda _: core.ingest(9002, at=110), range(2)))
    assert sum(r.queued for r in reports) == 1
    assert core.count(RuleHit) == core.count(Outbox) == 1


def test_preview_is_read_only_and_insufficient_summary_is_not_match(core):
    core.config.update_task(
        core.task,
        "Needs summary",
        Rule(
            scope="summary",
            groups=[
                ConditionGroup(all_of=["VPS"]),
            ],
        ),
        [core.target],
        at=1,
    )
    core.ingest(9001)
    report = core.ingest(9002, at=110)
    assert report.insufficient == 1 and report.queued == 0
    before = (core.count(SeenPost), core.count(RuleHit), core.count(Outbox))
    result = core.ingestion.preview(Rule(), limit=1)
    assert result["sample_count"] == 1
    assert result["first_seen_from"] == result["first_seen_until"]
    assert result["results"][0]["result"]["status"] == "match"
    assert before == (core.count(SeenPost), core.count(RuleHit), core.count(Outbox))


def test_pruning_readable_history_does_not_remove_dedupe_receipts(core):
    from seekbell.domain.delivery import SendResult

    core.queued()
    worker = DeliveryWorker(core.engine, {})
    claim = worker.claim(at=30)
    worker.finish(claim, SendResult(status="success"), at=31)
    with write_session(core.engine) as session:
        for model in (OutboxContribution, DeliveryAttempt, RuleHit, Outbox, Post, SourceItem):
            session.execute(delete(model))
    assert core.count(SeenPost) == 2 and core.count(DeliveredPost) == 1
    assert core.ingest(9002, 9001, at=40).queued == 0
    assert core.count(Post) == core.count(Outbox) == 0
