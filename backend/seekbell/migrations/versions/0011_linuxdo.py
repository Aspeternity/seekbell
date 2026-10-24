"""Linux DO, display-only author names and independent hotlist snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0011_linuxdo"
down_revision = "0010_overview_preferences"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    connection.execute(
        sa.text("INSERT INTO websites (id, name, enabled) VALUES ('linuxdo', 'LINUX DO', 0)")
    )
    connection.execute(
        sa.text(
            "INSERT INTO sources (id, website_id, url, enabled, interval_seconds) "
            "VALUES ('linuxdo-rss', 'linuxdo', :url, 0, 60)"
        ),
        {"url": "https://linux.do/latest.rss?order=created"},
    )
    connection.execute(
        sa.text(
            "INSERT INTO source_states "
            "(source_id, initialized, needs_baseline, failures, next_attempt_at, "
            "previous_window, window_count, possible_gap) "
            "VALUES ('linuxdo-rss', 0, 0, 0, 0, '[]', 0, 0)"
        )
    )
    op.add_column("posts", sa.Column("author_display_name", sa.String(500), nullable=True))
    op.create_table(
        "website_request_states",
        sa.Column("website_id", sa.String(80), sa.ForeignKey("websites.id"), primary_key=True),
        sa.Column("next_request_at", sa.Float(), nullable=False),
        sa.Column("blocked_until", sa.Float(), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
    )
    connection.execute(
        sa.text(
            "INSERT INTO website_request_states "
            "(website_id, next_request_at, blocked_until, failures) VALUES ('linuxdo', 0, 0, 0)"
        )
    )
    op.create_table(
        "hotlist_snapshots",
        sa.Column("website_id", sa.String(80), sa.ForeignKey("websites.id"), primary_key=True),
        sa.Column("provider_id", sa.String(80), primary_key=True),
        sa.Column("period", sa.String(32), primary_key=True),
        sa.Column("fetched_at", sa.Float(), nullable=False),
        sa.Column("source_updated_at", sa.Float(), nullable=True),
        sa.Column("items", sa.JSON(), nullable=False),
    )


def downgrade():
    raise RuntimeError("Restore the matching pre-upgrade backup to roll back this migration")
