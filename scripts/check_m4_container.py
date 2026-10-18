"""Exercise Compose and stopped-service restore using only temporary, network-none data."""

import argparse
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

CHECK = r"""
import http.cookiejar
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from seekbell.backup import create_backup, restore_backup
from seekbell.config import Settings
from seekbell.db.runtime import create_database_engine
from seekbell.notifiers.credentials import CredentialVault
from seekbell.services.configuration import Configuration

assert os.getuid() == 10001
try:
    Path('/rootfs-write-probe').write_text('must fail')
except OSError:
    pass
else:
    raise AssertionError('Root filesystem must be read-only')
password = 'synthetic M4 administrator phrase'
passphrase = 'synthetic M4 backup encryption phrase'
jar = http.cookiejar.CookieJar()
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

def call(path, data=None, csrf=None):
    headers = {'Content-Type': 'application/json', 'Origin': 'http://127.0.0.1:8000'}
    if csrf:
        headers['X-CSRF-Token'] = csrf
    request = urllib.request.Request('http://127.0.0.1:8000' + path,
        data=json.dumps(data).encode() if data is not None else None, headers=headers)
    try:
        with client.open(request, timeout=3) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)

def start(directory, should_fail=False):
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'seekbell.main:create_app',
        '--factory', '--host', '127.0.0.1', '--port', '8000', '--no-proxy-headers'],
        env={**os.environ, 'SEEKBELL_DATA_DIR': str(directory)},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            if process.poll() is not None:
                assert should_fail and process.returncode != 0
                return None
            try:
                if call('/health/ready')[0] == 200:
                    assert not should_fail
                    return process
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(.1)
        raise AssertionError('Service startup timed out')
    except BaseException:
        stop(process)
        raise

def stop(process):
    if process is not None:
        process.terminate()
        process.wait(timeout=30)

source = Settings(data_dir=Path('/data/source'), build_revision=sys.argv[1])
archive = Path('/data/checkpoint.sbb')
process = start(source.data_dir)
try:
    assert call('/api/version')[1]['build_revision'] == sys.argv[1]
    state = call('/api/auth/state')[1]
    credentials = {'username': 'synthetic-admin', 'password': password}
    code, state = call('/api/auth/setup', credentials, state['csrf_token'])
    assert code == 201
    csrf = state['csrf_token']
    code, target = call('/api/manage/targets', {'name': 'Synthetic restore target', 'kind': 'bark',
        'config': {'device_key': 'synthetic-m4-device-key'}, 'enabled': False}, csrf)
    assert code == 201
    code, task = call('/api/manage/tasks', {'name': 'Synthetic restore rule', 'rule': {},
        'target_ids': [target['id']], 'enabled': False}, csrf)
    assert code == 201
    assert call('/api/manage/site')[1]['scheduler']['enabled'] is False
    try:
        create_backup(source, archive, password=password, passphrase=passphrase)
    except RuntimeError:
        pass
    else:
        raise AssertionError('Live service backup must refuse')
finally:
    stop(process)

create_backup(source, archive, password=password, passphrase=passphrase)
assert archive.stat().st_mode & 0o777 == 0o600
restored = Settings(data_dir=Path('/data/restored'))
restore_backup(restored, archive, password=password, passphrase=passphrase)
original_key = (source.data_dir / 'credentials.key').read_bytes()
assert original_key == (restored.data_dir / 'credentials.key').read_bytes()
engine = create_database_engine(restored)
try:
    vault = CredentialVault.open(restored.data_dir)
    configuration = Configuration(engine, vault)
    assert configuration.get_target(target['id'])['configured_secrets'] == ['device_key']
finally:
    engine.dispose()
process = start(restored.data_dir)
try:
    assert call('/api/manage/tasks')[0] == 401  # cookie from source was revoked
    state = call('/api/auth/state')[1]
    code, state = call('/api/auth/login', credentials, state['csrf_token'])
    assert code == 200
    assert call('/api/manage/tasks')[1] == [task]
    restored_target = call('/api/manage/targets')[1][0]
    assert restored_target['id'] == target['id']
    assert restored_target['configured_secrets'] == ['device_key']
finally:
    stop(process)
# A migration version the image cannot handle must stop, not serve half-started.
with sqlite3.connect(restored.database_path) as connection:
    connection.execute("UPDATE alembic_version SET version_num='synthetic_future'")
assert start(restored.data_dir, should_fail=True) is None
rollback = Settings(data_dir=Path('/data/rollback'))
restore_backup(rollback, archive, password=password, passphrase=passphrase)
process = start(rollback.data_dir)
try:
    assert call('/api/version')[1]['database_revision'] == '0007_settings'
    state = call('/api/auth/state')[1]
    assert call('/api/auth/login', credentials, state['csrf_token'])[0] == 200
    assert call('/api/manage/tasks')[1] == [task]
finally:
    stop(process)
print(json.dumps({'compose': 'passed', 'uid': os.getuid(), 'read_only': True,
    'network': 'none', 'backup_restore': 'passed', 'original_key': 'passed',
    'session_revocation': 'passed', 'migration_failure_stops_service': 'passed',
    'pre_upgrade_backup_rollback': 'passed', 'revision': sys.argv[1]}))
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    project = "seekbell-m4-" + uuid.uuid4().hex[:12]
    environment = {
        **os.environ,
        "SEEKBELL_IMAGE": args.image,
        "SEEKBELL_PROJECT_NAME": project,
        "SEEKBELL_BACKGROUND_ENABLED": "false",
    }
    with tempfile.TemporaryDirectory(prefix="seekbell-m4-compose-") as temporary:
        override = Path(temporary) / "offline.yaml"
        override.write_text(
            "services:\n  seekbell:\n    network_mode: none\n    ports: !reset []\n"
        )
        command = [
            "docker",
            "compose",
            "-f",
            "deploy/compose.yaml",
            "-f",
            str(override),
        ]
        try:
            result = subprocess.run(
                [
                    *command,
                    "run",
                    "--rm",
                    "--no-deps",
                    "--pull",
                    "never",
                    "-T",
                    "seekbell",
                    "python",
                    "-",
                    args.revision,
                ],
                input=CHECK,
                text=True,
                env=environment,
                capture_output=True,
                timeout=180,
            )
            if result.returncode:
                raise RuntimeError("M4 container check failed:\n" + result.stderr + result.stdout)
            image = subprocess.run(
                ["docker", "image", "inspect", args.image, "--format", "{{.Id}}"],
                check=True,
                text=True,
                capture_output=True,
                timeout=15,
            ).stdout.strip()
            print(json.dumps({"image_id": image, **json.loads(result.stdout)}, indent=2))
        finally:
            subprocess.run(
                [*command, "down", "--volumes", "--remove-orphans"],
                env=environment,
                check=True,
                capture_output=True,
                timeout=30,
            )


if __name__ == "__main__":
    main()
