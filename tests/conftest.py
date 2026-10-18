import socket

import pytest

from tests.core_helpers import core  # noqa: F401


@pytest.fixture(autouse=True)
def forbid_external_network(monkeypatch):
    """Baseline tests must not contact forums or real notification services."""
    monkeypatch.setenv("SEEKBELL_BACKGROUND_ENABLED", "false")
    original_connect = socket.socket.connect

    def guarded_connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError("Tests must use in-process mocks, not network connections")
        return original_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


@pytest.fixture
def managed(tmp_path):
    from fastapi.testclient import TestClient
    from seekbell.config import Settings
    from seekbell.main import create_app

    from tests.test_authentication import setup

    settings = Settings(data_dir=tmp_path, static_dir=tmp_path / "static")
    app = create_app(settings)
    with TestClient(app) as client:
        auth = setup(client)
        client.headers["X-CSRF-Token"] = auth["csrf_token"]
        yield client, app, settings
