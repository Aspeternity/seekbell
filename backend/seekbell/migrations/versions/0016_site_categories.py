"""Mark versioned site category rules; all existing rows stay unchanged.

The revision prevents older binaries from opening new rule JSON they cannot
interpret. Legacy rules are resolved at read/evaluation time without rewriting
historical versions or creating new current versions during upgrade.
"""

revision = "0016_site_categories"
down_revision = "0015_category_values"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    raise RuntimeError("Restore the matching pre-upgrade backup to roll back this migration")
