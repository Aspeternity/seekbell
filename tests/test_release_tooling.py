"""Version bump, baseline reuse and anonymous release verification helpers."""

import hashlib
import importlib.util
import json
import shutil
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bump = load("bump_version")
reuse = load("ci_reuse")
release = load("verify_release")


@pytest.fixture
def project(tmp_path):
    for name in [
        "pyproject.toml",
        "uv.lock",
        "frontend/package.json",
        "CHANGELOG.md",
        *bump.TEMPLATES,
    ]:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / name, tmp_path / name)
    versions = tmp_path / "backend/seekbell/migrations/versions"
    versions.mkdir(parents=True)
    for name in ["0017_old.py", "0018_current.py"]:
        (versions / name).write_text("")
    return tmp_path


def test_repository_versions_are_consistent():
    assert bump.check() == (bump.check()[0], [])


@pytest.mark.parametrize(
    "text, expected",
    [
        ("0.3.0", ("0.3.0", "0.3.0")),
        ("v1.2.3-rc.4", ("1.2.3-rc.4", "1.2.3rc4")),
        ("0.3.0-alpha.1", ("0.3.0-alpha.1", "0.3.0a1")),
    ],
)
def test_versions_map_to_tag_and_python_forms(text, expected):
    assert bump.parse(text) == expected


@pytest.mark.parametrize("text", ["0.3", "0.3.0-rc.0", "0.3.0rc1", "latest"])
def test_invalid_versions_are_rejected(text):
    with pytest.raises(SystemExit):
        bump.parse(text)


def test_bump_updates_every_record_and_requires_a_written_changelog(project):
    bump.bump("0.3.0-rc.1", root=project)
    assert '"0.3.0-rc.1"' in (project / "frontend/package.json").read_text()
    assert 'version = "0.3.0rc1"' in (project / "pyproject.toml").read_text()
    for name in bump.TEMPLATES:
        text = (project / name).read_text()
        assert text.startswith("# SeekBell 0.3.0-rc.1; schema 0018.")
        assert "image: ghcr.io/aspeternity/seekbell:0.3.0-rc.1\n" in text
    semver, problems = bump.check(project)
    assert semver == "0.3.0-rc.1" and problems == []
    assert "## 0.3.0-rc.1 — " in (project / "CHANGELOG.md").read_text()
    # A second bump keeps the existing entry instead of stacking stubs.
    bump.bump("0.3.0-rc.1", root=project)
    assert (project / "CHANGELOG.md").read_text().count("## 0.3.0-rc.1 ") == 1


def test_check_reports_a_file_left_behind(project):
    bump.bump("0.3.0", root=project)
    path = project / bump.TEMPLATES[1]
    path.write_text(path.read_text().replace("seekbell:0.3.0", "seekbell:0.2.0"))
    assert any(bump.TEMPLATES[1] in problem for problem in bump.check(project)[1])


def artifact(repository_id=7, head_repository_id=7, expired=False):
    return {
        "name": "baseline-tree-abc",
        "expired": expired,
        "workflow_run": {
            "id": 99,
            "repository_id": repository_id,
            "head_repository_id": head_repository_id,
        },
    }


@pytest.mark.parametrize(
    "item, accepted",
    [
        (artifact(), True),
        (artifact(head_repository_id=8), False),  # fork PR run
        (artifact(repository_id=8), False),
        (artifact(expired=True), False),
    ],
)
def test_only_own_unexpired_markers_skip_the_baseline(item, accepted):
    found = reuse.find_marker(
        "baseline-tree-abc", "o/r", 7, "t", fetch=lambda _: {"artifacts": [item]}
    )
    assert (found == 99) is accepted


def test_failed_lookup_runs_the_full_baseline(tmp_path, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", broken)
    for key, value in {
        "GITHUB_REPOSITORY": "o/r",
        "GITHUB_REPOSITORY_ID": "7",
        "GITHUB_TOKEN": "t",
    }.items():
        monkeypatch.setenv(key, value)
    output = tmp_path / "output"
    assert reuse.main(["--output", str(output)]) == 0
    assert "verified=false" in output.read_text()


REVISION = "a" * 40
# Templates in the checkout carry the current release version.
VERSION = bump.check()[0]
DIGEST = "sha256:" + "5" * 64


def published_release(tamper=None):
    """Synthetic public view of a release: API, assets and registry responses."""
    image = "ghcr.io/aspeternity/seekbell"
    config = json.dumps(
        {
            "architecture": "amd64",
            "os": "linux",
            "config": {"Labels": {"org.opencontainers.image.revision": REVISION}},
        }
    ).encode()
    config_digest = "sha256:" + hashlib.sha256(config).hexdigest()
    manifest = json.dumps({"config": {"digest": config_digest}}).encode()
    manifest_digest = "sha256:" + hashlib.sha256(manifest).hexdigest()
    index = json.dumps(
        {
            "manifests": [
                {"platform": {"os": "linux", "architecture": "amd64"}, "digest": manifest_digest}
            ]
        }
    ).encode()
    digest = "sha256:" + hashlib.sha256(index).hexdigest()
    assets = {
        "release.json": {
            "published": True,
            "revision": REVISION,
            "digest": digest,
            "manifests": {"amd64": manifest_digest},
            "images": {"amd64": {"config_digest": config_digest}},
        },
        "version.json": {
            "published": True,
            "revision": REVISION,
            "version": "v" + VERSION,
            "digest": digest,
            "tags": [image + ":" + VERSION, image + ":latest"],
        },
        "package.json": {},
    }
    files = {name: json.dumps(value).encode() for name, value in assets.items()}
    pinned = image + ":" + VERSION + "@" + digest
    for name in bump.TEMPLATES:
        source = (ROOT / name).read_text()
        files[Path(name).name] = source.replace(
            "image: " + image + ":" + VERSION + "\n", "image: " + pinned + "\n"
        ).encode()
    deployment = {
        "revision": REVISION,
        "version": "v" + VERSION,
        "image": pinned,
        "sha256": {
            Path(n).name: hashlib.sha256(files[Path(n).name]).hexdigest() for n in bump.TEMPLATES
        },
    }
    files["deployment.json"] = json.dumps(deployment).encode()
    if tamper:
        tamper(files)
    responses = {
        "https://api.github.com/repos/Aspeternity/seekbell/releases/tags/v" + VERSION: json.dumps(
            {
                "draft": False,
                "prerelease": False,
                "assets": [
                    {"name": name, "browser_download_url": "asset:" + name} for name in files
                ],
            }
        ).encode(),
        "manifests/" + VERSION: index,
        "manifests/latest": index,
        "manifests/" + manifest_digest: manifest,
        "blobs/" + config_digest: config,
        **{"asset:" + name: data for name, data in files.items()},
    }

    def fetch(url, headers=None):
        if url.startswith("https://ghcr.io/token"):
            return b'{"token": "anonymous"}'
        key = url.split("/aspeternity/seekbell/", 1)[1] if "ghcr.io/v2" in url else url
        return responses[key]

    return fetch


def test_release_matches_the_public_view():
    result = release.verify(
        "v" + VERSION,
        REVISION,
        "Aspeternity/seekbell",
        fetch=published_release(),
        compose_check=False,
    )
    assert result["tags"][-1].endswith(":latest") and result["platforms"] == ["amd64"]


@pytest.mark.parametrize("asset", ["compose.portainer.yaml", "deployment.json", "version.json"])
def test_tampered_or_mismatching_assets_fail_verification(asset):
    def tamper(files):
        files[asset] = files[asset].replace(VERSION.encode(), b"9.9.9", 1)

    with pytest.raises(release.VerificationError):
        release.verify(
            "v" + VERSION,
            REVISION,
            "Aspeternity/seekbell",
            fetch=published_release(tamper),
            compose_check=False,
        )
