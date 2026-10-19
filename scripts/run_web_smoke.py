"""Disposable local-only service for Playwright; never uses the developer database."""

from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from seekbell.config import Settings
from seekbell.main import create_app

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    static = root / "frontend" / "dist"
    if not (static / "index.html").is_file():
        raise SystemExit("Build the production frontend before running browser checks")
    with TemporaryDirectory(prefix="seekbell-web-test-") as directory:
        uvicorn.run(
            create_app(Settings(data_dir=Path(directory), static_dir=static)),
            host="127.0.0.1",
            port=8011,
            workers=1,
            proxy_headers=False,
            access_log=False,
            log_level="warning",
        )
