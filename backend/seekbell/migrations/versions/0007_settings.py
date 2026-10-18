"""Persistent display/retention settings and account reauthentication budget.

Revision ID: 0007_settings
Revises: 0006_manual_deliveries
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_settings"
down_revision = "0006_manual_deliveries"
branch_labels = None
depends_on = None

INDEXES = {
    "outbox": "created_at",
    "rule_hits": "matched_at",
    "source_runs": "at",
    "target_test_attempts": "finished_at",
    "manual_delivery_attempts": "finished_at",
}


def upgrade():
    settings = op.create_table(
        "application_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=True),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("last_cleanup_at", sa.Float(), nullable=True),
        sa.Column("last_cleanup_counts", sa.JSON(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_application_settings_singleton"),
        sa.CheckConstraint("retention_days BETWEEN 1 AND 3650", name="ck_settings_retention"),
    )
    op.bulk_insert(
        settings,
        [
            {
                "id": 1,
                "revision": 1,
                "timezone": None,
                "retention_days": 30,
                "last_cleanup_counts": {},
            }
        ],
    )
    op.create_table(
        "account_throttle",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("window_started", sa.Float(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_account_throttle_singleton"),
    )
    for table, column in INDEXES.items():
        op.create_index(f"ix_{table}_retention", table, [column])


def downgrade():
    for table in INDEXES:
        op.drop_index(f"ix_{table}_retention", table_name=table)
    op.drop_table("account_throttle")
    op.drop_table("application_settings")
