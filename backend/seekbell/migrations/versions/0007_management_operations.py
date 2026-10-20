"""Keep deleted target identities and independent source connection checks."""

import sqlalchemy as sa
from alembic import op

revision = "0007_management_operations"
down_revision = "0006_manual_delivery"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("notification_targets", sa.Column("deleted_at", sa.Float(), nullable=True))
    op.create_table(
        "source_probes",
        sa.Column("source_id", sa.String(80), sa.ForeignKey("sources.id"), primary_key=True),
        sa.Column("started_at", sa.Float(), nullable=False),
        sa.Column("finished_at", sa.Float(), nullable=True),
        sa.Column("next_attempt_at", sa.Float(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("code", sa.String(80), nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_table("source_probes")
    op.drop_column("notification_targets", "deleted_at")
