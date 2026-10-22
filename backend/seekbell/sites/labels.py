"""Display labels only; RSS identifiers and rule values remain unchanged."""

# NodeSeek's official category names, checked against /categories/<identifier>.
_NODESEEK_CATEGORIES = {
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


def website_label(website_id: str | None) -> str:
    return "NodeSeek" if website_id == "nodeseek" else website_id or "未知网站"


def category_label(website_id: str | None, category: str | None) -> str | None:
    if website_id == "nodeseek":
        return _NODESEEK_CATEGORIES.get(category, category)
    return category
