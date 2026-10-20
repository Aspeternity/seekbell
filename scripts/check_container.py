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


MANAGEMENT_PROBE = """
import http.cookiejar
import json
import urllib.request

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
csrf = ""

def request(path, values=None, method=None):
    headers = {}
    if values is not None:
        headers = {"Content-Type": "application/json", "X-CSRF-Token": csrf}
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/" + path,
        data=None if values is None else json.dumps(values).encode(),
        headers=headers, method=method,
    )
    with opener.open(req, timeout=10) as response:
        if path in ("auth/setup", "auth/login"):
            assert "httponly" in response.headers["set-cookie"].lower()
        return json.load(response)

status = request("auth/status")
csrf = status["csrf"]
session = request("auth/login" if status["initialized"] else "auth/setup",
                  {"username": "container_admin", "password": "Synthetic-Container-2026"})
csrf = session["csrf"]
workspace = request("manage/workspace")
if not workspace["websites"]:
    request("manage/websites", {"adapter_id": "nodeseek"})
if not workspace["targets"]:
    target = request("manage/targets", {
        "name": "Container synthetic", "kind": "webhook", "enabled": False,
        "config": {"url": "https://receiver.example.test/synthetic"},
    })["id"]
else:
    target = workspace["targets"][0]["id"]
if not workspace["tasks"]:
    request("manage/tasks", {
        "name": "Container persistence", "description": "Retained across service restart",
        "website_id": "nodeseek", "enabled": False, "rule": {}, "target_ids": [target],
    })
workspace = request("manage/workspace")
assert len(workspace["websites"]) == 1 and len(workspace["tasks"]) == 1
assert workspace["tasks"][0]["description"] == "Retained across service restart"
assert "url" not in workspace["targets"][0]["config"]
assert workspace["runtime_active"] and workspace["runtime"]["status"] == "running"
# Packaged readonly routes use the same migrated database, with no demo rows.
assert request("manage/history/posts")["total"] == 0
assert request("manage/history/deliveries")["total"] == 0
assert request("manage/history/tests")["total"] == 0
assert request("manage/history/manual")["total"] == 0
assert request("manage/history/options")["websites"][0]["id"] == "nodeseek"
# Packaged management operations remain local and preserve current configuration.
policy = request("manage/retention")
if policy["days"] != 45:
    policy = request("manage/retention", {"days": 45, "revision": policy["revision"]}, method="PUT")
assert policy["days"] == 45
assert request("manage/workspace")["settings"]["retention"] == 45
display = request("manage/display")
if display["timezone"] != "America/Los_Angeles":
    display = request(
        "manage/display", {"timezone": "America/Los_Angeles", "revision": display["revision"]},
        method="PUT",
    )
assert request("manage/workspace")["settings"]["timezone"] == "America/Los_Angeles"
assert not request("manage/alerts")["enabled"]
assert request("manage/alerts/state")["total"] == 0
assert request("manage/alerts/history")["total"] == 0
trial = request("manage/rules/history", {"website_id": "nodeseek", "rule": {}, "limit": 100})
assert trial["sample_count"] == trial["available"] == 0
assert request("manage/websites/nodeseek/connection-test") is None
import urllib.error
try:
    request("manage/websites/nodeseek/connection-test", {"url": "https://receiver.example.test"})
    raise AssertionError("Connection check accepted an arbitrary URL")
except urllib.error.HTTPError as error:
    assert error.code == 422
try:
    request("manage/targets/" + target, {}, method="DELETE")
    raise AssertionError("Target dependency did not block removal")
except urllib.error.HTTPError as error:
    assert error.code == 409
disposable = request("manage/targets", {
    "name": "Container delete check", "kind": "webhook", "enabled": False,
    "config": {"url": "https://receiver.example.test/synthetic"},
})["id"]
request("manage/targets/" + disposable, {}, method="DELETE")
assert all(item["id"] != disposable for item in request("manage/workspace")["targets"])
overview = request("manage/overview?range=7d")
assert overview["runtime_active"] and not any(overview["window"].values())
assert request("manage/runtime")["status"] == "running"
assert overview["configuration"] == {"websites": 1, "tasks": 1, "enabled_tasks": 0, "targets": 1}
assert len(overview["buckets"]) == 7 and overview["recent_matches"] == []
print(json.dumps({
    "website": workspace["websites"][0]["id"], "task": workspace["tasks"][0]["id"],
    "target": workspace["targets"][0]["id"], "note": workspace["tasks"][0]["description"],
    "retention_days": policy["days"], "timezone": display["timezone"],
}))
"""


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], check=check, text=True, capture_output=True, timeout=30
    )


def wait_ready(container: str, *, require_healthcheck: bool = False, probe: str = PROBE) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        result = docker("exec", container, "python", "-c", probe, check=False)
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
        assert demo["manual_send_calls"] == 1 and demo["manual_dedup_preserved"]
        assert demo["target_test_send_calls"] == 1
        lifecycle = json.loads(
            docker("exec", container, "python", "-m", "seekbell.services.runtime_demo").stdout
        )
        assert lifecycle["mode"] == "offline_synthetic" and lifecycle["sends"] == 1
        assert lifecycle["system_alert_sends"] == 2 and lifecycle["alert_history_removed"]
        assert (
            lifecycle["baseline_silent"]
            and lifecycle["cleanup_history_removed"]
            and lifecycle["cleanup_ledgers_preserved"]
            and lifecycle["runtime_stopped"]
            and lifecycle["http_closed"]
        )
        managed_first = json.loads(
            docker("exec", container, "python", "-c", MANAGEMENT_PROBE).stdout
        )
        account_probe = MANAGEMENT_PROBE.replace(
            "print(json.dumps({",
            'csrf = request("auth/administrator", {'
            '"username": "container_updated",'
            '"current_password": "Synthetic-Container-2026",'
            '"new_password": "Synthetic-Container-Updated-2026"'
            '}, method="PUT")["csrf"]\n'
            'assert request("auth/status")["username"] == "container_updated"\n'
            "print(json.dumps({",
        )
        docker("exec", container, "python", "-c", account_probe)
        persisted_probe = MANAGEMENT_PROBE.replace(
            '"container_admin"', '"container_updated"'
        ).replace('"Synthetic-Container-2026"', '"Synthetic-Container-Updated-2026"')
        docker("restart", container)
        wait_ready(container, probe=persisted_probe)
        managed_second = json.loads(
            docker("exec", container, "python", "-c", persisted_probe).stdout
        )
        assert managed_first == managed_second, "Management configuration changed across restart"
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
                    "management_persistence": managed_second,
                    "offline_core_demo": demo,
                    "offline_runtime": lifecycle,
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
