"""Rehearse Compose, backups and restore with disposable volumes and NO external network."""

import argparse
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

from check_container import MANAGEMENT_PROBE, docker, wait_ready

LOCK_PROBE = """
from pathlib import Path
from seekbell.backup import create_backup
from seekbell.config import Settings
try:
    create_backup(Settings(), Path('/backup/running.tar.gz'))
except RuntimeError:
    assert not Path('/backup/running.tar.gz').exists()
else:
    raise AssertionError('Running service must own its data directory')
"""

RESTORE_PROBE = """
import json, tarfile
from pathlib import Path
from seekbell.backup import create_backup, restore_backup
from seekbell.config import Settings
from seekbell.services.authentication import password_hash
from seekbell.services.backup_demo import table_data
settings = Settings()
before = table_data(settings.database_path)
archive, destination = Path('/backup/rehearsal.tar.gz'), Path('/restore/restored')
create_backup(settings, archive)
with tarfile.open(archive) as tar:
    assert tar.getnames() == ['manifest.json', 'seekbell.sqlite3', 'credentials.key']
administrator = ('container_admin', password_hash('Synthetic-Container-2026'))
restore_backup(settings, archive, destination, administrator=administrator)
after = table_data(destination / 'seekbell.sqlite3')
assert after.pop('login_sessions') == []
assert [row[1] for row in after.pop('administrators')] == ['container_admin']
assert table_data(settings.database_path) == before
before.pop('login_sessions')
before.pop('administrators')
# The restored schedule keeps its settings (columns up to revision) but counts anew.
schedule_before, schedule_after = before.pop('backup_schedule'), after.pop('backup_schedule')
assert [row[:7] for row in schedule_after] == [row[:7] for row in schedule_before]
assert before == after
assert archive.stat().st_mode & 0o777 == 0o600
print(json.dumps({'all_tables_preserved': True, 'source_unchanged': True,
                  'standard_tar_gz': True, 'sessions_revoked': True}))
"""


WEB_PROBE = r"""
import http.cookiejar, json, urllib.request
from pathlib import Path
from seekbell.services.backup_demo import table_data
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
base = 'http://127.0.0.1:8000'
csrf = ''
def request(path, data=None, content_type='application/json'):
    headers = {'Content-Type': content_type, 'X-CSRF-Token': csrf}
    url = base + (path if path.startswith('/') else '/api/' + path)
    return opener.open(urllib.request.Request(url, data=data, headers=headers), timeout=60)
csrf = json.load(request('auth/status'))['csrf']
credentials = {'username': 'container_admin', 'password': 'Synthetic-Container-2026'}
csrf = json.load(request('auth/login', json.dumps(credentials).encode()))['csrf']
def business(path):
    # Configuration only: the live runtime keeps writing runs and events meanwhile.
    rows = table_data(path)
    return {name: rows[name] for name in (
        'websites', 'website_installations', 'notification_targets', 'tasks', 'task_versions',
        'workspace_preferences', 'retention_policy', 'alert_settings', 'overview_preferences',
        'administrators')}
before = business(Path('/data/seekbell.sqlite3'))
name = json.load(request('manage/backups', b''))['id']
stored = Path('/data/backups') / name
assert stored.stat().st_mode & 0o777 == 0o600
url = json.load(request('manage/backups/' + name + '/ticket', b''))['url']
with request(url) as response:
    assert response.headers['Cache-Control'] == 'no-store'
    archive = response.read()
assert archive == stored.read_bytes() and archive[:2] == b'\x1f\x8b'
found = json.load(request('manage/backups/' + name + '/inspect', b''))
assert found['backup']['summary'] == found['current']
body = json.dumps({'current_password': credentials['password'], 'pause': False}).encode()
result = json.load(request('manage/backups/inspect/' + found['stage'] + '/restore', body))
assert result['restored'] and result['username'] == 'container_admin'
csrf = result['csrf']
assert business(Path('/data/seekbell.sqlite3')) == before
kinds = [row['kind'] for row in json.load(request('manage/backups'))['backups']]
assert kinds == ['pre-restore', 'manual']
assert json.load(request('auth/status'))['authenticated']
assert json.load(request('manage/runtime'))['active']
assert not list(Path('/data').glob('.seekbell-*'))
assert not list(Path('/data').glob('before-restore-*'))
print(json.dumps({'library_backup': True, 'streamed_download': True, 'inspection': True,
                  'in_place_restore': True, 'pre_restore_backup': True,
                  'source_business_data_unchanged': True, 'runtime_running': True}))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    project = "seekbell-backup-check-" + uuid.uuid4().hex[:12]
    recovered = project + "-recovered"
    with tempfile.TemporaryDirectory(prefix=project) as temporary:
        directory = Path(temporary)
        override = directory / "offline.yaml"
        override.write_text(
            "services:\n  seekbell:\n    volumes:\n"
            "      - backup:/backup\n      - recovery:/restore\n"
            "volumes:\n  backup:\n  recovery:\n"
        )
        env = {
            **os.environ,
            "SEEKBELL_IMAGE": args.image,
            "SEEKBELL_BACKUP_DIR": str(directory),
            "SEEKBELL_RESTORE_DIR": str(directory),
        }
        base = ["docker", "compose", "-p", project, "-f", str(root / "compose.yaml")]
        maintenance = [*base, "-f", str(root / "compose.maintenance.yaml"), "-f", str(override)]

        def compose(*arguments, check=True):
            return subprocess.run(
                [*maintenance, *arguments],
                env=env,
                text=True,
                capture_output=True,
                check=check,
                timeout=60,
            )

        try:
            standard = json.loads(
                subprocess.run(
                    [*base, "config", "--format", "json"],
                    env=env,
                    check=True,
                    text=True,
                    capture_output=True,
                    timeout=15,
                ).stdout
            )["services"]["seekbell"]
            assert standard["ports"][0]["host_ip"] == "127.0.0.1"
            assert standard["read_only"] and standard["pull_policy"] == "never"
            assert standard["cap_drop"] == ["ALL"] and standard["stop_grace_period"] == "30s"
            config = json.loads(compose("config", "--format", "json").stdout)
            service = config["services"]["seekbell"]
            assert service["network_mode"] == "none" and not service.get("ports")
            assert service["read_only"]
            compose(
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "--user",
                "0",
                "--cap-add",
                "CHOWN",
                "--entrypoint",
                "python",
                "seekbell",
                "-c",
                "import os; "
                "[(os.chmod(p,0o700),os.chown(p,10001,10001)) for p in ('/backup','/restore')]",
            )
            compose("up", "-d")
            container = compose("ps", "-q", "seekbell").stdout.strip()
            wait_ready(
                container,
                probe=(
                    "import urllib.request; "
                    "urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"
                ),
            )
            info = json.loads(
                docker(
                    "exec",
                    container,
                    "python",
                    "-c",
                    "import json,urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/api/version').read().decode())",
                ).stdout
            )
            assert info["build_revision"] == args.revision
            before = json.loads(docker("exec", container, "python", "-c", MANAGEMENT_PROBE).stdout)
            web = json.loads(docker("exec", container, "python", "-c", WEB_PROBE).stdout)
            docker("exec", container, "python", "-c", LOCK_PROBE)
            compose("stop")
            result = compose(
                "run", "--rm", "--no-deps", "-T", "seekbell", "python", "-c", RESTORE_PROBE
            )
            restored = json.loads(result.stdout)
            demo = json.loads(
                compose(
                    "run",
                    "--rm",
                    "--no-deps",
                    "-T",
                    "seekbell",
                    "python",
                    "-m",
                    "seekbell.services.backup_demo",
                ).stdout
            )
            assert demo["all_tables_preserved"] and demo["resumed_sends"] == 1
            recovery_volume = config["volumes"]["recovery"]["name"]
            docker(
                "run",
                "--detach",
                "--name",
                recovered,
                "--network",
                "none",
                "--read-only",
                "--tmpfs",
                "/tmp",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--user",
                "10001:10001",
                "-e",
                "SEEKBELL_DATA_DIR=/restore/restored",
                "-v",
                recovery_volume + ":/restore",
                args.image,
            )
            wait_ready(
                recovered,
                probe=(
                    "import urllib.request; "
                    "urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"
                ),
            )
            after = json.loads(docker("exec", recovered, "python", "-c", MANAGEMENT_PROBE).stdout)
            assert after == before
            print(
                json.dumps(
                    {
                        "revision": args.revision,
                        "network": "none",
                        "compose": "passed",
                        "running_backup_refused": True,
                        "web_backup": web,
                        "restore": restored,
                        "restored_service_login_and_configuration": "passed",
                        "offline_demo": demo,
                    },
                    indent=2,
                )
            )
        finally:
            docker("rm", "--force", recovered, check=False)
            compose("down", "--volumes", "--remove-orphans", check=False)


if __name__ == "__main__":
    main()
