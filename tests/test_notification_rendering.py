import copy

import pytest
from seekbell.db.models import Outbox
from seekbell.domain.delivery import SendResult
from seekbell.notifiers.configs import validate_config
from seekbell.notifiers.rendering import format_timestamp, render, telegram_message, webhook_payload
from seekbell.services.delivery import DeliveryWorker
from seekbell.services.display import get_display, update_display
from seekbell.services.target_testing import TargetTesting

from tests.notifier_helpers import CONFIGS, payload


@pytest.mark.parametrize(
    "instant,zone,expected",
    [
        ("2026-10-21T12:09:01+00:00", "Asia/Shanghai", "2026-10-21 20:09:01"),
        ("2026-10-21T20:09:01+08:00", "Asia/Shanghai", "2026-10-21 20:09:01"),
        ("2026-10-21T12:09:01Z", "UTC", "2026-10-21 12:09:01"),
        ("2026-01-01T12:00:00+00:00", "America/New_York", "2026-01-01 07:00:00"),
        ("2026-07-01T12:00:00+00:00", "America/New_York", "2026-07-01 08:00:00"),
        ("2026-10-21T23:30:00+00:00", "Asia/Shanghai", "2026-10-22 07:30:00"),
    ],
)
def test_notification_time_converts_the_same_instant_including_dst(instant, zone, expected):
    assert format_timestamp(instant, zone) == expected + " (" + zone + ")"
    event = payload()
    event["display_timezone"] = zone
    event["post"]["published_at"] = instant
    text = telegram_message(event, validate_config("telegram", CONFIGS["telegram"]))["text"]
    assert "发布时间：" + expected in text
    assert zone not in text


def test_invalid_or_missing_time_does_not_show_raw_iso_or_crash():
    event = payload()
    event["display_timezone"] = "Asia/Shanghai"
    event["post"]["published_at"] = "invalid"
    event["post"]["first_seen_at"] = 0
    config = validate_config("telegram", CONFIGS["telegram"])
    assert "发现时间：1970-01-01 08:00:00 (Asia/Shanghai)" in render(event, config)
    event["post"]["first_seen_at"] = None
    assert "发现时间：未知" in render(event, config)
    assert format_timestamp(0, "missing/zone") == "1970-01-01 00:00:00 (UTC)"
    assert format_timestamp(float("inf")) is None


def test_telegram_styles_literal_title_and_keeps_a_complete_post_button():
    event = payload()
    event["display_timezone"] = "Asia/Shanghai"
    event["post"]["title"] = "😀 VPS <b>字面标签</b> & [链接](https://example.invalid/)"
    event["post"]["published_at"] = "2026-10-21T12:09:01+00:00"
    config = validate_config("telegram", CONFIGS["telegram"])
    before = copy.deepcopy(event)
    message = telegram_message(event, config)
    title = event["post"]["title"]
    assert message["text"].startswith(title + "\n\n")
    assert message["entities"] == [
        {"type": "bold", "offset": 0, "length": len(title.encode("utf-16-le")) // 2}
    ]
    assert "parse_mode" not in message
    assert "synthetic summary" not in message["text"]
    assert "2026-10-21 20:09:01" in message["text"]
    assert "Asia/Shanghai" not in message["text"]
    assert "作者：" in message["text"] and "命中任务：" in message["text"]
    assert event["post"]["url"] not in message["text"]
    assert message["reply_markup"] == {
        "inline_keyboard": [[{"text": "查看原帖 ↗", "url": event["post"]["url"]}]]
    }
    assert event == before


def test_telegram_long_unicode_summary_stays_bounded_with_valid_entities():
    event = payload()
    event["post"]["title"] = "😀" * 1000
    event["post"]["summary"] = "😀<&>" * 2000
    event["matched_tasks"] *= 100
    config = validate_config(
        "telegram", {**CONFIGS["telegram"], "include_summary": True, "summary_limit": 1000}
    )
    message = telegram_message(event, config)
    units = len(message["text"].encode("utf-16-le")) // 2
    assert units <= 4000
    for entity in message["entities"]:
        assert entity["offset"] + entity["length"] <= units
        span = (
            message["text"]
            .encode("utf-16-le")[entity["offset"] * 2 : (entity["offset"] + entity["length"]) * 2]
            .decode("utf-16-le")
        )
        assert span.endswith("…")
    assert "摘要：" in message["text"]
    assert message["reply_markup"]["inline_keyboard"][0][0]["url"] == event["post"]["url"]


def test_human_channels_use_timezone_but_webhook_keeps_machine_timestamp():
    event = payload()
    original = copy.deepcopy(event)
    event["display_timezone"] = "Asia/Shanghai"
    for kind in ("telegram", "bark", "smtp"):
        config = validate_config(kind, CONFIGS[kind])
        assert "2026-10-18 08:00:00 (Asia/Shanghai)" in render(event, config)
    config = validate_config("webhook", CONFIGS["webhook"])
    assert webhook_payload(event, config) == webhook_payload(original, config)
    assert event["post"] == original["post"]


def test_legacy_queue_reads_current_timezone_for_each_attempt_without_rewriting_snapshot(core):
    core.queued()
    before = copy.deepcopy(core.one(Outbox).payload)
    update_display(core.engine, "Asia/Tokyo", get_display(core.engine)["revision"])
    worker = DeliveryWorker(core.engine, {})
    claim = worker.claim(at=30)
    assert claim.payload["display_timezone"] == "Asia/Tokyo"
    assert claim.payload["post"] == before["post"]
    assert "display_timezone" not in core.one(Outbox).payload
    worker.finish(claim, SendResult(status="transient_error", code="http_retry"), at=30)
    update_display(core.engine, "America/New_York", get_display(core.engine)["revision"])
    retry = worker.claim(at=100)
    assert retry.payload["display_timezone"] == "America/New_York"
    assert retry.payload["post"] == before["post"]


def test_target_test_uses_saved_timezone_and_discovery_time(core):
    update_display(core.engine, "Asia/Shanghai", get_display(core.engine)["revision"])
    _, _, event = TargetTesting(core.engine, {}, clock=lambda: 0)._start(core.target)
    text = render(event, validate_config("telegram", CONFIGS["telegram"]))
    assert "发现时间：1970-01-01 08:00:00 (Asia/Shanghai)" in text
    telegram = telegram_message(event, validate_config("telegram", CONFIGS["telegram"]))["text"]
    assert "发现时间：1970-01-01 08:00:00" in telegram
    assert "Asia/Shanghai" not in telegram
