"""Change-management API — diff, operational impact, HIL change requests."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_firm_data_source
from app.db.base import get_db
from app.db.models import ChangeEvent, ChangeRequest, Document, Obligation
from app.services import change_service

router = APIRouter(tags=["changes"])


def _serialise_change_event(db: Session, ev: ChangeEvent | None) -> dict | None:
    """Return a display-ready representation of a change event: old/new
    obligation summaries plus the from/to document titles."""
    if ev is None:
        return None
    from_doc = db.get(Document, ev.from_document_id) if ev.from_document_id else None
    to_doc = db.get(Document, ev.to_document_id) if ev.to_document_id else None

    def _resolve_side(side: dict | None) -> dict | None:
        if not side:
            return None
        ob_id = side.get("id")
        ob = db.get(Obligation, ob_id) if ob_id else None
        return {
            "obligation_id": ob_id,
            "text": side.get("text"),
            "clause_path": ob.clause_path if ob else None,
            "verbatim_text": ob.verbatim_text if ob else None,
            "citation": (ob.citation if ob else {}) or {},
        }

    return {
        "id": ev.id,
        "type": ev.type,
        "similarity": ev.similarity,
        "field_changes": ev.field_changes or {},
        "from_document": {
            "id": from_doc.id if from_doc else ev.from_document_id,
            "title": from_doc.title if from_doc else None,
            "circular_number": from_doc.circular_number if from_doc else None,
        } if ev.from_document_id else None,
        "to_document": {
            "id": to_doc.id if to_doc else ev.to_document_id,
            "title": to_doc.title if to_doc else None,
            "circular_number": to_doc.circular_number if to_doc else None,
        } if ev.to_document_id else None,
        "old": _resolve_side(ev.old_version),
        "new": _resolve_side(ev.new_version),
    }


def _serialise_change_request(db: Session, cr: ChangeRequest) -> dict:
    ev = db.get(ChangeEvent, cr.change_event_id) if cr.change_event_id else None
    return {
        "id": cr.id,
        "firm_id": cr.firm_id,
        "change_event_id": cr.change_event_id,
        "operational_action_text": cr.operational_action_text,
        "citation": cr.citation,
        "affected_controls": cr.affected_controls,
        "affected_tests": cr.affected_tests,
        "status": cr.status,
        "approved_by": cr.approved_by,
        "approved_at": cr.approved_at.isoformat() if cr.approved_at else None,
        "recorded_at": cr.recorded_at.isoformat() if cr.recorded_at else None,
        "change_event": _serialise_change_event(db, ev),
    }


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
    return [_serialise_change_request(db, cr) for cr in rows]


@router.post(
    "/firms/{firm_id}/change-impact/rescan",
    dependencies=[Depends(require_firm_data_source)],
)
def rescan_impact(
    firm_id: str,
    document_id: str | None = Query(
        None,
        description="Restrict rescan to a single document. Omit to check every ingested document.",
    ),
    db: Session = Depends(get_db),
):
    """Re-run the impact detector for this firm.

    Compares the firm's adopted obligations against the extracted obligations
    of ``document_id`` (or every document, if omitted). Idempotent: change
    events / requests that already exist are not duplicated.
    """
    if document_id:
        drafts = change_service.detect_impact_on_adopted_obligations(db, document_id, firm_id)
        scanned = 1 if drafts is not None else 0
        return {"scanned_documents": scanned, "action_items_created": len(drafts), "drafts": drafts}

    doc_ids = [
        d.id
        for d in db.execute(select(Document).order_by(Document.recorded_at.asc())).scalars().all()
    ]
    all_drafts: list[dict] = []
    for did in doc_ids:
        all_drafts.extend(change_service.detect_impact_on_adopted_obligations(db, did, firm_id))
    return {
        "scanned_documents": len(doc_ids),
        "action_items_created": len(all_drafts),
        "drafts": all_drafts,
    }


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
