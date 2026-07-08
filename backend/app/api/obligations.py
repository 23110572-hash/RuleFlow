"""Obligation Register API — searchable canonical obligations + source clause."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from pydantic import BaseModel

from app.api.deps import get_current_firm
from app.db.base import get_db
from app.db.models import Control, Document, Firm, Obligation, ObligationTest
from app.schemas.models import ObligationOut
from app.services import audit

router = APIRouter(prefix="/obligations", tags=["obligations"])


class DecisionIn(BaseModel):
    decision: str  # approve | reject


def _out(o: Obligation) -> ObligationOut:
    return ObligationOut(
        id=o.id,
        source_document_id=o.source_document_id,
        clause_path=o.clause_path,
        verbatim_text=o.verbatim_text,
        normalized_statement=o.normalized_statement,
        modality=o.modality,
        trigger_condition=o.trigger_condition,
        deadline_or_periodicity=o.deadline_or_periodicity,
        threshold=o.threshold,
        applies_to=o.applies_to or [],
        version=o.version,
        citation=o.citation or {},
        citation_fidelity=o.citation_fidelity,
        status=o.status,
    )


@router.get("", response_model=list[ObligationOut])
def list_obligations(
    q: str | None = Query(None, description="full-text search over statement/clause"),
    document_id: str | None = None,
    modality: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(Obligation)
    if document_id:
        stmt = stmt.where(Obligation.source_document_id == document_id)
    if modality:
        stmt = stmt.where(Obligation.modality == modality)
    if status:
        stmt = stmt.where(Obligation.status == status)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func_lower(Obligation.normalized_statement).like(like),
                func_lower(Obligation.verbatim_text).like(like),
                func_lower(Obligation.clause_path).like(like),
            )
        )
    stmt = stmt.order_by(Obligation.clause_path).limit(1000)
    return [_out(o) for o in db.execute(stmt).scalars().all()]


def func_lower(col):
    from sqlalchemy import func

    return func.lower(col)


@router.post("/{obligation_id}/decision")
def decide_obligation(
    obligation_id: str,
    body: DecisionIn,
    firm: Firm = Depends(get_current_firm),
    db: Session = Depends(get_db),
):
    """Human-in-the-loop: the compliance officer accepts or rejects an extracted
    obligation. Only accepted obligations enter the firm's live compliance record."""
    o = db.get(Obligation, obligation_id)
    if not o:
        raise HTTPException(404, "obligation not found")
    if body.decision not in {"approve", "reject"}:
        raise HTTPException(400, "decision must be approve|reject")
    before = o.status
    o.status = "approved" if body.decision == "approve" else "rejected"
    audit.record(
        db,
        action=f"obligation.{body.decision}d",
        payload={"obligation_id": o.id, "clause_path": o.clause_path},
        firm_id=firm.id,
        actor=firm.name,
        before_hash=before,
        after_hash=o.status,
    )
    db.commit()
    return {"id": o.id, "status": o.status}


@router.get("/{obligation_id}")
def get_obligation(obligation_id: str, db: Session = Depends(get_db)):
    o = db.get(Obligation, obligation_id)
    if not o:
        raise HTTPException(404, "obligation not found")
    doc = db.get(Document, o.source_document_id)
    test = db.execute(
        select(ObligationTest).where(ObligationTest.obligation_id == o.id)
    ).scalars().first()
    # firm controls linking this obligation
    controls = db.execute(select(Control)).scalars().all()
    linked = [
        {"id": c.id, "firm_id": c.firm_id, "description": c.description, "frequency": c.frequency}
        for c in controls
        if o.id in (c.obligation_ids or [])
    ]
    return {
        "obligation": _out(o).model_dump(),
        "document": {
            "id": doc.id if doc else None,
            "title": doc.title if doc else None,
            "circular_number": doc.circular_number if doc else None,
        },
        "test": {"spec": test.spec, "last_status": test.last_status, "evaluator": test.evaluator}
        if test
        else None,
        "controls": linked,
    }
