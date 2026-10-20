"""Publication boundaries and artifact identity, using a synthetic Docker CLI."""

import copy
import hashlib
import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "release_images", Path(__file__).parents[1] / "scripts" / "release_images.py"
)
images = importlib.util.module_from_spec(spec)
spec.loader.exec_module(images)
REVISION = "a" * 40
REPOSITORY = "synthetic/seekbell"
SOURCE = f"https://github.com/{REPOSITORY}"
IDS = {"amd64": "sha256:" + "1" * 64, "arm64": "sha256:" + "2" * 64}
DIGESTS = {"amd64": "sha256:" + "3" * 64, "arm64": "sha256:" + "4" * 64}
INDEX_DIGEST = "sha256:" + "5" * 64


def image(architecture):
    return {
        "Id": IDS[architecture],
        "Os": "linux",
        "Architecture": architecture,
        "RootFS": {"Layers": ["sha256:" + "9" * 64]},
        "Config": {
            "User": "10001:10001",
            "Env": [f"SEEKBELL_BUILD_REVISION={REVISION}"],
            "Labels": {
                "org.opencontainers.image.revision": REVISION,
                "org.opencontainers.image.source": SOURCE,
            },
        },
    }


def archive(path, architecture, *, tag=None):
    item = image(architecture)
    config = json.dumps(
        {
            "os": item["Os"],
            "architecture": item["Architecture"],
            "config": item["Config"],
            "rootfs": {"diff_ids": item["RootFS"]["Layers"]},
        }
    ).encode()
    name = hashlib.sha256(config).hexdigest() + ".json"
    tag = tag or f"seekbell-artifact:sha-{REVISION}-{architecture}"
    manifest = json.dumps([{"Config": name, "RepoTags": [tag], "Layers": []}]).encode()
    with tarfile.open(path, "w") as tar:
        for filename, data in [("manifest.json", manifest), (name, config)]:
            member = tarfile.TarInfo(filename)
            member.size = len(data)
            tar.addfile(member, io.BytesIO(data))
    return "sha256:" + hashlib.sha256(config).hexdigest()


def index():
    return {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "digest": INDEX_DIGEST,
        "manifests": [
            {"digest": DIGESTS[arch], "platform": {"os": "linux", "architecture": arch}}
            for arch in images.ARCHITECTURES
        ],
    }


@pytest.fixture
def artifacts(tmp_path):
    for architecture in images.ARCHITECTURES:
        directory = tmp_path / architecture
        directory.mkdir()
        archive_path = directory / "image.tar"
        config_digest = archive(archive_path, architecture)
        receipt = {
            "schema": 1,
            "architecture": architecture,
            "revision": REVISION,
            "source": SOURCE,
            "image_id": IDS[architecture],
            "archive_sha256": images.checksum(archive_path),
            "archive_tag": f"seekbell-artifact:sha-{REVISION}-{architecture}",
            "config_digest": config_digest,
        }
        (directory / "image.json").write_text(json.dumps(receipt))
    return tmp_path


@pytest.fixture
def docker(monkeypatch, tmp_path):
    calls = []
    config_digests = {}
    for arch in images.ARCHITECTURES:
        config_digests[arch] = archive(tmp_path / (arch + "-config.tar"), arch)

    def command(*args):
        calls.append(args)
        if args[:2] == ("image", "inspect"):
            architecture = args[2].rsplit("-", 1)[1]
            return json.dumps([image(architecture)])
        if args[:2] == ("image", "push"):
            return "CLI note and pushed repository tag; not a digest"
        if args[:3] == ("buildx", "imagetools", "inspect"):
            if "--raw" in args:
                architecture = next(
                    arch for arch, digest in DIGESTS.items() if args[-1].endswith(digest)
                )
                return json.dumps({"config": {"digest": config_digests[architecture]}})
            if args[-1].endswith(("-amd64", "-arm64")):
                arch = args[-1].rsplit("-", 1)[1]
                return json.dumps(
                    {
                        "mediaType": "application/vnd.oci.image.manifest.v1+json",
                        "digest": DIGESTS[arch],
                    }
                )
            return json.dumps(index())
        return ""

    monkeypatch.setattr(images, "docker", command)
    return calls


def test_default_release_only_checks_local_artifacts(artifacts, docker):
    result = images.release(artifacts, REVISION, REPOSITORY, "123-1")
    assert not result["published"]
    assert {args[:2] for args in docker} == {("image", "load"), ("image", "inspect")}
    assert result["tag"].endswith(f"sha-{REVISION}-123-1")


def test_publish_uses_tested_ids_then_pinned_manifests(artifacts, docker):
    result = images.release(artifacts, REVISION, REPOSITORY, "123-2", execute=True)
    assert result["published"]
    assert result["reference"] == f"ghcr.io/{REPOSITORY}@{INDEX_DIGEST}"
    first_push = next(i for i, args in enumerate(docker) if args[:2] == ("image", "push"))
    assert sum(args[:2] == ("image", "inspect") for args in docker[:first_push]) == 2
    assert [args[2] for args in docker if args[:2] == ("image", "tag")] == list(IDS.values())
    create = next(args for args in docker if args[:3] == ("buildx", "imagetools", "create"))
    assert create[-2:] == tuple(f"ghcr.io/{REPOSITORY}@{value}" for value in DIGESTS.values())
    assert docker[-1][-1] == result["reference"]


@pytest.mark.parametrize(
    "fault",
    ["checksum", "revision", "architecture", "source", "image_id", "archive_tag", "config_digest"],
)
def test_second_artifact_mismatch_prevents_all_registry_writes(artifacts, docker, fault):
    path = artifacts / "arm64" / "image.json"
    receipt = json.loads(path.read_text())
    if fault == "checksum":
        (artifacts / "arm64" / "image.tar").write_bytes(b"changed")
    else:
        receipt[fault] = "wrong"
        path.write_text(json.dumps(receipt))
    with pytest.raises(images.ReleaseError):
        images.release(artifacts, REVISION, REPOSITORY, "123-1", execute=True)
    assert all(args[0] == "image" and args[1] in ("load", "inspect") for args in docker)


@pytest.mark.parametrize("fault", ["Architecture", "Os", "Id", "User", "Env", "revision", "source"])
def test_loaded_image_is_checked_independently_of_receipt(monkeypatch, fault):
    item = image("amd64")
    if fault in ("Architecture", "Os", "Id"):
        item[fault] = "wrong"
    elif fault in ("User", "Env"):
        item["Config"][fault] = [] if fault == "Env" else "root"
    else:
        item["Config"]["Labels"]["org.opencontainers.image." + fault] = "wrong"
    monkeypatch.setattr(images, "docker", lambda *args: json.dumps([item]))
    with pytest.raises(images.ReleaseError):
        images.inspect_image(IDS["amd64"], "amd64", REVISION, SOURCE)


@pytest.mark.parametrize("fault", ["extra", "duplicate", "digest", "os", "variant", "index_digest"])
def test_index_rejects_wrong_or_missing_platforms(fault):
    value = copy.deepcopy(index())
    if fault == "extra":
        value["manifests"].append(value["manifests"][0])
    elif fault == "duplicate":
        value["manifests"][1] = value["manifests"][0]
    elif fault == "digest":
        value["manifests"][0]["digest"] = DIGESTS["arm64"]
    elif fault in ("os", "variant"):
        value["manifests"][0]["platform"][fault] = "wrong"
    else:
        value["digest"] = "wrong"
    with pytest.raises(images.ReleaseError):
        images.verify_index(value, DIGESTS)


def test_arm64_v8_index_is_accepted():
    value = index()
    value["manifests"][1]["platform"]["variant"] = "v8"
    assert images.verify_index(value, DIGESTS) == INDEX_DIGEST


@pytest.mark.parametrize("fault", ["push", "config"])
def test_failed_push_or_remote_config_does_not_create_index(artifacts, docker, monkeypatch, fault):
    original = images.docker

    def failed(*args):
        if fault == "push" and args[:2] == ("image", "push"):
            raise images.ReleaseError("synthetic failure")
        if fault == "config" and "--raw" in args:
            return json.dumps({"config": {"digest": IDS["arm64"]}})
        return original(*args)

    monkeypatch.setattr(images, "docker", failed)
    with pytest.raises(images.ReleaseError):
        images.release(artifacts, REVISION, REPOSITORY, "123-1", execute=True)
    assert not any(args[:3] == ("buildx", "imagetools", "create") for args in docker)


@pytest.mark.parametrize(
    "revision,repository,run",
    [
        ("main", REPOSITORY, "123-1"),
        (REVISION, "other.registry/repo/image", "123-1"),
        (REVISION, REPOSITORY, "latest"),
    ],
)
def test_invalid_identity_fails_before_loading(artifacts, docker, revision, repository, run):
    with pytest.raises(images.ReleaseError):
        images.release(artifacts, revision, repository, run, execute=True)
    assert docker == []


def test_pack_saves_the_inspected_content_id(tmp_path, monkeypatch):
    calls = []

    def command(*args):
        calls.append(args)
        if args[:2] == ("image", "inspect"):
            return json.dumps([image("amd64")])
        if args[:2] == ("image", "save"):
            archive(Path(args[3]), "amd64")
        return ""

    monkeypatch.setattr(images, "docker", command)
    output = tmp_path / "package"
    receipt = images.pack("seekbell:mutable", "amd64", REVISION, REPOSITORY, output)
    assert calls[-2][2] == IDS["amd64"]
    assert calls[-1][-1] == receipt["archive_tag"]
    assert receipt["archive_sha256"] == images.checksum(output / "image.tar")
    with pytest.raises(FileExistsError):
        images.pack("seekbell:mutable", "amd64", REVISION, REPOSITORY, output)


def test_containerd_index_id_can_change_after_loading_into_classic_store(
    artifacts, docker, monkeypatch
):
    original = images.docker
    classic_id = "sha256:" + "7" * 64

    def changed(*args):
        result = original(*args)
        if args[:2] == ("image", "inspect"):
            value = json.loads(result)
            value[0]["Id"] = classic_id
            return json.dumps(value)
        return result

    monkeypatch.setattr(images, "docker", changed)
    result = images.release(artifacts, REVISION, REPOSITORY, "123-1", execute=True)
    assert result["published"]
    assert all(args[2] == classic_id for args in docker if args[:2] == ("image", "tag"))


def test_archive_with_unexpected_tag_is_rejected_before_load(artifacts, docker):
    directory = artifacts / "arm64"
    archive(directory / "image.tar", "arm64", tag="seekbell:unrelated")
    receipt_path = directory / "image.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["archive_sha256"] = images.checksum(directory / "image.tar")
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(images.ReleaseError):
        images.verify(directory, "arm64", REVISION, REPOSITORY)
    assert docker == []


def test_loaded_layers_must_match_archive(artifacts, docker, monkeypatch):
    original = images.docker

    def changed(*args):
        result = original(*args)
        if args[:2] == ("image", "inspect"):
            value = json.loads(result)
            value[0]["RootFS"]["Layers"] = []
            return json.dumps(value)
        return result

    monkeypatch.setattr(images, "docker", changed)
    with pytest.raises(images.ReleaseError):
        images.verify(artifacts / "amd64", "amd64", REVISION, REPOSITORY)


@pytest.mark.parametrize("fault", ["index", "digest"])
def test_single_platform_push_must_resolve_to_a_real_manifest(
    artifacts, docker, monkeypatch, fault
):
    original = images.docker

    def changed(*args):
        if args[:3] == ("buildx", "imagetools", "inspect") and args[-1].endswith("-amd64"):
            return json.dumps(
                {
                    "mediaType": "application/vnd.oci.image.index.v1+json"
                    if fault == "index"
                    else "application/vnd.oci.image.manifest.v1+json",
                    "digest": DIGESTS["amd64"] if fault == "index" else "invalid",
                }
            )
        return original(*args)

    monkeypatch.setattr(images, "docker", changed)
    with pytest.raises(images.ReleaseError):
        images.release(artifacts, REVISION, REPOSITORY, "123-1", execute=True)
    assert not any(args[:3] == ("buildx", "imagetools", "create") for args in docker)


def published_receipt():
    return {
        "published": True,
        "revision": REVISION,
        "digest": INDEX_DIGEST,
        "reference": f"ghcr.io/{REPOSITORY}@{INDEX_DIGEST}",
        "manifests": DIGESTS,
    }


def test_alias_default_only_reads_the_pinned_registry_index(docker):
    result = images.alias(published_receipt(), REVISION, REPOSITORY, "rss-fix-1")
    assert result["published"] is False
    assert all(args[:3] == ("buildx", "imagetools", "inspect") for args in docker)


def test_alias_copies_the_verified_two_platform_index_without_rebuild(docker):
    report = published_receipt()
    result = images.alias(report, REVISION, REPOSITORY, "rss-fix-1", execute=True)
    assert result["published"] and result["digest"] == INDEX_DIGEST
    assert docker == [
        ("buildx", "imagetools", "inspect", "--format", "{{json .Manifest}}", report["reference"]),
        (
            "buildx",
            "imagetools",
            "create",
            "--tag",
            f"ghcr.io/{REPOSITORY}:rss-fix-1",
            report["reference"],
        ),
        ("buildx", "imagetools", "inspect", "--format", "{{json .Manifest}}", result["tag"]),
    ]


@pytest.mark.parametrize("tag", ["latest", "../other", "other/image:tag", "--append", "x" * 65])
def test_invalid_alias_never_accesses_registry(docker, tag):
    with pytest.raises(images.ReleaseError):
        images.alias(published_receipt(), REVISION, REPOSITORY, tag, execute=True)
    assert not docker


@pytest.mark.parametrize("fault", ["published", "revision", "digest", "reference", "manifests"])
def test_alias_rejects_unverified_or_mismatching_receipt_before_registry_access(docker, fault):
    report = published_receipt()
    report[fault] = {} if fault == "manifests" else "wrong"
    with pytest.raises(images.ReleaseError):
        images.alias(report, REVISION, REPOSITORY, "rss-fix-1", execute=True)
    assert not docker


def test_changed_alias_index_does_not_record_success(docker, monkeypatch):
    original = images.docker

    def changed(*args):
        if args[-1].endswith(":rss-fix-1") and args[2] == "inspect":
            return json.dumps({**index(), "digest": "sha256:" + "6" * 64})
        return original(*args)

    monkeypatch.setattr(images, "docker", changed)
    with pytest.raises(images.ReleaseError, match="Short tag differs"):
        images.alias(published_receipt(), REVISION, REPOSITORY, "rss-fix-1", execute=True)
