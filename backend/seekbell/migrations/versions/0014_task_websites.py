"""Version the full set of websites monitored by a task."""

import sqlalchemy as sa
from alembic import op

revision = "0014_task_websites"
down_revision = "0013_site_order"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "task_versions",
        sa.Column("website_ids", sa.JSON(), nullable=False, server_default="[]"),
    )
    # All old versions shared the task's original, immutable website.
    op.execute(
        "UPDATE task_versions SET website_ids = json_array(("
        "SELECT website_id FROM tasks WHERE tasks.id=task_versions.task_id))"
    )


def downgrade():
    raise RuntimeError("Restore the matching pre-upgrade backup to roll back this migration")
