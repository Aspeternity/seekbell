"""Independent overview layout and hotlist selection preferences."""

import sqlalchemy as sa
from alembic import op

revision = "0010_overview_preferences"
down_revision = "0009_display_alerts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "overview_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("modules", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.String(80), nullable=True),
        sa.Column("periods", sa.JSON(), nullable=False),
        sa.Column("selection_revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_overview_singleton"),
    )
    table = sa.table(
        "overview_preferences",
        sa.column("id", sa.Integer()),
        sa.column("modules", sa.JSON()),
        sa.column("revision", sa.Integer()),
        sa.column("website_id", sa.String()),
        sa.column("periods", sa.JSON()),
        sa.column("selection_revision", sa.Integer()),
    )
    op.bulk_insert(
        table,
        [
            {
                "id": 1,
                "modules": [
                    {"id": key, "visible": True} for key in ("tasks", "matches", "hotlist")
                ],
                "revision": 1,
                "website_id": None,
                "periods": {},
                "selection_revision": 1,
            }
        ],
    )


def downgrade():
    op.drop_table("overview_preferences")
