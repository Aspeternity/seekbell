"""Regenerate the offline demo snapshot using the production Telegram renderer."""

import argparse
import json
from pathlib import Path

from seekbell.notifiers.preview import telegram_preview, telegram_preview_payload

DEMO_TIMEZONES = ("UTC", "Asia/Shanghai", "Asia/Tokyo", "America/Los_Angeles")

DESTINATION = (
    Path(__file__).resolve().parents[1] / "frontend/src/prototype/telegramPreview.sample.json"
)


def sample_fixture():
    base = telegram_preview("UTC", include_summary=False)
    summary = telegram_preview_payload("UTC")["post"]["summary"]
    # Generated suffixes let the offline demo vary its setting without a second template.
    suffixes = [
        telegram_preview("UTC", summary_limit=limit)["text"][len(base["text"]) :]
        for limit in range(len(summary.encode("utf-16-le")) // 2 + 1)
    ]
    return {
        "messages": {
            timezone: telegram_preview(timezone, include_summary=False)
            for timezone in DEMO_TIMEZONES
        },
        "summary_suffixes": suffixes,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    fixture = sample_fixture()
    if args.check:
        if json.loads(DESTINATION.read_text()) != fixture:
            raise SystemExit("Regenerate the demo notification preview snapshot")
        print("Notification preview snapshot matches the production renderer")
    else:
        DESTINATION.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n")
        print(DESTINATION)
