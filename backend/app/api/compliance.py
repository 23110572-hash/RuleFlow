"""Compliance API — obligation tests, gaps, health, and the Time Machine."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_firm_data_source
from app.db.base import get_db
from app.db.models import Firm, Gap
from app.services import compliance_service

router = APIRouter(
    prefix="/firms/{firm_id}/compliance",
    tags=["compliance"],
    dependencies=[Depends(require_firm_data_source)],
)


def _firm(db: Session, firm_id: str) -> Firm:
    f = db.get(Firm, firm_id)
    if not f:
        raise HTTPException(404, "firm not found")
    return f


@router.get("/evaluate")
def evaluate(firm_id: str, db: Session = Depends(get_db)):
    """Live obligation-test results + classified gaps + health score."""
    f = _firm(db, firm_id)
    return compliance_service.evaluate_firm(db, firm_id, f.category)


@router.post("/refresh-gaps")
def refresh_gaps(firm_id: str, db: Session = Depends(get_db)):
    """Recompute and persist the gap ledger."""
    f = _firm(db, firm_id)
    return compliance_service.refresh_gaps(db, firm_id, f.category)


@router.get("/gaps")
def list_gaps(firm_id: str, status: str = "open", db: Session = Depends(get_db)):
    _firm(db, firm_id)
    rows = db.execute(
        select(Gap).where(Gap.firm_id == firm_id, Gap.status == status)
    ).scalars().all()
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    rows.sort(key=lambda g: order.get(g.severity, 9))
    return [
        {
            "id": g.id, "obligation_id": g.obligation_id, "reason": g.reason,
            "severity": g.severity, "detail": g.detail, "status": g.status,
        }
        for g in rows
    ]


@router.get("/time-machine")
def time_machine(
    firm_id: str,
    as_of: datetime = Query(..., description="Point in time (ISO8601)"),
    db: Session = Depends(get_db),
):
    """Reconstruct 'what was required and what evidence existed as of date X'."""
    f = _firm(db, firm_id)
    return compliance_service.point_in_time(db, firm_id, f.category, as_of)
