"""Offline lifecycle probe: real app actors, synthetic RSS/notifier, disposable data."""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seekbell.config import Settings
from seekbell.db.models import (
    AlertDelivery,
    DeliveredPost,
    Outbox,
    Post,
    RetentionPolicy,
    SeenPost,
    Source,
    SourceItem,
    SourceState,
    SystemEvent,
    Website,
    WebsiteInstallation,
)
from seekbell.db.transactions import database_call, write_session
from seekbell.domain.delivery import SendResult
from seekbell.domain.rules import Rule
from seekbell.main import create_app
from seekbell.services.alerts import observe, update_settings
from seekbell.services.authentication import initialize
from seekbell.services.configuration import Configuration
from seekbell.services.demo import SyntheticStream
from seekbell.services.runtime import Runtime


async def exercise(directory):
    clock, cleanup_clock, polls, sends = [100.0], [100.0], [], []

    def feed(request):
        polls.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "application/rss+xml"},
            stream=SyntheticStream([9001] if len(polls) == 1 else [9001, 9002]),
        )

    class SyntheticNotifier:
        async def send(self, target, payload):
            sends.append(payload)
            return SendResult(status="success")

    def factory(engine, notifiers):
        actor = Runtime(
            engine,
            {"webhook": SyntheticNotifier()},
            http_transport=httpx.MockTransport(feed),
            tick=0.02,
        )
        actor.source.clock = actor.worker.clock = lambda: clock[0]
        actor.retention.clock = lambda: cleanup_clock[0]
        actor.alerts.clock = lambda: clock[0]
        return actor

    app = create_app(Settings(data_dir=directory), runtime_factory=factory)
    async with app.router.lifespan_context(app):
        engine = app.state.engine

        def prepare():
            initialize(engine, "offline_admin", "Synthetic-Offline-Runtime-2026")
            config = Configuration(engine, app.state.vault)
            target = config.create_target(
                "Synthetic runtime",
                kind="webhook",
                config={
                    "url": "https://receiver.example.test/offline-runtime",
                },
            )
            for name in ("first rule", "second rule"):
                config.create_task(name, Rule(), [target], at=1)
            with write_session(engine) as session:
                session.add(WebsiteInstallation(website_id="nodeseek"))
                session.get(Website, "nodeseek").enabled = True
                session.get(Source, "nodeseek-rss").enabled = True
            return target

        target = await database_call(prepare)

        def initialized():
            with Session(engine) as session:
                return session.get(SourceState, "nodeseek-rss").initialized

        def delivered():
            with Session(engine) as session:
                return session.scalar(select(func.count()).select_from(DeliveredPost)) == 1

        async def wait_for(check):
            async with asyncio.timeout(5):
                while not await database_call(check):
                    await asyncio.sleep(0.02)

        await wait_for(initialized)
        assert not sends
        clock[0] = 110
        await wait_for(delivered)
        assert app.state.runtime.active and len(sends) == 1
        assert len(sends[0]["matched_tasks"]) == 2
        assert len(polls) == 2

        def create_system_events():
            update_settings(engine, True, [target], 1)
            with write_session(engine) as session:
                observe(
                    session,
                    "runtime:offline_demo",
                    True,
                    label="合成系统事件",
                    code="synthetic_failure",
                    at=111,
                )
                observe(session, "runtime:offline_demo", False, label="合成系统事件", at=112)

        def alerts_delivered():
            with Session(engine) as session:
                return (
                    session.scalar(
                        select(func.count())
                        .select_from(AlertDelivery)
                        .where(AlertDelivery.result == "success")
                    )
                    == 2
                )

        await database_call(create_system_events)
        await wait_for(alerts_delivered)
        assert [
            message["alert"]["phase"] for message in sends if message.get("type") == "system_alert"
        ] == ["fault", "recovery"]

        def schedule_cleanup():
            with write_session(engine) as session:
                session.get(RetentionPolicy, 1).next_run_at = 0

        def history_removed():
            with Session(engine) as session:
                return (
                    session.scalar(select(func.count()).select_from(Post)) == 0
                    and session.scalar(select(func.count()).select_from(Outbox)) == 0
                )

        cleanup_clock[0] = 110 + 31 * 86400
        await database_call(schedule_cleanup)
        await wait_for(history_removed)
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(SeenPost)) == 2
            assert session.scalar(select(func.count()).select_from(SourceItem)) == 2
            assert session.scalar(select(func.count()).select_from(DeliveredPost)) == 1
            assert session.scalar(select(func.count()).select_from(SystemEvent)) == 0
            assert session.scalar(select(func.count()).select_from(AlertDelivery)) == 0
    assert app.state.runtime.client.is_closed
    assert all(task.done() for task in app.state.runtime.tasks.values())
    return {
        "mode": "offline_synthetic",
        "polls": len(polls),
        "sends": len([message for message in sends if message.get("type") != "system_alert"]),
        "system_alert_sends": len(
            [message for message in sends if message.get("type") == "system_alert"]
        ),
        "alert_history_removed": True,
        "merged_tasks": len(sends[0]["matched_tasks"]),
        "baseline_silent": True,
        "cleanup_history_removed": True,
        "cleanup_ledgers_preserved": True,
        "runtime_stopped": app.state.runtime.status == "stopped",
        "http_closed": app.state.runtime.client.is_closed,
    }


def main():
    with TemporaryDirectory(prefix="seekbell-runtime-demo-") as directory:
        result = asyncio.run(exercise(Path(directory)))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
