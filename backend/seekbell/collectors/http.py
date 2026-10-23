"""Anonymous fixed-source HTTP reads; response cookies never become credentials."""

from contextlib import asynccontextmanager


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
