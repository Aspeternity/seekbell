"""Normalize configuration choices per site; never rewrite saved history."""

from seekbell.domain.rules import Rule
from seekbell.sites.categories import normalize_categories


def normalized_rule(rule, website_ids):
    if rule.site_categories is not None:
        if set(rule.site_categories) != set(website_ids):
            raise ValueError("Category scopes must match the selected websites")
        scopes = {
            website: {
                "mode": scope.mode,
                "values": normalize_categories(scope.values, [website]),
            }
            for website, scope in rule.site_categories.items()
        }
        return Rule.model_validate({**rule.model_dump(mode="json"), "site_categories": scopes})
    values = normalize_categories(rule.categories, website_ids)
    if tuple(values) == rule.categories:
        return rule
    return Rule.model_validate({**rule.model_dump(mode="json"), "categories": values})
