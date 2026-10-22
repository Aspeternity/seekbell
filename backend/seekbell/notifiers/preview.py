"""Read-only synthetic content, rendered by the real Telegram formatter."""

from seekbell.notifiers.rendering import telegram_message


def telegram_preview_payload(timezone):
    return {
        "schema_version": 1,
        "event_id": "preview",
        "display_timezone": timezone,
        "post": {
            "website_id": "nodeseek",
            "external_post_id": "preview",
            "title": "DMIT 洛杉矶套餐补货",
            "summary": "新一批套餐开放，记录本次优惠信息。",
            "author": "cloud_note",
            "category": "info",
            "published_at": "2026-10-22T10:40:33+00:00",
            "first_seen_at": 1792665633,
            "url": "https://www.nodeseek.com/",
        },
        "matched_tasks": [{"id": "preview", "version": 1, "name": "好价服务器雷达"}],
    }


def telegram_preview(timezone, *, include_summary=True, summary_limit=160):
    return telegram_message(
        telegram_preview_payload(timezone),
        {"include_summary": include_summary, "summary_limit": summary_limit},
    )
