"""Repair current legacy category choices in new versions; preserve all history."""

import json
import time

import sqlalchemy as sa
from alembic import op

revision = "0015_category_values"
down_revision = "0014_task_websites"
branch_labels = None
depends_on = None

# Frozen old label -> stable RSS identifier mapping for this migration.
ALIASES = {
    "日常": "daily",
    "技术": "tech",
    "情报": "info",
    "测评": "review",
    "交易": "trade",
    "拼车": "carpool",
    "推广": "promotion",
    "生活": "life",
    "Dev": "dev",
    "贴图": "photo-share",
    "曝光": "expose",
    "沙盒": "sandbox",
}


def upgrade():
    connection = op.get_bind()
    rows = (
        connection.execute(
            sa.text(
                "SELECT v.* FROM tasks t JOIN task_versions v "
                "ON v.task_id=t.id AND v.version=t.current_version WHERE t.deleted_at IS NULL"
            )
        )
        .mappings()
        .all()
    )
    at = time.time()
    for row in rows:
        rule, sites = json.loads(row["rule"]), json.loads(row["website_ids"])
        categories = rule.get("categories", []) if isinstance(rule, dict) else []
        if (
            "nodeseek" not in sites
            or not isinstance(categories, list)
            or not all(isinstance(value, str) for value in categories)
        ):
            continue
        selected = []
        for value in categories:
            canonical = ALIASES.get(value, value)
            if len(sites) > 1 and canonical != value and value not in selected:
                selected.append(value)
            if canonical not in selected:
                selected.append(canonical)
        if selected == categories or len(selected) > 64:
            continue
        version = connection.execute(
            sa.text("SELECT MAX(version)+1 FROM task_versions WHERE task_id=:key"),
            {"key": row["task_id"]},
        ).scalar_one()
        fixed = {**rule, "categories": selected}
        connection.execute(
            sa.text(
                "INSERT INTO task_versions(task_id,version,name,description,rule,target_ids,"
                "website_ids,created_at) VALUES(:task_id,:version,:name,:description,:rule,"
                ":target_ids,:website_ids,:created_at)"
            ),
            {
                **row,
                "version": version,
                "rule": json.dumps(fixed, ensure_ascii=False),
                "created_at": at,
            },
        )
        connection.execute(
            sa.text("UPDATE tasks SET current_version=:version WHERE id=:key"),
            {"key": row["task_id"], "version": version},
        )


def downgrade():
    raise RuntimeError("Restore the matching pre-upgrade backup to roll back this migration")
