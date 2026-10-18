"""Disposable browser-test server: no persistent development data or outbound networking."""

import socket
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from seekbell.config import Settings
from seekbell.main import create_app


def main() -> None:
    original_connect = socket.socket.connect

    def deny_outbound(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise RuntimeError("Browser test backend must not connect to external services")
        return original_connect(sock, address)

    socket.socket.connect = deny_outbound
    with TemporaryDirectory(prefix="seekbell-browser-") as directory:
        app = create_app(
            Settings(
                data_dir=Path(directory),
                static_dir=Path("frontend/dist"),
                build_revision="browser-synthetic",
                trusted_proxies=[],
            )
        )
        uvicorn.run(app, host="127.0.0.1", port=18765, proxy_headers=False, access_log=False)


if __name__ == "__main__":
    main()
