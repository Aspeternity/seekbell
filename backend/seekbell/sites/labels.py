"""Display labels only; stored post values remain unchanged."""

from seekbell.sites.categories import NODESEEK_CATEGORIES


def website_label(website_id: str | None) -> str:
    return {"nodeseek": "NodeSeek", "linuxdo": "LINUX DO"}.get(website_id, website_id or "未知网站")


def category_label(website_id: str | None, category: str | None) -> str | None:
    if website_id == "nodeseek":
        return NODESEEK_CATEGORIES.get(category, category)
    return category
