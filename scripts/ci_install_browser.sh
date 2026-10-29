#!/usr/bin/env bash
# Install Chromium for Playwright on a GitHub runner with bounded apt downloads.
set -euo pipefail
sudo python3 - <<'PY'
from pathlib import Path
mirrors = Path("/etc/apt/apt-mirrors.txt")
if mirrors.is_file():
    mirrors.write_text(
        "https://archive.ubuntu.com/ubuntu/\tpriority:1\n"
        "https://security.ubuntu.com/ubuntu/\tpriority:2\n"
        "http://azure.archive.ubuntu.com/ubuntu/\tpriority:3\n"
    )
Path("/etc/apt/apt.conf.d/99seekbell-ci-network").write_text(
    'Acquire::Retries "2";\n'
    'Acquire::http::Timeout "30";\n'
    'Acquire::https::Timeout "30";\n'
)
PY
timeout --signal=TERM --kill-after=10s 4m pnpm --dir frontend exec playwright install --with-deps chromium
