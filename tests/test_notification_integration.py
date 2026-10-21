import asyncio
import json

import httpx
import pytest
from cryptography.fernet import Fernet
from seekbell.db.models import (
    DeliveredPost,
    DeliveryAttempt,
    Outbox,
    RuleHit,
    TargetTestAttempt,
)
from seekbell.domain.delivery import DeliveryPolicy
from seekbell.domain.rules import Rule
from seekbell.notifiers.credentials import CredentialVault
from seekbell.notifiers.registry import NotifierRegistry
from seekbell.services.configuration import Configuration
from seekbell.services.delivery import DeliveryWorker
from seekbell.services.display import get_display, update_display
from seekbell.services.target_testing import TargetTesting
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.notifier_helpers import CONFIGS
from tests.test_notifier_smtp import SMTPServer, install


def configured(core, kinds):
    keyring = CredentialVault(Fernet.generate_key())
    service = Configuration(core.engine, keyring)
    targets = {kind: service.create_target(kind, kind=kind, config=CONFIGS[kind]) for kind in kinds}
    service.update_task(core.task, "rule one", Rule(), targets.values(), at=2)
    return keyring, service, targets


def test_four_channels_merge_by_target_and_retry_only_failed_target(core, monkeypatch):
    keyring, service, targets = configured(core, CONFIGS)
    update_display(core.engine, "Asia/Shanghai", get_display(core.engine)["revision"])
    service.create_task("rule two", Rule(), targets.values(), at=2)
    server = SMTPServer()
    install(monkeypatch, server)
    core.queued()
    assert core.count(RuleHit) == 2 and core.count(Outbox) == 4
    calls = []
    webhook_calls = []

    def handle(request):
        calls.append(request)
        body = json.loads(request.content)
        if request.url.path.endswith("sendMessage"):
            assert "rule one" in body["text"] and "rule two" in body["text"]
            assert "2026-10-18 20:00:00 (Asia/Shanghai)" in body["text"]
            assert body["entities"][0]["type"] == "bold"
            assert body["reply_markup"]["inline_keyboard"][0][0]["url"].endswith("/post-9002-1")
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
        if request.url.path.endswith("/push"):
            assert "2026-10-18 20:00:00 (Asia/Shanghai)" in body["body"]
            return httpx.Response(200, json={"code": 200})
        webhook_calls.append(request)
        assert len(body["matched_tasks"]) == 2
        assert body["post"]["published_at"] == "2026-10-18T12:00:00+00:00"
        assert "display_timezone" not in body
        if len(webhook_calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "80"})
        return httpx.Response(204)

    async def run():
        registry = NotifierRegistry(keyring, http_transport=httpx.MockTransport(handle))
        now = [30]
        worker = DeliveryWorker(core.engine, registry.notifiers, clock=lambda: now[0])
        try:
            for _ in range(4):
                assert await worker.run_once()
            assert await worker.run_once() is None
            assert core.count(DeliveredPost) == 3
            now[0] = 109
            assert await worker.run_once() is None
            now[0] = 110
            assert await worker.run_once()
            assert await worker.run_once() is None
        finally:
            await registry.aclose()

    asyncio.run(run())
    assert len(calls) == 4
    assert sum(call[0] == "data" for call in server.calls) == 1
    mail = next(call[1] for call in server.calls if call[0] == "data")
    assert "2026-10-18 20:00:00 (Asia/Shanghai)" in mail.get_content()
    assert core.count(DeliveredPost) == 4 and core.count(DeliveryAttempt) == 5
    assert webhook_calls[0].content == webhook_calls[1].content
    assert (
        webhook_calls[0].headers["idempotency-key"] == webhook_calls[1].headers["idempotency-key"]
    )


def test_unknown_remote_acceptance_retries_with_same_id_and_retains_uncertainty(core):
    keyring, _, _ = configured(core, ["webhook"])
    core.queued()
    accepted_ids = []

    def handle(request):
        accepted_ids.append(json.loads(request.content)["event_id"])
        if len(accepted_ids) == 1:
            raise httpx.ReadTimeout("remote accepted; response lost", request=request)
        return httpx.Response(204)

    async def run():
        registry = NotifierRegistry(keyring, http_transport=httpx.MockTransport(handle))
        now = [30]
        worker = DeliveryWorker(core.engine, registry.notifiers, clock=lambda: now[0])
        try:
            await worker.run_once()
            assert core.one(Outbox).status == "retry" and core.one(Outbox).uncertain
            now[0] = 35
            await worker.run_once()
        finally:
            await registry.aclose()

    asyncio.run(run())
    assert accepted_ids[0] == accepted_ids[1]
    assert core.one(Outbox).status == "sent" and core.one(Outbox).uncertain


@pytest.mark.parametrize("status,max_attempts,expected_attempts", [(403, 5, 1), (503, 2, 2)])
def test_permanent_and_finite_transient_failures(core, status, max_attempts, expected_attempts):
    keyring, _, _ = configured(core, ["bark"])
    core.queued()

    async def run():
        registry = NotifierRegistry(
            keyring,
            http_transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"code": status})
            ),
        )
        now = [30]
        worker = DeliveryWorker(
            core.engine,
            registry.notifiers,
            clock=lambda: now[0],
            policy=DeliveryPolicy(max_attempts=max_attempts),
        )
        try:
            for _ in range(5):
                await worker.run_once()
                now[0] += 1000
        finally:
            await registry.aclose()

    asyncio.run(run())
    assert core.one(Outbox).status == "failed"
    assert core.count(DeliveryAttempt) == expected_attempts


def test_disabled_target_stays_cancelled_and_config_edit_keeps_old_wire_snapshot(core):
    keyring, service, targets = configured(core, ["webhook"])
    core.queued()
    service.update_target(
        targets["webhook"], name="new", config={"url": "https://new.example.invalid/new"}
    )
    calls = []

    async def run():
        registry = NotifierRegistry(
            keyring,
            http_transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(204)),
        )
        worker = DeliveryWorker(core.engine, registry.notifiers, clock=lambda: 30)
        try:
            await worker.run_once()
            assert str(calls[0].url) == CONFIGS["webhook"]["url"]
            core.ingest(9001, 9002, 9003, at=40)
            service.set_target_enabled(targets["webhook"], False)
            service.set_target_enabled(targets["webhook"], True)
            assert worker.claim(at=50) is None
            core.ingest(9001, 9002, 9003, 9004, at=60)
            claim = worker.claim(at=70)
            await registry.notifiers["webhook"].send(claim.target_snapshot, claim.payload)
            assert str(calls[1].url) == "https://new.example.invalid/new"
        finally:
            await registry.aclose()

    asyncio.run(run())
    with Session(core.engine) as session:
        assert sorted(session.scalars(select(Outbox.status))) == ["cancelled", "leased", "sent"]


def test_wrong_restored_key_records_permanent_failure_without_network(core):
    _, _, _ = configured(core, ["telegram"])
    core.queued()

    def forbidden(request):
        raise AssertionError("must not contact service")

    async def run():
        registry = NotifierRegistry(
            CredentialVault(Fernet.generate_key()), http_transport=httpx.MockTransport(forbidden)
        )
        try:
            await DeliveryWorker(core.engine, registry.notifiers, clock=lambda: 30).run_once()
        finally:
            await registry.aclose()

    asyncio.run(run())
    assert core.one(Outbox).last_error_code == "target_credentials_invalid"
    assert core.one(Outbox).status == "failed"


@pytest.mark.parametrize("failure", [False, True])
def test_explicit_target_test_has_separate_history_and_no_automatic_dedup(core, failure):
    keyring, service, targets = configured(core, ["webhook"])
    service.set_target_enabled(targets["webhook"], False)
    calls = []

    def handle(request):
        calls.append(request)
        if failure:
            raise httpx.ReadTimeout("secret", request=request)
        return httpx.Response(204)

    async def run():
        registry = NotifierRegistry(keyring, http_transport=httpx.MockTransport(handle))
        tester = TargetTesting(core.engine, registry.notifiers)
        try:
            a = await tester.run(targets["webhook"])
            b = await tester.run(targets["webhook"])
            assert a != b
            result = tester.get_result(a)
            assert result["result"] == ("unknown" if failure else "success")
            assert "snapshot" not in json.dumps(result)
            assert "secret" not in json.dumps(result)
        finally:
            await registry.aclose()

    asyncio.run(run())
    assert len(calls) == 2 and calls[0].content != calls[1].content
    assert core.count(TargetTestAttempt) == 2
    assert core.count(DeliveredPost) == core.count(Outbox) == core.count(RuleHit) == 0
    with Session(core.engine) as session:
        rows = session.scalars(select(TargetTestAttempt)).all()
        assert all("config_ciphertext" in row.target_snapshot for row in rows)
        assert "synthetic-url-secret" not in json.dumps([row.target_snapshot for row in rows])


def test_database_dump_contains_no_target_credentials(core):
    configured(core, CONFIGS)
    core.queued()
    with core.engine.connect() as connection:
        dump = "\n".join(connection.connection.driver_connection.iterdump())
    for values in CONFIGS.values():
        for field, value in values.items():
            if isinstance(value, str) and field != "response_mode":
                assert value not in dump


def test_target_test_timeout_and_interruption_remain_unknown(core):
    from seekbell.domain.delivery import SendResult

    from tests.core_helpers import RecordingNotifier

    configured(core, ["webhook"])

    class Hanging:
        async def send(self, snapshot, payload):
            await asyncio.Event().wait()

    async def run():
        tester = TargetTesting(core.engine, {"mock": Hanging()}, timeout=0.01)
        key = await tester.run(core.target)
        result = tester.get_result(key)
        assert result["result"] == "unknown" and result["code"] == "send_timeout"
        interrupted, _, _ = tester._start(core.target)
        state = tester.get_result(interrupted)
        assert state["result"] == "unknown" and state["finished_at"] is None
        tester = TargetTesting(
            core.engine,
            {
                "mock": RecordingNotifier(
                    SendResult(status="permanent_error", code="synthetic_rejected")
                )
            },
        )
        key = await tester.run(core.target)
        assert tester.get_result(key)["result"] == "permanent_error"

    asyncio.run(run())
