"""Decide what an image workflow run may publish, before anything is built.

Three entry points share the publication jobs:

- release: a Release published by hand (also used for prereleases);
- workflow_run: the baseline passed for a push to main whose pyproject version
  has no tag yet, so this run publishes it and creates the Release afterwards;
- workflow_dispatch: a manual candidate check, publishing only when enabled.

Outputs (GITHUB_OUTPUT): repository, version (tag, empty for candidates) and
publish (true/false). Assertions stop the run; a push without a new final
version simply publishes nothing.
"""

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.release_images import version_tags  # noqa: E402

FINAL = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def package_version(root=Path(".")):
    return tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]


def pep440(tag):
    return re.sub(
        r"-(alpha|beta|rc)\.([1-9][0-9]*)",
        lambda m: {"alpha": "a", "beta": "b", "rc": "rc"}[m[1]] + m[2],
        tag[1:],
    )


def tag_exists(tag, run=subprocess.run):
    return run(["git", "rev-parse", "-q", "--verify", "refs/tags/" + tag]).returncode == 0


def plan(env, run=subprocess.run, root=Path(".")):
    event = env["GITHUB_EVENT_NAME"]
    revision = env["REVISION"]
    branch = "origin/" + env["DEFAULT_BRANCH"]
    version, publish = "", False
    if event == "release":
        version = env["RELEASE_TAG"]
        version_tags(version)
        assert env["GITHUB_REF"] == "refs/tags/" + version
        run(["git", "merge-base", "--is-ancestor", revision, branch], check=True)
        assert package_version(root) == pep440(version), (
            "Bump pyproject.toml and uv.lock before creating the release"
        )
        assert ("-" in version) == (env["PRERELEASE"] == "true"), "Release prerelease flag mismatch"
        publish = True
    elif event == "workflow_run":
        # The checkout is main's current head, never a commit named by the event. If
        # main moved on, the newer push's own passed baseline publishes instead.
        # Only final versions publish automatically; prereleases use a manual Release.
        current = package_version(root)
        if (
            env["PASSED_REVISION"] == revision
            and FINAL.fullmatch(current)
            and not tag_exists("v" + current, run)
        ):
            run(["git", "merge-base", "--is-ancestor", revision, branch], check=True)
            version, publish = "v" + current, True
    else:
        expected = env["EXPECTED_REVISION"]
        assert re.fullmatch("[0-9a-f]{40}", expected), "Use a full commit SHA"
        assert expected == revision, "Selected branch has a different commit"
        tag = env["SHORT_TAG"]
        publish = env["PUBLISH"] == "true"
        if tag:
            assert (
                len(tag) <= 64
                and re.fullmatch(r"[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*", tag)
                and tag != "latest"
            ), "Invalid short candidate tag"
            assert publish, "A short tag requires publication"
        if publish:
            assert env["ENABLED"] == "true", "Manual candidate publication is not enabled"
            assert env["GITHUB_REF"] == "refs/heads/" + env["DEFAULT_BRANCH"], (
                "Publish from the default branch only"
            )
    return {
        "repository": env["GITHUB_REPOSITORY"].lower(),
        "version": version,
        "publish": "true" if publish else "false",
    }


def newer(version, other):
    """Whether final tag `version` sorts above `other` (any tag, or None)."""
    if other is None:
        return True
    key = [int(part) for part in version[1:].split(".")]
    base, _, pre = other[1:].partition("-")
    other_key = [int(part) for part in base.split(".")]
    return key > other_key or (key == other_key and bool(pre))


def release_notes(version, changelog=Path("CHANGELOG.md")):
    """The CHANGELOG section for `version` (vX.Y.Z), required to be filled in."""
    heading = re.compile(r"^## " + re.escape(version[1:]) + r"(\s|$)")
    lines, inside = [], False
    for line in changelog.read_text().splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = bool(heading.match(line))
            continue
        if inside:
            lines.append(line)
    notes = "\n".join(lines).strip()
    assert notes and "TODO" not in notes, "CHANGELOG has no finished entry for " + version
    return notes + "\n"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["notes"]:
        sys.stdout.write(release_notes(argv[1]))
        return 0
    outputs = plan(os.environ)
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        for key, value in outputs.items():
            output.write(f"{key}={value}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
