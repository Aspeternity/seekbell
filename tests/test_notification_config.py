import json
import os

import pytest
from cryptography.fernet import Fernet
from seekbell.db.models import NotificationTarget, Outbox
from seekbell.domain.rules import Rule
from seekbell.notifiers.configs import channel_schemas, validate_config
from seekbell.notifiers.credentials import CredentialError, CredentialVault
from seekbell.services.configuration import Configuration
from sqlalchemy.orm import Session

from tests.notifier_helpers import CONFIGS


def vault():
    return CredentialVault(Fernet.generate_key())


@pytest.mark.parametrize("kind", list(CONFIGS))
def test_configuration_encrypted_and_public_projection_has_no_secret(core, kind):
    keyring = vault()
    service = Configuration(core.engine, keyring)
    key = service.create_target("target", kind=kind, config=CONFIGS[kind])
    public = service.get_target(key)
    assert public["kind"] == kind
    assert public["configured_secrets"]
    for field in public["configured_secrets"]:
        assert field not in public["config"]
        assert str(CONFIGS[kind].get(field, "")) not in json.dumps(public, ensure_ascii=False)
    with Session(core.engine) as session:
        row = session.get(NotificationTarget, key)
        assert keyring.unseal(key, kind, row.config_ciphertext) == validate_config(
            kind, CONFIGS[kind]
        )
        stored = row.config_ciphertext
    for value in CONFIGS[kind].values():
        if isinstance(value, str):
            assert value not in stored


def test_target_update_keeps_omitted_secrets_and_outbox_keeps_encrypted_old_revision(core):
    keyring = vault()
    service = Configuration(core.engine, keyring)
    key = service.create_target("old", kind="webhook", config=CONFIGS["webhook"])
    service.update_task(core.task, "rule", Rule(), [key], at=2)
    core.queued()
    old = core.one(Outbox).target_snapshot
    assert old["revision"] == 1 and "config" not in old
    assert service.update_target(key, name="new", config={"include_summary": True}) == 2
    with Session(core.engine) as session:
        row = session.get(NotificationTarget, key)
        updated = keyring.unseal(key, "webhook", row.config_ciphertext)
    assert updated["url"] == CONFIGS["webhook"]["url"]
    assert updated["headers"] == CONFIGS["webhook"]["headers"]
    assert updated["include_summary"]
    assert not keyring.unseal(key, "webhook", old["config_ciphertext"])["include_summary"]
    assert core.one(Outbox).target_snapshot == old


def test_wrong_key_tamper_or_cross_target_ciphertext_rejected():
    keyring = vault()
    ciphertext = keyring.seal("target-a", "bark", {"device_key": "secret"})
    with pytest.raises(CredentialError):
        vault().unseal("target-a", "bark", ciphertext)
    with pytest.raises(CredentialError):
        keyring.unseal("target-b", "bark", ciphertext)
    with pytest.raises(CredentialError):
        keyring.unseal("target-a", "telegram", ciphertext)
    with pytest.raises(CredentialError):
        keyring.unseal("target-a", "bark", "tampered" + ciphertext)
    assert "secret" not in ciphertext


def test_key_file_private_persistent_and_never_overwritten(tmp_path):
    with pytest.raises(CredentialError):
        CredentialVault.open(tmp_path)
    keyring = CredentialVault.open(tmp_path, create=True)
    path = tmp_path / "credentials.key"
    assert path.stat().st_mode & 0o777 == 0o600
    sealed = keyring.seal("a", "bark", {"device_key": "synthetic"})
    assert CredentialVault.open(tmp_path).unseal("a", "bark", sealed)["device_key"] == "synthetic"
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        CredentialVault.open(tmp_path, create=True)
    assert path.read_bytes() == original
    os.chmod(path, 0o644)
    with pytest.raises(CredentialError):
        CredentialVault.open(tmp_path)
    path.unlink()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(CredentialError):
        CredentialVault.open(tmp_path)


@pytest.mark.parametrize(
    "kind,change",
    [
        ("telegram", {"bot_token": "secret/unsafe"}),
        ("telegram", {"chat_id": "secret\nvalue"}),
        ("telegram", {"message_thread_id": 0}),
        ("telegram", {"base_url": "file:///secret"}),
        ("telegram", {"base_url": "https://example.invalid/?key=secret"}),
        ("bark", {"device_key": ""}),
        ("bark", {"base_url": "https://user:secret@example.invalid"}),
        ("webhook", {"url": "ftp://example.invalid/secret"}),
        ("webhook", {"url": "https://example.invalid/#secret"}),
        ("webhook", {"url": "https://example.invalid:70000/secret"}),
        ("webhook", {"url": "https://example.invalid/\nsecret"}),
        ("webhook", {"headers": {"Authorization": "secret\r\ninjected"}}),
        ("webhook", {"headers": {"Host": "secret"}}),
        ("webhook", {"headers": {"Proxy-Authorization": "secret"}}),
        ("webhook", {"headers": {"Cookie": "secret"}}),
        ("webhook", {"headers": {"X-Token": "secret", "x-token": "secret"}}),
        ("smtp", {"to_address": "a@example.invalid,b@example.invalid"}),
        ("smtp", {"from_address": "sender@example.invalid\nsecret"}),
        ("smtp", {"host": "smtp://secret@example.invalid"}),
        ("smtp", {"port": 0}),
        ("smtp", {"username": ""}),
        ("smtp", {"security": "plain"}),
        ("smtp", {"unknown-secret-field": "secret"}),
        ("bark", {"summary_limit": -1}),
        ("bark", {"include_summary": "secret"}),
    ],
)
def test_invalid_config_rejected_without_echoing_input(kind, change):
    with pytest.raises(ValueError) as error:
        validate_config(kind, {**CONFIGS[kind], **change})
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("kind", list(CONFIGS))
def test_exact_endpoint_duplicate_warning_does_not_merge_targets(core, kind):
    service = Configuration(core.engine, vault())
    a = service.create_target("a", kind=kind, config=CONFIGS[kind])
    b = service.create_target("b", kind=kind, config={**CONFIGS[kind], "include_summary": True})
    assert a != b and service.duplicate_targets(a) == [b]
    change = {
        "telegram": {"chat_id": "-100999"},
        "bark": {"device_key": "different"},
        "webhook": {"headers": {"Authorization": "different"}},
        "smtp": {"to_address": "different@example.invalid"},
    }[kind]
    service.update_target(b, name="different", config=change)
    assert service.duplicate_targets(a) == []


def test_channel_schemas_have_secret_markers_and_require_validated_vault(core):
    schemas = channel_schemas()
    assert set(schemas) == {"telegram", "bark", "smtp", "webhook"}
    for schema in schemas.values():
        assert schema["additionalProperties"] is False
        assert any(field.get("writeOnly") for field in schema["properties"].values())
    with pytest.raises(ValueError, match="vault required"):
        core.config.create_target("a", kind="bark", config=CONFIGS["bark"])
    with pytest.raises(ValueError, match="Unsupported"):
        validate_config("unknown", {})


def test_key_and_database_survive_reopen_without_changing_queued_credentials(core):
    from seekbell.config import Settings
    from seekbell.db.runtime import create_database_engine, migrate

    keyring = CredentialVault.open(core.data_dir, create=True)
    service = Configuration(core.engine, keyring)
    key = service.create_target("persistent", kind="telegram", config=CONFIGS["telegram"])
    service.update_task(core.task, "rule", Rule(), [key], at=2)
    core.queued()
    original = core.one(Outbox).target_snapshot
    core.engine.dispose()
    reopened = create_database_engine(Settings(data_dir=core.data_dir))
    try:
        migrate(reopened)
        restored = CredentialVault.open(core.data_dir)
        view = Configuration(reopened, restored).get_target(key)
        assert view["revision"] == 1 and "bot_token" not in view["config"]
        with Session(reopened) as session:
            snapshot = session.query(Outbox).one().target_snapshot
        assert snapshot == original
        values = restored.unseal(key, "telegram", snapshot["config_ciphertext"])
        assert values["bot_token"] == CONFIGS["telegram"]["bot_token"]
    finally:
        reopened.dispose()
