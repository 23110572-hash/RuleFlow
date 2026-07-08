"""SQLAlchemy engine/session setup. Works on SQLite (zero-infra dev) and
PostgreSQL+pgvector (full deployment)."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs() -> dict:
    if settings.is_sqlite:
        return {"connect_args": {"check_same_thread": False}}
    # Remote Postgres (e.g. Neon serverless). Neon closes idle connections and
    # cold-starts compute, so a naive pooled connection can be dead by the time
    # we use it -> dropped request -> the frontend sees "Failed to fetch".
    #   * pool_pre_ping  : validate a connection before handing it out.
    #   * pool_recycle   : proactively drop connections older than 5 min.
    #   * keepalives     : keep the TCP link alive through NAT/idle timeouts.
    #   * connect_timeout: fail fast (and retry) instead of hanging on a cold start.
    return {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 5,
        "max_overflow": 10,
        "connect_args": {
            "connect_timeout": 15,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
    }


engine = create_engine(settings.database_url, **_engine_kwargs())
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
