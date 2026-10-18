"""Local manual review only: real app, no background jobs or outbound IP connections.

Mounted by compose.acceptance.yaml; never packaged in the production image.
This application-process guard is not a container firewall or a security sandbox.
"""

import ipaddress
import socket

import uvicorn
from seekbell.config import Settings
from seekbell.main import create_app


class AcceptanceNetworkDisabled(OSError):
    pass


def disable_outbound() -> None:
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_sendto = socket.socket.sendto
    original_getaddrinfo = socket.getaddrinfo

    def reject_ip(sock, original, *args, **kwargs):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise AcceptanceNetworkDisabled("Outbound networking disabled for local acceptance")
        return original(sock, *args, **kwargs)

    def connect(sock, *args, **kwargs):
        return reject_ip(sock, original_connect, *args, **kwargs)

    def connect_ex(sock, *args, **kwargs):
        return reject_ip(sock, original_connect_ex, *args, **kwargs)

    def sendto(sock, *args, **kwargs):
        return reject_ip(sock, original_sendto, *args, **kwargs)

    def resolve(host, *args, **kwargs):
        # Numeric bind/listen addresses remain valid, without querying external DNS.
        try:
            host = host.decode("ascii") if isinstance(host, bytes) else host
            ipaddress.ip_address(host)
        except (ValueError, TypeError):
            raise AcceptanceNetworkDisabled("External DNS disabled for local acceptance") from None
        return original_getaddrinfo(host, *args, **kwargs)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.socket.sendto = sendto
    socket.getaddrinfo = resolve


def main() -> None:
    disable_outbound()
    # Prove the guard before opening the manual review listener. No packets are sent.
    for operation in (
        lambda: socket.create_connection(("192.0.2.1", 443), timeout=1),
        lambda: socket.getaddrinfo("example.com", 443),
    ):
        try:
            operation()
        except AcceptanceNetworkDisabled:
            pass
        else:
            raise RuntimeError("Local acceptance network guard did not activate")
    print("local_acceptance: outbound guard active; background disabled", flush=True)
    uvicorn.run(
        create_app(Settings(background_enabled=False, trusted_proxies=[])),
        host="0.0.0.0",
        port=8000,
        proxy_headers=False,
        access_log=False,
    )


if __name__ == "__main__":
    main()
