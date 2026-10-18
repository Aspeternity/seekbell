from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Installation(Base):
    """Persistent installation identity; this does not represent an administrator."""

    __tablename__ = "installation"
    __table_args__ = (CheckConstraint("id = 1", name="ck_installation_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
