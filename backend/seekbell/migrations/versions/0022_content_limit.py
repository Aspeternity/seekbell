"""Add the optional content limit and drop the unread last-cleanup counts."""

import sqlalchemy as sa
from alembic import op

revision = "0022_content_limit"
down_revision = "0021_backup_schedule"
branch_labels = None
depends_on = None


def upgrade():
    # No limit by default: existing installations keep exactly what they kept before.
    with op.batch_alter_table("retention_policy") as batch:
        batch.add_column(sa.Column("max_posts", sa.Integer(), nullable=True))
        batch.drop_column("last_run_at")
        batch.drop_column("last_counts")
        batch.create_check_constraint(
            "ck_retention_max_posts", "max_posts IS NULL OR max_posts BETWEEN 1 AND 1000000"
        )


def downgrade():
    raise RuntimeError("Restore the matching pre-upgrade backup to roll back this migration")
