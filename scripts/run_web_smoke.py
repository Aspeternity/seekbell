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
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    static = root / "frontend" / "dist"
    if not (static / "index.html").is_file():
        raise SystemExit("Build the production frontend before running browser checks")
    with TemporaryDirectory(prefix="seekbell-web-test-") as directory:
        if args.history:
            # Explicit synthetic-only harness; never an application API or seed flag.
            sys.path.insert(0, str(root))
            from seekbell.db.runtime import create_database_engine, instance_lock, migrate
            from seekbell.notifiers.credentials import CredentialVault

            from tests.history_helpers import seed_history

            settings = Settings(data_dir=Path(directory), static_dir=static)
            with instance_lock(Path(directory)):
                engine = create_database_engine(settings)
                try:
                    migrate(engine)
                    seed_history(engine, CredentialVault.open(Path(directory), create=True))
                finally:
                    engine.dispose()
        uvicorn.run(
            create_app(Settings(data_dir=Path(directory), static_dir=static)),
            host="127.0.0.1",
            port=8012 if args.history else 8011,
            workers=1,
            proxy_headers=False,
            access_log=False,
            log_level="warning",
        )
