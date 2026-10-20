"""Authentication, explicit website installations and workspace identity."""

import sqlalchemy as sa
from alembic import op

revision = "0004_management"
down_revision = "0003_notifications"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "administrators",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(32), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_administrator_singleton"),
    )
    op.create_table(
        "login_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("csrf", sa.String(80), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
    )
    op.create_table(
        "website_installations",
        sa.Column("website_id", sa.String(80), sa.ForeignKey("websites.id"), primary_key=True),
    )
    # Identity rows remain available to historical ledgers. Only this table
    # represents user-installed websites. Preserve all existing deployments.
    if op.get_context().config.attributes.get("upgrading_existing", True):
        op.execute("INSERT INTO website_installations (website_id) SELECT id FROM websites")
    op.create_table(
        "workspace_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(24), nullable=False),
        sa.Column("description", sa.String(40), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_workspace_singleton"),
    )
    op.execute("INSERT INTO workspace_preferences VALUES (1, '个人工作空间', 'Administrator')")
    op.add_column(
        "task_versions", sa.Column("description", sa.String(160), nullable=False, server_default="")
    )


def downgrade():
    op.drop_column("task_versions", "description")
    for table in (
        "workspace_preferences",
        "website_installations",
        "login_sessions",
        "administrators",
    ):
        op.drop_table(table)
