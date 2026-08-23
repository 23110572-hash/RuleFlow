"""Create tables (dev convenience). Production uses Alembic migrations."""
from __future__ import annotations

from sqlalchemy import inspect, text

from app.db.base import Base, engine
from app.db import models  # noqa: F401  (register models on Base.metadata)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    # Ensure firm_id column exists on documents (added post-launch)
    _migrate_documents_firm_id()


def _migrate_documents_firm_id() -> None:
    """Add firm_id to documents if it doesn't exist yet."""
    insp = inspect(engine)
    columns = [c["name"] for c in insp.get_columns("documents")]
    if "firm_id" not in columns:
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE documents ADD COLUMN firm_id VARCHAR(32) REFERENCES firms(id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_documents_firm_id ON documents(firm_id)"
            ))
