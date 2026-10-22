import asyncio
import copy
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from seekbell.config import Settings
from seekbell.db.models import ManualDelivery, NotificationTarget, Outbox, TargetTestAttempt
from seekbell.main import create_app
from seekbell.notifiers.configs import validate_config
from seekbell.notifiers.http import HTTPNotifier
from seekbell.notifiers.preview import telegram_preview, telegram_preview_payload
from seekbell.notifiers.rendering import telegram_message
from seekbell.services.display import get_display, update_display
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scripts.export_notification_preview import DEMO_TIMEZONES, DESTINATION, sample_fixture
from tests.notifier_helpers import CONFIGS
from tests.test_management import authenticate

URL = "/api/manage/notification-preview/telegram"


@pytest.fixture
def preview_app(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, static_dir=tmp_path / "static"))
    with TestClient(app) as client:
        yield app, client


def business_counts(engine):
    with Session(engine) as session:
        return {
            model.__tablename__: session.scalar(select(func.count()).select_from(model))
            for model in (NotificationTarget, Outbox, TargetTestAttempt, ManualDelivery)
        }


def test_preview_requires_login_and_needs_no_target_or_credentials_or_send(
    preview_app, monkeypatch
):
    app, client = preview_app
    assert client.get(URL).status_code == 401
    authenticate(client)
    before = business_counts(app.state.engine)
    calls = []

    async def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("A preview must never send")

    monkeypatch.setattr(app.state.target_testing, "run", forbidden)
    response = client.get(URL, params={"include_summary": "true", "summary_limit": 160})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == telegram_preview("UTC")
    assert not calls
    assert business_counts(app.state.engine) == before
    assert not any(
        word in response.text for word in ("bot_token", "chat_id", "ciphertext", "event_id")
    )
    client.post("/api/auth/logout")
    assert client.get(URL).status_code == 401


@pytest.mark.parametrize(
    "zone",
    [
        "UTC",
        "Asia/Shanghai",
        "Asia/Tokyo",
        "America/Los_Angeles",
        "America/New_York",
        "Europe/Berlin",
    ],
)
def test_preview_uses_saved_timezone_and_the_actual_sender_message(preview_app, zone):
    app, client = preview_app
    authenticate(client)
    update_display(app.state.engine, zone, get_display(app.state.engine)["revision"])
    values = {"include_summary": True, "summary_limit": 7}
    response = client.get(URL, params=values)
    assert response.status_code == 200, response.text
    payload = telegram_preview_payload(zone)
    before = copy.deepcopy(payload)
    config = validate_config("telegram", {**CONFIGS["telegram"], **values})
    bodies = []

    def receive(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    async def send():
        notifier = HTTPNotifier("telegram", transport=httpx.MockTransport(receive))
        try:
            return await notifier.send(config, payload)
        finally:
            await notifier.aclose()

    assert asyncio.run(send()).status == "success"
    assert {key: bodies[0][key] for key in response.json()} == response.json()
    assert payload == before
    assert "🎯" not in response.json()["text"] and "🕒" not in response.json()["text"]
    assert "发布时间：" in response.json()["text"] and zone not in response.json()["text"]


@pytest.mark.parametrize(
    "values",
    [
        {"summary_limit": -1},
        {"summary_limit": 1001},
        {"summary_limit": "1.5"},
        {"include_summary": "not-a-boolean"},
        {"bot_token": "synthetic-preview-private-value"},
        {"target_id": "synthetic-preview-private-value"},
    ],
)
def test_preview_validates_options_and_rejects_credentials(preview_app, values):
    app, client = preview_app
    authenticate(client)
    before = business_counts(app.state.engine)
    response = client.get(URL, params=values)
    assert response.status_code == 422, response.text
    assert "synthetic-preview-private-value" not in response.text
    assert business_counts(app.state.engine) == before


def test_demo_snapshot_and_all_summary_suffixes_match_the_production_renderer():
    sample = json.loads(DESTINATION.read_text())
    assert sample == sample_fixture()
    assert set(sample["messages"]) == set(DEMO_TIMEZONES)
    for zone in DEMO_TIMEZONES:
        for limit in (*range(len(sample["summary_suffixes"])), 160, 1000):
            for include in (True, False):
                message = copy.deepcopy(sample["messages"][zone])
                if include:
                    message["text"] += sample["summary_suffixes"][
                        min(limit, len(sample["summary_suffixes"]) - 1)
                    ]
                assert message == telegram_preview(
                    zone, include_summary=include, summary_limit=limit
                )
    assert telegram_preview("UTC", include_summary=False) == telegram_message(
        telegram_preview_payload("UTC"), {"include_summary": False, "summary_limit": 160}
    )
