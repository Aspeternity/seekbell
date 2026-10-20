"""Read GitHub package metadata without logging credentials or changing visibility."""

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request


class PackageError(ValueError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api(path: str, token: str) -> dict | None:
    request = urllib.request.Request(
        "https://api.github.com" + path,
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise PackageError(f"GitHub metadata request rejected (HTTP {error.code})") from None
    except (urllib.error.URLError, ValueError):
        raise PackageError("Could not verify GitHub metadata") from None


def check(repository: str, token: str, *, allow_missing: bool = False, wait: int = 0) -> dict:
    if not re.fullmatch(r"[a-z0-9]+(?:[._-][a-z0-9]+)*/[a-z0-9]+(?:[._-][a-z0-9]+)*", repository):
        raise PackageError("Expected lowercase owner/repository")
    if not token or not 0 <= wait <= 60:
        raise PackageError("Short-lived GitHub token and wait in 0..60 required")
    owner, name = repository.split("/")
    repo = api(f"/repos/{repository}", token)
    if (
        not repo
        or repo.get("full_name", "").lower() != repository
        or repo.get("private") is not True
    ):
        raise PackageError("Expected the authorized private repository")
    kind = {"User": "users", "Organization": "orgs"}.get(repo.get("owner", {}).get("type"))
    if kind is None:
        raise PackageError("Unknown repository owner type")
    deadline = time.monotonic() + wait
    while True:
        package = api(f"/{kind}/{owner}/packages/container/{name}", token)
        if package is not None or time.monotonic() >= deadline:
            break
        time.sleep(min(2, max(0, deadline - time.monotonic())))
    result = {"package": f"ghcr.io/{repository}", "repository": repository}
    if package is None:
        if not allow_missing:
            raise PackageError("Published package metadata is not readable")
        # 404 can also mean inaccessible. It never authorizes changing package permissions.
        return {**result, "visibility": "not-found", "private_verified": False}
    if package.get("visibility") != "private":
        raise PackageError("Refusing to publish to a package whose visibility is not private")
    linked = package.get("repository") or {}
    if linked.get("full_name", "").lower() != repository or linked.get("private") is not True:
        raise PackageError("Package must be linked to the authorized private repository")
    if package.get("name") != name or package.get("package_type") != "container":
        raise PackageError("Unexpected package identity")
    return {**result, "visibility": "private", "private_verified": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--allow-missing", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=0)
    args = parser.parse_args()
    try:
        result = check(
            args.repository,
            os.environ.get("GITHUB_TOKEN", ""),
            allow_missing=args.allow_missing,
            wait=args.wait_seconds,
        )
    except PackageError as error:
        raise SystemExit(str(error)) from None
    print(json.dumps(result))


if __name__ == "__main__":
    main()
