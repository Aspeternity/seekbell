"""Check an already-built local image in an isolated, disposable Docker environment."""

import argparse
import json
import subprocess
import time
import uuid

PROBE = """
import importlib.util
import json
import os
import re
import sqlite3
import urllib.request

def get(path):
    return urllib.request.urlopen('http://127.0.0.1:8000' + path, timeout=3).read().decode()

assert json.loads(get('/health/live'))['status'] == 'ok'
assert json.loads(get('/health/ready'))['status'] == 'ok'
info = json.loads(get('/api/version'))
from alembic.script import ScriptDirectory
from seekbell.db.runtime import migration_config
expected = ScriptDirectory.from_config(migration_config()).get_current_head()
assert info['database_revision'] == expected
assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', get('/'))
assert len(assets) >= 2
for asset in assets:
    assert get(asset)
assert os.getuid() == 10001
for module in ('pytest', 'ruff'):
    assert importlib.util.find_spec(module) is None
with sqlite3.connect('/data/seekbell.sqlite3') as connection:
    marker = connection.execute('SELECT * FROM installation').fetchall()
    assert connection.execute('SELECT enabled FROM sources').fetchall() == [(0,)]
    assert connection.execute('SELECT COUNT(*) FROM notification_targets').fetchone() == (0,)
# Verify the installed wheel includes channel schemas and working encryption.
import tempfile
from pathlib import Path
from seekbell.notifiers.configs import channel_schemas
from seekbell.notifiers.credentials import CredentialVault
from seekbell.notifiers.registry import NotifierRegistry
assert set(channel_schemas()) == {'telegram', 'bark', 'smtp', 'webhook'}
with tempfile.TemporaryDirectory(prefix='seekbell-crypto-check-') as directory:
    keyring = CredentialVault.open(Path(directory), create=True)
    sealed = keyring.seal('synthetic', 'bark', {'device_key': 'synthetic-secret'})
    assert 'synthetic-secret' not in sealed
    restored = CredentialVault.open(Path(directory))
    assert restored.unseal('synthetic', 'bark', sealed) == {'device_key': 'synthetic-secret'}
print(json.dumps({'version': info, 'uid': os.getuid(), 'assets': assets, 'marker': marker}))
"""


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], check=check, text=True, capture_output=True, timeout=30
    )


def wait_ready(container: str, *, require_healthcheck: bool = False) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        result = docker("exec", container, "python", "-c", PROBE, check=False)
        if result.returncode == 0:
            health = docker("inspect", container, "--format", "{{.State.Health.Status}}")
            if not require_healthcheck or health.stdout.strip() == "healthy":
                return
        time.sleep(0.5)
    raise RuntimeError("Container did not become ready:\n" + docker("logs", container).stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    container = "seekbell-check-" + uuid.uuid4().hex[:12]
    volume = container + "-data"
    try:
        docker("volume", "create", volume)
        docker(
            "run",
            "-d",
            "--pull",
            "never",
            "--name",
            container,
            "--network",
            "none",
            "--mount",
            f"type=volume,source={volume},target=/data",
            args.image,
        )
        wait_ready(container, require_healthcheck=True)
        first = json.loads(docker("exec", container, "python", "-c", PROBE).stdout)
        assert first["version"]["build_revision"] == args.revision
        locked = docker("exec", container, "python", "-m", "seekbell.db", "current", check=False)
        assert locked.returncode != 0 and "Another SeekBell process" in locked.stderr
        docker("restart", container)
        wait_ready(container)
        second = json.loads(docker("exec", container, "python", "-c", PROBE).stdout)
        assert first == second, "Installation or API changed across restart"
        demo = json.loads(
            docker("exec", container, "python", "-m", "seekbell.services.demo").stdout
        )
        assert demo["mode"] == "offline_synthetic"
        assert demo["final_status"] == "sent" and demo["duplicate_poll_queued"] == 0
        image_id = docker("image", "inspect", args.image, "--format", "{{.Id}}").stdout.strip()
        print(
            json.dumps(
                {
                    "image_id": image_id,
                    **second,
                    "healthcheck": "passed before restart",
                    "restart_persistence": "passed",
                    "instance_lock": "passed",
                    "network": "none",
                    "offline_core_demo": demo,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        docker("rm", "-f", container, check=False)
        docker("volume", "rm", volume, check=False)


if __name__ == "__main__":
    main()
