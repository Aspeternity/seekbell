"""Keep a disposable real TLS proxy alive for browser checks; no real targets."""

import os
import signal
import threading

from proxy_fixture import ProxyFixture

if __name__ == "__main__":
    image = os.environ.get("SEEKBELL_IMAGE")
    revision = os.environ.get("SEEKBELL_REVISION")
    if not image or not revision:
        raise SystemExit("Set SEEKBELL_IMAGE and SEEKBELL_REVISION to the fixed local test build")
    stop = threading.Event()
    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, lambda *args: stop.set())
    with ProxyFixture(image, revision, port=8020):
        stop.wait()
