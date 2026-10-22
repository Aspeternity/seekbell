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


@pytest.mark.parametrize(
    "title,summary,expected",
    [
        ("[出]180出Vmiss Tri 来", None, "match"),
        ("[出]180出Vmiss Tri 来", "", "match"),
        ("[出]180出Vmiss Tri 来", "普通合成摘要", "match"),
        ("[出]180出Vmiss Tri 来", "包含 core 的合成摘要", "no_match"),
        ("[出]180出Vmiss Tri 来", "收一台同款", "no_match"),
        ("收 Vmiss Tri", None, "no_match"),
        ("Vmiss Tri core", None, "no_match"),
        ("出 Vmiss", None, "no_match"),
        ("出 Vmiss", "Tri 套餐", "match"),
        ("无关标题", "Vmiss Tri 套餐", "match"),
        ("无关标题", None, "no_match"),
    ],
)
def test_combined_scope_matches_only_received_fields(title, summary, expected):
    rule = {
        "scope": "title_summary",
        "groups": [{"all_of": ["vmiss", "tri"]}],
        "exclude": ["core", "收"],
    }
    answer = result(rule, title=title, summary=summary)
    assert answer.status == expected
    assert all(reason.truth != "unknown" for reason in answer.reasons)
    assert "missing_summary" not in {reason.code for reason in answer.reasons}
    assert "摘要缺失时仅按标题判断" in explain(Rule.model_validate(rule))


@pytest.mark.parametrize(
    "restriction,missing_reason",
    [
        ({"authors_include": ["fixture"]}, "missing_author"),
        ({"authors_exclude": ["fixture"]}, "missing_author"),
        ({"categories": ["tech"]}, "missing_category"),
    ],
)
def test_title_fallback_does_not_bypass_required_metadata(restriction, missing_reason):
    answer = result(
        {
            "scope": "title_summary",
            "groups": [{"all_of": ["vmiss", "tri"]}],
            "exclude": ["core", "收"],
            **restriction,
        },
        title="[出]180出Vmiss Tri 来",
    )
    assert answer.status == "insufficient_data"
    assert missing_reason in {reason.code for reason in answer.reasons}
    assert "missing_summary" not in {reason.code for reason in answer.reasons}


def test_summary_only_exclusions_still_distinguish_missing_from_empty():
    rule = {"scope": "summary", "exclude": ["core", "收"]}
    assert result(rule, title="Vmiss Tri", summary=None).status == "insufficient_data"
    assert result(rule, title="Vmiss Tri", summary="").status == "match"
    assert result(rule, title="Vmiss Tri", summary="收").status == "no_match"


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
