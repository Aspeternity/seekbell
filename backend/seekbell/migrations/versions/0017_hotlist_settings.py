"""Store independent per-website hotlist refresh settings."""

import sqlalchemy as sa
from alembic import op

revision = "0017_hotlist_settings"
down_revision = "0016_site_categories"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "website_installations",
        sa.Column("hotlist_settings", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade():
    raise RuntimeError("Restore the matching pre-upgrade backup to roll back this migration")
