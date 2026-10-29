"""Offline backup/restore rehearsal; all databases, passwords and messages are synthetic."""

import asyncio
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seekbell.backup import create_backup, restore_backup
from seekbell.collectors.rss import parse_rss
from seekbell.config import Settings
from seekbell.db.models import (
    AlertDelivery,
    DeliveredPost,
    Outbox,
    RetentionPolicy,
    Source,
    Website,
    WebsiteInstallation,
    WorkspacePreferences,
)
from seekbell.db.runtime import create_database_engine, migrate
from seekbell.db.transactions import write_session
from seekbell.domain.delivery import SendResult
from seekbell.domain.rules import Rule
from seekbell.notifiers.credentials import CredentialVault
from seekbell.services.alerts import observe, update_settings
from seekbell.services.authentication import initialize, login, session_info
from seekbell.services.configuration import Configuration
from seekbell.services.delivery import DeliveryWorker
from seekbell.services.demo import SyntheticStream
from seekbell.services.ingestion import Ingestion
from seekbell.sites.nodeseek import NodeSeekAdapter

PASSWORD = "Synthetic-Backup-Password"
ADMIN_PASSWORD = "Synthetic-Administrator-2026"


def table_data(path):
    with closing(sqlite3.connect(path)) as connection:
        names = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return {
            name: connection.execute('SELECT * FROM "' + name.replace('"', '""') + '"').fetchall()
            for (name,) in names
        }


def prepare(settings):
    settings.data_dir.mkdir(mode=0o700)
    engine = create_database_engine(settings)
    migrate(engine)
    vault = CredentialVault.open(settings.data_dir, create=True)
    token, _ = initialize(engine, "backup_admin", ADMIN_PASSWORD, timezone="America/Los_Angeles")
    config = Configuration(engine, vault)
    target = config.create_target(
        "Synthetic backup target",
        kind="webhook",
        config={"url": "https://receiver.example.test/backup-synthetic-private"},
    )
    config.create_task("Synthetic backup rule", Rule(), [target], at=1)
    with write_session(engine) as session:
        session.add(WebsiteInstallation(website_id="nodeseek"))
        session.get(Website, "nodeseek").enabled = True
        session.get(Source, "nodeseek-rss").enabled = True
        session.get(WorkspacePreferences, 1).name = "合成恢复空间"
        session.get(RetentionPolicy, 1).days = 45
    adapter, ingestion = NodeSeekAdapter(), Ingestion(engine)

    def batch(*ids):
        # The existing offline stream generates deterministic synthetic RSS bytes.
        stream = SyntheticStream(ids)
        return adapter.normalize(parse_rss(stream.body))

    ingestion.ingest("nodeseek-rss", batch(9001), at=10)
    ingestion.ingest("nodeseek-rss", batch(9001, 9002), at=20)
    worker = DeliveryWorker(engine, {})
    claim = worker.claim(at=20)
    worker.finish(claim, SendResult(status="success"), at=21)
    ingestion.ingest("nodeseek-rss", batch(9001, 9002, 9003), at=30)
    update_settings(engine, True, [target], 1)
    with write_session(engine) as session:
        observe(
            session,
            "runtime:backup_demo",
            True,
            label="合成备份事件",
            code="synthetic_failure",
            at=31,
        )
        observe(session, "runtime:backup_demo", False, label="合成备份事件", at=32)
    engine.dispose()
    return token, target


def exercise(root):
    settings = Settings(data_dir=root / "source", build_revision="synthetic-backup-demo")
    token, target = prepare(settings)
    before = table_data(settings.database_path)
    archive, restored = root / "rehearsal.sbbackup", root / "restored"
    create_backup(settings, archive, password=PASSWORD)
    restore_backup(
        settings,
        archive,
        restored,
        password=PASSWORD,
    )
    assert table_data(settings.database_path) == before
    after = table_data(restored / "seekbell.sqlite3")
    assert after.pop("login_sessions") == []
    before.pop("login_sessions")
    assert after == before
    engine = create_database_engine(Settings(data_dir=restored))
    try:
        assert session_info(engine, token) is None
        assert login(engine, "backup_admin", ADMIN_PASSWORD)
        vault = CredentialVault.open(restored)
        sends = []

        class SyntheticNotifier:
            async def send(self, snapshot, message):
                decoded = vault.unseal(
                    snapshot["id"], snapshot["kind"], snapshot["config_ciphertext"]
                )
                assert decoded["url"].endswith("backup-synthetic-private")
                sends.append(message)
                return SendResult(status="success")

        with Session(engine) as session:
            pending = session.scalar(
                select(func.count()).select_from(Outbox).where(Outbox.status == "pending")
            )
            alerts = session.scalar(
                select(func.count())
                .select_from(AlertDelivery)
                .where(AlertDelivery.result == "pending")
            )
            assert pending == 1 and alerts == 2
        asyncio.run(
            DeliveryWorker(engine, {"webhook": SyntheticNotifier()}, clock=lambda: 40).run_once()
        )
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(DeliveredPost)) == 2
        assert len(sends) == 1 and sends[0]["post"]["external_post_id"] == "9003"
    finally:
        engine.dispose()
    return {
        "mode": "offline_synthetic",
        "all_tables_preserved": True,
        "source_unchanged": True,
        "old_sessions_revoked": True,
        "restored_login": True,
        "original_key_usable": True,
        "pending_automatic": pending,
        "pending_alerts": alerts,
        "resumed_sends": 1,
    }


def main():
    with TemporaryDirectory(prefix="seekbell-backup-demo-") as directory:
        print(json.dumps(exercise(Path(directory))))


if __name__ == "__main__":
    main()
