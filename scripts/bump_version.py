"""Set or check the release version everywhere it is recorded.

    python3 scripts/bump_version.py 0.3.0        # or v0.3.0-rc.1
    python3 scripts/bump_version.py --check      # all files agree, CHANGELOG has an entry

Updates pyproject.toml, the seekbell entry in uv.lock, frontend/package.json
and both Portainer templates (version, image tag and current schema). A
missing CHANGELOG heading is added as a stub that still has to be written.
"""

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ["deploy/compose.portainer.yaml", "deploy/compose.portainer.compare.yaml"]
IMAGE = "ghcr.io/aspeternity/seekbell"
VERSION = re.compile(r"v?(\d+\.\d+\.\d+)(?:-(alpha|beta|rc)\.([1-9]\d*))?")
PEP440 = {"alpha": "a", "beta": "b", "rc": "rc"}


def parse(text):
    """Return (SemVer used by tags/images/frontend, PEP 440 used by Python)."""
    match = VERSION.fullmatch(text.strip())
    if not match:
        raise SystemExit(f"Not a release version: {text!r} (use X.Y.Z or X.Y.Z-rc.N)")
    core, kind, number = match.groups()
    if not kind:
        return core, core
    return f"{core}-{kind}.{number}", f"{core}{PEP440[kind]}{number}"


def schema(root):
    names = sorted(
        (root / "backend/seekbell/migrations/versions").glob("[0-9][0-9][0-9][0-9]_*.py")
    )
    return names[-1].name[:4]


def replace(path, pattern, value, count=1):
    text = path.read_text()
    updated, found = re.subn(pattern, value, text, count=count, flags=re.M)
    if found != count:
        raise SystemExit(f"{path.relative_to(ROOT)}: expected version field not found")
    path.write_text(updated)


def recorded(root):
    """Versions as currently written in each file, normalised to SemVer."""
    pyproject = re.search(r'^version = "([^"]+)"', (root / "pyproject.toml").read_text(), re.M)
    lock = re.search(
        r'^name = "seekbell"\nversion = "([^"]+)"', (root / "uv.lock").read_text(), re.M
    )
    found = {
        "pyproject.toml": pyproject and pyproject[1],
        "uv.lock": lock and lock[1],
        "frontend/package.json": json.loads((root / "frontend/package.json").read_text())[
            "version"
        ],
    }
    for name in TEMPLATES:
        text = (root / name).read_text()
        header = re.match(r"# SeekBell (\S+); schema (\d{4})\.", text)
        image = re.search(r"^\s*image: " + re.escape(IMAGE) + r":(\S+)$", text, re.M)
        found[name] = header and image and header[1] == image[1] and header[1]
        found[name + " schema"] = header and header[2]
    return found


def check(root=ROOT):
    found = recorded(root)
    semver, pep440 = parse(found["frontend/package.json"])
    problems = []
    for name, value in found.items():
        expected = (
            schema(root)
            if name.endswith(" schema")
            else pep440
            if name in ("pyproject.toml", "uv.lock")
            else semver
        )
        if value != expected:
            problems.append(f"{name}: {value!r}, expected {expected!r}")
    if not re.search(r"^## " + re.escape(semver) + r" ", (root / "CHANGELOG.md").read_text(), re.M):
        problems.append(f"CHANGELOG.md: no '## {semver} — date' entry")
    return semver, problems


def bump(text, root=ROOT, today=None):
    semver, pep440 = parse(text)
    replace(root / "pyproject.toml", r'^version = "[^"]+"', f'version = "{pep440}"')
    replace(root / "uv.lock", r'^(name = "seekbell"\nversion = )"[^"]+"', rf'\g<1>"{pep440}"')
    replace(root / "frontend/package.json", r'^  "version": "[^"]+"', f'  "version": "{semver}"')
    current = schema(root)
    for name in TEMPLATES:
        replace(
            root / name,
            r"^# SeekBell \S+; schema \d{4}\.",
            f"# SeekBell {semver}; schema {current}.",
        )
        replace(root / name, r"^(\s*image: " + re.escape(IMAGE) + r"):\S+$", rf"\g<1>:{semver}")
    changelog = root / "CHANGELOG.md"
    text = changelog.read_text()
    if not re.search(r"^## " + re.escape(semver) + r" ", text, re.M):
        date = (today or datetime.date.today()).isoformat()
        stub = f"## {semver} — {date}\n\n- TODO: 写明用户可见变化、迁移与升级/回退注意事项。\n\n"
        changelog.write_text(text.replace("\n## ", "\n" + stub + "## ", 1))
        print(f"Added a CHANGELOG stub for {semver}; fill it in before the PR.")
    return semver


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("version", nargs="?")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if bool(args.version) == args.check:
        parser.error("give a version to set, or --check")
    if args.version:
        semver = bump(args.version)
        print(f"Version set to {semver}; tag the release as v{semver}.")
    semver, problems = check()
    if "TODO:" in (ROOT / "CHANGELOG.md").read_text().split("\n## ", 2)[1]:
        problems.append(f"CHANGELOG.md: {semver} entry still contains TODO")
    for problem in problems:
        print(problem, file=sys.stderr)
    if args.check and not problems:
        print(f"Version {semver} is consistent.")
    return 1 if args.check and problems else 0


if __name__ == "__main__":
    sys.exit(main())
