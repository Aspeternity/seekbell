import asyncio
import smtplib
import ssl
import threading

import pytest
from seekbell.notifiers.configs import validate_config
from seekbell.notifiers.smtp import SMTPNotifier

from tests.notifier_helpers import CONFIGS, payload


class SMTPServer:
    def __init__(self, *, error=None, phase="data", refused=None):
        self.error, self.phase, self.refused = error, phase, refused
        self.calls = []

    def login(self, *args):
        self.calls.append(("login", args))
        if self.phase == "login" and self.error:
            raise self.error

    def ehlo(self):
        self.calls.append(("ehlo",))

    def starttls(self, *, context):
        assert context.check_hostname
        assert context.verify_mode == ssl.CERT_REQUIRED
        self.calls.append(("starttls",))

    def send_message(self, message, **kwargs):
        self.calls.append(("data", message, kwargs))
        if self.error:
            raise self.error
        return self.refused or {}

    def close(self):
        self.calls.append(("close",))


def install(monkeypatch, server):
    def factory(host, port, **kwargs):
        assert host == "mail.example.invalid" and 0 < port <= 65535
        assert kwargs["timeout"] == 3
        if "context" in kwargs:
            assert kwargs["context"].check_hostname
            assert kwargs["context"].verify_mode == ssl.CERT_REQUIRED
        server.calls.append(("connect", kwargs))
        return server

    monkeypatch.setattr(smtplib, "SMTP_SSL", factory)
    monkeypatch.setattr(smtplib, "SMTP", factory)


@pytest.mark.parametrize("security", ["tls", "starttls", "plain"])
def test_smtp_contract_and_server_acceptance(monkeypatch, security):
    server = SMTPServer()
    install(monkeypatch, server)
    event = payload()
    event["post"]["title"] = "title\r\nBcc: victim@example.invalid"
    config = validate_config(
        "smtp", {**CONFIGS["smtp"], "security": security, "allow_insecure": security == "plain"}
    )
    result = asyncio.run(SMTPNotifier().send(config, event))
    assert result.status == "success" and result.code == "smtp_accepted"
    data = next(call for call in server.calls if call[0] == "data")
    message, envelope = data[1:]
    assert message["Message-ID"] == "<" + event["event_id"] + "@seekbell.invalid>"
    assert message["Bcc"] is None
    assert message.get_content_type() == "text/plain"
    assert event["post"]["url"] in message.get_content()
    assert "摘要" not in message.get_content()
    assert envelope == {
        "from_addr": CONFIGS["smtp"]["from_address"],
        "to_addrs": [CONFIGS["smtp"]["to_address"]],
    }
    assert server.calls[-1] == ("close",)
    assert any(call[0] == "starttls" for call in server.calls) == (security == "starttls")


@pytest.mark.parametrize(
    "error,expected",
    [
        (smtplib.SMTPDataError(451, b"secret"), "transient_error"),
        (smtplib.SMTPDataError(550, b"secret"), "permanent_error"),
        (smtplib.SMTPAuthenticationError(535, b"secret"), "permanent_error"),
        (
            smtplib.SMTPRecipientsRefused({"recipient@example.invalid": (450, b"secret")}),
            "transient_error",
        ),
        (
            smtplib.SMTPRecipientsRefused({"recipient@example.invalid": (550, b"secret")}),
            "permanent_error",
        ),
        (smtplib.SMTPNotSupportedError("secret"), "permanent_error"),
        (ssl.SSLCertVerificationError("secret"), "permanent_error"),
        (TimeoutError("secret"), "unknown"),
        (smtplib.SMTPServerDisconnected("secret"), "unknown"),
    ],
)
def test_smtp_fault_matrix(monkeypatch, error, expected):
    server = SMTPServer(error=error)
    install(monkeypatch, server)
    result = asyncio.run(SMTPNotifier().send(validate_config("smtp", CONFIGS["smtp"]), payload()))
    assert result.status == expected
    assert "secret" not in result.model_dump_json()
    assert server.calls[-1] == ("close",)


@pytest.mark.parametrize("code,expected", [(450, "transient_error"), (550, "permanent_error")])
def test_refusal_return_is_not_success(monkeypatch, code, expected):
    server = SMTPServer(refused={"recipient@example.invalid": (code, b"secret")})
    install(monkeypatch, server)
    assert (
        asyncio.run(SMTPNotifier().send(validate_config("smtp", CONFIGS["smtp"]), payload())).status
        == expected
    )


def test_pre_data_timeout_is_transient_and_close_failure_does_not_undo_success(monkeypatch):
    server = SMTPServer(error=TimeoutError("secret"), phase="login")
    install(monkeypatch, server)
    notifier = SMTPNotifier()
    config = validate_config("smtp", CONFIGS["smtp"])
    assert asyncio.run(notifier.send(config, payload())).status == "transient_error"
    server.error = None

    def close():
        raise smtplib.SMTPServerDisconnected("secret")

    monkeypatch.setattr(server, "close", close)
    assert asyncio.run(notifier.send(config, payload())).status == "success"


def test_cancelled_thread_does_not_overlap_retry_or_block_event_loop(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    server = SMTPServer()
    install(monkeypatch, server)

    def blocking_data(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return {}

    monkeypatch.setattr(server, "send_message", blocking_data)

    async def run():
        notifier = SMTPNotifier()
        config = validate_config("smtp", CONFIGS["smtp"])
        first = asyncio.create_task(notifier.send(config, payload()))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            second = await notifier.send(config, payload())
            assert second.code == "smtp_busy"
        finally:
            release.set()

    asyncio.run(run())
    assert server.calls[-1] == ("close",)
