"""Evaluate a bounded local sample with draft rules; no ingestion or delivery writes."""

from sqlalchemy import func, select

from seekbell.db.models import Post
from seekbell.domain.posts import PostFields
from seekbell.domain.rules import evaluate
from seekbell.services.history import read_session


def trial_history(engine, website_id, rule, limit=20):
    with read_session(engine) as session:
        available = session.scalar(
            select(func.count()).select_from(Post).where(Post.website_id == website_id)
        )
        posts = session.scalars(
            select(Post)
            .where(Post.website_id == website_id)
            .order_by(Post.first_seen_at.desc(), Post.external_post_id.desc())
            .limit(limit)
        ).all()
        return {
            "website_id": website_id,
            "available": available,
            "sample_count": len(posts),
            "from_at": min((post.first_seen_at for post in posts), default=None),
            "to_at": max((post.first_seen_at for post in posts), default=None),
            "items": [
                {
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
