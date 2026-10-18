from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from seekbell.api.system import router
from seekbell.config import Settings
from seekbell.db.runtime import create_database_engine, instance_lock, migrate


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        with instance_lock(settings.data_dir.resolve()):
            engine = create_database_engine(settings)
            try:
                # A migration failure prevents startup; there is no background collector in M0.
                await run_in_threadpool(migrate, engine)
                app.state.engine = engine
                yield
            finally:
                engine.dispose()

    app = FastAPI(title="SeekBell", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.include_router(router)
    # No SPA catch-all: unknown API endpoints and missing assets keep their real 404 status.
    if (settings.static_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="frontend")
    return app
