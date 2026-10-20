from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Installation(Base):
    __tablename__ = "installation"
    __table_args__ = (CheckConstraint("id = 1", name="ck_installation_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


class Website(Base):
    __tablename__ = "websites"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (CheckConstraint("interval_seconds >= 1", name="ck_source_interval"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    website_id: Mapped[str] = mapped_column(ForeignKey("websites.id"))
    url: Mapped[str] = mapped_column(String(2048))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=10)


class SourceState(Base):
    __tablename__ = "source_states"
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), primary_key=True)
    initialized: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_baseline: Mapped[bool] = mapped_column(Boolean, default=False)
    last_attempt_at: Mapped[float | None] = mapped_column(Float)
    last_success_at: Mapped[float | None] = mapped_column(Float)
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    failures: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[float] = mapped_column(Float, default=0)
    previous_window: Mapped[list] = mapped_column(JSON, default=list)
    window_count: Mapped[int] = mapped_column(Integer, default=0)
    possible_gap: Mapped[bool] = mapped_column(Boolean, default=False)
    last_gap_at: Mapped[float | None] = mapped_column(Float)


class SourceRun(Base):
    __tablename__ = "source_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    at: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32))
    code: Mapped[str | None] = mapped_column(String(80))
    raw_count: Mapped[int] = mapped_column(Integer, default=0)
    new_posts: Mapped[int] = mapped_column(Integer, default=0)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    queued_count: Mapped[int] = mapped_column(Integer, default=0)
    insufficient_count: Mapped[int] = mapped_column(Integer, default=0)
    possible_gap: Mapped[bool] = mapped_column(Boolean, default=False)
    diagnostics: Mapped[list] = mapped_column(JSON, default=list)


class SourceProbe(Base):
    """Last explicit connection check; independent from collection/baseline history."""

    __tablename__ = "source_probes"
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), primary_key=True)
    started_at: Mapped[float] = mapped_column(Float)
    finished_at: Mapped[float | None] = mapped_column(Float)
    next_attempt_at: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32))
    code: Mapped[str | None] = mapped_column(String(80))
    item_count: Mapped[int | None] = mapped_column(Integer)


class NotificationTarget(Base):
    __tablename__ = "notification_targets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(32))
    deleted_at: Mapped[float | None] = mapped_column(Float)
    config_ciphertext: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    website_id: Mapped[str] = mapped_column(ForeignKey("websites.id"), index=True)
    current_version: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted_at: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[float] = mapped_column(Float)


class TaskVersion(Base):
    __tablename__ = "task_versions"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(160), default="", server_default="")
    rule: Mapped[dict] = mapped_column(JSON)
    target_ids: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float)


class SeenPost(Base):
    """Minimal identity ledger; independent of retained readable post/history content."""

    __tablename__ = "seen_posts"
    website_id: Mapped[str] = mapped_column(ForeignKey("websites.id"), primary_key=True)
    external_post_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    first_seen_at: Mapped[float] = mapped_column(Float)


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["website_id", "external_post_id"],
            ["seen_posts.website_id", "seen_posts.external_post_id"],
        ),
    )
    website_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    external_post_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(500))
    category: Mapped[str | None] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(2048))
    published_at: Mapped[float | None] = mapped_column(Float)
    first_seen_at: Mapped[float] = mapped_column(Float, index=True)
    baseline: Mapped[bool | None] = mapped_column(Boolean)


class SourceItem(Base):
    __tablename__ = "source_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["website_id", "external_post_id"],
            ["seen_posts.website_id", "seen_posts.external_post_id"],
        ),
    )
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), primary_key=True)
    source_item_id: Mapped[str] = mapped_column(Text, primary_key=True)
    website_id: Mapped[str] = mapped_column(String(80))
    external_post_id: Mapped[str] = mapped_column(String(128))
    first_seen_at: Mapped[float] = mapped_column(Float)


class RuleHit(Base):
    __tablename__ = "rule_hits"
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_id", "task_version"], ["task_versions.task_id", "task_versions.version"]
        ),
        ForeignKeyConstraint(
            ["website_id", "external_post_id"],
            ["seen_posts.website_id", "seen_posts.external_post_id"],
        ),
        UniqueConstraint(
            "task_id", "task_version", "website_id", "external_post_id", name="uq_task_hit"
        ),
        Index("ix_rule_hits_post", "website_id", "external_post_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), index=True)
    task_version: Mapped[int] = mapped_column(Integer)
    website_id: Mapped[str] = mapped_column(String(80))
    external_post_id: Mapped[str] = mapped_column(String(128))
    reason: Mapped[dict] = mapped_column(JSON)
    matched_at: Mapped[float] = mapped_column(Float)


class Outbox(Base):
    __tablename__ = "outbox"
    __table_args__ = (
        ForeignKeyConstraint(
            ["website_id", "external_post_id"],
            ["seen_posts.website_id", "seen_posts.external_post_id"],
        ),
        UniqueConstraint(
            "website_id", "external_post_id", "target_id", name="uq_automatic_delivery"
        ),
        CheckConstraint(
            "status IN ('pending','retry','leased','sent','failed','cancelled')",
            name="ck_outbox_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_outbox_attempt_count"),
        CheckConstraint(
            "(status = 'leased' AND lease_token IS NOT NULL AND lease_until IS NOT NULL) OR "
            "(status != 'leased' AND lease_token IS NULL AND lease_until IS NULL)",
            name="ck_outbox_lease",
        ),
        Index("ix_outbox_available", "status", "available_at"),
        Index("ix_outbox_created_at", "created_at", "id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    website_id: Mapped[str] = mapped_column(String(80))
    external_post_id: Mapped[str] = mapped_column(String(128))
    target_id: Mapped[str] = mapped_column(ForeignKey("notification_targets.id"))
    target_snapshot: Mapped[dict] = mapped_column(JSON)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[float] = mapped_column(Float)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[float | None] = mapped_column(Float)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    uncertain: Mapped[bool] = mapped_column(Boolean, default=False)
    last_result: Mapped[str | None] = mapped_column(String(32))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[float] = mapped_column(Float)


class OutboxContribution(Base):
    __tablename__ = "outbox_contributions"
    event_id: Mapped[str] = mapped_column(ForeignKey("outbox.id"), primary_key=True)
    hit_id: Mapped[str] = mapped_column(ForeignKey("rule_hits.id"), primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempts"
    __table_args__ = (UniqueConstraint("event_id", "sequence", name="uq_delivery_attempt"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("outbox.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    lease_token: Mapped[str] = mapped_column(String(36), unique=True)
    started_at: Mapped[float] = mapped_column(Float)
    finished_at: Mapped[float | None] = mapped_column(Float)
    result: Mapped[str] = mapped_column(String(32), default="in_progress")
    error_code: Mapped[str | None] = mapped_column(String(80))
    late_result: Mapped[str | None] = mapped_column(String(32))
    late_finished_at: Mapped[float | None] = mapped_column(Float)


class DeliveredPost(Base):
    """A receipt tombstone survives pruning delivery and post history."""

    __tablename__ = "delivered_posts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["website_id", "external_post_id"],
            ["seen_posts.website_id", "seen_posts.external_post_id"],
        ),
    )
    website_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    external_post_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    target_id: Mapped[str] = mapped_column(ForeignKey("notification_targets.id"), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(36))
    delivered_at: Mapped[float] = mapped_column(Float)


class TargetTestAttempt(Base):
    __tablename__ = "target_test_attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    target_id: Mapped[str] = mapped_column(ForeignKey("notification_targets.id"), index=True)
    target_snapshot: Mapped[dict] = mapped_column(JSON)
    started_at: Mapped[float] = mapped_column(Float)
    finished_at: Mapped[float | None] = mapped_column(Float)
    result: Mapped[str] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(80))


class Administrator(Base):
    __tablename__ = "administrators"
    __table_args__ = (CheckConstraint("id = 1", name="ck_administrator_singleton"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(32))
    password_hash: Mapped[str] = mapped_column(String(256))


class LoginSession(Base):
    __tablename__ = "login_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    csrf: Mapped[str] = mapped_column(String(80))
    expires_at: Mapped[float] = mapped_column(Float)


class WebsiteInstallation(Base):
    __tablename__ = "website_installations"
    website_id: Mapped[str] = mapped_column(ForeignKey("websites.id"), primary_key=True)


class WorkspacePreferences(Base):
    __tablename__ = "workspace_preferences"
    __table_args__ = (CheckConstraint("id = 1", name="ck_workspace_singleton"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(24))
    description: Mapped[str] = mapped_column(String(40))


class TaskEvaluation(Base):
    """Immutable outcome for a task version when a post is first discovered."""

    __tablename__ = "task_evaluations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_id", "task_version"], ["task_versions.task_id", "task_versions.version"]
        ),
        ForeignKeyConstraint(
            ["website_id", "external_post_id"],
            ["seen_posts.website_id", "seen_posts.external_post_id"],
        ),
        CheckConstraint(
            "status IN ('match','no_match','insufficient_data')", name="ck_evaluation_status"
        ),
        Index("ix_evaluations_post_status", "website_id", "external_post_id", "status"),
    )
    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    website_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    external_post_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    status: Mapped[str] = mapped_column(String(32))
    result: Mapped[dict] = mapped_column(JSON)
    evaluated_at: Mapped[float] = mapped_column(Float)


class ManualDelivery(Base):
    __tablename__ = "manual_deliveries"
    __table_args__ = (
        Index("ix_manual_started", "started_at", "id"),
        Index("ix_manual_source", "source_event_id"),
        Index("ix_manual_target", "target_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_event_id: Mapped[str] = mapped_column(String(36))
    target_id: Mapped[str] = mapped_column(ForeignKey("notification_targets.id"))
    target_snapshot: Mapped[dict] = mapped_column(JSON)
    payload: Mapped[dict] = mapped_column(JSON)
    started_at: Mapped[float] = mapped_column(Float)
    finished_at: Mapped[float | None] = mapped_column(Float)
    result: Mapped[str] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(80))
