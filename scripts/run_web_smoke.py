"""Disposable local-only service for Playwright; never uses the developer database."""

import argparse
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from seekbell.config import Settings
from seekbell.main import create_app

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--history", action="store_true")
    group.add_argument("--sending", action="store_true")
    group.add_argument("--runtime", action="store_true")
    group.add_argument("--operations", action="store_true")
    group.add_argument("--retention", action="store_true")
    group.add_argument("--system", action="store_true")
    args = parser.parse_args()
    seeded = args.history or args.sending or args.operations or args.retention or args.system
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from tests.retention_helpers import retention_runtime_factory, seed_retention
    from tests.runtime_helpers import (
        PassiveRuntime,
        operations_runtime_factory,
        synthetic_runtime_factory,
    )
    from tests.system_helpers import seed_system, system_runtime_factory

    static = root / "frontend" / "dist"
    if not (static / "index.html").is_file():
        raise SystemExit("Build the production frontend before running browser checks")
    with TemporaryDirectory(prefix="seekbell-web-test-") as directory:
        if seeded:
            # Explicit synthetic-only harness; never an application API or seed flag.
            from seekbell.db.runtime import create_database_engine, instance_lock, migrate
            from seekbell.notifiers.credentials import CredentialVault

            from tests.history_helpers import seed_history

            settings = Settings(data_dir=Path(directory), static_dir=static)
            with instance_lock(Path(directory)):
                engine = create_database_engine(settings)
                try:
                    migrate(engine)
                    if args.system:
                        seed_system(engine)
                    elif args.retention:
                        seed_retention(engine)
                    else:
                        seed_history(engine, CredentialVault.open(Path(directory), create=True))
                finally:
                    engine.dispose()
        app = create_app(
            Settings(data_dir=Path(directory), static_dir=static),
            runtime_factory=(
                system_runtime_factory
                if args.system
                else retention_runtime_factory
                if args.retention
                else operations_runtime_factory
                if args.operations
                else synthetic_runtime_factory
                if args.runtime
                else PassiveRuntime
            ),
        )
        if seeded:
            from datetime import UTC, datetime

            from seekbell.api.overview import snapshot_time

            app.dependency_overrides[snapshot_time] = lambda: datetime(
                2026, 10, 20, tzinfo=UTC
            ).timestamp()
        if args.sending or args.operations:
            from tests.sending_helpers import install_synthetic_sending

            install_synthetic_sending(app)
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=8017
            if args.system
            else 8016
            if args.retention
            else 8015
            if args.operations
            else 8014
            if args.runtime
            else 8013
            if args.sending
            else 8012
            if args.history
            else 8011,
            workers=1,
            proxy_headers=False,
            access_log=False,
            log_level="warning",
        )
