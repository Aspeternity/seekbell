"""Authenticated encryption; never reconstruct a lost key beside existing ciphertext."""

import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class CredentialError(ValueError):
    pass


class CredentialVault:
    def __init__(self, key: bytes):
        try:
            self._fernet = Fernet(key)
        except (ValueError, TypeError):
            raise CredentialError("Invalid credential key") from None

    @classmethod
    def open(cls, data_dir: Path, *, create: bool = False):
        path = data_dir / "credentials.key"
        if create:
            # Explicit initialization only; exclusive creation never overwrites a key.
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(Fernet.generate_key())
                stream.flush()
                os.fsync(stream.fileno())
        try:
            if path.is_symlink() or path.stat().st_mode & 0o077:
                raise CredentialError("Credential key must be a private regular file")
            if not path.is_file():
                raise CredentialError("Invalid credential key file")
            return cls(path.read_bytes())
        except OSError:
            raise CredentialError("Credential key unavailable; restore the original key") from None

    def seal(self, target_id: str, kind: str, values: dict) -> str:
        envelope = {"target_id": target_id, "kind": kind, "config": values}
        return self._fernet.encrypt(json.dumps(envelope, ensure_ascii=False).encode()).decode()

    def unseal(self, target_id: str, kind: str, ciphertext: str) -> dict:
        try:
            envelope = json.loads(self._fernet.decrypt(ciphertext.encode()))
            if envelope["target_id"] != target_id or envelope["kind"] != kind:
                raise ValueError
            if not isinstance(envelope["config"], dict):
                raise ValueError
            return envelope["config"]
        except (InvalidToken, ValueError, TypeError, KeyError, AttributeError):
            raise CredentialError("Credential decryption failed; check the original key") from None
