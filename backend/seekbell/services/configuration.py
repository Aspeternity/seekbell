from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from seekbell.db.models import (
    NotificationTarget,
    Outbox,
    OutboxContribution,
    RuleHit,
    Source,
    SourceState,
    Task,
    TaskVersion,
    Website,
)
from seekbell.db.transactions import write_session
from seekbell.domain.rules import Rule
from seekbell.notifiers.configs import public_config, validate_config
from seekbell.notifiers.credentials import CredentialVault
from seekbell.sites.nodeseek import BUILTIN_ADAPTERS


def identifier() -> str:
    return str(uuid4())


def target_snapshot(target: NotificationTarget) -> dict:
    return {
        "id": target.id,
        "name": target.name,
        "kind": target.kind,
        "revision": target.revision,
        **({"config_ciphertext": target.config_ciphertext} if target.config_ciphertext else {}),
    }


class ConfigurationConflict(ValueError):
    pass


class Configuration:
    def __init__(self, engine: Engine, vault: CredentialVault | None = None):
        self.engine = engine
        self.vault = vault

    @staticmethod
    def _name(name: str) -> str:
        name = name.strip()
        if not name or len(name) > 200:
            raise ValueError("Name must contain 1 to 200 characters")
        return name

    @staticmethod
    def _targets(session, target_ids) -> list[str]:
        target_ids = list(dict.fromkeys(target_ids))
        if not target_ids or len(target_ids) > 64:
            raise ValueError("Select between 1 and 64 configured targets")
        if any(session.get(NotificationTarget, key) is None for key in target_ids):
            raise ValueError("Unknown notification target")
        return target_ids

    def _vault(self) -> CredentialVault:
        if self.vault is None:
            raise ValueError("Credential vault required for configured targets")
        return self.vault

    def create_target(
        self, name: str, *, kind: str = "mock", enabled: bool = True, config: dict | None = None
    ) -> str:
        key = identifier()
        ciphertext = None
        if kind == "mock":
            if config:
                raise ValueError("Mock targets cannot store configuration")
        else:
            values = validate_config(kind, config or {})
            ciphertext = self._vault().seal(key, kind, values)
        with write_session(self.engine) as session:
            session.add(
                NotificationTarget(
                    id=key,
                    name=self._name(name),
                    kind=kind,
                    revision=1,
                    enabled=enabled,
                    config_ciphertext=ciphertext,
                )
            )
        return key

    def update_target(
        self, key: str, *, name: str, config: dict, expected_revision: int | None = None
    ) -> int:
        with write_session(self.engine) as session:
            target = session.get(NotificationTarget, key)
            if target is None or target.kind == "mock":
                raise ValueError("Unknown configured target")
            if expected_revision is not None and target.revision != expected_revision:
                raise ConfigurationConflict
            vault = self._vault()
            current = vault.unseal(key, target.kind, target.config_ciphertext)
            values = validate_config(target.kind, {**current, **config})
            target.config_ciphertext = vault.seal(key, target.kind, values)
            target.name = self._name(name)
            target.revision += 1
            # Already queued notifications retain their original encrypted snapshot.
            return target.revision

    def get_target(self, key: str) -> dict:
        """Safe presentation contract: secret values are never returned."""
        with Session(self.engine) as session:
            target = session.get(NotificationTarget, key)
            if target is None:
                raise ValueError("Unknown target")
            return self._target_view(target)

    def _target_view(self, target: NotificationTarget) -> dict:
        config, configured = {}, []
        if target.kind != "mock":
            values = self._vault().unseal(target.id, target.kind, target.config_ciphertext)
            config, configured = public_config(target.kind, values)
        return {
            "id": target.id,
            "kind": target.kind,
            "name": target.name,
            "revision": target.revision,
            "enabled": target.enabled,
            "config": config,
            "configured_secrets": configured,
        }

    def list_targets(self) -> list[dict]:
        with Session(self.engine) as session:
            return [
                self._target_view(target)
                for target in session.scalars(
                    select(NotificationTarget).order_by(
                        NotificationTarget.name, NotificationTarget.id
                    )
                )
            ]

    def duplicate_targets(self, key: str) -> list[str]:
        """Warn only for exactly recognizable endpoints; never merge identities."""
        fields = {
            "telegram": ("base_url", "bot_token", "chat_id", "message_thread_id"),
            "bark": ("base_url", "device_key"),
            "smtp": ("host", "port", "security", "username", "from_address", "to_address"),
            "webhook": ("url", "headers"),
        }
        with Session(self.engine) as session:
            target = session.get(NotificationTarget, key)
            if target is None or target.kind not in fields:
                return []
            vault = self._vault()
            original = vault.unseal(key, target.kind, target.config_ciphertext)
            duplicates = []
            for other in session.scalars(
                select(NotificationTarget).where(
                    NotificationTarget.kind == target.kind, NotificationTarget.id != key
                )
            ):
                values = vault.unseal(other.id, other.kind, other.config_ciphertext)
                if all(values[field] == original[field] for field in fields[target.kind]):
                    duplicates.append(other.id)
            return sorted(duplicates)

    def create_task(
        self,
        name: str,
        rule: Rule,
        target_ids,
        *,
        at: float,
        website_id: str = "nodeseek",
        enabled: bool = True,
    ) -> str:
        if website_id not in BUILTIN_ADAPTERS:
            raise ValueError("Unsupported website")
        key = identifier()
        with write_session(self.engine) as session:
            targets = self._targets(session, target_ids)
            session.add(
                Task(
                    id=key,
                    website_id=website_id,
                    current_version=1,
                    enabled=enabled,
                    created_at=at,
                )
            )
            session.flush()
            session.add(
                TaskVersion(
                    task_id=key,
                    version=1,
                    name=self._name(name),
                    rule=rule.model_dump(mode="json"),
                    target_ids=targets,
                    created_at=at,
                )
            )
        return key

    def update_task(
        self,
        key: str,
        name: str,
        rule: Rule,
        target_ids,
        *,
        at: float,
        expected_version: int | None = None,
    ) -> int:
        with write_session(self.engine) as session:
            task = session.get(Task, key)
            if task is None or task.deleted_at is not None:
                raise ValueError("Unknown active task")
            if expected_version is not None and task.current_version != expected_version:
                raise ConfigurationConflict
            targets = self._targets(session, target_ids)
            task.current_version += 1
            version = task.current_version
            session.add(
                TaskVersion(
                    task_id=key,
                    version=version,
                    name=self._name(name),
                    rule=rule.model_dump(mode="json"),
                    target_ids=targets,
                    created_at=at,
                )
            )
            # Existing hits and outbox snapshots keep their original versions.
        return version

    @staticmethod
    def _cancel_contributions(session, task_id: str) -> None:
        hit_ids = select(RuleHit.id).where(RuleHit.task_id == task_id)
        contributions = session.scalars(
            select(OutboxContribution)
            .join(Outbox)
            .where(
                Outbox.status.in_(("pending", "retry", "leased")),
                OutboxContribution.hit_id.in_(hit_ids),
                OutboxContribution.active.is_(True),
            )
        ).all()
        event_ids = {item.event_id for item in contributions}
        for item in contributions:
            item.active = False
        session.flush()
        for event_id in event_ids:
            event = session.get(Outbox, event_id)
            active = session.scalar(
                select(OutboxContribution.hit_id)
                .where(OutboxContribution.event_id == event_id, OutboxContribution.active.is_(True))
                .limit(1)
            )
            if active is None and event.status in ("pending", "retry", "leased"):
                event.cancel_requested = True
                if event.status != "leased":
                    event.status = "cancelled"
                    event.last_error_code = "task_contributions_removed"

    def set_task_enabled(self, key: str, enabled: bool) -> None:
        with write_session(self.engine) as session:
            task = session.get(Task, key)
            if task is None or task.deleted_at is not None:
                raise ValueError("Unknown active task")
            task.enabled = enabled
            if not enabled:
                self._cancel_contributions(session, key)

    def delete_task(self, key: str, *, at: float) -> None:
        with write_session(self.engine) as session:
            task = session.get(Task, key)
            if task is None:
                raise ValueError("Unknown task")
            task.deleted_at = at
            task.enabled = False
            self._cancel_contributions(session, key)

    def set_target_enabled(self, key: str, enabled: bool) -> None:
        with write_session(self.engine) as session:
            target = session.get(NotificationTarget, key)
            if target is None:
                raise ValueError("Unknown target")
            if target.enabled != enabled:
                target.revision += 1
            target.enabled = enabled
            if not enabled:
                for item in session.scalars(
                    select(Outbox).where(
                        Outbox.target_id == key, Outbox.status.in_(("pending", "retry", "leased"))
                    )
                ):
                    item.cancel_requested = True
                    if item.status != "leased":
                        item.status = "cancelled"
                        item.last_error_code = "target_disabled"
            # Re-enabling never uncancels old messages.

    def set_source_enabled(self, key: str, enabled: bool, *, at: float) -> None:
        with write_session(self.engine) as session:
            source = session.get(Source, key)
            state = session.get(SourceState, key)
            if source is None or state is None:
                raise ValueError("Unknown source")
            if source.enabled and not enabled:
                state.needs_baseline = True
            source.enabled = enabled
            if enabled:
                state.next_attempt_at = max(at, state.next_attempt_at)

    def set_website_enabled(self, key: str, enabled: bool, *, at: float) -> None:
        with write_session(self.engine) as session:
            website = session.get(Website, key)
            if website is None:
                raise ValueError("Unknown website")
            was_enabled = website.enabled
            website.enabled = enabled
            for source in session.scalars(select(Source).where(Source.website_id == key)):
                state = session.get(SourceState, source.id)
                if was_enabled and not enabled:
                    state.needs_baseline = True
                if enabled:
                    state.next_attempt_at = max(at, state.next_attempt_at)
