"""Only built-in, fixed-endpoint monitoring adapters are accepted."""

from typing import Literal

from seekbell.sites.linuxdo import LinuxDoAdapter
from seekbell.sites.nodeseek import NodeSeekAdapter

WebsiteId = Literal["nodeseek", "linuxdo"]
BUILTIN_ADAPTERS = {"nodeseek": NodeSeekAdapter(), "linuxdo": LinuxDoAdapter()}


def validate_rule_capabilities(website_id, rule):
    adapter = BUILTIN_ADAPTERS[website_id]
    if "author" not in adapter.capabilities and (rule.authors_include or rule.authors_exclude):
        raise ValueError("This website does not provide reliable usernames")
