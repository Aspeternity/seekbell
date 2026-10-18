"""Encrypted notification target configuration.

Revision ID: 0003_notifications
Revises: 0002_core
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_notifications"
down_revision = "0002_core"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "target_test_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "target_id", sa.String(36), sa.ForeignKey("notification_targets.id"), nullable=False
        ),
        sa.Column("target_snapshot", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.Float(), nullable=False),
        sa.Column("finished_at", sa.Float(), nullable=True),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
    )
    op.create_index("ix_target_test_attempts_target_id", "target_test_attempts", ["target_id"])
    op.add_column("notification_targets", sa.Column("config_ciphertext", sa.Text(), nullable=True))


def downgrade():
    op.drop_table("target_test_attempts")
    op.drop_column("notification_targets", "config_ciphertext")
