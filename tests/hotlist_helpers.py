"""Synthetic hotlists for every browser harness; no external requests."""

import json
import time

import httpx
from seekbell.services.hotlists import HotlistService

from tests.linuxdo_helpers import linuxdo_rss
from tests.rss_samples import Chunks


def snapshot(period="hot", count=12, now=None):
    return {
        "updated_at": int(time.time() if now is None else now),
        "posts": [
            {
                "post": {
                    "id": 8800 + i,
                    "title": f"合成{period}热榜帖子 {i + 1}",
                    "author": "SyntheticUser",
                    "category": "tech",
                    "comments": i * 3,
                    "views": i * 20,
                },
                "score": 100 - i,
            }
            for i in range(count)
        ],
    }


def synthetic_hotlists():
    async def handler(request):
        if request.url.host == "linux.do":
            assert request.url.path in ("/hot.rss", "/top.rss")
            period = request.url.params.get("period", "hot")
            return httpx.Response(
                200,
                headers={"Content-Type": "application/rss+xml"},
                stream=Chunks(
                    linuxdo_rss(*range(9800, 9812), title="合成LinuxDO" + period + "热榜帖子")
                ),
            )
        assert request.url.host == "api.bimg.eu.org"
        period = request.url.path.strip("/").split(".")[0]
        return httpx.Response(200, stream=Chunks(json.dumps(snapshot(period)).encode()))

    return HotlistService(transport=httpx.MockTransport(handler))
