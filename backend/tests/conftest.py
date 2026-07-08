"""Test fixtures. Points the app at an isolated temp SQLite DB before importing
any app module that reads settings, so tests never touch a real database."""
from __future__ import annotations

import os
import tempfile

import pytest

# Must be set BEFORE app.config is imported anywhere.
_TMP_DB = os.path.join(tempfile.gettempdir(), "regnexus_test.db")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ["GROQ_API_KEY"] = ""  # ensure deterministic tests never call the network


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.db.init_db import init_db
    from app.main import app

    init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db():
    from app.db.base import SessionLocal
    from app.db.init_db import init_db

    init_db()
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
