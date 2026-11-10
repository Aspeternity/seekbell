"""Add the alert delay and per-session start time for remembered sign-ins."""

import sqlalchemy as sa
from alembic import op

revision = "0019_settings_reorganization"
down_revision = "0018_settings_maintenance"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "alert_settings",
        sa.Column("delay_seconds", sa.Integer(), nullable=False, server_default="0"),
    )
    # Existing sessions keep the fixed lifetime they were created with.
    op.add_column("login_sessions", sa.Column("created_at", sa.Float(), nullable=True))


def downgrade():
    raise RuntimeError("Restore the matching pre-upgrade backup to roll back this migration")
