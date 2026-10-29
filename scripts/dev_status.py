"""One-screen snapshot for resuming work in a new conversation.

    python3 scripts/dev_status.py            # local Git state + latest public CI runs
    python3 scripts/dev_status.py --offline  # local only

Replaces running several git/CI commands at the start of every session.
Read docs/PROJECT_STATE.md next; it says what to read after that.
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "Aspeternity/seekbell"


def git(*args):
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return result.stdout.rstrip() if result.returncode == 0 else ""


def runs(branch, limit=4):
    url = f"https://api.github.com/repos/{REPOSITORY}/actions/runs?per_page={limit}" + (
        f"&branch={branch}" if branch else ""
    )
    request = urllib.request.Request(url, headers={"User-Agent": "seekbell-dev-status"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)["workflow_runs"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)
    branch = git("branch", "--show-current")
    print(f"WSL: {os.environ.get('WSL_DISTRO_NAME', '?')}  dir: {ROOT}")
    print(f"branch: {branch or '(detached)'}  HEAD: {git('log', '-1', '--format=%h %s')}")
    counts = git("rev-list", "--left-right", "--count", "@{upstream}...HEAD")
    if counts:
        behind, ahead = counts.split()
        upstream = git("rev-parse", "--abbrev-ref", "@{upstream}")
        print(f"upstream: {upstream}  ahead {ahead} / behind {behind}")
    main_counts = git("rev-list", "--left-right", "--count", "origin/main...HEAD")
    if main_counts and branch != "main":
        behind, ahead = main_counts.split()
        print(f"vs origin/main: ahead {ahead} / behind {behind}")
    version = subprocess.run(
        [sys.executable, str(ROOT / "scripts/bump_version.py"), "--check"],
        capture_output=True,
        text=True,
    )
    print("version: " + (version.stdout or version.stderr).strip().replace("\n", "; "))
    changes = git("status", "--porcelain").splitlines()
    print(f"working tree: {len(changes) or 'clean'}" + (" changed" if changes else ""))
    for line in changes[:25]:
        print("  " + line)
    if len(changes) > 25:
        print(f"  … {len(changes) - 25} more")
    print("recent commits:")
    for line in git("log", "-4", "--format=  %h %ad %s", "--date=short").splitlines():
        print(line)
    if not args.offline:
        try:
            for run in runs(branch) or runs(None):
                state = run["conclusion"] or run["status"]
                where = f"{run['event']}, {run['head_sha'][:7]}"
                print(f"CI: {state:<11} {run['name']} ({where}) {run['html_url']}")
        except Exception as error:
            print(f"CI: unavailable ({error.__class__.__name__}); use --offline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
