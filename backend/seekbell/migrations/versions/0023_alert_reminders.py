"""Allow repeated reminders for an unresolved fault and a 1-minute delay for new installs."""

import sqlalchemy as sa
from alembic import op

revision = "0023_alert_reminders"
down_revision = "0022_content_limit"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "alert_settings",
        sa.Column("remind_seconds", sa.Integer(), nullable=False, server_default="0"),
    )
    # Rebuilding system_events drops the old table, which foreign keys (on, and fixed for the
    # migration transaction) refuse while alert deliveries point at it. Set them aside meanwhile.
    op.execute("CREATE TEMP TABLE alert_deliveries_kept AS SELECT * FROM alert_deliveries")
    op.execute("DELETE FROM alert_deliveries")
    with op.batch_alter_table("system_events") as batch:
        batch.drop_constraint("uq_system_transition", type_="unique")
        batch.drop_constraint("ck_system_phase", type_="check")
        batch.create_check_constraint("ck_system_phase", "phase IN ('fault','recovery','reminder')")
    op.execute("INSERT INTO alert_deliveries SELECT * FROM alert_deliveries_kept")
    op.execute("DROP TABLE alert_deliveries_kept")
    op.create_index(
        "uq_system_transition",
        "system_events",
        ["component", "generation", "phase"],
        unique=True,
        sqlite_where=sa.text("phase != 'reminder'"),
    )
    # A fresh installation (no administrator yet, alerts never saved) starts with the
    # 1-minute delay; existing installations keep the delay they chose.
    op.execute(
        "UPDATE alert_settings SET delay_seconds = 60 "
        "WHERE revision = 1 AND NOT EXISTS (SELECT 1 FROM administrators)"
    )


def downgrade():
    raise RuntimeError("Restore the matching pre-upgrade backup to roll back this migration")
