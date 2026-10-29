"""Reuse a passed baseline for an identical source tree.

The baseline result depends only on the checked-out tree, so a later run for
the same tree (push to main after a merged PR, or the release tag) can skip
the full suite. Proof is a marker artifact uploaded as the baseline's last
step; only markers produced by this repository's own workflow runs count, so
fork PRs cannot vouch for a tree. Any lookup failure falls back to running
the baseline.
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request

PREFIX = "baseline-tree-"


def tree(revision="HEAD"):
    return subprocess.check_output(["git", "rev-parse", revision + "^{tree}"], text=True).strip()


def trusted(artifact, repository_id):
    run = artifact.get("workflow_run") or {}
    return (
        not artifact.get("expired")
        and str(run.get("repository_id")) == str(repository_id)
        and str(run.get("head_repository_id")) == str(repository_id)
    )


def find_marker(name, repository, repository_id, token, fetch=None):
    url = f"https://api.github.com/repos/{repository}/actions/artifacts?name={name}&per_page=20"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "User-Agent": "seekbell-ci-reuse",
        },
    )
    if fetch is None:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.load(response)
    else:
        data = fetch(request)
    for artifact in data.get("artifacts", []):
        if artifact.get("name") == name and trusted(artifact, repository_id):
            return artifact["workflow_run"]["id"]
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=os.environ.get("GITHUB_OUTPUT"))
    args = parser.parse_args(argv)
    name = PREFIX + tree()
    run = None
    try:
        run = find_marker(
            name,
            os.environ["GITHUB_REPOSITORY"],
            os.environ["GITHUB_REPOSITORY_ID"],
            os.environ["GITHUB_TOKEN"],
        )
    except Exception as error:  # never block CI on the shortcut itself
        print(f"Baseline reuse lookup failed, running the full baseline: {error}")
    if run:
        print(f"Tree already passed the baseline in run {run}; reusing that result.")
    else:
        print("No trusted baseline marker for this tree; running the full baseline.")
    if args.output:
        with open(args.output, "a") as output:
            output.write(f"marker={name}\nverified={'true' if run else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
