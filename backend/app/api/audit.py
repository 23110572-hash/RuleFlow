"""Audit Trail API — tamper-evident, hash-chained log viewer + verification."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_firm
from app.db.base import get_db
from app.db.models import AuditEntry, Firm
from app.services import audit as audit_service

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def list_entries(
    firm: Firm = Depends(get_current_firm),
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
):
    """Return audit entries scoped to the authenticated user's firm."""
    # Tiebreak on id, matching the ordering the chain itself is built and
    # verified with (see audit_service._latest_chain_hash and .verify). Several
    # entries routinely share a recorded_at — an upload and the change analysis
    # it triggers land in the same millisecond — and ordering on the timestamp
    # alone left those in arbitrary order, so the page could show effects above
    # their causes. Displaying the chain's own sequence is the defensible answer.
    stmt = select(AuditEntry).where(AuditEntry.firm_id == firm.id)
    stmt = stmt.order_by(AuditEntry.recorded_at.desc(), AuditEntry.id.desc()).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return [
        {
            "id": e.id, "actor": e.actor, "action": e.action, "payload": e.payload,
            "prev_chain_hash": e.prev_chain_hash, "chain_hash": e.chain_hash, "ts": e.ts,
        }
        for e in rows
    ]


@router.get("/verify")
def verify_chain(firm: Firm = Depends(get_current_firm), db: Session = Depends(get_db)):
    """Verify hash chain integrity for the authenticated user's firm."""
    ok, broken = audit_service.verify(db, firm.id)
    return {"intact": ok, "first_broken_index": broken}
