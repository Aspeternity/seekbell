from uuid import uuid4

from sqlalchemy import Engine, select

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
from seekbell.sites.nodeseek import BUILTIN_ADAPTERS


def identifier() -> str:
    return str(uuid4())


def target_snapshot(target: NotificationTarget) -> dict:
    # M1 has no credential/config column. Real encrypted channel configs belong to M2.
    return {
        "id": target.id,
        "name": target.name,
        "kind": target.kind,
        "revision": target.revision,
    }


class Configuration:
    def __init__(self, engine: Engine):
        self.engine = engine

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

    def create_target(self, name: str, *, kind: str = "mock", enabled: bool = True) -> str:
        if kind != "mock":
            raise ValueError("Only explicitly injected mock transport is implemented in M1")
        key = identifier()
        with write_session(self.engine) as session:
            session.add(
                NotificationTarget(
                    id=key,
                    name=self._name(name),
                    kind=kind,
                    revision=1,
                    enabled=enabled,
                )
            )
        return key

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

    def update_task(self, key: str, name: str, rule: Rule, target_ids, *, at: float) -> int:
        with write_session(self.engine) as session:
            task = session.get(Task, key)
            if task is None or task.deleted_at is not None:
                raise ValueError("Unknown active task")
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
