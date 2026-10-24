"""Anonymous fixed-source HTTP reads; response cookies never become credentials."""

from contextlib import asynccontextmanager

import httpx


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
