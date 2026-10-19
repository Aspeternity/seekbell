import re
import unicodedata
from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from seekbell.domain.posts import PostFields


class Truth(StrEnum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


def conjunction(values: list[Truth]) -> Truth:
    if Truth.FALSE in values:
        return Truth.FALSE
    return Truth.UNKNOWN if Truth.UNKNOWN in values else Truth.TRUE


def disjunction(values: list[Truth]) -> Truth:
    if Truth.TRUE in values:
        return Truth.TRUE
    return Truth.UNKNOWN if Truth.UNKNOWN in values else Truth.FALSE


def negate(value: Truth) -> Truth:
    return {Truth.TRUE: Truth.FALSE, Truth.FALSE: Truth.TRUE, Truth.UNKNOWN: Truth.UNKNOWN}[value]


def clean_values(values):
    if not isinstance(values, (tuple, list)):
        raise ValueError("Conditions must be arrays of text tags")
    result = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError("Condition tags must be text")
        value = value.strip()
        if len(value) > 200:
            raise ValueError("A condition tag may not exceed 200 characters")
        if value and value not in result:
            result.append(value)
    return tuple(result)


class ConditionGroup(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    all_of: tuple[str, ...] = Field(default=(), max_length=64)
    any_of: tuple[str, ...] = Field(default=(), max_length=64)

    @field_validator("all_of", "any_of", mode="before")
    @classmethod
    def normalize(cls, value):
        return clean_values(value)


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    scope: Literal["title", "summary", "title_summary"] = "title"
    groups: tuple[ConditionGroup, ...] = Field(default=(), max_length=16)
    exclude: tuple[str, ...] = Field(default=(), max_length=64)
    authors_include: tuple[str, ...] = Field(default=(), max_length=64)
    authors_exclude: tuple[str, ...] = Field(default=(), max_length=64)
    categories: tuple[str, ...] = Field(default=(), max_length=64)
    case_sensitive: bool = False
    mode: Literal["contains", "english_word"] = "contains"
    notify_on_insufficient: bool = False

    @field_validator("exclude", "authors_include", "authors_exclude", "categories", mode="before")
    @classmethod
    def normalize(cls, value):
        return clean_values(value)

    @model_validator(mode="after")
    def remove_empty_groups(self):
        # An empty OR group must never bypass a populated group.
        groups = tuple(group for group in self.groups if group.all_of or group.any_of)
        object.__setattr__(self, "groups", groups)
        return self


class Reason(BaseModel):
    code: str
    truth: Truth
    group: int | None = None
    term: str | None = None


class MatchResult(BaseModel):
    status: Literal["match", "no_match", "insufficient_data"]
    reasons: tuple[Reason, ...]
    warnings: tuple[str, ...] = ()


_ASCII_WORD = re.compile(r"[a-zA-Z0-9_]")


def _normalize_text(value: str, *, case_sensitive: bool) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", value).split())
    return normalized if case_sensitive else normalized.casefold()


@lru_cache(maxsize=1024)
def _word_pattern(term: str) -> re.Pattern[str]:
    prefix = r"(?<![a-zA-Z0-9_])" if _ASCII_WORD.fullmatch(term[0]) else ""
    suffix = r"(?![a-zA-Z0-9_])" if _ASCII_WORD.fullmatch(term[-1]) else ""
    return re.compile(prefix + re.escape(term) + suffix)


def contains(text: str, term: str, rule: Rule) -> bool:
    text = _normalize_text(text, case_sensitive=rule.case_sensitive)
    term = _normalize_text(term, case_sensitive=rule.case_sensitive)
    if not term:
        return False
    if rule.mode == "contains":
        return term in text
    return _word_pattern(term).search(text) is not None


def evaluate(rule: Rule, post: PostFields) -> MatchResult:
    """Pure three-valued evaluation: no database, network, or side effects."""
    fields: list[str | None] = {
        "title": [post.title],
        "summary": [post.summary],
        "title_summary": [post.title, post.summary],
    }[rule.scope]
    reasons = []

    def keyword(term: str, code: str, group: int | None = None) -> Truth:
        if any(contains(field, term, rule) for field in fields if field is not None):
            value = Truth.TRUE
        elif any(field is None for field in fields):
            value = Truth.UNKNOWN
        else:
            value = Truth.FALSE
        reasons.append(Reason(code=code, truth=value, term=term, group=group))
        return value

    def member(value: str | None, choices: tuple[str, ...], code: str) -> Truth:
        result = (
            Truth.UNKNOWN if value is None else (Truth.TRUE if value in choices else Truth.FALSE)
        )
        reasons.append(Reason(code=code, truth=result))
        return result

    predicates = []
    if rule.authors_include:
        predicates.append(member(post.author, rule.authors_include, "author_include"))
    if rule.authors_exclude:
        predicates.append(negate(member(post.author, rule.authors_exclude, "author_exclude")))
    if rule.categories:
        predicates.append(member(post.category, rule.categories, "category"))
    if rule.groups:
        groups = []
        for index, group in enumerate(rule.groups, start=1):
            conditions = [keyword(term, "all_of", index) for term in group.all_of]
            if group.any_of:
                conditions.append(
                    disjunction([keyword(term, "any_of", index) for term in group.any_of])
                )
            groups.append(conjunction(conditions))
        predicates.append(disjunction(groups))
    if rule.exclude:
        predicates.append(negate(disjunction([keyword(term, "exclude") for term in rule.exclude])))

    value = conjunction(predicates)
    if value == Truth.UNKNOWN:
        if any(
            reason.truth == Truth.UNKNOWN and reason.code in ("all_of", "any_of", "exclude")
            for reason in reasons
        ):
            reasons.append(Reason(code="missing_summary", truth=Truth.UNKNOWN))
        if post.author is None and (rule.authors_include or rule.authors_exclude):
            reasons.append(Reason(code="missing_author", truth=Truth.UNKNOWN))
        if post.category is None and rule.categories:
            reasons.append(Reason(code="missing_category", truth=Truth.UNKNOWN))
    unrestricted = not (
        rule.groups
        or rule.exclude
        or rule.authors_include
        or rule.authors_exclude
        or rule.categories
    )
    return MatchResult(
        status={
            Truth.TRUE: "match",
            Truth.FALSE: "no_match",
            Truth.UNKNOWN: "insufficient_data",
        }[value],
        reasons=tuple(reasons),
        warnings=("all_new_posts",) if unrestricted else (),
    )


def explain(rule: Rule) -> str:
    parts = ["条件组之间为“或”，组内非空条件为“且”；排除条件优先否决。"]
    if not rule.groups:
        parts.append("不限制关键词。")
    if rule.scope == "title_summary":
        parts.append("标题与摘要分别匹配，各词可分布在两字段，不跨字段拼词。")
    if rule.mode == "english_word":
        parts.append("英文词边界使用英文字母、数字和下划线，中文按包含匹配。")
    if rule.notify_on_insufficient:
        parts.append("字段缺失导致信息不足时仍发送通知并标注。")
    if not any(
        (rule.groups, rule.exclude, rule.authors_include, rule.authors_exclude, rule.categories)
    ):
        parts.append("将匹配全部新帖。")
    return "".join(parts)
