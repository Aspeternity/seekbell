"""One bounded, plain text template; external text never becomes markup."""

from datetime import UTC, datetime


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


def render(payload: dict, config: dict, *, limit: int = 4000) -> str:
    post = payload["post"]
    timestamp = post.get("published_at")
    seen = post.get("first_seen_at")
    if not timestamp and seen is not None:
        timestamp = (
            datetime.fromtimestamp(seen, UTC).isoformat()
            if isinstance(seen, (int, float))
            else str(seen)
        )
    lines = [
        clip(line(post["title"]), 600),
        post["url"],
        "作者：" + clip(line(post.get("author")), 100),
        "版块：" + clip(line(post.get("category")), 100),
        "时间：" + line(timestamp),
        "命中任务："
        + clip("、".join(line(task["name"]) for task in payload["matched_tasks"]), 1000),
    ]
    if config["include_summary"] and post.get("summary"):
        lines.append("摘要：" + clip(str(post["summary"]), config["summary_limit"]))
    return clip("\n".join(lines), limit)


def webhook_payload(payload: dict, config: dict) -> dict:
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
