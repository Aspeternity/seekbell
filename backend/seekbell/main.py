from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from seekbell.api.auth import router as auth_router
from seekbell.api.management import router as management_router
from seekbell.api.system import router
from seekbell.config import Settings
from seekbell.db.runtime import create_database_engine, instance_lock, migrate
from seekbell.services.auth import Authentication, AuthError
from seekbell.services.management import application_configuration


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        with instance_lock(settings.data_dir.resolve()):
            engine = create_database_engine(settings)
            try:
                # A migration failure prevents serving any requests.
                await run_in_threadpool(migrate, engine)
                app.state.engine = engine
                app.state.authentication = await run_in_threadpool(Authentication, engine)
                app.state.configuration = await run_in_threadpool(
                    application_configuration, engine, settings.data_dir.resolve()
                )
                yield
            finally:
                engine.dispose()

    app = FastAPI(title="SeekBell", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.trusted_proxies)

    @app.middleware("http")
    async def response_policy(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.exception_handler(AuthError)
    async def auth_error(_request: Request, error: AuthError):
        headers = {"Retry-After": "60"} if error.status == 429 else None
        return JSONResponse({"detail": error.message}, status_code=error.status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _error: RequestValidationError):
        # FastAPI's default includes rejected inputs, which may contain credentials.
        return JSONResponse({"detail": "请求参数无效，请检查输入。"}, status_code=422)

    app.state.settings = settings
    app.include_router(auth_router)
    app.include_router(management_router)
    app.include_router(router)
    # No SPA catch-all: unknown API endpoints and missing assets keep their real 404 status.
    if (settings.static_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="frontend")
    return app
