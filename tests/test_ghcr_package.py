import copy
import importlib.util
import io
import urllib.error
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "ghcr_package", Path(__file__).parents[1] / "scripts" / "check_ghcr_package.py"
)
package_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package_tool)
REPO = {"full_name": "Synthetic/SeekBell", "private": True, "owner": {"type": "User"}}
PACKAGE = {
    "name": "seekbell",
    "package_type": "container",
    "visibility": "private",
    "repository": REPO,
}


def respond(monkeypatch, repo=REPO, package=PACKAGE):
    calls = []

    def api(path, token):
        calls.append(path)
        return copy.deepcopy(repo if path.startswith("/repos/") else package)

    monkeypatch.setattr(package_tool, "api", api)
    return calls


def test_existing_private_linked_package_is_accepted(monkeypatch):
    calls = respond(monkeypatch)
    result = package_tool.check("synthetic/seekbell", "synthetic-token")
    assert result["private_verified"]
    assert calls == ["/repos/synthetic/seekbell", "/users/synthetic/packages/container/seekbell"]


def test_organization_uses_the_organization_endpoint(monkeypatch):
    repo = copy.deepcopy(REPO)
    repo["owner"]["type"] = "Organization"
    calls = respond(monkeypatch, repo)
    package_tool.check("synthetic/seekbell", "synthetic-token")
    assert calls[-1].startswith("/orgs/")


@pytest.mark.parametrize("visibility", ["public", "internal", None])
def test_nonprivate_package_is_rejected_even_when_missing_is_allowed(monkeypatch, visibility):
    respond(monkeypatch, package={**PACKAGE, "visibility": visibility})
    with pytest.raises(package_tool.PackageError, match="visibility"):
        package_tool.check("synthetic/seekbell", "synthetic-token", allow_missing=True)


@pytest.mark.parametrize(
    "fault",
    [
        "repo-public",
        "repo-mismatch",
        "owner",
        "linked-public",
        "linked-other",
        "invalid-link",
        "name",
        "type",
    ],
)
def test_unexpected_identity_or_access_is_rejected(monkeypatch, fault):
    repo, package = copy.deepcopy(REPO), copy.deepcopy(PACKAGE)
    if fault == "repo-public":
        repo["private"] = False
    elif fault == "repo-mismatch":
        repo["full_name"] = "other/project"
    elif fault == "owner":
        repo["owner"]["type"] = "unknown"
    elif fault == "linked-public":
        package["repository"]["private"] = False
    elif fault == "linked-other":
        package["repository"]["full_name"] = "other/project"
    elif fault == "invalid-link":
        package["repository"] = "invalid"
    elif fault == "name":
        package["name"] = "other"
    else:
        package["package_type"] = "npm"
    respond(monkeypatch, repo, package)
    with pytest.raises(package_tool.PackageError):
        package_tool.check("synthetic/seekbell", "synthetic-token", allow_missing=True)


def test_404_is_only_allowed_before_publication(monkeypatch):
    respond(monkeypatch, package=None)
    assert not package_tool.check("synthetic/seekbell", "synthetic-token", allow_missing=True)[
        "private_verified"
    ]
    with pytest.raises(package_tool.PackageError):
        package_tool.check("synthetic/seekbell", "synthetic-token")


@pytest.mark.parametrize("status", [301, 401, 403, 500])
def test_api_errors_are_not_interpreted_as_missing_or_exposed(monkeypatch, status):
    class Opener:
        def open(self, request, timeout):
            assert request.headers["Authorization"] == "Bearer synthetic-sensitive-token"
            raise urllib.error.HTTPError(
                request.full_url,
                status,
                "sensitive-body",
                {},
                io.BytesIO(b"synthetic-sensitive-token"),
            )

    monkeypatch.setattr(package_tool.urllib.request, "build_opener", lambda *args: Opener())
    with pytest.raises(package_tool.PackageError) as error:
        package_tool.api("/repos/synthetic/seekbell", "synthetic-sensitive-token")
    assert str(status) in str(error.value)
    assert "sensitive" not in str(error.value)


def test_metadata_404_can_be_reported_without_leaking_body(monkeypatch):
    class Opener:
        def open(self, request, timeout):
            raise urllib.error.HTTPError(request.full_url, 404, "private", {}, None)

    monkeypatch.setattr(package_tool.urllib.request, "build_opener", lambda *args: Opener())
    assert package_tool.api("/repos/synthetic/seekbell", "synthetic-token") is None


def test_redirects_never_forward_the_token():
    assert (
        package_tool.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.test")
        is None
    )


@pytest.mark.parametrize("reported", [False, True])
def test_nullable_or_absent_repository_follows_the_official_schema(monkeypatch, reported):
    package = copy.deepcopy(PACKAGE)
    if reported:
        package["repository"] = None
    else:
        package.pop("repository")
    respond(monkeypatch, package=package)
    result = package_tool.check("synthetic/seekbell", "synthetic-token")
    assert result["private_verified"] is True
    assert result["repository_binding"] == "not-reported"


def test_reported_repository_is_explicitly_distinguished(monkeypatch):
    respond(monkeypatch)
    assert (
        package_tool.check("synthetic/seekbell", "synthetic-token")["repository_binding"]
        == "reported"
    )
