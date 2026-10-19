import pytest
from pydantic import ValidationError
from seekbell.domain.posts import PostFields
from seekbell.domain.rules import Rule, evaluate, explain


def result(rule, **fields):
    return evaluate(Rule.model_validate(rule), PostFields(**fields))


def test_groups_and_exclusions_follow_specification():
    rule = {
        "groups": [
            {"all_of": ["DMIT"], "any_of": ["优惠", "补货"]},
            {"all_of": ["搬瓦工"], "any_of": ["折扣", "促销"]},
        ],
        "exclude": ["求购", "已出"],
    }
    assert result(rule, title="DMIT 优惠").status == "match"
    assert result(rule, title="搬瓦工促销").status == "match"
    assert result(rule, title="DMIT 无活动").status == "no_match"
    assert result(rule, title="求购 DMIT 优惠").status == "no_match"


def test_empty_or_group_cannot_bypass_real_conditions():
    rule = Rule(groups=[{}, {"all_of": ["required"]}])
    assert len(rule.groups) == 1
    assert evaluate(rule, PostFields(title="unrelated")).status == "no_match"
    unrestricted = Rule(groups=[{}])
    assert evaluate(unrestricted, PostFields()).warnings == ("all_new_posts",)
    assert "全部新帖" in explain(unrestricted)


def test_case_and_internal_spaces():
    rule = {"groups": [{"all_of": ["  Black Friday  "]}]}
    assert result(rule, title="black friday offer").status == "match"
    assert result({**rule, "case_sensitive": True}, title="black friday").status == "no_match"
    assert result(rule, title="BlackFriday").status == "no_match"
    assert result({"groups": [{"all_of": ["中文短语"]}]}, title="新中文短语活动").status == "match"


@pytest.mark.parametrize(
    "title,expected",
    [
        ("VPS sale", "match"),
        ("cheapVPS", "no_match"),
        ("VPS_Pro", "no_match"),
        ("优惠VPS优惠", "match"),
        ("pre-VPS offer", "match"),
    ],
)
def test_english_word_boundaries(title, expected):
    assert (
        result(
            {
                "mode": "english_word",
                "groups": [{"all_of": ["VPS"]}],
            },
            title=title,
        ).status
        == expected
    )


def test_no_regex_execution():
    assert (
        result(
            {
                "mode": "english_word",
                "groups": [{"all_of": ["[offer]"]}],
            },
            title="normal offer",
        ).status
        == "no_match"
    )
    with pytest.raises(ValidationError):
        Rule.model_validate({"regex": "synthetic"})


def test_terms_may_span_fields_but_not_field_boundaries():
    assert (
        result(
            {
                "scope": "title_summary",
                "groups": [{"all_of": ["DMIT", "优惠"]}],
            },
            title="DMIT",
            summary="优惠",
        ).status
        == "match"
    )
    assert (
        result(
            {
                "scope": "title_summary",
                "groups": [{"all_of": ["DMIT"]}],
            },
            title="DM",
            summary="IT",
        ).status
        == "no_match"
    )
    assert (
        result(
            {
                "scope": "title_summary",
                "groups": [{"all_of": ["Black Friday"]}],
            },
            title="Black",
            summary="Friday",
        ).status
        == "no_match"
    )


def test_missing_summary_is_different_from_known_empty_summary():
    rule = {"scope": "summary", "groups": [{"all_of": ["offer"]}]}
    missing = result(rule, title="offer")
    assert missing.status == "insufficient_data"
    assert "missing_summary" in {reason.code for reason in missing.reasons}
    assert result(rule, summary="").status == "no_match"


def test_known_positive_and_unknown_exclusion():
    rule = {"scope": "title_summary", "groups": [{"all_of": ["DMIT"]}]}
    assert result(rule, title="DMIT").status == "match"
    assert result({**rule, "exclude": ["求购"]}, title="DMIT").status == "insufficient_data"
    assert result({**rule, "exclude": ["求购"]}, title="DMIT 求购").status == "no_match"
    assert result({**rule, "scope": "title"}, title="unrelated").status == "no_match"


def test_unknown_field_does_not_override_a_definite_no_match():
    assert (
        result(
            {
                "scope": "title_summary",
                "authors_include": ["required-author"],
                "groups": [{"all_of": ["DMIT"]}],
            },
            title="DMIT",
            author="different-author",
        ).status
        == "no_match"
    )


def test_author_and_category_are_exact_original_fields():
    rule = {"authors_include": ["FixtureUser"], "categories": ["合成版块"]}
    assert result(rule, title="FixtureUser 合成版块").status == "insufficient_data"
    assert result(rule, author="FixtureUser", category="合成版块").status == "match"
    assert result(rule, author="fixtureuser", category="合成版块").status == "no_match"
    assert result({"authors_exclude": ["FixtureUser"]}, author="FixtureUser").status == "no_match"
    assert result({"categories": ["known"]}, category="unknown").status == "no_match"


def test_author_only_rule_does_not_require_summary():
    answer = result({"scope": "title_summary", "authors_include": ["fixture"]})
    assert answer.status == "insufficient_data"
    assert {reason.code for reason in answer.reasons} == {"author_include", "missing_author"}


def test_nfkc_whitespace_and_notify_on_insufficient():
    rule = Rule(
        groups=[{"all_of": ["DMIT", "Black Friday"]}],
        notify_on_insufficient=True,
    )
    assert evaluate(rule, PostFields(title="ＤＭＩＴ   Black\t\nFriday 特惠")).status == "match"
    word_rule = Rule(
        mode="english_word",
        groups=[{"all_of": ["VPS"]}],
    )
    assert evaluate(word_rule, PostFields(title="优惠 ＶＰＳ 促销")).status == "match"
    assert "信息不足时仍发送通知" in explain(rule)
