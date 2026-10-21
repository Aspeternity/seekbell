"""HTTP channel transports; no redirects, ambient proxies, or remote error text."""

import json
import logging
import time

import httpx

from seekbell.domain.delivery import SendResult
from seekbell.domain.http import retry_after_seconds
from seekbell.notifiers.rendering import (
    clip,
    line,
    message_title,
    message_url,
    render,
    telegram_message,
    webhook_payload,
)

MAX_RESPONSE_BYTES = 64 * 1024


def result_for_code(code: int, *, retry_after=None, prefix="http") -> SendResult:
    if code == 429 or code >= 500:
        return SendResult(status="transient_error", code=prefix + "_retry", retry_after=retry_after)
    if code == 408:
        return SendResult(status="unknown", code=prefix + "_timeout")
    return SendResult(status="permanent_error", code=prefix + "_rejected")


class HTTPNotifier:
    def __init__(self, kind: str, *, transport: httpx.AsyncBaseTransport | None = None):
        self.kind = kind
        # HTTPX INFO includes token-bearing request URLs; wire DEBUG may include headers.
        # Keep these libraries quiet even when application diagnostics use DEBUG.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        self.client = httpx.AsyncClient(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(8, connect=3),
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=4),
        )

    async def aclose(self):
        await self.client.aclose()

    async def send(self, config: dict, payload: dict) -> SendResult:
        headers = {"Accept-Encoding": "identity"}
        if self.kind == "telegram":
            url = config["base_url"] + "/bot" + config["bot_token"] + "/sendMessage"
            body = {
                "chat_id": config["chat_id"],
                **telegram_message(payload, config),
                "link_preview_options": {"is_disabled": True},
            }
            if config["message_thread_id"] is not None:
                body["message_thread_id"] = config["message_thread_id"]
        elif self.kind == "bark":
            url = config["base_url"] + "/push"
            body = {
                "device_key": config["device_key"],
                "title": clip(line(message_title(payload)), 100),
                "body": render(payload, config, limit=1800),
                "group": config["group"],
            }
            if message_url(payload):
                body["url"] = message_url(payload)
        else:
            url = config["url"]
            headers.update(config["headers"])
            headers["Idempotency-Key"] = payload["event_id"]
            body = webhook_payload(payload, config)
        try:
            request = self.client.build_request("POST", url, json=body, headers=headers)
            # Never let a service's Set-Cookie become credentials for a different target.
            request.headers.pop("cookie", None)
            response = await self.client.send(request, stream=True, follow_redirects=False)
            try:
                wait = retry_after_seconds(response.headers.get("Retry-After"), time.time())
                if not 200 <= response.status_code < 300:
                    return result_for_code(response.status_code, retry_after=wait)
                if self.kind == "webhook" and config["response_mode"] == "status":
                    return SendResult(status="success", code="webhook_accepted")
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    return SendResult(status="unknown", code="unexpected_response_encoding")
                data = bytearray()
                async for part in response.aiter_bytes(chunk_size=8192):
                    data.extend(part)
                    if len(data) > MAX_RESPONSE_BYTES:
                        return SendResult(status="unknown", code="response_too_large")
                try:
                    value = json.loads(data)
                except (ValueError, UnicodeError, RecursionError):
                    return SendResult(status="unknown", code="invalid_response")
                if not isinstance(value, dict):
                    return SendResult(status="unknown", code="invalid_response")
                return self._business_result(value, wait)
            finally:
                await response.aclose()
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            return SendResult(status="transient_error", code="http_connect")
        except httpx.TransportError:
            # Read/write failures cannot prove whether the receiver accepted the POST.
            return SendResult(status="unknown", code="http_result_unknown")

    def _business_result(self, value: dict, wait: float | None) -> SendResult:
        if self.kind == "bark":
            code = value.get("code")
            if type(code) is int and code == 200:
                return SendResult(status="success", code="bark_accepted")
            if type(code) is int and 400 <= code <= 599:
                return result_for_code(code, retry_after=wait, prefix="bark")
        else:
            if value.get("ok") is True and (
                self.kind != "telegram"
                or (
                    isinstance(value.get("result"), dict)
                    and type(value["result"].get("message_id")) is int
                )
            ):
                return SendResult(status="success", code=self.kind + "_accepted")
            if value.get("ok") is False:
                code = value.get("error_code", 400)
                if type(code) is not int or not 400 <= code <= 599:
                    return SendResult(status="unknown", code="invalid_response")
                parameters = value.get("parameters")
                retry = parameters.get("retry_after") if isinstance(parameters, dict) else None
                if type(retry) in (int, float):
                    retry = retry_after_seconds(str(retry), time.time())
                    wait = max(wait or 0, retry or 0)
                return result_for_code(code, retry_after=wait, prefix=self.kind)
        return SendResult(status="unknown", code="invalid_response")
