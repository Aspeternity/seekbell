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
