"""Per-website hotlist capability, validation and effective refresh policy."""

from copy import deepcopy

from seekbell.sites.hotlists import HOTLIST_SOURCES

MAX_INTERVAL = 86400


def validate_settings(website_id, mode, intervals):
    source = HOTLIST_SOURCES.get(website_id)
    if source is None:
        raise ValueError("该网站尚不支持社区热榜。")
    if mode == "recommended":
        if intervals:
            raise ValueError("推荐模式无需填写自定义热榜间隔。")
        return {}
    if mode != "custom" or set(intervals) != set(source.periods):
        raise ValueError("请填写该网站实际支持的全部热榜周期。")
    for period, value in intervals.items():
        if (
            type(value) is not int
            or not source.minimum_interval(period) <= value <= MAX_INTERVAL
            or value % 60
        ):
            raise ValueError(
                f"热榜间隔应为 {source.minimum_interval(period) // 60}–1440 之间的整数分钟。"
            )
    return {"mode": "custom", "intervals": deepcopy(intervals)}


def configuration(website_id, settings):
    source = HOTLIST_SOURCES.get(website_id)
    if source is None:
        return None
    custom = settings.get("mode") == "custom"
    intervals = settings.get("intervals", {}) if custom else {}
    return {
        "provider": source.provider,
        "provider_url": source.provider_url,
        "mode": "custom" if custom else "recommended",
        "periods": [
            {
                **period,
                "interval_seconds": intervals.get(
                    period["id"], source.recommended_interval(period["id"])
                ),
                "recommended_seconds": source.recommended_interval(period["id"]),
                "minimum_seconds": source.minimum_interval(period["id"]),
            }
            for period in source.metadata()["periods"]
        ],
    }
