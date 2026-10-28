import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_privacy.py"
spec = importlib.util.spec_from_file_location("privacy", SCRIPT)
privacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(privacy)


def run(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL)


@pytest.fixture
def repo(tmp_path):
    run(tmp_path, "init", "-b", "main")
    run(tmp_path, "config", "user.name", "Synthetic Writer")
    run(tmp_path, "config", "user.email", "123+synthetic@users.noreply.github.com")
    (tmp_path / "sample.txt").write_text("Synthetic content\n")
    run(tmp_path, "add", ".")
    run(tmp_path, "commit", "-qm", "Synthetic baseline")
    return tmp_path


def test_accepts_noreply_and_reserved_examples(repo):
    (repo / "sample.txt").write_text("mail@example.com demo@sample.invalid")
    run(repo, "add", ".")
    assert privacy.check(repo, staged=True)[0] == 1


def test_rejects_non_noreply_author_even_for_synthetic_address(repo):
    run(repo, "config", "user.email", "synthetic@sample.invalid")
    with pytest.raises(ValueError, match="Current Git identity"):
        privacy.check(repo, staged=True)


def test_rejects_historical_identity(repo):
    run(repo, "config", "user.email", "synthetic@sample.invalid")
    run(repo, "commit", "--allow-empty", "-qm", "Synthetic non-noreply identity")
    with pytest.raises(ValueError, match="identity in commit"):
        privacy.check(repo)


def test_rejects_non_reserved_email_without_logging_address():
    address = b"synthetic@" + b"not-a-reserved-domain" + b".com"
    assert not privacy.safe_content(address)
    assert privacy.safe_content(b"noreply@github.com")
    assert privacy.safe_content(b"123+synthetic@users.noreply.github.com")


def test_historical_content_cannot_be_hidden_by_deletion(repo):
    candidate = "synthetic@" + "not-a-reserved-domain" + ".com"
    (repo / "sample.txt").write_text(candidate)
    run(repo, "add", ".")
    run(repo, "commit", "-qm", "Synthetic address policy violation")
    run(repo, "rm", "sample.txt")
    run(repo, "commit", "-qm", "Remove synthetic file")
    with pytest.raises(ValueError) as failure:
        privacy.check(repo)
    assert candidate not in str(failure.value)
    assert "Git blob" in str(failure.value)


def test_staged_content_checked_before_commit(repo):
    (repo / "sample.txt").write_text("synthetic@" + "not-a-reserved-domain" + ".com")
    run(repo, "add", ".")
    with pytest.raises(ValueError, match="tracked index file"):
        privacy.check(repo, staged=True)


BOT = b"49699333+dependabot[bot]@users.noreply.github.com"
BOT_TRAILER = b"Signed-off-by: dependabot[bot] <support" + bytes([64]) + b"github.com>"


def test_accepts_only_official_bot_trailer_in_bot_commit_message(repo):
    run(repo, "config", "user.email", BOT.decode())
    run(
        repo,
        "commit",
        "--allow-empty",
        "-qm",
        (b"Bump synthetic dependency\n\n" + BOT_TRAILER).decode(),
    )
    assert privacy.check(repo)[0] == 2
    assert not privacy.safe_content(BOT_TRAILER)


def test_bot_trailer_does_not_exempt_unrelated_author():
    assert not privacy.safe_commit_message(BOT_TRAILER, b"123+synthetic@users.noreply.github.com")


def test_bot_commit_still_rejects_personal_address_elsewhere():
    address = b"synthetic" + bytes([64]) + b"not-a-reserved-domain.com"
    assert not privacy.safe_commit_message(address + b"\n" + BOT_TRAILER, BOT)
    assert not privacy.safe_commit_message(
        b"Signed-off-by: dependabot[bot] <" + address + b">", BOT
    )


def test_bot_trailer_in_tracked_content_is_still_rejected(repo):
    (repo / "sample.txt").write_bytes(BOT_TRAILER)
    run(repo, "add", ".")
    with pytest.raises(ValueError, match="tracked index file"):
        privacy.check(repo, staged=True)
