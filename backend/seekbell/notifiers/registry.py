"""Decrypt only at the network boundary. No plaintext configuration in outbox."""

import httpx

from seekbell.domain.delivery import SendResult
from seekbell.notifiers.configs import validate_config
from seekbell.notifiers.credentials import CredentialError, CredentialVault
from seekbell.notifiers.http import HTTPNotifier
from seekbell.notifiers.smtp import SMTPNotifier


class ConfiguredNotifier:
    def __init__(self, kind, vault, transport):
        self.kind, self.vault, self.transport = kind, vault, transport

    async def send(self, target_snapshot: dict, payload: dict) -> SendResult:
        try:
            config = self.vault.unseal(
                target_snapshot["id"], self.kind, target_snapshot["config_ciphertext"]
            )
            config = validate_config(self.kind, config)
        except (CredentialError, ValueError, KeyError):
            return SendResult(status="permanent_error", code="target_credentials_invalid")
        return await self.transport.send(config, payload)


class NotifierRegistry:
    def __init__(
        self, vault: CredentialVault, *, http_transport: httpx.AsyncBaseTransport | None = None
    ):
        self.http = {
            kind: HTTPNotifier(kind, transport=http_transport)
            for kind in ("telegram", "bark", "webhook")
        }
        transports = {**self.http, "smtp": SMTPNotifier()}
        self.notifiers = {
            kind: ConfiguredNotifier(kind, vault, transport)
            for kind, transport in transports.items()
        }

    async def aclose(self):
        for transport in self.http.values():
            await transport.aclose()
