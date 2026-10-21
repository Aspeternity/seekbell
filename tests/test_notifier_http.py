import asyncio
import json
import logging

import httpx
import pytest
from seekbell.notifiers.configs import validate_config
from seekbell.notifiers.http import MAX_RESPONSE_BYTES, HTTPNotifier
from seekbell.notifiers.rendering import clip, render

from tests.notifier_helpers import CONFIGS, payload


def send(kind, handler, *, values=None, content=None):
    async def run():
        notifier = HTTPNotifier(kind, transport=httpx.MockTransport(handler))
        try:
            return await notifier.send(
                validate_config(kind, values or CONFIGS[kind]), content or payload()
            )
        finally:
            await notifier.aclose()

    return asyncio.run(run())


@pytest.mark.parametrize(
    "kind,body",
    [
        ("telegram", {"ok": True, "result": {"message_id": 7}}),
        ("bark", {"code": 200}),
        ("webhook", None),
    ],
)
def test_wire_contract_and_acceptance(kind, body):
    event = payload()

    def handle(request):
        data = json.loads(request.content)
        assert request.method == "POST"
        assert request.headers["accept-encoding"] == "identity"
        if kind == "telegram":
            assert request.url.path.endswith("/bot123456:synthetic-secret/sendMessage")
            assert data["chat_id"] == "-100123"
            assert data["link_preview_options"] == {"is_disabled": True}
            assert "parse_mode" not in data
            assert "<b>合成消息</b>" in data["text"]
            assert data["reply_markup"]["inline_keyboard"][0][0]["url"] == event["post"]["url"]
            assert data["entities"][0]["type"] == "bold"
            assert "synthetic summary" not in data["text"]
        elif kind == "bark":
            assert str(request.url) == "http://192.168.1.2:8080/bark/push"
            assert data["device_key"] == "synthetic-device-secret"
            assert data["url"] == event["post"]["url"]
            assert len(data["body"]) <= 1800
        else:
            assert data["schema_version"] == 1
            assert data["event_id"] == event["event_id"]
            assert data["matched_tasks"] == event["matched_tasks"]
            assert data["post"]["summary"] is None
            assert request.headers["idempotency-key"] == event["event_id"]
            assert request.headers["authorization"] == "Bearer synthetic-header-secret"
        return httpx.Response(204) if body is None else httpx.Response(200, json=body)

    assert send(kind, handle, content=event).status == "success"


@pytest.mark.parametrize("kind", ["telegram", "bark", "webhook"])
@pytest.mark.parametrize(
    "status,expected",
    [
        (301, "permanent_error"),
        (307, "permanent_error"),
        (400, "permanent_error"),
        (401, "permanent_error"),
        (403, "permanent_error"),
        (404, "permanent_error"),
        (408, "unknown"),
        (429, "transient_error"),
        (500, "transient_error"),
        (503, "transient_error"),
    ],
)
def test_http_fault_matrix_never_follows_redirect(kind, status, expected):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            status, headers={"Retry-After": "70", "Location": "https://other.example.invalid"}
        )

    result = send(kind, handle)
    assert result.status == expected
    if status == 429 or status >= 500:
        assert result.retry_after == 70
    assert len(requests) == 1


@pytest.mark.parametrize(
    "kind,body,expected",
    [
        ("telegram", {"ok": False, "error_code": 400}, "permanent_error"),
        (
            "telegram",
            {"ok": False, "error_code": 429, "parameters": {"retry_after": 80}},
            "transient_error",
        ),
        ("telegram", {"ok": False, "error_code": 500}, "transient_error"),
        ("telegram", {"ok": True}, "unknown"),
        ("telegram", {"ok": 1, "result": {"message_id": 7}}, "unknown"),
        ("telegram", {"ok": True, "result": {"message_id": True}}, "unknown"),
        ("telegram", {"ok": False, "error_code": "429"}, "unknown"),
        ("telegram", {"ok": False, "error_code": 429, "parameters": []}, "transient_error"),
        ("bark", {"code": 400}, "permanent_error"),
        ("bark", {"code": 500}, "transient_error"),
        ("bark", {"code": "200"}, "unknown"),
        ("bark", {"code": True}, "unknown"),
        ("webhook", {"ok": True}, "success"),
        ("webhook", {"ok": False}, "permanent_error"),
        ("webhook", {"ok": False, "error_code": 503}, "transient_error"),
        ("webhook", {}, "unknown"),
    ],
)
def test_http_200_business_matrix(kind, body, expected):
    config = dict(CONFIGS[kind])
    if kind == "webhook":
        config["response_mode"] = "json_ok"
    result = send(kind, lambda r: httpx.Response(200, json=body), values=config)
    assert result.status == expected
    if body.get("parameters") == {"retry_after": 80}:
        assert result.retry_after == 80


@pytest.mark.parametrize(
    "body", [b"not json", b"[]", b"null", b"true", b"x" * (MAX_RESPONSE_BYTES + 1)]
)
def test_unusable_response_is_unknown(body):
    assert send("telegram", lambda r: httpx.Response(200, content=body)).status == "unknown"


@pytest.mark.parametrize(
    "exception,expected",
    [
        (httpx.ConnectTimeout, "transient_error"),
        (httpx.ConnectError, "transient_error"),
        (httpx.ReadTimeout, "unknown"),
        (httpx.WriteTimeout, "unknown"),
        (httpx.RemoteProtocolError, "unknown"),
    ],
)
def test_transport_failure_classification(exception, expected):
    def fail(request):
        raise exception("synthetic-secret", request=request)

    assert send("telegram", fail).status == expected


def test_response_encoding_and_retry_after_date():
    # Use a raw streaming response to avoid the mock eagerly attempting decompression.
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"{}"

    assert (
        send(
            "telegram",
            lambda r: httpx.Response(200, stream=Stream(), headers={"content-encoding": "br"}),
        ).code
        == "unexpected_response_encoding"
    )
    assert (
        send(
            "telegram",
            lambda r: httpx.Response(429, headers={"Retry-After": "Sun, 18 Oct 2099 00:00:00 GMT"}),
        ).retry_after
        > 0
    )


def test_secrets_do_not_enter_library_logs(caplog):
    caplog.set_level(logging.DEBUG)
    send(
        "telegram",
        lambda r: httpx.Response(
            200, json={"ok": False, "error_code": 403, "description": "remote-secret"}
        ),
    )
    send("webhook", lambda r: httpx.Response(204))
    assert "synthetic-secret" not in caplog.text
    assert "synthetic-url-secret" not in caplog.text
    assert "synthetic-header-secret" not in caplog.text
    assert "remote-secret" not in caplog.text


def test_cookie_isolation_and_stable_event_id():
    event = payload()
    requests = []

    async def run():
        def handle(request):
            requests.append(request)
            assert "cookie" not in request.headers
            return httpx.Response(204, headers={"set-cookie": "secret=value; Path=/"})

        notifier = HTTPNotifier("webhook", transport=httpx.MockTransport(handle))
        config = validate_config("webhook", CONFIGS["webhook"])
        try:
            await notifier.send(config, event)
            await notifier.send(config, event)
        finally:
            await notifier.aclose()

    asyncio.run(run())
    assert requests[0].content == requests[1].content
    assert requests[0].headers["idempotency-key"] == requests[1].headers["idempotency-key"]


def test_template_is_bounded_and_summary_optional():
    event = payload()
    event["post"]["title"] = "😀" * 5000
    event["post"]["summary"] = "summary" * 1000
    config = validate_config(
        "telegram", {**CONFIGS["telegram"], "include_summary": True, "summary_limit": 10}
    )
    text = render(event, config)
    assert len(text.encode("utf-16-le")) <= 8000
    assert event["post"]["url"] in text
    assert "摘要：summarysu…" in text
    assert clip("abc", 0) == ""
