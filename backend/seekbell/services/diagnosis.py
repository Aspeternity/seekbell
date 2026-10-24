"""Explain saved truth values without re-evaluating historical decisions."""

from collections import defaultdict

from seekbell.domain.rules import Truth, conjunction, disjunction, negate


def summarize(result):
    reasons = result.get("reasons", [])
    by_code = defaultdict(list)
    for reason in reasons:
        by_code[reason["code"]].append(reason)
    checks = []

    def add(code, label, value, failure):
        checks.append(
            {
                "code": code,
                "label": label,
                "state": {"true": "passed", "false": "blocked", "unknown": "unknown"}[value],
                "message": failure
                if value == "false"
                else label + ("已满足" if value == "true" else "所需信息不足"),
            }
        )

    for code, label, failure, inverse in (
        ("category", "版块条件", "版块条件未通过", False),
        ("author_include", "作者包含条件", "作者不在包含名单内", False),
        ("author_exclude", "作者排除条件", "作者在排除名单内", True),
    ):
        if by_code[code]:
            value = Truth(by_code[code][0]["truth"])
            add(code, label, negate(value) if inverse else value, failure)
    if by_code["exclude"]:
        value = disjunction([Truth(r["truth"]) for r in by_code["exclude"]])
        terms = [r["term"] for r in by_code["exclude"] if r["truth"] == "true" and r["term"]]
        failure = "触发排除词" + ("「" + "」「".join(terms[:3]) + "」" if terms else "")
        add("exclude", "排除词条件", negate(value), failure)

    groups = defaultdict(lambda: {"all": [], "any": []})
    for code, kind in (("all_of", "all"), ("any_of", "any")):
        for reason in by_code[code]:
            groups[reason["group"]][kind].append(Truth(reason["truth"]))
    if groups:
        values = []
        for group in groups.values():
            values.append(
                conjunction(group["all"] + ([disjunction(group["any"])] if group["any"] else []))
            )
        add("keywords", "关键词条件", disjunction(values), "没有条件组满足关键词要求")

    blocked = [item["message"] for item in checks if item["state"] == "blocked"]
    unknown = [item["message"] for item in checks if item["state"] == "unknown"]
    status = result["status"]
    headline = (
        "满足已保存的匹配条件"
        if status == "match"
        else (blocked[0] if blocked else "当时判定为未命中，具体阻断条件未完整保存")
        if status == "no_match"
        else (unknown[0] if unknown else "当时缺少作出完整判断所需的信息")
        if status == "insufficient_data"
        else "历史判定未完整记录"
    )
    return {"headline": headline, "blockers": blocked, "checks": checks}
