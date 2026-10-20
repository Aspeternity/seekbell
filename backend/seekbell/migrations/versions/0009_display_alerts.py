"""Display preference and independent, durable system incident notifications."""

import sqlalchemy as sa
from alembic import op

revision = "0009_display_alerts"
down_revision = "0008_retention"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "workspace_preferences",
        sa.Column("timezone", sa.String(80), nullable=False, server_default="Asia/Shanghai"),
    )
    op.add_column(
        "workspace_preferences",
        sa.Column("display_revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "alert_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("target_ids", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_alert_settings_singleton"),
    )
    op.execute("INSERT INTO alert_settings(id,enabled,target_ids,revision) VALUES(1,0,'[]',1)")
    op.create_table(
        "system_states",
        sa.Column("component", sa.String(120), primary_key=True),
        sa.Column("fault", sa.Boolean(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("code", sa.String(80), nullable=True),
        sa.Column("updated_at", sa.Float(), nullable=False),
    )
    op.create_table(
        "system_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "component", sa.String(120), sa.ForeignKey("system_states.component"), nullable=False
        ),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("code", sa.String(80), nullable=True),
        sa.Column("at", sa.Float(), nullable=False),
        sa.UniqueConstraint("component", "generation", "phase", name="uq_system_transition"),
        sa.CheckConstraint("phase IN ('fault','recovery')", name="ck_system_phase"),
    )
    op.create_index("ix_system_events_at", "system_events", ["at", "id"])
    op.create_table(
        "alert_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_id", sa.String(36), sa.ForeignKey("system_events.id"), nullable=False),
        sa.Column(
            "target_id", sa.String(36), sa.ForeignKey("notification_targets.id"), nullable=False
        ),
        sa.Column("target_snapshot", sa.JSON(), nullable=False),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("started_at", sa.Float(), nullable=True),
        sa.Column("finished_at", sa.Float(), nullable=True),
        sa.UniqueConstraint("event_id", "target_id", name="uq_alert_target"),
        sa.CheckConstraint(
            "result IN ('pending','unknown','success','transient_error',"
            "'permanent_error','cancelled')",
            name="ck_alert_result",
        ),
    )
    op.create_index("ix_alert_deliveries_event", "alert_deliveries", ["event_id"])
    op.create_index("ix_alert_deliveries_pending", "alert_deliveries", ["result", "id"])


def downgrade():
    op.drop_table("alert_deliveries")
    op.drop_table("system_events")
    op.drop_table("system_states")
    op.drop_table("alert_settings")
    op.drop_column("workspace_preferences", "display_revision")
    op.drop_column("workspace_preferences", "timezone")
