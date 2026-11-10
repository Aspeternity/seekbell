"""Add the automatic backup schedule (on by default: daily at 03:00, keep 7)."""

import time

import sqlalchemy as sa
from alembic import op

revision = "0021_backup_schedule"
down_revision = "0020_drop_backup_records"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "backup_schedule",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("frequency", sa.String(8), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("minute", sa.Integer(), nullable=False),
        sa.Column("keep", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("since", sa.Float(), nullable=False),
        sa.Column("next_run_at", sa.Float(), nullable=True),
        sa.Column("last_attempt_at", sa.Float(), nullable=True),
        sa.Column("last_error", sa.String(200), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_backup_schedule_singleton"),
        sa.CheckConstraint("frequency IN ('daily','weekly')", name="ck_backup_frequency"),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_backup_weekday"),
        sa.CheckConstraint("minute BETWEEN 0 AND 1439", name="ck_backup_minute"),
        sa.CheckConstraint("keep BETWEEN 1 AND 60", name="ck_backup_keep"),
    )
    # The first run is the next 03:00 after this moment, never an immediate catch-up.
    op.execute(
        sa.text(
            "INSERT INTO backup_schedule(id,enabled,frequency,weekday,minute,keep,revision,since) "
            "VALUES(1,1,'daily',0,180,7,1,:since)"
        ).bindparams(since=time.time())
    )


def downgrade():
    raise RuntimeError("Restore the matching pre-upgrade backup to roll back this migration")
