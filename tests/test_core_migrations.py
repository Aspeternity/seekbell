import pytest
from seekbell.config import Settings
from seekbell.db.models import NotificationTarget, Source, SourceState
from seekbell.db.runtime import create_database_engine, migrate, schema_revision
from sqlalchemy import event, inspect, text
from sqlalchemy.orm import Session


def test_upgrade_existing_m0_preserves_installation_and_seeds_disabled_source(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0001_installation")
        with engine.connect() as connection:
            marker = connection.execute(text("SELECT * FROM installation")).all()
        migrate(engine)
        migrate(engine)
        with engine.connect() as connection:
            assert connection.execute(text("SELECT * FROM installation")).all() == marker
        with Session(engine) as session:
            assert not session.get(Source, "nodeseek-rss").enabled
            assert not session.get(SourceState, "nodeseek-rss").initialized
            assert session.query(NotificationTarget).count() == 0
    finally:
        engine.dispose()


def test_failed_core_schema_migration_rolls_back_ddl_and_revision(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0001_installation")

        def fail(_connection, _cursor, statement, _parameters, _context, _many):
            if "CREATE TABLE outbox " in statement:
                raise RuntimeError("synthetic migration fault")

        event.listen(engine, "before_cursor_execute", fail)
        with pytest.raises(RuntimeError, match="migration fault"):
            migrate(engine)
        event.remove(engine, "before_cursor_execute", fail)
        assert schema_revision(engine) == "0001_installation"
        assert set(inspect(engine).get_table_names()) == {"installation", "alembic_version"}
        migrate(engine)
        assert schema_revision(engine) == "0003_notifications"
    finally:
        engine.dispose()
