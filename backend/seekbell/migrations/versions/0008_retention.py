"""Persist ordinary-history policy without expiring identity/receipt ledgers."""

import sqlalchemy as sa
from alembic import op

revision = "0008_retention"
down_revision = "0007_management_operations"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("outbox", sa.Column("completed_at", sa.Float(), nullable=True))
    # Legacy terminal timestamps were not recorded. Keep a full retention window
    # from upgrade instead of guessing when old deliveries became terminal.
    op.execute(
        "UPDATE outbox SET completed_at=CAST(strftime('%s','now') AS REAL) "
        "WHERE status IN ('sent','failed','cancelled')"
    )
    op.create_index("ix_outbox_completed", "outbox", ["status", "completed_at"])
    for table, column in (
        ("source_runs", "at"),
        ("rule_hits", "matched_at"),
        ("task_evaluations", "evaluated_at"),
        ("target_test_attempts", "finished_at"),
        ("manual_deliveries", "finished_at"),
    ):
        op.create_index("ix_" + table + "_retention", table, [column])
    op.create_table(
        "retention_policy",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.Float(), nullable=False),
        sa.Column("last_run_at", sa.Float(), nullable=True),
        sa.Column("last_counts", sa.JSON(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_retention_singleton"),
        sa.CheckConstraint("days BETWEEN 1 AND 365", name="ck_retention_days"),
    )
    op.execute(
        "INSERT INTO retention_policy(id,days,revision,next_run_at,last_counts) "
        "VALUES(1,30,1,0,'{}')"
    )


def downgrade():
    op.drop_table("retention_policy")
    for table in (
        "source_runs",
        "rule_hits",
        "task_evaluations",
        "target_test_attempts",
        "manual_deliveries",
    ):
        op.drop_index("ix_" + table + "_retention", table_name=table)
    op.drop_index("ix_outbox_completed", table_name="outbox")
    op.drop_column("outbox", "completed_at")
