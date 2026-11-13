"""Anonymous fixed-source HTTP reads; response cookies never become credentials."""

import asyncio
from contextlib import asynccontextmanager

import httpx

from seekbell.domain.errors import SourceFailure
from seekbell.domain.http import retry_after_seconds

# Connection and response phases are bounded apart: a slow cross-border handshake
# no longer eats the time a slow but reachable origin needs to answer.
SOURCE_TIMEOUT = httpx.Timeout(15.0, connect=8.0)
# A failed connection never carried the request, so one quick second try costs the
# origin nothing and keeps a dropped handshake from failing the whole round.
CONNECT_RETRY_GAP = 2
# Bound of one read: two connection attempts, the gap, one response phase and parsing.
SOURCE_TOTAL_TIMEOUT = 2 * SOURCE_TIMEOUT.connect + CONNECT_RETRY_GAP + SOURCE_TIMEOUT.read + 2
# Linux DO is read about once a minute; keeping its HTTP/2 connection past one interval
# lets the next read skip the TCP and TLS handshake, where its timeouts mostly arose.
LINUXDO_KEEPALIVE = 150


def public_client(*, transport=None, **options):
    # Injected transports own all test IO. Production enables HTTP/2 only for
    # Linux DO; the default pool keeps other sources on their existing protocol.
    mounts = None
    if transport is None:
        limits = options.get("limits", httpx.Limits())
        mounts = {
            "https://linux.do": httpx.AsyncHTTPTransport(
                http2=True,
                trust_env=False,
                limits=linuxdo_limits(limits),
            )
        }
    return httpx.AsyncClient(
        transport=transport,
        mounts=mounts,
        trust_env=False,
        follow_redirects=False,
        **options,
    )


def linuxdo_limits(limits):
    return httpx.Limits(
        max_connections=limits.max_connections,
        max_keepalive_connections=limits.max_keepalive_connections,
        keepalive_expiry=LINUXDO_KEEPALIVE,
    )


async def _send(client, request):
    try:
        return await client.send(request, stream=True, follow_redirects=False)
    except (httpx.ConnectTimeout, httpx.ConnectError):
        await asyncio.sleep(CONNECT_RETRY_GAP)
        return await client.send(request, stream=True, follow_redirects=False)


@asynccontextmanager
async def public_response(client, url, *, headers=None, timeout=None):
    options = {"headers": headers}
    if timeout is not None:
        options["timeout"] = timeout
    request = client.build_request("GET", url, **options)
    request.headers.pop("cookie", None)
    response = await _send(client, request)
    try:
        yield response
    finally:
        await response.aclose()


def source_failure(response, now):
    # Challenge Pages may use 429 (or even 200); the explicit provider header
    # takes precedence over the status code, without parsing untrusted HTML.
    challenge = response.headers.get("cf-mitigated", "").lower() == "challenge"
    if response.status_code == 200 and not challenge:
        return None
    return SourceFailure(
        "access_challenge" if challenge else f"http_{response.status_code}",
        retry_after=retry_after_seconds(response.headers.get("retry-after"), now),
    )


def timeout_code(error):
    """connect_timeout: the request never left; timeout: it left and no answer came in time."""
    return "connect_timeout" if isinstance(error, httpx.ConnectTimeout) else "timeout"
