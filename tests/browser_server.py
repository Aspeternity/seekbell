"""Disposable browser-test server: no persistent development data or outbound networking."""

import socket
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
import uvicorn
from seekbell.config import Settings
from seekbell.main import create_app
from seekbell.services.configuration import Configuration
from seekbell.services.ingestion import Ingestion
from seekbell.services.runtime import ApplicationRuntime

from tests.core_helpers import batch
from tests.rss_samples import Chunks, rss


def main() -> None:
    original_connect = socket.socket.connect

    def deny_outbound(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise RuntimeError("Browser test backend must not connect to external services")
        return original_connect(sock, address)

    socket.socket.connect = deny_outbound
    with TemporaryDirectory(prefix="seekbell-browser-") as directory:
        calls = 0

        def fake_rss(request):
            nonlocal calls
            assert str(request.url) == "https://rss.nodeseek.com/"
            calls += 1
            ids = [9001, 9002] if calls <= 2 else [9001, 9002, 9003]
            return httpx.Response(
                200,
                headers={"content-type": "application/xml"},
                stream=Chunks(
                    rss(
                        [
                            {
                                "id": key,
                                "title": f"VPS synthetic offer {key}",
                                "summary": "Synthetic known summary",
                                "author": "fixture-user",
                                "category": "fixture-section",
                            }
                            for key in ids
                        ]
                    )
                ),
            )

        class BrowserRuntime(ApplicationRuntime):
            async def start(self):
                # Seed before loops start. Entries are retained at 30 days but expire at 1 day.
                config = Configuration(self.engine)
                old = time.time() - 2 * 86400
                config.set_source_enabled("nodeseek-rss", True, at=old - 1)
                ingestion = Ingestion(self.engine)
                ingestion.ingest("nodeseek-rss", batch(9001), at=old)
                ingestion.ingest("nodeseek-rss", batch(9001, 9002), at=old + 10)
                config.set_source_enabled("nodeseek-rss", False, at=old + 11)
                await super().start()

        def runtime_factory(engine, vault, *, enabled):
            return BrowserRuntime(
                engine,
                vault,
                enabled=enabled,
                rss_transport=httpx.MockTransport(fake_rss),
                notification_transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={"ok": True, "code": 200})
                ),
            )

        app = create_app(
            Settings(
                data_dir=Path(directory),
                static_dir=Path("frontend/dist"),
                build_revision="browser-synthetic",
                trusted_proxies=[],
                background_enabled=True,
            ),
            runtime_factory=runtime_factory,
        )
        uvicorn.run(app, host="127.0.0.1", port=18765, proxy_headers=False, access_log=False)


if __name__ == "__main__":
    main()
