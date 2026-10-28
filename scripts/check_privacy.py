"""Reject personal email addresses in Git identities and versioned content."""

import argparse
import re
import subprocess
from pathlib import Path

EMAIL = re.compile(rb"[A-Z0-9.!#$%&'*+/=?^_{|}~\[\]-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL)


def noreply(address: bytes) -> bool:
    address = address.lower()
    return address.endswith(b"@users.noreply.github.com") or address == b"noreply@github.com"


def safe_content(data: bytes) -> bool:
    for match in EMAIL.finditer(data):
        address = match.group()
        domain = address.rsplit(b"@", 1)[1].lower().rstrip(b".")
        if noreply(address):
            continue
        if domain in (b"example.com", b"example.net", b"example.org"):
            continue
        if domain.endswith((b".invalid", b".test", b".localhost")):
            continue
        return False
    return True


def safe_commit_message(data: bytes, author: bytes) -> bool:
    # Dependabot's public service sign-off is metadata, not a personal address.
    # Restrict the exception to that exact trailer and official noreply identity.
    if author.lower() == b"49699333+dependabot[bot]@users.noreply.github.com":
        data = re.sub(
            rb"(?m)^Signed-off-by: dependabot\[bot\] <support\x40github\.com>\r?$",
            b"Signed-off-by: dependabot[bot]",
            data,
        )
    return safe_content(data)


def check(repo: Path, *, staged: bool = False, identity: bool = False) -> tuple[int, int]:
    if staged or identity:
        for field in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
            value = git(repo, "var", field)
            match = re.search(rb"<([^<>]+)>", value)
            if match is None or not noreply(match.group(1)):
                raise ValueError("Current Git identity must use a GitHub noreply address")

    commits = git(repo, "log", "--all", "--format=%H%x09%ae%x09%ce").splitlines()
    for line in commits:
        sha, author, committer = line.split(b"\t")
        if not noreply(author) or not noreply(committer):
            raise ValueError(f"Non-noreply identity in commit {sha.decode()}")
    messages = git(repo, "log", "--all", "--format=%ae%x00%B%x00").split(b"\0")
    for index in range(0, len(messages) - 1, 2):
        if not safe_commit_message(messages[index + 1], messages[index].strip()):
            raise ValueError("Non-example, non-noreply email in commit messages")

    # Check reachable history and the index; deleting a file must not conceal a leak.
    objects = git(repo, "rev-list", "--objects", "--all").splitlines()
    checked = set()
    for line in objects:
        sha = line.split(b" ", 1)[0]
        if sha in checked or git(repo, "cat-file", "-t", sha.decode()).strip() != b"blob":
            continue
        checked.add(sha)
        if not safe_content(git(repo, "cat-file", "blob", sha.decode())):
            raise ValueError(f"Non-example, non-noreply email in Git blob {sha.decode()}")
    for name in git(repo, "ls-files", "-z").split(b"\0"):
        if not name:
            continue
        try:
            data = git(repo, "show", f":{name.decode()}")
        except subprocess.CalledProcessError:
            continue  # A staged deletion has no index blob.
        if not safe_content(data):
            raise ValueError("Non-example, non-noreply email in a tracked index file")
    return len(commits), len(checked)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--identity", action="store_true")
    args = parser.parse_args()
    try:
        commits, blobs = check(args.repo, staged=args.staged, identity=args.identity)
    except (ValueError, subprocess.CalledProcessError) as exc:
        # Never include the rejected address or file contents in logs.
        message = str(exc) if isinstance(exc, ValueError) else "Cannot inspect Git metadata"
        parser.exit(1, f"Privacy check failed: {message}\n")
    print(f"Privacy check passed: {commits} commits, {blobs} historical blobs")


if __name__ == "__main__":
    main()
