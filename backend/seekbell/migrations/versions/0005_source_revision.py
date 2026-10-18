"""Version source configuration separately from collection state.

Revision ID: 0005_source_revision
Revises: 0004_authentication
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_source_revision"
down_revision = "0004_authentication"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "sources", sa.Column("revision", sa.Integer(), nullable=False, server_default="1")
    )


def downgrade():
    op.drop_column("sources", "revision")
