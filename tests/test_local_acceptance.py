"""Only the new manual-review network guard; no repeat of product/browser suites."""

import runpy
import socket
from pathlib import Path

import pytest


@pytest.fixture
def guard(monkeypatch):
    values = runpy.run_path(str(Path(__file__).parents[1] / "scripts/local_acceptance_server.py"))
    # Register every mutation so the guard cannot escape into unrelated tests.
    for name in ("connect", "connect_ex", "sendto"):
        monkeypatch.setattr(socket.socket, name, getattr(socket.socket, name))
    monkeypatch.setattr(socket, "getaddrinfo", socket.getaddrinfo)
    values["disable_outbound"]()
    return values["AcceptanceNetworkDisabled"]


@pytest.mark.parametrize("family", [socket.AF_INET, socket.AF_INET6])
@pytest.mark.parametrize("operation", ["connect", "connect_ex", "sendto"])
def test_guard_blocks_ip_connections_and_udp_without_packets(guard, family, operation):
    address = ("192.0.2.1", 443) if family == socket.AF_INET else ("2001:db8::1", 443)
    with (
        socket.socket(
            family, socket.SOCK_DGRAM if operation == "sendto" else socket.SOCK_STREAM
        ) as client,
        pytest.raises(guard),
    ):
        if operation == "sendto":
            client.sendto(b"synthetic", address)
        else:
            getattr(client, operation)(address)


@pytest.mark.parametrize("hostname", ["example.com", b"example.com", b"a.co"])
def test_guard_rejects_external_dns_but_keeps_numeric_listener_resolution(guard, hostname):
    with pytest.raises(guard):
        socket.getaddrinfo(hostname, 443)
    assert socket.getaddrinfo("127.0.0.1", 8000, type=socket.SOCK_STREAM)


def test_guard_keeps_local_unix_socket_pairs_for_event_loop(guard):
    first, second = socket.socketpair()
    with first, second:
        first.sendall(b"local")
        assert second.recv(5) == b"local"
