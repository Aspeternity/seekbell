"""Independent manual resends do not mutate the automatic delivery ledger."""

import sqlalchemy as sa
from alembic import op

revision = "0006_manual_delivery"
down_revision = "0005_history"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "manual_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        # Source ID is evidence, not an FK: readable automatic history may be pruned.
        sa.Column("source_event_id", sa.String(36), nullable=False),
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
    op.create_index("ix_manual_started", "manual_deliveries", ["started_at", "id"])
    op.create_index("ix_manual_source", "manual_deliveries", ["source_event_id"])
    op.create_index("ix_manual_target", "manual_deliveries", ["target_id"])


def downgrade():
    op.drop_table("manual_deliveries")
