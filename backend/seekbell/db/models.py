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
    __table_args__ = (Index("ix_source_runs_retention", "at"),)
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
    # Keep the original website as legacy provenance, never as current scope.
    origin_website_id: Mapped[str] = mapped_column(
        "website_id", ForeignKey("websites.id"), index=True
    )
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
    website_ids: Mapped[list] = mapped_column(JSON, server_default="[]")
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
    author_display_name: Mapped[str | None] = mapped_column(String(500))
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
        Index("ix_rule_hits_retention", "matched_at"),
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
        Index("ix_outbox_completed", "status", "completed_at"),
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
    completed_at: Mapped[float | None] = mapped_column(Float)


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
    __table_args__ = (Index("ix_target_test_attempts_retention", "finished_at"),)
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
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class WorkspacePreferences(Base):
    __tablename__ = "workspace_preferences"
    __table_args__ = (CheckConstraint("id = 1", name="ck_workspace_singleton"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(24))
    description: Mapped[str] = mapped_column(String(40))
    timezone: Mapped[str] = mapped_column(
        String(80), default="Asia/Shanghai", server_default="Asia/Shanghai"
    )
    display_revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


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
        Index("ix_task_evaluations_retention", "evaluated_at"),
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
        Index("ix_manual_deliveries_retention", "finished_at"),
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


class RetentionPolicy(Base):
    __tablename__ = "retention_policy"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_retention_singleton"),
        CheckConstraint("days BETWEEN 1 AND 365", name="ck_retention_days"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    days: Mapped[int] = mapped_column(Integer, default=30)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    next_run_at: Mapped[float] = mapped_column(Float, default=0)
    last_run_at: Mapped[float | None] = mapped_column(Float)
    last_counts: Mapped[dict] = mapped_column(JSON, default=dict)


class AlertSettings(Base):
    __tablename__ = "alert_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_alert_settings_singleton"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    target_ids: Mapped[list] = mapped_column(JSON, default=list)
    revision: Mapped[int] = mapped_column(Integer, default=1)


class SystemState(Base):
    """Transition anchor survives ordinary event-history retention."""

    __tablename__ = "system_states"
    component: Mapped[str] = mapped_column(String(120), primary_key=True)
    fault: Mapped[bool] = mapped_column(Boolean, default=False)
    generation: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str] = mapped_column(String(200))
    code: Mapped[str | None] = mapped_column(String(80))
    updated_at: Mapped[float] = mapped_column(Float)


class SystemEvent(Base):
    __tablename__ = "system_events"
    __table_args__ = (
        UniqueConstraint("component", "generation", "phase", name="uq_system_transition"),
        CheckConstraint("phase IN ('fault','recovery')", name="ck_system_phase"),
        Index("ix_system_events_at", "at", "id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    component: Mapped[str] = mapped_column(ForeignKey("system_states.component"))
    generation: Mapped[int] = mapped_column(Integer)
    phase: Mapped[str] = mapped_column(String(16))
    label: Mapped[str] = mapped_column(String(200))
    code: Mapped[str | None] = mapped_column(String(80))
    at: Mapped[float] = mapped_column(Float)


class AlertDelivery(Base):
    __tablename__ = "alert_deliveries"
    __table_args__ = (
        UniqueConstraint("event_id", "target_id", name="uq_alert_target"),
        CheckConstraint(
            "result IN ('pending','unknown','success','transient_error',"
            "'permanent_error','cancelled')",
            name="ck_alert_result",
        ),
        Index("ix_alert_deliveries_event", "event_id"),
        Index("ix_alert_deliveries_pending", "result", "id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("system_events.id"))
    target_id: Mapped[str] = mapped_column(ForeignKey("notification_targets.id"))
    target_snapshot: Mapped[dict] = mapped_column(JSON)
    result: Mapped[str] = mapped_column(String(32), default="pending")
    error_code: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[float | None] = mapped_column(Float)
    finished_at: Mapped[float | None] = mapped_column(Float)


class OverviewPreferences(Base):
    __tablename__ = "overview_preferences"
    __table_args__ = (CheckConstraint("id = 1", name="ck_overview_singleton"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    modules: Mapped[list] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(Integer)
    website_id: Mapped[str | None] = mapped_column(String(80))
    periods: Mapped[dict] = mapped_column(JSON)
    selection_revision: Mapped[int] = mapped_column(Integer)


class WebsiteRequestState(Base):
    __tablename__ = "website_request_states"
    website_id: Mapped[str] = mapped_column(ForeignKey("websites.id"), primary_key=True)
    next_request_at: Mapped[float] = mapped_column(Float, default=0)
    blocked_until: Mapped[float] = mapped_column(Float, default=0)
    retry_after_until: Mapped[float] = mapped_column(Float, default=0)
    next_manual_at: Mapped[float] = mapped_column(Float, default=0)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80))


class HotlistSnapshot(Base):
    __tablename__ = "hotlist_snapshots"
    website_id: Mapped[str] = mapped_column(ForeignKey("websites.id"), primary_key=True)
    provider_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    period: Mapped[str] = mapped_column(String(32), primary_key=True)
    fetched_at: Mapped[float] = mapped_column(Float)
    source_updated_at: Mapped[float | None] = mapped_column(Float)
    items: Mapped[list] = mapped_column(JSON)
