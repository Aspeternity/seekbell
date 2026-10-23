import pytest
from seekbell.config import Settings
from seekbell.db.models import NotificationTarget
from seekbell.db.runtime import create_database_engine, migrate, schema_revision
from sqlalchemy import event, inspect, text
from sqlalchemy.orm import Session


def test_upgrade_from_m1_preserves_rows_and_migration_is_idempotent(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0002_core")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO notification_targets (id,name,kind,revision,enabled) "
                    "VALUES ('synthetic-target','old target','mock',1,1)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO seen_posts (website_id,external_post_id,first_seen_at) "
                    "VALUES ('nodeseek','9002',1)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO outbox (id,website_id,external_post_id,target_id,target_snapshot,"
                    "payload,status,attempt_count,available_at,"
                    "cancel_requested,uncertain,created_at) "
                    "VALUES ('synthetic-event','nodeseek','9002','synthetic-target',"
                    """'{"kind":"mock"}','{"event_id":"synthetic-event"}','pending',0,1,0,0,1)"""
                )
            )
        migrate(engine)
        migrate(engine)
        with Session(engine) as session:
            target = session.get(NotificationTarget, "synthetic-target")
            assert target.name == "old target" and target.config_ciphertext is None
        with engine.connect() as connection:
            row = connection.execute(text("SELECT status,target_snapshot FROM outbox")).one()
            assert row.status == "pending" and row.target_snapshot == '{"kind":"mock"}'
        assert schema_revision(engine) == "0011_linuxdo"
    finally:
        engine.dispose()


def test_failed_notification_migration_rolls_back_tables_columns_and_revision(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0002_core")

        def fail(connection, cursor, statement, parameters, context, many):
            if "ADD COLUMN config_ciphertext" in statement:
                raise RuntimeError("synthetic notification migration failure")

        event.listen(engine, "before_cursor_execute", fail)
        with pytest.raises(RuntimeError, match="notification migration failure"):
            migrate(engine)
        event.remove(engine, "before_cursor_execute", fail)
        assert schema_revision(engine) == "0002_core"
        assert "target_test_attempts" not in inspect(engine).get_table_names()
        assert "config_ciphertext" not in {
            col["name"] for col in inspect(engine).get_columns("notification_targets")
        }
        migrate(engine)
        assert schema_revision(engine) == "0011_linuxdo"
    finally:
        engine.dispose()
