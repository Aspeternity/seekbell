"""Evaluate a bounded local sample with draft rules; no ingestion or delivery writes."""

from sqlalchemy import func, select

from seekbell.db.models import Post
from seekbell.domain.posts import PostFields
from seekbell.domain.rules import evaluate
from seekbell.services.history import read_session


def trial_history(engine, website_ids, rule, limit=20):
    # Preserve the internal single-site call contract while sharing one bounded sample.
    selected = [website_ids] if isinstance(website_ids, str) else website_ids
    with read_session(engine) as session:
        available = session.scalar(
            select(func.count()).select_from(Post).where(Post.website_id.in_(selected))
        )
        posts = session.scalars(
            select(Post)
            .where(Post.website_id.in_(selected))
            .order_by(Post.first_seen_at.desc(), Post.website_id, Post.external_post_id.desc())
            .limit(limit)
        ).all()
        return {
            "website_id": selected[0] if len(selected) == 1 else None,
            "website_ids": selected,
            "available": available,
            "sample_count": len(posts),
            "from_at": min((post.first_seen_at for post in posts), default=None),
            "to_at": max((post.first_seen_at for post in posts), default=None),
            "items": [
                {
                    "website_id": post.website_id,
                    "sample": (
                        fields := PostFields(
                            title=post.title,
                            summary=post.summary,
                            author=post.author,
                            category=post.category,
                        )
                    ).model_dump(mode="json"),
                    "result": evaluate(rule, fields).model_dump(mode="json"),
                }
                for post in posts
            ],
        }
