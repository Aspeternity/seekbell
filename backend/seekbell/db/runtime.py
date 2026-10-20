import sqlite3
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import URL, Engine, create_engine, event, text

from seekbell.config import Settings


def migration_config() -> Config:
    config = Config()
    # Installed wheels carry migrations, so startup does not depend on the checkout.
    config.set_main_option("script_location", str(files("seekbell").joinpath("migrations")))
    return config


def create_database_engine(settings: Settings) -> Engine:
    engine = create_engine(
        URL.create("sqlite", database=str(settings.database_path)),
        connect_args={"check_same_thread": False, "timeout": 5},
        hide_parameters=True,
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection: sqlite3.Connection, _record: object) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine


def migrate(engine: Engine, revision: str = "head") -> None:
    config = migration_config()
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        config.attributes["upgrading_existing"] = (
            MigrationContext.configure(connection).get_current_revision() is not None
        )
        config.attributes["connection"] = connection
        try:
            command.upgrade(config, revision)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def schema_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def database_ready(engine: Engine) -> bool:
    expected = ScriptDirectory.from_config(migration_config()).get_current_head()
    with engine.connect() as connection:
        revision = MigrationContext.configure(connection).get_current_revision()
        return revision == expected and connection.scalar(text("SELECT id FROM installation")) == 1


@contextmanager
def instance_lock(data_dir: Path):
    # Linux is the supported service runtime. Hold the descriptor for the entire lifespan.
    import fcntl

    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (data_dir / ".instance.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another SeekBell process owns this data directory") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
