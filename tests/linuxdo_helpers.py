"""Synthetic Discourse list RSS, never copied from live community content."""

from tests.rss_samples import rss


def linuxdo_rss(*ids, summary="<p>Synthetic topic summary</p>", **overrides):
    return rss(
        [
            {
                "id": key,
                "guid": f"linux.do-topic-{key}",
                "link": f"https://linux.do/t/synthetic-topic/{key}",
                "title": f"Synthetic Linux DO VPS {key}",
                "author": "Synthetic Display Name",
                "category": "合成技术",
                "summary": None
                if summary is None
                else summary
                + (
                    "<p><small>3 个帖子 - 2 位参与者</small></p>"
                    f'<p><a href="https://linux.do/t/synthetic-topic/{key}">阅读完整话题</a></p>'
                ),
                **overrides,
            }
            for key in ids
        ]
    )
