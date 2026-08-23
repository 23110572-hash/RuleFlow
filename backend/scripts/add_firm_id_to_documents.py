"""One-time migration: add firm_id column to documents table.

Run this ONCE against your production database:
    python -m scripts.add_firm_id_to_documents

SQLAlchemy's create_all won't add columns to existing tables, so we do it manually.
"""
import sys
sys.path.insert(0, ".")

from app.db.base import engine
from sqlalchemy import text

with engine.connect() as conn:
    # Add the column if it doesn't exist
    try:
        conn.execute(text(
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS firm_id VARCHAR(32) REFERENCES firms(id)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_documents_firm_id ON documents(firm_id)"
        ))
        conn.commit()
        print("OK: firm_id column added to documents table")
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
