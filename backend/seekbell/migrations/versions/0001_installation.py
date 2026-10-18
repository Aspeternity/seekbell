"""Create persistent singleton installation marker (not an administrator)."""

import sqlalchemy as sa
from alembic import op

revision = "0001_installation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    installation = op.create_table(
        "installation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.CheckConstraint("id = 1", name="ck_installation_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(installation, [{"id": 1}])


def downgrade() -> None:
    op.drop_table("installation")
