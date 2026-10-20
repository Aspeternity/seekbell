"""Explicit synthetic dispatch only; never installed in the product runtime."""

import asyncio

from fastapi import Request
from seekbell.api.sending import services
from seekbell.domain.delivery import SendResult
from seekbell.services.manual_sending import ConfiguredTargetTesting, ManualSending


def install_synthetic_sending(app):
    class SyntheticNotifier:
        async def send(self, snapshot, payload):
            await asyncio.sleep(0.08)
            status = (
                "unknown"
                if "合成未知" in snapshot["name"]
                else "permanent_error"
                if "合成失败" in snapshot["name"]
                else "success"
            )
            return SendResult(status=status)

    async def synthetic_services(request: Request):
        engine = request.app.state.engine
        notifiers = {kind: SyntheticNotifier() for kind in ("telegram", "bark", "smtp", "webhook")}
        return ConfiguredTargetTesting(engine, notifiers), ManualSending(engine, notifiers)

    app.dependency_overrides[services] = synthetic_services
