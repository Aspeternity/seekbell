"""Disposable offline release rehearsal, including synthetic future migration failures."""

import argparse
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

import manage_release as release
from check_backup_container import WEB_PROBE
from check_container import MANAGEMENT_PROBE, docker, wait_ready

ROOT = Path(__file__).resolve().parents[1]
FINGERPRINT = """
import hashlib
from pathlib import Path
root=Path('/source')
digest=hashlib.sha256()
for name in ('seekbell.sqlite3','seekbell.sqlite3-wal','credentials.key'):
    path=root/name
    if path.exists():
        digest.update(name.encode()+path.read_bytes())
print(digest.hexdigest())
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("--revision", required=True)
    parser.add_argument(
        "--source-image", help="Optional older local image for cross-version rehearsal"
    )
    args = parser.parse_args()
    project = "seekbell-release-check-" + uuid.uuid4().hex[:12]
    base_image = release.image(args.source_image or args.image)
    tags = [project + ":good", project + ":bad", project + ":startup-bad"]
    candidates = {}
    source_volume = None
    env = {**os.environ, "SEEKBELL_IMAGE": base_image, "SEEKBELL_TRUSTED_PROXY_IPS": "192.0.2.10"}
    command = [
        "docker",
        "compose",
        "-p",
        project,
        "-f",
        str(ROOT / "compose.yaml"),
        "-f",
        str(ROOT / "compose.release-offline.yaml"),
        "-f",
        str(ROOT / "compose.proxy.yaml"),
    ]

    def compose(*arguments):
        return subprocess.run(
            [*command, *arguments], env=env, capture_output=True, text=True, check=True, timeout=60
        )

    def run_tool(path, *arguments, succeeds=True):
        result = subprocess.run(
            ["python3", str(ROOT / "scripts/manage_release.py"), "--state", str(path), *arguments],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if path.exists():
            saved = release.load(path)
            candidates[saved["next"]["volume"]] = saved["id"]
        assert (result.returncode == 0) == succeeds, result.stderr
        return json.loads(result.stdout) if succeeds else None

    def fingerprint():
        return release.run(
            base_image, [(source_volume, "/source", True)], "python", "-c", FINGERPRINT
        )

    try:
        with tempfile.TemporaryDirectory(prefix=project) as temp:
            directory = Path(temp)
            for tag, fails in zip(tags[:2], (False, True), strict=True):
                migration = directory / "0010_release_fixture.py"
                migration.write_text(
                    "from alembic import op\nrevision='0010_release_fixture'\n"
                    "down_revision='0018_settings_maintenance'\n"
                    'def upgrade():\n    op.execute("UPDATE workspace_preferences '
                    "SET name='Synthetic migration'\")\n"
                    + ("    raise RuntimeError('Synthetic migration failure')\n" if fails else "")
                )
                dockerfile = directory / "Dockerfile"
                dockerfile.write_text(
                    "FROM " + args.image + "\nUSER root\n"
                    "COPY 0010_release_fixture.py /app/.venv/lib/python3.12/site-packages/"
                    "seekbell/migrations/versions/0010_release_fixture.py\n"
                    "USER 10001:10001\n"
                )
                subprocess.run(
                    ["docker", "build", "-t", tag, str(directory)],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=90,
                )
            dockerfile.write_text(
                "FROM " + args.image + '\nCMD ["python","-c","raise SystemExit(23)"]\n'
            )
            subprocess.run(
                ["docker", "build", "-t", tags[2], str(directory)],
                capture_output=True,
                text=True,
                check=True,
                timeout=90,
            )
            compose("up", "-d")
            container = release.current(project)["container"]
            wait_ready(
                container,
                probe="import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health/ready',timeout=3)",
            )
            docker("exec", container, "python", "-c", MANAGEMENT_PROBE)
            docker("exec", container, "python", "-c", WEB_PROBE)
            compose("stop")
            source_volume = release.current(project)["volume"]
            before = fingerprint()
            # Failed target migration cannot alter/start the original or publish a candidate.
            failed = directory / "failed.json"
            run_tool(failed, "prepare", "--project", project, "--image", tags[1], succeeds=False)
            assert release.load(failed)["phase"] == "prepare_failed"
            assert fingerprint() == before and not release.current(project)["running"]
            run_tool(failed, "rollback", succeeds=False)
            run_tool(failed, "rollback", "--accept-data-loss")
            assert release.current(project)["running"]
            docker("stop", release.current(project)["container"])
            # A valid synthetic future migration is prepared entirely offline, then switched.
            good = directory / "good.json"
            before = fingerprint()
            assert (
                run_tool(good, "prepare", "--project", project, "--image", tags[0])["phase"]
                == "prepared"
            )
            assert fingerprint() == before and not release.current(project)["running"]
            assert run_tool(good, "activate")["phase"] == "active"
            active = release.current(project)
            assert active["volume"] != source_volume
            probe = "import json,urllib.request;print(json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/version'))['database_revision'])"
            assert (
                docker("exec", active["container"], "python", "-c", probe).stdout.strip()
                == "0010_release_fixture"
            )
            assert fingerprint() == before
            assert run_tool(good, "rollback", "--accept-data-loss")["phase"] == "rolled_back"
            assert release.current(project)["volume"] == source_volume
            docker("exec", release.current(project)["container"], "python", "-c", MANAGEMENT_PROBE)
            docker("stop", release.current(project)["container"])
            startup = directory / "startup.json"
            before = fingerprint()
            run_tool(startup, "prepare", "--project", project, "--image", tags[2])
            run_tool(startup, "activate", succeeds=False)
            assert release.load(startup)["phase"] == "activation_failed"
            assert not release.current(project)["running"] and fingerprint() == before
            run_tool(startup, "rollback", "--accept-data-loss")
            docker("stop", release.current(project)["container"])
            # The existing Web candidate is copied out of the original volume before activation.
            restored = directory / "restored.json"
            before = fingerprint()
            run_tool(restored, "prepare", "--project", project, "--image", args.image, "--restored")
            assert run_tool(restored, "activate")["phase"] == "active"
            assert fingerprint() == before
            assert run_tool(restored, "rollback", "--accept-data-loss")["phase"] == "rolled_back"
            print(
                json.dumps(
                    {
                        "revision": args.revision,
                        "base_image": base_image,
                        "network": "none",
                        "synthetic_failed_migration_preserves_original": True,
                        "synthetic_future_migration_switch": True,
                        "explicit_rollback_to_original_pair": True,
                        "startup_failure_stopped_without_automatic_rollback": True,
                        "web_candidate_switch": True,
                        "original_volume_retained": True,
                    },
                    indent=2,
                )
            )
    finally:
        # This unique project's resources ONLY. The operator tool itself never deletes volumes.
        ids = docker(
            "ps", "-aq", "--filter", "label=com.docker.compose.project=" + project
        ).stdout.split()
        if ids:
            docker("rm", "--force", *ids, check=False)
        volumes = docker(
            "volume", "ls", "-q", "--filter", "label=com.docker.compose.project=" + project
        ).stdout.split()
        owned = []
        for name, identifier in candidates.items():
            labels = release.inspect("volume", name).get("Labels") or {}
            if labels.get(release.LABEL) == identifier:
                owned.append(name)
        if volumes or owned:
            docker("volume", "rm", *volumes, *owned, check=False)
        docker("image", "rm", *tags, check=False)


if __name__ == "__main__":
    main()
