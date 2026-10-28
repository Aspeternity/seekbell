"""Package checked native images; publish the same bytes only on explicit request."""

import argparse
import hashlib
import json
import re
import subprocess
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ARCHITECTURES = ("amd64", "arm64")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
REPOSITORY = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*/[a-z0-9]+(?:[._-][a-z0-9]+)*")
MANIFEST_TYPES = {
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
}
INDEX_TYPES = {
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
}


class ReleaseError(ValueError):
    pass


def docker(*args: str) -> str:
    # Never print Docker stderr: registry credentials and local paths are private.
    result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=1800)
    if result.returncode:
        raise ReleaseError(f"Docker {args[0]} failed; inspect the runner privately")
    return result.stdout.strip()


def identity(revision: str, repository: str) -> tuple[str, str]:
    if not REVISION.fullmatch(revision) or not REPOSITORY.fullmatch(repository):
        raise ReleaseError("Expected full lowercase commit SHA and owner/repository")
    return f"ghcr.io/{repository}", f"https://github.com/{repository}"


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inspect_image(image: str, architecture: str, revision: str, source: str) -> dict:
    if architecture not in ARCHITECTURES:
        raise ReleaseError("Unsupported architecture")
    items = json.loads(docker("image", "inspect", image))
    if not isinstance(items, list) or len(items) != 1:
        raise ReleaseError("Expected one local image")
    item = items[0]
    config = item.get("Config", {})
    labels = config.get("Labels") or {}
    if (
        item.get("Os") != "linux"
        or item.get("Architecture") != architecture
        or not DIGEST.fullmatch(item.get("Id", ""))
        or config.get("User") != "10001:10001"
        or labels.get("org.opencontainers.image.revision") != revision
        or labels.get("org.opencontainers.image.source") != source
        or f"SEEKBELL_BUILD_REVISION={revision}" not in config.get("Env", [])
    ):
        raise ReleaseError("Image platform, source, revision, environment or user mismatch")
    return item


def archive_config(archive: Path, tag: str) -> tuple[str, dict]:
    # Read bounded metadata without extracting any paths to the host filesystem.
    with tarfile.open(archive) as tar:

        def read(name: str) -> bytes:
            member = tar.getmember(name)
            if not member.isfile() or member.size > 1024 * 1024:
                raise ReleaseError("Unexpected image archive metadata")
            return tar.extractfile(member).read()

        manifests = json.loads(read("manifest.json"))
        if len(manifests) != 1 or manifests[0].get("RepoTags") != [tag]:
            raise ReleaseError("Expected exactly one runtime image with the artifact tag")
        config = read(manifests[0]["Config"])
        return "sha256:" + hashlib.sha256(config).hexdigest(), json.loads(config)


def match_config(item: dict, archived: dict) -> None:
    if (
        item["Os"] != archived.get("os")
        or item["Architecture"] != archived.get("architecture")
        or item.get("RootFS", {}).get("Layers") != archived.get("rootfs", {}).get("diff_ids")
        or any(
            item["Config"].get(key) != value for key, value in archived.get("config", {}).items()
        )
    ):
        raise ReleaseError("Archive configuration/layers differ from inspected image")


def pack(image: str, architecture: str, revision: str, repository: str, output: Path) -> dict:
    _, source = identity(revision, repository)
    item = inspect_image(image, architecture, revision, source)
    output.mkdir(parents=True, exist_ok=False)
    archive = output / "image.tar"
    tag = f"seekbell-artifact:sha-{revision}-{architecture}"
    # A private deterministic tag lets both classic and containerd stores load it.
    docker("image", "tag", item["Id"], tag)
    docker("image", "save", "--output", str(archive), tag)
    config_digest, config = archive_config(archive, tag)
    match_config(item, config)
    receipt = {
        "schema": 1,
        "architecture": architecture,
        "revision": revision,
        "source": source,
        "image_id": item["Id"],
        "archive_tag": tag,
        "config_digest": config_digest,
        "archive_sha256": checksum(archive),
    }
    (output / "image.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def verify(directory: Path, architecture: str, revision: str, repository: str) -> dict:
    _, source = identity(revision, repository)
    receipt = json.loads((directory / "image.json").read_text())
    tag = f"seekbell-artifact:sha-{revision}-{architecture}"
    if (
        receipt.get("schema") != 1
        or receipt.get("architecture") != architecture
        or receipt.get("revision") != revision
        or receipt.get("source") != source
        or not DIGEST.fullmatch(receipt.get("image_id", ""))
        or receipt.get("archive_tag") != tag
        or receipt.get("archive_sha256") != checksum(directory / "image.tar")
    ):
        raise ReleaseError("Artifact checksum, architecture or build identity mismatch")
    digest, config = archive_config(directory / "image.tar", tag)
    if digest != receipt.get("config_digest"):
        raise ReleaseError("Artifact runtime configuration digest mismatch")
    docker("image", "load", "--input", str(directory / "image.tar"))
    item = inspect_image(tag, architecture, revision, source)
    match_config(item, config)
    # Engine image IDs can refer to a config, manifest or index. Keep them distinct.
    return {**receipt, "loaded_id": item["Id"]}


def verify_index(index: dict, digests: dict[str, str]) -> str:
    if index.get("mediaType") not in INDEX_TYPES or not DIGEST.fullmatch(index.get("digest", "")):
        raise ReleaseError("Expected registry index with content digest")
    manifests = index.get("manifests", [])
    if len(manifests) != 2:
        raise ReleaseError("Expected exactly two platform manifests")
    observed = {}
    for manifest in manifests:
        platform = manifest.get("platform", {})
        architecture = platform.get("architecture")
        if (
            platform.get("os") != "linux"
            or architecture not in ARCHITECTURES
            or architecture in observed
            or platform.get("variant", "") not in ("", "v8" if architecture == "arm64" else "")
            or manifest.get("digest") != digests[architecture]
        ):
            raise ReleaseError("Registry index platform/digest mismatch")
        observed[architecture] = manifest["digest"]
    if observed != digests:
        raise ReleaseError("Registry index missing a required platform")
    return index["digest"]


def release(
    artifacts: Path, revision: str, repository: str, run: str, *, execute: bool = False
) -> dict:
    image, _ = identity(revision, repository)
    if not re.fullmatch(r"[1-9][0-9]*-[1-9][0-9]*", run):
        raise ReleaseError("Expected run ID and attempt, e.g. 12345-1")
    tag = f"{image}:sha-{revision}-{run}"
    # Check BOTH artifacts before the first registry write. No rebuild after testing.
    receipts = {
        arch: verify(artifacts / arch, arch, revision, repository) for arch in ARCHITECTURES
    }
    result = {"revision": revision, "tag": tag, "published": False, "images": receipts}
    if not execute:
        return result
    digests = {}
    for architecture, receipt in receipts.items():
        platform_tag = f"{tag}-{architecture}"
        docker("image", "tag", receipt["loaded_id"], platform_tag)
        docker("image", "push", "--quiet", "--platform", f"linux/{architecture}", platform_tag)
        # CLI push stdout varies by version. Read the digest from the registry instead.
        descriptor = json.loads(
            docker(
                "buildx", "imagetools", "inspect", "--format", "{{json .Manifest}}", platform_tag
            )
        )
        digest = descriptor.get("digest", "")
        if descriptor.get("mediaType") not in MANIFEST_TYPES or not DIGEST.fullmatch(digest):
            raise ReleaseError("Expected a single-platform registry manifest with digest")
        # Confirm the pushed manifest refers to the exact tested image configuration.
        manifest = json.loads(
            docker("buildx", "imagetools", "inspect", "--raw", f"{image}@{digest}")
        )
        if manifest.get("config", {}).get("digest") != receipt["config_digest"]:
            raise ReleaseError("Pushed image configuration differs from tested artifact")
        digests[architecture] = digest
    docker(
        "buildx",
        "imagetools",
        "create",
        "--tag",
        tag,
        *(f"{image}@{digests[arch]}" for arch in ARCHITECTURES),
    )
    index = json.loads(
        docker("buildx", "imagetools", "inspect", "--format", "{{json .Manifest}}", tag)
    )
    digest = verify_index(index, digests)
    # Verify again by immutable reference, not just the tag.
    pinned = json.loads(
        docker(
            "buildx", "imagetools", "inspect", "--format", "{{json .Manifest}}", f"{image}@{digest}"
        )
    )
    if verify_index(pinned, digests) != digest:
        raise ReleaseError("Pinned registry index changed")
    result.update(published=True, digest=digest, reference=f"{image}@{digest}", manifests=digests)
    return result


def alias(report: dict, revision: str, repository: str, tag: str, *, execute: bool = False) -> dict:
    image, _ = identity(revision, repository)
    if (
        len(tag) > 64
        or not re.fullmatch(r"[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*", tag)
        or tag == "latest"
    ):
        raise ReleaseError("Expected an explicit short candidate tag, not latest")
    digest = report.get("digest", "")
    digests = report.get("manifests", {})
    if (
        report.get("published") is not True
        or report.get("revision") != revision
        or not DIGEST.fullmatch(digest)
        or report.get("reference") != f"{image}@{digest}"
        or set(digests) != set(ARCHITECTURES)
        or any(not DIGEST.fullmatch(value) for value in digests.values())
    ):
        raise ReleaseError("Alias requires the matching published two-platform receipt")
    pinned = json.loads(
        docker(
            "buildx", "imagetools", "inspect", "--format", "{{json .Manifest}}", report["reference"]
        )
    )
    if verify_index(pinned, digests) != digest:
        raise ReleaseError("Alias source differs from verified registry index")
    target = f"{image}:{tag}"
    result = {
        "revision": revision,
        "tag": target,
        "reference": report["reference"],
        "digest": digest,
        "published": False,
    }
    if execute:
        # One existing index source is copied verbatim; do not rebuild or combine runs.
        docker("buildx", "imagetools", "create", "--tag", target, report["reference"])
        tagged = json.loads(
            docker("buildx", "imagetools", "inspect", "--format", "{{json .Manifest}}", target)
        )
        if verify_index(tagged, digests) != digest:
            raise ReleaseError("Short tag differs from verified registry index")
        result["published"] = True
    return result


def version_tags(version: str, *, latest: bool = False) -> list[str]:
    number = r"(?:0|[1-9][0-9]*)"
    match = re.fullmatch(
        rf"v({number}\.{number}\.{number})(-(?:alpha|beta|rc)\.[1-9][0-9]*)?", version
    )
    if match is None:
        raise ReleaseError("Expected vX.Y.Z or vX.Y.Z-alpha/beta/rc.N")
    tags = [version[1:]]
    if latest:
        if match[2]:
            raise ReleaseError("A prerelease cannot update latest")
        tags.append("latest")
    return tags


def public_digest(image: str, tag: str) -> str | None:
    """Distinguish a missing public tag from a registry/authentication failure."""
    repository = image.removeprefix("ghcr.io/")
    if image != "ghcr.io/" + repository or not REPOSITORY.fullmatch(repository):
        raise ReleaseError("Expected a public GHCR repository")
    query = urllib.parse.urlencode({"service": "ghcr.io", "scope": f"repository:{repository}:pull"})
    try:
        with urllib.request.urlopen("https://ghcr.io/token?" + query, timeout=30) as response:
            token = json.load(response)["token"]
        request = urllib.request.Request(
            f"https://ghcr.io/v2/{repository}/manifests/{tag}",
            headers={
                "Authorization": "Bearer " + token,
                "Accept": ", ".join(sorted(INDEX_TYPES | MANIFEST_TYPES)),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                digest = response.headers.get("Docker-Content-Digest", "")
                content = response.read(1024 * 1024 + 1)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        if len(content) > 1024 * 1024 or digest != "sha256:" + hashlib.sha256(content).hexdigest():
            raise ReleaseError("Registry manifest content digest mismatch")
        return digest
    except ReleaseError:
        raise
    except (OSError, ValueError, KeyError) as exc:
        raise ReleaseError("Cannot verify public registry tag; no version tags written") from exc


def promote(
    report: dict,
    revision: str,
    repository: str,
    version: str,
    *,
    latest: bool = False,
    execute: bool = False,
) -> dict:
    tags = version_tags(version, latest=latest)
    image, _ = identity(revision, repository)
    # Reuse all receipt and exact two-platform checks before any registry writes.
    checked = alias(report, revision, repository, "version-check")
    existing = public_digest(image, tags[0])
    if existing is not None and existing != checked["digest"]:
        raise ReleaseError("Version tag already identifies different bytes; choose a new version")
    result = {
        **checked,
        "version": version,
        "tags": [f"{image}:{tag}" for tag in tags],
        "published": False,
    }
    result.pop("tag")
    if execute:
        for target in result["tags"]:
            docker("buildx", "imagetools", "create", "--tag", target, report["reference"])
            tagged = json.loads(
                docker("buildx", "imagetools", "inspect", "--format", "{{json .Manifest}}", target)
            )
            if verify_index(tagged, report["manifests"]) != checked["digest"]:
                raise ReleaseError("Version tag differs from verified registry index")
        result["published"] = True
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--repository", required=True, help="lowercase GitHub owner/repository")
    commands = parser.add_subparsers(dest="command", required=True)
    package = commands.add_parser("pack", help="Save an already checked local image")
    package.add_argument("--image", required=True)
    package.add_argument("--architecture", choices=ARCHITECTURES, required=True)
    package.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("verify", help="Verify checksum and load one local artifact")
    check.add_argument("--directory", type=Path, required=True)
    check.add_argument("--architecture", choices=ARCHITECTURES, required=True)
    publish = commands.add_parser("release", help="Plan locally; --execute explicitly writes GHCR")
    publish.add_argument("--artifacts", type=Path, required=True)
    publish.add_argument("--run", required=True)
    publish.add_argument("--execute", action="store_true")
    publish.add_argument("--report", type=Path, required=True)
    short = commands.add_parser(
        "alias", help="Alias a checked published index; --execute writes GHCR"
    )
    short.add_argument("--receipt", type=Path, required=True)
    short.add_argument("--tag", required=True)
    short.add_argument("--execute", action="store_true")
    short.add_argument("--report", type=Path, required=True)
    versioned = commands.add_parser(
        "promote", help="Tag a verified release version and optional latest"
    )
    versioned.add_argument("--receipt", type=Path, required=True)
    versioned.add_argument(
        "--version", required=True, help="Git release tag vX.Y.Z[-alpha/beta/rc.N]"
    )
    versioned.add_argument("--latest", action="store_true")
    versioned.add_argument("--execute", action="store_true")
    versioned.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "pack":
            result = pack(
                args.image, args.architecture, args.revision, args.repository, args.output
            )
        elif args.command == "verify":
            result = verify(args.directory, args.architecture, args.revision, args.repository)
        elif args.command == "promote":
            result = promote(
                json.loads(args.receipt.read_text()),
                args.revision,
                args.repository,
                args.version,
                latest=args.latest,
                execute=args.execute,
            )
            args.report.write_text(json.dumps(result, indent=2) + "\n")
        elif args.command == "alias":
            result = alias(
                json.loads(args.receipt.read_text()),
                args.revision,
                args.repository,
                args.tag,
                execute=args.execute,
            )
            args.report.write_text(json.dumps(result, indent=2) + "\n")
        else:
            result = release(
                args.artifacts, args.revision, args.repository, args.run, execute=args.execute
            )
            args.report.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
    except ReleaseError as exc:
        raise SystemExit(f"Image release check failed: {exc}; no success recorded") from None
    except (ValueError, OSError, tarfile.TarError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(
            f"Image release check failed ({type(exc).__name__}); no success recorded"
        ) from None


if __name__ == "__main__":
    main()
