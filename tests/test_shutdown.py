import http.client
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parents[1]


def image_command(path):
    """The container's uvicorn command, served on a Unix socket (tests use no TCP)."""
    command = json.loads(re.search(r"^CMD (\[.*\])$", (ROOT / "Dockerfile").read_text(), re.M)[1])
    host = command.index("--host")
    del command[host : host + 4]  # --host value --port value
    return [sys.executable, "-m", *command, "--uds", str(path)]


class UnixClient:
    def __init__(self, path):
        self.path, self.cookies = str(path), {}

    def call(self, target, data=None, csrf=None):
        connection = http.client.HTTPConnection("localhost", timeout=40)
        connection.sock = socket.socket(socket.AF_UNIX)
        connection.sock.connect(self.path)
        headers = {"Content-Type": "application/json", "Origin": "http://localhost"}
        if csrf:
            headers["X-CSRF-Token"] = csrf
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        body = json.dumps(data) if data is not None else None
        connection.request("POST" if data is not None else "GET", target, body, headers)
        reply = connection.getresponse()
        for value in reply.headers.get_all("Set-Cookie") or []:
            name, _, rest = value.partition("=")
            self.cookies[name] = rest.split(";", 1)[0]
        assert reply.status == 200, reply.read()
        result = json.loads(reply.read())
        connection.close()
        return result


def test_stop_answers_an_open_long_poll_and_exits_cleanly_within_seconds(tmp_path):
    path = tmp_path / "seekbell.sock"
    server = subprocess.Popen(
        image_command(path),
        env={**os.environ, "SEEKBELL_DATA_DIR": str(tmp_path / "data")},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    client = UnixClient(path)
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                csrf = client.call("/api/auth/status")["csrf"]
                break
            except OSError:
                assert time.monotonic() < deadline and server.poll() is None
                time.sleep(0.2)
        csrf = client.call(
            "/api/auth/setup", {"username": "test_admin", "password": "synthetic-pass-1"}, csrf
        )["csrf"]
        tag = client.call("/api/manage/hotlists")["tag"]
        answered = []
        poll = threading.Thread(
            target=lambda: answered.append(client.call("/api/manage/hotlists?after=" + tag)["tag"])
        )
        poll.start()
        time.sleep(1)
        assert poll.is_alive()
        started = time.monotonic()
        server.send_signal(signal.SIGTERM)
        output, _ = server.communicate(timeout=10)
        elapsed = time.monotonic() - started
        poll.join(5)
    finally:
        if server.poll() is None:
            server.kill()
            server.communicate()
    # The long poll got its board instead of being cancelled by the 3 s timeout.
    assert answered == [tag]
    # Uvicorn re-raises SIGTERM after a clean stop; as PID 1 in the container it exits 0.
    assert server.returncode in (0, -signal.SIGTERM) and elapsed < 3, (elapsed, output)
    assert "Application shutdown complete" in output
    assert "ERROR" not in output and "Traceback" not in output
