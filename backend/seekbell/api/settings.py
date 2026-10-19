import time
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field, SecretStr, field_validator

from seekbell.api.auth import require_administrator
from seekbell.api.management import Input, mutate
from seekbell.services.auth import COOKIE_NAME, Identity

router = APIRouter(prefix="/api/manage", dependencies=[Depends(require_administrator)])


class SettingsInput(Input):
    expected_revision: int = Field(ge=1)
    timezone: str = Field(min_length=1, max_length=64)
    retention_days: int = Field(ge=1, le=3650)
    alert_target_id: str | None = Field(default=None, min_length=1, max_length=36)


class CleanupInput(Input):
    expected_revision: int = Field(ge=1)
    confirmed: bool

    @field_validator("confirmed")
    @classmethod
    def require_confirmation(cls, value):
        if not value:
            raise ValueError("Confirmation required")
        return value


class AccountInput(Input):
    username: str = Field(min_length=1, max_length=64)
    current_password: SecretStr = Field(min_length=1, max_length=128)
    new_password: SecretStr | None = Field(default=None, min_length=15, max_length=128)

    @field_validator("username")
    @classmethod
    def clean_username(cls, value):
        value = value.strip()
        if not value or not value.isprintable():
            raise ValueError("Invalid username")
        return value


@router.get("/settings")
def settings(request: Request):
    return {
        **request.app.state.runtime.settings.get(),
        "username": request.app.state.authentication.username(),
        "scheduler": request.app.state.runtime.snapshot(),
    }


@router.get("/settings/timezones")
def timezones(request: Request):
    return request.app.state.runtime.settings.timezones()


@router.put("/settings")
def update_settings(request: Request, body: SettingsInput):
    mutate(request.app.state.runtime.settings.update, **body.model_dump())
    return settings(request)


@router.post("/settings/cleanup")
def cleanup(request: Request, body: CleanupInput):
    return mutate(
        request.app.state.runtime.settings.cleanup,
        at=time.time(),
        expected_revision=body.expected_revision,
    )


@router.put("/account", status_code=204)
def account(
    request: Request,
    response: Response,
    body: AccountInput,
    identity: Annotated[Identity, Depends(require_administrator)],
):
    request.app.state.authentication.change_account(
        identity,
        current_password=body.current_password.get_secret_value(),
        username=body.username,
        new_password=body.new_password.get_secret_value() if body.new_password else None,
    )
    response.delete_cookie(
        COOKIE_NAME, httponly=True, secure=request.url.scheme == "https", samesite="strict"
    )
