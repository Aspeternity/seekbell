"""Add workspace concurrency and bounded backup operation metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0018_settings_maintenance"
down_revision = "0017_hotlist_settings"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "workspace_preferences",
        sa.Column("workspace_revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "backup_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("at", sa.Float(), nullable=False),
        sa.Column("archive_bytes", sa.Integer(), nullable=True),
        sa.Column("application_version", sa.String(80), nullable=False),
        sa.Column("database_revision", sa.String(80), nullable=False),
    )
    op.create_index("ix_backup_records_at", "backup_records", ["at"])


def downgrade():
    raise RuntimeError("Restore the matching pre-upgrade backup to roll back this migration")
