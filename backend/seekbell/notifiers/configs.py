"""Validated channel contracts. The entire stored configuration is encrypted."""

import re
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

Text = Annotated[str, Field(min_length=1, max_length=2048)]
Secret = Annotated[
    str, Field(min_length=1, max_length=4096, repr=False, json_schema_extra={"writeOnly": True})
]


def http_url(value: str, *, base: bool = False) -> str:
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme in ("http", "https")
            and parsed.hostname
            and parsed.port != 0
            and not parsed.username
            and not parsed.password
            and not parsed.fragment
            and not any(ord(c) <= 32 or ord(c) == 127 for c in value)
            and "\\" not in value
        )
    except ValueError:
        valid = False
    if not valid or (base and parsed.query):
        raise ValueError("Use an HTTP(S) URL without userinfo or fragment")
    return value.rstrip("/") if base else value


class ChannelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    include_summary: bool = False
    summary_limit: int = Field(default=300, ge=0, le=1000)


class TelegramConfig(ChannelConfig):
    base_url: str = Field(
        default="https://api.telegram.org", repr=False, json_schema_extra={"writeOnly": True}
    )
    bot_token: Secret
    chat_id: Secret
    message_thread_id: int | None = Field(default=None, gt=0)

    @field_validator("base_url")
    @classmethod
    def url(cls, value):
        return http_url(value, base=True)

    @field_validator("bot_token")
    @classmethod
    def token(cls, value):
        if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", value):
            raise ValueError("Invalid bot token format")
        return value

    @field_validator("chat_id")
    @classmethod
    def chat(cls, value):
        if not re.fullmatch(r"-?[0-9]+|@[A-Za-z0-9_]+", value):
            raise ValueError("Use a numeric chat ID or @username")
        return value


class BarkConfig(ChannelConfig):
    base_url: str = Field(
        default="https://api.day.app", repr=False, json_schema_extra={"writeOnly": True}
    )
    device_key: Secret
    group: str = Field(default="SeekBell", max_length=100)

    @field_validator("base_url")
    @classmethod
    def url(cls, value):
        return http_url(value, base=True)


class WebhookConfig(ChannelConfig):
    url: Secret
    headers: dict[str, str] = Field(
        default_factory=dict, repr=False, json_schema_extra={"writeOnly": True}
    )
    # Generic receivers may acknowledge with any 2xx or explicit {"ok": true}.
    response_mode: Literal["status", "json_ok"] = "json_ok"

    @field_validator("url")
    @classmethod
    def url_value(cls, value):
        return http_url(value)

    @field_validator("headers")
    @classmethod
    def valid_headers(cls, value):
        blocked = {
            "host",
            "content-length",
            "transfer-encoding",
            "connection",
            "content-type",
            "idempotency-key",
            "cookie",
            "proxy-authorization",
            "accept-encoding",
        }
        if len(value) > 20:
            raise ValueError("At most 20 custom headers")
        for key, item in value.items():
            if (
                not re.fullmatch(r"[!#$%&'*+.^_~0-9A-Za-z-]+", key)
                or key.lower() in blocked
                or key.lower().startswith("proxy-")
                or len(item) > 4096
                or any(ord(c) < 32 or ord(c) > 126 for c in item)
            ):
                raise ValueError("Invalid custom header")
        if len({key.lower() for key in value}) != len(value):
            raise ValueError("Duplicate header")
        return value


def mailbox(value: str) -> str:
    # One ASCII envelope recipient per target avoids partial-acceptance ambiguity.
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_{}|~-]+@[A-Za-z0-9.-]+", value):
        raise ValueError("Use a single mailbox address without display name")
    if len(value) > 254:
        raise ValueError("Mailbox address too long")
    return value


class SMTPConfig(ChannelConfig):
    host: Text
    port: int = Field(default=465, ge=1, le=65535)
    security: Literal["tls", "starttls", "plain"] = "tls"
    allow_insecure: bool = False
    username: str = Field(
        default="", max_length=500, repr=False, json_schema_extra={"writeOnly": True}
    )
    password: str = Field(
        default="", max_length=4096, repr=False, json_schema_extra={"writeOnly": True}
    )
    from_address: Secret
    to_address: Secret

    @field_validator("host")
    @classmethod
    def host_value(cls, value):
        if any(ord(c) <= 32 for c in value) or any(c in value for c in "/@\\"):
            raise ValueError("Use a hostname or IP address")
        return value

    @field_validator("from_address", "to_address")
    @classmethod
    def address(cls, value):
        return mailbox(value)

    @model_validator(mode="after")
    def credentials(self):
        if bool(self.username) != bool(self.password):
            raise ValueError("Username and password must be provided together")
        if self.security == "plain" and not self.allow_insecure:
            raise ValueError("Plain SMTP requires explicit allow_insecure")
        return self


CONFIGS = {
    "telegram": TelegramConfig,
    "bark": BarkConfig,
    "smtp": SMTPConfig,
    "webhook": WebhookConfig,
}


def validate_config(kind: str, values: dict) -> dict:
    if kind not in CONFIGS:
        raise ValueError("Unsupported notification channel")
    try:
        return CONFIGS[kind].model_validate(values).model_dump(mode="json")
    except ValidationError as error:
        fields = sorted(
            {
                str(item["loc"][0])
                if item["loc"] and item["loc"][0] in CONFIGS[kind].model_fields
                else "configuration"
                for item in error.errors(include_input=False)
            }
        )
        raise ValueError("Invalid notification fields: " + ", ".join(fields)) from None


def channel_schemas() -> dict:
    return {kind: model.model_json_schema() for kind, model in CONFIGS.items()}


def public_config(kind: str, values: dict) -> tuple[dict, list[str]]:
    model = CONFIGS[kind]
    secrets = {
        name
        for name, field in model.model_fields.items()
        if (field.json_schema_extra or {}).get("writeOnly")
    }
    return (
        {key: item for key, item in values.items() if key not in secrets},
        sorted(key for key in secrets if values.get(key)),
    )
