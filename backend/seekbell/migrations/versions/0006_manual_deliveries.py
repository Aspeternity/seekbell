"""Independent explicit resend evidence.

Revision ID: 0006_manual_deliveries
Revises: 0005_source_revision
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_manual_deliveries"
down_revision = "0005_source_revision"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "manual_delivery_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("original_event_id", sa.String(36), sa.ForeignKey("outbox.id"), nullable=False),
        sa.Column(
            "target_id", sa.String(36), sa.ForeignKey("notification_targets.id"), nullable=False
        ),
        sa.Column("target_snapshot", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.Float(), nullable=False),
        sa.Column("finished_at", sa.Float(), nullable=True),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
    )
    op.create_index(
        "ix_manual_delivery_attempts_original_event_id",
        "manual_delivery_attempts",
        ["original_event_id"],
    )
    op.create_index(
        "ix_manual_delivery_attempts_target_id", "manual_delivery_attempts", ["target_id"]
    )


def downgrade():
    op.drop_table("manual_delivery_attempts")
