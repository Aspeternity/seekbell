"""Site category identifiers and labels; no network or fuzzy matching."""

NODESEEK_CATEGORIES = {
    "daily": "日常",
    "tech": "技术",
    "info": "情报",
    "review": "测评",
    "trade": "交易",
    "carpool": "拼车",
    "promotion": "推广",
    "life": "生活",
    "dev": "Dev",
    "photo-share": "贴图",
    "expose": "曝光",
    "sandbox": "沙盒",
}
NODESEEK_ALIASES = {label: key for key, label in NODESEEK_CATEGORIES.items()}


def category_options(website_id, observed=()):
    values = dict(NODESEEK_CATEGORIES) if website_id == "nodeseek" else {}
    for value in observed:
        if isinstance(value, str) and value and len(value) <= 500:
            canonical = NODESEEK_ALIASES.get(value, value) if website_id == "nodeseek" else value
            values.setdefault(canonical, value)
    return [{"value": value, "label": label} for value, label in values.items()]


def normalize_categories(categories, website_ids):
    if "nodeseek" not in website_ids:
        return list(categories)
    # A mixed-site task retains literal names used by the other website.
    mixed = len(website_ids) > 1
    result = []
    for value in categories:
        canonical = NODESEEK_ALIASES.get(value, value)
        if mixed and canonical != value and value not in result:
            result.append(value)
        if canonical not in result:
            result.append(canonical)
    return result
