import socket

import pytest


@pytest.fixture(autouse=True)
def forbid_external_network(monkeypatch):
    """Baseline tests must not contact forums or real notification services."""
    original_connect = socket.socket.connect

    def guarded_connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError("Tests must use in-process mocks, not network connections")
        return original_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
