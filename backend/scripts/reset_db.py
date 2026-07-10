"""Wipe every table in the configured database and recreate them empty.

DESTRUCTIVE. Removes all users, firms, data sources, documents, obligations,
controls, evidence, gaps, change requests, findings, and the audit chain.

Usage (from backend/):
    python -m scripts.reset_db

The target database is whatever ``app.config.settings.database_url`` resolves
to (defaults to the Neon Postgres URL). Set ``DATABASE_URL`` in the environment
or ``backend/.env`` to point at a different database before running.
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from app.config import settings
from app.db.base import Base, engine
from app.db import models  # noqa: F401  (register every model on Base.metadata)


def _dialect_name() -> str:
    return engine.dialect.name


def _drop_public_schema_postgres() -> None:
    """Nuke the entire ``public`` schema so we also clean up anything that isn't
    tracked in ``Base.metadata`` any more (renamed tables, dropped columns via
    old migrations, etc.). Then recreate an empty ``public`` schema."""
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


def main() -> int:
    dialect = _dialect_name()
    print(f"[reset_db] target: {engine.url.render_as_string(hide_password=True)}")
    print(f"[reset_db] dialect: {dialect}")

    before = inspect(engine).get_table_names()
    print(f"[reset_db] tables before: {len(before)} -> {sorted(before)}")

    if dialect == "postgresql":
        _drop_public_schema_postgres()
    else:
        Base.metadata.drop_all(bind=engine)

    Base.metadata.create_all(bind=engine)

    after = inspect(engine).get_table_names()
    print(f"[reset_db] tables after: {len(after)} -> {sorted(after)}")
    print("[reset_db] done. database is empty and schema is fresh.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
