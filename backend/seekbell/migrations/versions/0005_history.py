"""Persist immutable task decisions; preserve legacy history without re-evaluation."""

import sqlalchemy as sa
from alembic import op

revision = "0005_history"
down_revision = "0004_management"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("posts", sa.Column("baseline", sa.Boolean(), nullable=True))
    op.create_table(
        "task_evaluations",
        sa.Column("task_id", sa.String(36), primary_key=True),
        sa.Column("task_version", sa.Integer(), primary_key=True),
        sa.Column("website_id", sa.String(80), primary_key=True),
        sa.Column("external_post_id", sa.String(128), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("evaluated_at", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id", "task_version"], ["task_versions.task_id", "task_versions.version"]
        ),
        sa.ForeignKeyConstraint(
            ["website_id", "external_post_id"],
            ["seen_posts.website_id", "seen_posts.external_post_id"],
        ),
        sa.CheckConstraint(
            "status IN ('match','no_match','insufficient_data')", name="ck_evaluation_status"
        ),
    )
    op.create_index(
        "ix_evaluations_post_status",
        "task_evaluations",
        ["website_id", "external_post_id", "status"],
    )
    op.create_index("ix_rule_hits_post", "rule_hits", ["website_id", "external_post_id"])
    op.create_index("ix_outbox_created_at", "outbox", ["created_at", "id"])


def downgrade():
    op.drop_index("ix_outbox_created_at", table_name="outbox")
    op.drop_index("ix_rule_hits_post", table_name="rule_hits")
    op.drop_table("task_evaluations")
    op.drop_column("posts", "baseline")
