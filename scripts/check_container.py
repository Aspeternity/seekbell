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


AUTH_CHECK = """
import http.cookiejar
import json
import sys
import urllib.error
import urllib.request

jar = http.cookiejar.MozillaCookieJar('/data/.synthetic-auth-cookie')
if sys.argv[1] == 'restart':
    jar.load(ignore_discard=True, ignore_expires=True)
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
base = 'http://127.0.0.1:8000'

def call(path, payload=None, csrf=None, method=None):
    headers = {'Content-Type': 'application/json'}
    if csrf:
        headers['X-CSRF-Token'] = csrf
    request = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with opener.open(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())

credentials = {
    'username': 'synthetic-container-admin', 'password': 'synthetic container passphrase'
}
status, state = call('/api/auth/state')
assert status == 200
if sys.argv[1] == 'setup':
    assert not state['initialized'] and not state['authenticated']
    status, state = call('/api/auth/setup', credentials, state['csrf_token'])
    assert status == 201 and state['authenticated']
    assert call('/api/manage/targets')[1] == []
    assert call('/api/manage/tasks')[1] == []
    status, target = call('/api/manage/targets', {
        'name': 'synthetic packaged Bark', 'kind': 'bark', 'enabled': False,
        'config': {'device_key': 'synthetic-packaged-secret'},
    }, state['csrf_token'])
    assert status == 201 and 'device_key' not in target['config']
    status, task = call('/api/manage/tasks', {
        'name': 'synthetic packaged task', 'rule': {}, 'enabled': False,
        'target_ids': [target['id']],
    }, state['csrf_token'])
    assert status == 201 and task['version'] == 1
    with open('/data/.synthetic-management-state', 'w') as stream:
        json.dump({'target': target['id'], 'task': task['id']}, stream)
    initial = call('/api/manage/settings')[1]
    assert initial['timezone'] is None and initial['retention_days'] == 30
    status, preference = call('/api/manage/settings', {
        'expected_revision': initial['revision'], 'timezone': 'Asia/Shanghai', 'retention_days': 7
    }, state['csrf_token'], method='PUT')
    assert status == 200 and preference['timezone'] == 'Asia/Shanghai'
    jar.save(ignore_discard=True, ignore_expires=True)
else:
    assert state['initialized'] and state['authenticated']
    assert state['username'] == credentials['username']
    status, _ = call('/api/auth/setup', credentials, state['csrf_token'])
    assert status == 409
    status, state = call('/api/auth/login', credentials, state['csrf_token'])
    assert status == 200 and state['authenticated']
    with open('/data/.synthetic-management-state') as stream:
        saved = json.load(stream)
    targets = call('/api/manage/targets')[1]
    tasks = call('/api/manage/tasks')[1]
    assert len(targets) == len(tasks) == 1
    assert targets[0]['id'] == saved['target'] and 'device_key' not in targets[0]['config']
    assert tasks[0]['id'] == saved['task'] and tasks[0]['target_ids'] == [saved['target']]
    assert not targets[0]['enabled'] and not tasks[0]['enabled']
    status, preview = call('/api/manage/rules/preview', {
        'rule': {'groups': [{'all_of': ['VPS']}]}, 'sample': {'title': 'VPS synthetic'},
    }, state['csrf_token'])
    assert status == 200 and preview['result']['status'] == 'match'
preference = call('/api/manage/settings')[1]
assert preference['timezone'] == 'Asia/Shanghai' and preference['retention_days'] == 7
assert 'Asia/Shanghai' in call('/api/manage/settings/timezones')[1]
cleanup_status, cleanup = call('/api/manage/settings/cleanup', {
    'expected_revision': preference['revision'], 'confirmed': True
}, state['csrf_token'])
assert cleanup_status == 200 and sum(cleanup['counts'].values()) == 0
site_status, site = call('/api/manage/site')
assert site_status == 200 and not site['enabled']
assert site['scheduler']['enabled'] and site['scheduler']['healthy']
assert site['scheduler']['components'] == {
    'collector': 'running', 'delivery': 'running', 'maintenance': 'running'
}
assert call('/api/manage/content')[1]['total'] == 0
assert call('/api/manage/overview')[1]['counts']['posts'] == 0
assert len(call('/api/manage/content/options')[1]) == 1
for kind in ('automatic', 'manual', 'test'):
    status, records = call('/api/manage/deliveries?kind=' + kind)
    assert status == 200 and records['items'] == [] and records['total'] == 0
print(json.dumps({
    'administrator_session': 'passed', 'configuration': 'passed', 'mode': sys.argv[1]
}))
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
        docker("exec", container, "python", "-c", AUTH_CHECK, "setup")
        docker("restart", container)
        wait_ready(container)
        second = json.loads(docker("exec", container, "python", "-c", PROBE).stdout)
        assert first == second, "Installation or API changed across restart"
        auth = json.loads(docker("exec", container, "python", "-c", AUTH_CHECK, "restart").stdout)
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
                    "administrator_session_restart": auth["administrator_session"],
                    "management_restart": auth["configuration"],
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
