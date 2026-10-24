"""Normalize legacy UI category labels at the configuration/trial boundary."""

from seekbell.domain.rules import Rule
from seekbell.sites.categories import normalize_categories


def normalized_rule(rule, website_ids):
    values = normalize_categories(rule.categories, website_ids)
    if tuple(values) == rule.categories:
        return rule
    return Rule.model_validate({**rule.model_dump(mode="json"), "categories": values})
