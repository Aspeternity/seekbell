"""Anonymous fixed-source HTTP reads; response cookies never become credentials."""

from contextlib import asynccontextmanager

import httpx

from seekbell.domain.errors import SourceFailure
from seekbell.domain.http import retry_after_seconds


def public_client(*, transport=None, **options):
    # Injected transports own all test IO. Production enables HTTP/2 only for
    # Linux DO; the default pool keeps other sources on their existing protocol.
    mounts = None
    if transport is None:
        mounts = {
            "https://linux.do": httpx.AsyncHTTPTransport(
                http2=True,
                trust_env=False,
                limits=options.get("limits", httpx.Limits()),
            )
        }
    return httpx.AsyncClient(
        transport=transport,
        mounts=mounts,
        trust_env=False,
        follow_redirects=False,
        **options,
    )


@asynccontextmanager
async def public_response(client, url, *, headers=None, timeout=None):
    options = {"headers": headers}
    if timeout is not None:
        options["timeout"] = timeout
    request = client.build_request("GET", url, **options)
    request.headers.pop("cookie", None)
    response = await client.send(request, stream=True, follow_redirects=False)
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
