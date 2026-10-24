"""Preserve website insertion order and repair manual-only retry quotas."""

import sqlalchemy as sa
from alembic import op

revision = "0013_site_order"
down_revision = "0012_retry_controls"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    # The old table has a text primary key and SQLite rowid insertion order.
    installed = list(
        connection.execute(
            sa.text("SELECT website_id FROM website_installations ORDER BY rowid")
        ).scalars()
    )
    op.add_column(
        "website_installations",
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    for position, website_id in enumerate(installed, 1):
        connection.execute(
            sa.text(
                "UPDATE website_installations SET position=:position WHERE website_id=:website_id"
            ),
            {"position": position, "website_id": website_id},
        )
    # Automatic failures used to reserve manual quota even with no probe.
    # Rebuild from actual manual evidence; keep real/cancelled checks limited.
    op.execute(
        "UPDATE website_request_states SET next_manual_at = COALESCE(("
        "SELECT MAX(COALESCE(probe.finished_at, probe.started_at) + 60) "
        "FROM source_probes AS probe JOIN sources AS source ON source.id=probe.source_id "
        "WHERE source.website_id=website_request_states.website_id "
        "AND probe.status IN ('success','failure','unknown')), 0)"
    )


def downgrade():
    raise RuntimeError("Restore the matching pre-upgrade backup to roll back this migration")
