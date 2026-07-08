"""Audit Trail API — tamper-evident, hash-chained log viewer + verification."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import AuditEntry
from app.services import audit as audit_service

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def list_entries(
    firm_id: str | None = Query(None),
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
):
    stmt = select(AuditEntry).where(AuditEntry.firm_id == firm_id)
    stmt = stmt.order_by(AuditEntry.recorded_at.desc()).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return [
        {
            "id": e.id, "actor": e.actor, "action": e.action, "payload": e.payload,
            "prev_chain_hash": e.prev_chain_hash, "chain_hash": e.chain_hash, "ts": e.ts,
        }
        for e in rows
    ]


@router.get("/verify")
def verify_chain(firm_id: str | None = Query(None), db: Session = Depends(get_db)):
    ok, broken = audit_service.verify(db, firm_id)
    return {"intact": ok, "first_broken_index": broken}
