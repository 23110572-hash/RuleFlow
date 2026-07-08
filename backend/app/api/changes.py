"""Change-management API — diff, operational impact, HIL change requests."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_firm_data_source
from app.db.base import get_db
from app.db.models import ChangeRequest
from app.services import change_service

router = APIRouter(tags=["changes"])


@router.post("/documents/{from_id}/diff/{to_id}")
def diff(from_id: str, to_id: str, db: Session = Depends(get_db)):
    """Deterministic canonical diff between two document versions."""
    return change_service.diff_documents(db, from_id, to_id)


@router.post(
    "/firms/{firm_id}/change-impact",
    dependencies=[Depends(require_firm_data_source)],
)
def change_impact(
    firm_id: str,
    change_event_ids: list[str] = Body(..., embed=True),
    db: Session = Depends(get_db),
):
    """Operational-impact analysis: draft pending Change Requests for the firm."""
    return change_service.operational_impact(db, firm_id, change_event_ids)


@router.get("/firms/{firm_id}/change-requests")
def list_change_requests(firm_id: str, status: str | None = None, db: Session = Depends(get_db)):
    stmt = select(ChangeRequest).where(ChangeRequest.firm_id == firm_id)
    if status:
        stmt = stmt.where(ChangeRequest.status == status)
    rows = db.execute(stmt.order_by(ChangeRequest.recorded_at.desc())).scalars().all()
    return [
        {
            "id": cr.id, "firm_id": cr.firm_id, "change_event_id": cr.change_event_id,
            "operational_action_text": cr.operational_action_text, "citation": cr.citation,
            "affected_controls": cr.affected_controls, "affected_tests": cr.affected_tests,
            "status": cr.status, "approved_by": cr.approved_by,
            "approved_at": cr.approved_at.isoformat() if cr.approved_at else None,
        }
        for cr in rows
    ]


@router.post("/change-requests/{cr_id}/decision")
def decide(
    cr_id: str,
    decision: str = Body(..., embed=True),
    approver: str = Body("compliance_officer", embed=True),
    note: str = Body("", embed=True),
    db: Session = Depends(get_db),
):
    """HIL decision on a change request: approve | escalate | reject."""
    try:
        cr = change_service.decide_change_request(db, cr_id, decision, approver, note)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"id": cr.id, "status": cr.status, "approved_by": cr.approved_by}


@router.post("/change-requests/{cr_id}/applied")
def applied(cr_id: str, actor: str = Body("compliance_officer", embed=True), db: Session = Depends(get_db)):
    """Firm marks the approved change as applied in their own systems."""
    try:
        cr = change_service.mark_applied(db, cr_id, actor)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"id": cr.id, "status": cr.status}
