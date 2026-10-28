"""Rehearse real encrypted backups across two installed cryptography versions offline."""

import argparse
import json
import socket
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def no_network(*args, **kwargs):
    raise RuntimeError("Network access is forbidden in the synthetic compatibility rehearsal")


def stage(mode: str, root: Path, destination: Path | None) -> dict:
    # Both interpreters use the same application source and independent dependencies.
    import cryptography
    from seekbell.backup import create_backup, restore_backup, validate_credentials
    from seekbell.config import Settings
    from seekbell.db.runtime import create_database_engine
    from seekbell.services.authentication import login, session_info
    from seekbell.services.backup_demo import (
        ADMIN_PASSWORD,
        PASSWORD,
        prepare,
        table_data,
    )

    socket.socket.connect = no_network
    socket.socket.connect_ex = no_network
    socket.create_connection = no_network
    settings = Settings(data_dir=root / "source", build_revision="synthetic-crypto-compatibility")
    archive = root / "synthetic.sbbackup"
    if mode == "create":
        root.mkdir(mode=0o700)
        token, _ = prepare(settings)
        before = table_data(settings.database_path)
        create_backup(settings, archive, password=PASSWORD)
        assert table_data(settings.database_path) == before
        identity = root / "synthetic-session.json"
        identity.write_text(json.dumps({"token": token}))
        identity.chmod(0o600)
        return {"cryptography": cryptography.__version__, "source_unchanged": True}

    assert destination is not None
    before = table_data(settings.database_path)
    source_key = (settings.data_dir / "credentials.key").read_bytes()
    restore_backup(
        settings,
        archive,
        destination,
        password=PASSWORD,
        username="backup_admin",
        admin_password=ADMIN_PASSWORD,
    )
    assert table_data(settings.database_path) == before
    after = table_data(destination / "seekbell.sqlite3")
    assert after.pop("login_sessions") == []
    before.pop("login_sessions")
    assert before == after
    assert (destination / "credentials.key").read_bytes() == source_key
    validate_credentials(destination)
    engine = create_database_engine(Settings(data_dir=destination))
    try:
        token = json.loads((root / "synthetic-session.json").read_text())["token"]
        assert session_info(engine, token) is None
        assert login(engine, "backup_admin", ADMIN_PASSWORD)
    finally:
        engine.dispose()
    return {
        "cryptography": cryptography.__version__,
        "source_unchanged": True,
        "all_tables_preserved": True,
        "original_key_and_ciphertexts_readable": True,
        "old_session_revoked": True,
        "restored_login": True,
    }


def child(python: Path, mode: str, root: Path, destination: Path | None = None) -> dict:
    command = [str(python), str(Path(__file__).resolve()), "--stage", mode, "--root", str(root)]
    if destination is not None:
        command.extend(["--destination", str(destination)])
    result = subprocess.run(command, capture_output=True, text=True, timeout=240)
    if result.returncode:
        raise RuntimeError(f"Synthetic compatibility stage {mode} failed ({result.returncode})")
    return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-python", type=Path)
    parser.add_argument("--new-python", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--stage", choices=["create", "restore"], help=argparse.SUPPRESS)
    parser.add_argument("--root", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--destination", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.stage:
        if args.root is None:
            parser.error("--root is required for an internal stage")
        result = stage(args.stage, args.root, args.destination)
    else:
        if args.old_python is None or args.new_python is None:
            parser.error("Provide both installed Python interpreters")
        with TemporaryDirectory(prefix="seekbell-crypto-compatibility-") as directory:
            root = Path(directory)
            old, new = root / "old", root / "new"
            created_old = child(args.old_python, "create", old)
            created_new = child(args.new_python, "create", new)
            result = {
                "mode": "offline_synthetic",
                "old_cryptography": created_old["cryptography"],
                "new_cryptography": created_new["cryptography"],
                "old_backup_read_by_new": child(args.new_python, "restore", old, root / "to-new"),
                "new_backup_read_by_old": child(args.old_python, "restore", new, root / "to-old"),
            }
    encoded = json.dumps(result, indent=2) + "\n"
    if args.report is not None:
        args.report.write_text(encoded)
    sys.stdout.write(encoded)


if __name__ == "__main__":
    main()
