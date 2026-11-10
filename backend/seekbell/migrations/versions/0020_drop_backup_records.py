"""Drop the backup operation records; the backup library itself is the history."""

from alembic import op

revision = "0020_drop_backup_records"
down_revision = "0019_settings_reorganization"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("ix_backup_records_at", table_name="backup_records")
    op.drop_table("backup_records")


def downgrade():
    raise RuntimeError("Restore the matching pre-upgrade backup to roll back this migration")
