"""Synchronous SMTP runs off the event loop; success means server acceptance."""

import asyncio
import smtplib
import ssl
import threading
from contextlib import suppress
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime

from seekbell.domain.delivery import SendResult
from seekbell.notifiers.rendering import clip, line, render


class SMTPNotifier:
    def __init__(self):
        # Cancellation of to_thread cannot stop a socket operation. This guard remains
        # held by the thread until it closes, so no overlapping SMTP retry can start.
        self._sending = threading.Lock()

    async def send(self, config: dict, payload: dict) -> SendResult:
        return await asyncio.to_thread(self._send, config, payload)

    def _send(self, config: dict, payload: dict) -> SendResult:
        if not self._sending.acquire(blocking=False):
            return SendResult(status="transient_error", code="smtp_busy")
        server = None
        data_started = False
        try:
            message = EmailMessage()
            message["From"] = config["from_address"]
            message["To"] = config["to_address"]
            message["Subject"] = clip(line(payload["post"]["title"]), 200)
            message["Message-ID"] = "<" + payload["event_id"] + "@seekbell.invalid>"
            message["Date"] = format_datetime(datetime.now(UTC))
            message.set_content(render(payload, config))
            context = ssl.create_default_context()
            if config["security"] == "tls":
                server = smtplib.SMTP_SSL(
                    config["host"], config["port"], timeout=3, context=context
                )
            else:
                server = smtplib.SMTP(config["host"], config["port"], timeout=3)
                if config["security"] == "starttls":
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
            if config["username"]:
                server.login(config["username"], config["password"])
            data_started = True
            refused = server.send_message(
                message, from_addr=config["from_address"], to_addrs=[config["to_address"]]
            )
            if refused:
                code = next(iter(refused.values()))[0]
                return self._smtp_error(code)
            return SendResult(status="success", code="smtp_accepted")
        except smtplib.SMTPRecipientsRefused as error:
            codes = [value[0] for value in error.recipients.values()]
            return self._smtp_error(min(codes) if codes else 550)
        except smtplib.SMTPResponseException as error:
            # SMTP 4xx are retryable; unlike HTTP, SMTP 5xx are permanent.
            return self._smtp_error(error.smtp_code)
        except (smtplib.SMTPNotSupportedError, ssl.SSLCertVerificationError):
            return SendResult(status="permanent_error", code="smtp_security")
        except (OSError, smtplib.SMTPException):
            return SendResult(
                status="unknown" if data_started else "transient_error",
                code="smtp_result_unknown" if data_started else "smtp_connect",
            )
        finally:
            # QUIT failure after DATA acceptance must not turn success into a retry.
            if server is not None:
                with suppress(Exception):
                    server.close()
            self._sending.release()

    @staticmethod
    def _smtp_error(code: int) -> SendResult:
        return SendResult(
            status="transient_error" if 400 <= code < 500 else "permanent_error",
            code="smtp_retry" if 400 <= code < 500 else "smtp_rejected",
        )
