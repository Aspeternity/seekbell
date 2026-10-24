"""Separate server-directed waits from bounded manual RSS diagnostics."""

import sqlalchemy as sa
from alembic import op

revision = "0012_retry_controls"
down_revision = "0011_linuxdo"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "website_request_states",
        sa.Column("retry_after_until", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "website_request_states",
        sa.Column("next_manual_at", sa.Float(), nullable=False, server_default="0"),
    )
    # Legacy rows did not distinguish Retry-After from our policy. Preserve
    # their deadline rather than accidentally overriding a server-required wait.
    op.execute(
        "UPDATE website_request_states SET retry_after_until = MAX(blocked_until, "
        "COALESCE((SELECT MAX(state.next_attempt_at) FROM source_states AS state "
        "JOIN sources AS source ON source.id = state.source_id "
        "WHERE source.website_id = website_request_states.website_id AND state.failures > 0), 0), "
        "COALESCE((SELECT MAX(probe.next_attempt_at) FROM source_probes AS probe "
        "JOIN sources AS source ON source.id = probe.source_id "
        "WHERE source.website_id = website_request_states.website_id "
        "AND probe.status = 'failure'), 0))"
    )


def downgrade():
    raise RuntimeError("Restore the matching pre-upgrade backup to roll back this migration")
