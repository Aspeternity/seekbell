"""Singleton administrator and persistent server-side sessions.

Revision ID: 0004_authentication
Revises: 0003_notifications
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_authentication"
down_revision = "0003_notifications"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "administrators",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_administrator_singleton"),
    )
    op.create_table(
        "browser_sessions",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column(
            "administrator_id", sa.Integer(), sa.ForeignKey("administrators.id"), nullable=True
        ),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("secure", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "auth_throttle",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("window_started", sa.Float(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_auth_throttle_singleton"),
    )


def downgrade():
    op.drop_table("auth_throttle")
    op.drop_table("browser_sessions")
    op.drop_table("administrators")
