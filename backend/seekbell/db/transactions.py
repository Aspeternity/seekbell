import asyncio
from contextlib import contextmanager

from sqlalchemy import Engine
from sqlalchemy.orm import Session


@contextmanager
def write_session(engine: Engine):
    """Serialize configuration and discovery before reading mutable snapshots."""
    with Session(engine, expire_on_commit=False) as session:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise


async def database_call(action, *args, **kwargs):
    """A cancelled actor must join its SQLite thread before engine disposal."""
    task = asyncio.create_task(asyncio.to_thread(action, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise
