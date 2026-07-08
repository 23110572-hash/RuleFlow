"""Create tables (dev convenience). Production uses Alembic migrations."""
from __future__ import annotations

from app.db.base import Base, engine
from app.db import models  # noqa: F401  (register models on Base.metadata)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
