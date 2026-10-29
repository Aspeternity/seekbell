import asyncio
import secrets
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from seekbell.api.auth import router as auth_router
from seekbell.api.backups import router as backups_router
from seekbell.api.backups import setup_router as backup_setup_router
from seekbell.api.history import router as history_router
from seekbell.api.hotlists import router as hotlists_router
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
from seekbell.services.hotlists import HotlistService
from seekbell.services.manual_sending import ConfiguredTargetTesting, ManualSending
from seekbell.services.request_budget import WebsiteRequestBudget
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


def create_app(
    settings: Settings | None = None, *, runtime_factory=None, hotlist_factory=None
) -> FastAPI:
    settings = settings or Settings()

    async def open_workspace(app: FastAPI):
        """Build every database-bound service; a backup restore closes and reopens them."""
        stack = AsyncExitStack()
        try:
            engine = create_database_engine(settings)
            stack.callback(engine.dispose)
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
            stack.push_async_callback(registry.aclose)
            runtime = (runtime_factory or Runtime)(engine, registry.notifiers)
            request_budget = getattr(runtime, "request_budget", None) or WebsiteRequestBudget(
                engine
            )
            app.state.hotlists = (
                hotlist_factory()
                if hotlist_factory
                else HotlistService(
                    engine=engine,
                    request_budget=request_budget,
                    collection_active=lambda: runtime.active,
                )
            )
            stack.push_async_callback(app.state.hotlists.aclose)
            app.state.target_testing = ConfiguredTargetTesting(engine, registry.notifiers)
            app.state.manual_sending = ManualSending(engine, registry.notifiers)
            app.state.sending_gate = asyncio.Semaphore(2)
            app.state.runtime = runtime
            stack.push_async_callback(runtime.aclose)
            await runtime.start()
        except BaseException:
            await stack.aclose()
            raise
        app.state.workspace = stack

    async def close_workspace(app: FastAPI):
        stack, app.state.workspace = app.state.workspace, None
        if stack is not None:
            await stack.aclose()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        with instance_lock(settings.data_dir.resolve()):
            app.state.backup_gate = asyncio.Lock()
            await open_workspace(app)
            try:
                yield
            finally:
                await close_workspace(app)

    app = FastAPI(title="SeekBell", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.csrf_key = secrets.token_bytes(32)
    app.state.login_limiter = LoginLimiter()
    app.state.open_workspace = open_workspace
    app.state.close_workspace = close_workspace
    app.state.restoring = False
    app.state.in_flight = 0

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
    async def restore_pause(request: Request, call_next):
        # While a restore swaps the data files no request may touch the old services.
        if request.url.path.startswith(("/api/", "/health/")):
            if app.state.restoring:
                return JSONResponse(
                    {"detail": "正在恢复备份，请稍候刷新。"},
                    status_code=503,
                    headers={"Retry-After": "5", "Cache-Control": "no-store"},
                )
            app.state.in_flight += 1
            try:
                return await call_next(request)
            finally:
                app.state.in_flight -= 1
        return await call_next(request)

    @app.middleware("http")
    async def private_responses(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        return response

    if settings.trusted_proxy_ips:
        # Applied consistently to the packaged Uvicorn and in-process ASGI entrypoints.
        # Uvicorn's outer proxy middleware remains disabled to avoid double interpretation.
        app.add_middleware(
            ProxyHeadersMiddleware, trusted_hosts=settings.trusted_proxy_ips.split(",")
        )

    app.include_router(router)
    app.include_router(auth_router)
    app.include_router(management_router)
    app.include_router(hotlists_router)
    app.include_router(backups_router)
    app.include_router(backup_setup_router)
    app.include_router(history_router)
    app.include_router(overview_router)
    app.include_router(sending_router)
    install_errors(app)
    # No SPA catch-all: unknown API endpoints and missing assets keep their real 404 status.
    if (settings.static_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="frontend")
    return app
