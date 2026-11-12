"""One bounded, plain text template; external text never becomes markup."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from seekbell.sites.labels import category_label, website_label


def clip(value: str, limit: int) -> str:
    if limit <= 0:
        return ""
    # Count UTF-16 units conservatively for Telegram, including emoji.
    if len(value.encode("utf-16-le")) <= limit * 2:
        return value
    return (
        value.encode("utf-16-le")[: max(0, limit - 1) * 2].decode("utf-16-le", errors="ignore")
        + "…"
    )


def line(value) -> str:
    return " ".join(str(value or "未知").split())


def format_timestamp(value, timezone="UTC", *, show_timezone=True):
    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        zone = ZoneInfo("UTC")
    try:
        instant = (
            datetime.fromisoformat(value)
            if isinstance(value, str)
            else datetime.fromtimestamp(value, UTC)
        )
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=UTC)
        text = instant.astimezone(zone).strftime("%Y-%m-%d %H:%M:%S")
        return text + " (" + zone.key + ")" if show_timezone else text
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def post_time(payload, *, show_timezone=True):
    post = payload["post"]
    zone = payload.get("display_timezone", "UTC")
    published = format_timestamp(post.get("published_at"), zone, show_timezone=show_timezone)
    if published:
        return "发布时间：" + published
    return "发现时间：" + (
        format_timestamp(post.get("first_seen_at"), zone, show_timezone=show_timezone) or "未知"
    )


def telegram_post_time(payload):
    post = payload["post"]
    zone = payload.get("display_timezone", "UTC")
    published = format_timestamp(post.get("published_at"), zone, show_timezone=False)
    # A synthetic target test has no source post. Its sample time is its creation time.
    if published is None and payload.get("type") == "target_test":
        published = format_timestamp(post.get("first_seen_at"), zone, show_timezone=False)
    return "发布时间：" + (published or "来源未提供")


ALERT_PHASES = {
    "fault": ("故障", "SeekBell 系统故障："),
    "recovery": ("已恢复", "SeekBell 系统恢复："),
    "reminder": ("仍未恢复", "SeekBell 故障仍未恢复："),
    "test": ("测试", "SeekBell 告警测试："),
}


def format_duration(seconds) -> str:
    minutes = int(seconds // 60)
    if minutes < 1:
        return "不到 1 分钟"
    days, rest = divmod(minutes, 1440)
    hours, minutes = divmod(rest, 60)
    if days:
        return f"{days} 天" + (f" {hours} 小时" if hours else "")
    if hours:
        return f"{hours} 小时" + (f" {minutes} 分钟" if minutes else "")
    return f"{minutes} 分钟"


def alert_lines(payload: dict, *, show_timezone=True) -> list[str]:
    alert = payload["alert"]
    phase = alert["phase"]
    zone = payload.get("display_timezone", "UTC")

    def stamp(value):
        return format_timestamp(value, zone, show_timezone=show_timezone) or "未知"

    lines = ["状态：" + ALERT_PHASES.get(phase, ALERT_PHASES["recovery"])[0]]
    if phase in ("fault", "reminder") and alert.get("summary"):
        lines.append("原因：" + line(alert["summary"]))
    duration = alert.get("duration_seconds")
    if phase in ("recovery", "reminder") and isinstance(duration, int | float):
        lines.append(("持续：" if phase == "recovery" else "已持续：") + format_duration(duration))
    if phase == "reminder" and alert.get("started_at") is not None:
        lines.append("开始时间：" + stamp(alert["started_at"]))
    else:
        lines.append("时间：" + stamp(alert["at"]))
    if phase in ("fault", "reminder") and alert.get("code"):
        lines.append("诊断代码：" + line(alert["code"]))
    return lines


def render(payload: dict, config: dict, *, limit: int = 4000, show_timezone=True) -> str:
    if payload.get("type") == "system_alert":
        return clip(
            "\n".join([message_title(payload), *alert_lines(payload, show_timezone=show_timezone)]),
            limit,
        )
    post = payload["post"]
    lines = [
        clip(line(post["title"]), 600),
        post["url"],
        "作者：" + clip(line(post.get("author") or post.get("author_display_name")), 100),
        "版块：" + clip(line(post.get("category")), 100),
        post_time(payload, show_timezone=show_timezone),
        "命中任务："
        + clip("、".join(line(task["name"]) for task in payload["matched_tasks"]), 1000),
    ]
    if config["include_summary"] and post.get("summary"):
        lines.append("摘要：" + clip(str(post["summary"]), config["summary_limit"]))
    return clip("\n".join(lines), limit)


def telegram_message(payload: dict, config: dict) -> dict:
    """Structured entities style trusted spans; external text stays literal."""
    title = clip(line(message_title(payload)), 600)
    if payload.get("type") == "system_alert":
        details = alert_lines(payload, show_timezone=False)
    else:
        post = payload["post"]
        details = [
            clip(line(website_label(post.get("website_id"))), 80)
            + " · "
            + clip(line(category_label(post.get("website_id"), post.get("category"))), 100)
            + " · 作者："
            + clip(line(post.get("author") or post.get("author_display_name")), 100),
            "命中任务："
            + clip("、".join(line(task["name"]) for task in payload["matched_tasks"]), 1000),
            telegram_post_time(payload),
        ]
    text = title + "\n\n" + "\n".join(details)
    if payload.get("type") != "system_alert" and config["include_summary"]:
        summary = payload["post"].get("summary")
        if summary:
            text += "\n\n摘要：" + clip(str(summary), config["summary_limit"])
    message = {
        "text": clip(text, 4000),
        "entities": [{"type": "bold", "offset": 0, "length": len(title.encode("utf-16-le")) // 2}],
    }
    url = message_url(payload)
    if url:
        message["reply_markup"] = {
            "inline_keyboard": [[{"text": "查看原帖 ↗", "url": url}]],
        }
    return message


def message_title(payload):
    if payload.get("type") == "system_alert":
        phase = ALERT_PHASES.get(payload["alert"]["phase"], ALERT_PHASES["recovery"])
        return phase[1] + line(payload["alert"]["label"])
    return payload["post"]["title"]


def message_url(payload):
    return None if payload.get("type") == "system_alert" else payload["post"]["url"]


def webhook_payload(payload: dict, config: dict) -> dict:
    if payload.get("type") == "system_alert":
        return {
            "schema_version": 2,
            "event_id": payload["event_id"],
            "type": "system_alert",
            "alert": dict(payload["alert"]),
        }
    post = dict(payload["post"])
    post["summary"] = (
        clip(post["summary"], config["summary_limit"])
        if config["include_summary"] and post.get("summary")
        else None
    )
    return {
        "schema_version": 1,
        "event_id": payload["event_id"],
        "post": post,
        "matched_tasks": payload["matched_tasks"],
    }
