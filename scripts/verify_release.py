"""Verify a published release the way an anonymous user would see it.

Downloads the Release assets without credentials, checks them against
deployment.json and the tagged source templates, and resolves every recorded
registry tag to the receipt's two-platform index. Runs as the last release
job; it can also be rerun locally on the tagged checkout.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = {
    "release.json",
    "version.json",
    "package.json",
    "deployment.json",
    "compose.portainer.yaml",
    "compose.portainer.compare.yaml",
}
MANIFESTS = ", ".join(
    [
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ]
)
LIMIT = 4 * 1024 * 1024


class VerificationError(Exception):
    pass


def check(condition, message):
    if not condition:
        raise VerificationError(message)


def fetch(url, headers=None):
    request = urllib.request.Request(
        url, headers={"User-Agent": "seekbell-release-verification", **(headers or {})}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(LIMIT + 1)
    check(len(data) <= LIMIT, "Response too large: " + url)
    return data


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def verify(tag, revision, repository, fetch=fetch, compose_check=True):
    check(re.fullmatch(r"v\d+\.\d+\.\d+(-(alpha|beta|rc)\.[1-9]\d*)?", tag), "Bad tag")
    check(re.fullmatch("[0-9a-f]{40}", revision), "Use a full commit SHA")
    image = "ghcr.io/" + repository.lower()
    api = "https://api.github.com/repos/" + repository
    release = json.loads(fetch(api + "/releases/tags/" + tag))
    check(not release["draft"], "Release is still a draft")
    check(release["prerelease"] == ("-" in tag), "Prerelease flag does not match the tag")
    published = {asset["name"]: asset for asset in release["assets"]}
    check(set(published) >= ASSETS, f"Missing assets: {sorted(ASSETS - set(published))}")
    files = {name: fetch(published[name]["browser_download_url"]) for name in ASSETS}
    receipt, version, deployment = (
        json.loads(files[name]) for name in ["release.json", "version.json", "deployment.json"]
    )
    for record in [receipt, version, deployment]:
        check(record["revision"] == revision, "Asset records a different revision")
    check(receipt["published"] and version["published"], "Receipt is not a published run")
    check(version["version"] == deployment["version"] == tag, "Asset version mismatch")
    digest = receipt["digest"]
    check(version["digest"] == digest, "version.json digest mismatch")
    pinned = image + ":" + tag[1:]
    check(deployment["image"] == pinned + "@" + digest, "Deployment image is not pinned")
    check(pinned in version["tags"], "Version tag missing from version.json")
    for name, expected in deployment["sha256"].items():
        check(name in files and sha256(files[name]) == expected, "Checksum mismatch: " + name)
        source = (ROOT / "deploy" / name).read_text()
        expected_text = source.replace(
            "image: " + pinned + "\n", "image: " + deployment["image"] + "\n"
        )
        check(files[name].decode() == expected_text, name + " differs from the tagged template")
        if compose_check:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / name
                path.write_bytes(files[name])
                subprocess.run(
                    ["docker", "compose", "-f", str(path), "config", "--quiet"], check=True
                )
    query = urllib.parse.urlencode(
        {"service": "ghcr.io", "scope": "repository:" + repository.lower() + ":pull"}
    )
    token = json.loads(fetch("https://ghcr.io/token?" + query))["token"]
    headers = {"Authorization": "Bearer " + token, "Accept": MANIFESTS}
    base = "https://ghcr.io/v2/" + repository.lower()
    for reference in version["tags"]:
        data = fetch(base + "/manifests/" + reference.rsplit(":", 1)[1], headers)
        check("sha256:" + sha256(data) == digest, reference + " does not resolve to the receipt")
        observed = {
            entry["platform"]["architecture"]: entry["digest"]
            for entry in json.loads(data)["manifests"]
            if entry["platform"]["os"] == "linux"
        }
        check(observed == receipt["manifests"], reference + " platforms differ from the receipt")
    for architecture, manifest_digest in receipt["manifests"].items():
        manifest = json.loads(fetch(base + "/manifests/" + manifest_digest, headers))
        config_digest = manifest["config"]["digest"]
        check(
            config_digest == receipt["images"][architecture]["config_digest"],
            architecture + " config differs from the tested image",
        )
        config = json.loads(fetch(base + "/blobs/" + config_digest, headers))
        labels = config["config"]["Labels"]
        check(labels["org.opencontainers.image.revision"] == revision, "Image revision label")
        check(config["architecture"] == architecture and config["os"] == "linux", "Platform")
    return {
        "tag": tag,
        "revision": revision,
        "digest": digest,
        "tags": version["tags"],
        "platforms": sorted(receipt["manifests"]),
        "asset_sha256": {name: sha256(data) for name, data in sorted(files.items())},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="vX.Y.Z or vX.Y.Z-rc.N")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--repository", default="Aspeternity/seekbell")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if head != args.revision:
        parser.error("Check out the tagged revision first so templates can be compared")
    try:
        result = verify(args.tag, args.revision, args.repository)
    except VerificationError as error:
        print("Release verification failed: " + str(error), file=sys.stderr)
        return 1
    text = json.dumps(result, indent=2) + "\n"
    if args.report:
        args.report.write_text(text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
