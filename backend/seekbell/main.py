import asyncio
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from seekbell.api.auth import router as auth_router
from seekbell.api.history import router as history_router
from seekbell.api.management import router as management_router
from seekbell.api.overview import router as overview_router
from seekbell.api.sending import install_errors
from seekbell.api.sending import router as sending_router
from seekbell.api.system import router
from seekbell.config import Settings
from seekbell.db.models import (
    AlertDelivery,
    ManualDelivery,
    NotificationTarget,
    Outbox,
    TargetTestAttempt,
)
from seekbell.db.runtime import create_database_engine, instance_lock, migrate
from seekbell.notifiers.credentials import CredentialError, CredentialVault
from seekbell.notifiers.registry import NotifierRegistry
from seekbell.services.authentication import LoginLimiter
from seekbell.services.manual_sending import ConfiguredTargetTesting, ManualSending
from seekbell.services.runtime import Runtime


def stored_credentials(session):
    values = list(
        session.execute(
            select(
                NotificationTarget.id, NotificationTarget.kind, NotificationTarget.config_ciphertext
            ).where(NotificationTarget.config_ciphertext.is_not(None))
        ).all()
    )
    if not values:
        # Deleting the last current config must not silently reconstruct a key
        # beside retained encrypted delivery evidence. One snapshot verifies
        # the same installation key without scanning the full history.
        for model in (Outbox, TargetTestAttempt, ManualDelivery, AlertDelivery):
            snapshot = session.scalar(
                select(model.target_snapshot)
                .where(model.target_snapshot["config_ciphertext"].as_string().is_not(None))
                .limit(1)
            )
            if snapshot:
                values.append((snapshot["id"], snapshot["kind"], snapshot["config_ciphertext"]))
                break
    return values


def create_app(settings: Settings | None = None, *, runtime_factory=None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        with instance_lock(settings.data_dir.resolve()):
            engine = create_database_engine(settings)
            try:
                # Migration/credential validation must complete before actors can start.
                await run_in_threadpool(migrate, engine)
                app.state.engine = engine
                key_path = settings.data_dir.resolve() / "credentials.key"
                with Session(engine) as session:
                    encrypted = stored_credentials(session)
                if not key_path.exists() and not encrypted:
                    app.state.vault = CredentialVault.open(settings.data_dir.resolve(), create=True)
                else:
                    app.state.vault = CredentialVault.open(settings.data_dir.resolve())
                # Validate current credentials, or retained snapshots after deletion.
                for key, kind, ciphertext in encrypted:
                    app.state.vault.unseal(key, kind, ciphertext)
                registry = NotifierRegistry(app.state.vault)
                try:
                    app.state.target_testing = ConfiguredTargetTesting(engine, registry.notifiers)
                    app.state.manual_sending = ManualSending(engine, registry.notifiers)
                    app.state.sending_gate = asyncio.Semaphore(2)
                    runtime = (runtime_factory or Runtime)(engine, registry.notifiers)
                    app.state.runtime = runtime
                    try:
                        await runtime.start()
                        yield
                    finally:
                        await runtime.aclose()
                finally:
                    await registry.aclose()
            finally:
                engine.dispose()

    app = FastAPI(title="SeekBell", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.csrf_key = secrets.token_bytes(32)
    app.state.login_limiter = LoginLimiter()

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, error: RequestValidationError):
        # Never serialize body/input values (credentials, rules or pasted secrets).
        return JSONResponse({"detail": "字段格式或长度无效，请检查后重试。"}, status_code=422)

    @app.exception_handler(ValueError)
    async def invalid_configuration(request: Request, error: ValueError):
        detail = (
            "凭据不可用，请检查原始密钥。"
            if isinstance(error, CredentialError)
            else "配置无效，请检查字段及关联目标。"
        )
        return JSONResponse({"detail": detail}, status_code=422)

    @app.middleware("http")
    async def private_responses(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        return response

    app.include_router(router)
    app.include_router(auth_router)
    app.include_router(management_router)
    app.include_router(history_router)
    app.include_router(overview_router)
    app.include_router(sending_router)
    install_errors(app)
    # No SPA catch-all: unknown API endpoints and missing assets keep their real 404 status.
    if (settings.static_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="frontend")
    return app
