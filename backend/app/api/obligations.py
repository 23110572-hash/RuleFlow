"""Obligation Register API — searchable canonical obligations + source clause."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from pydantic import BaseModel

from app.agents.reasoning import propose_control_for_obligation
from app.api.deps import get_current_firm
from app.db.base import get_db
from app.db.models import Control, Document, Firm, Obligation, ObligationTest
from app.schemas.models import ObligationOut
from app.services import audit, datasource_service

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


def _existing_control_for(db: Session, firm_id: str, obligation_id: str) -> Control | None:
    """Return the firm's Control that already references this obligation, if any."""
    controls = db.execute(select(Control).where(Control.firm_id == firm_id)).scalars().all()
    for c in controls:
        if obligation_id in (c.obligation_ids or []):
            return c
    return None


def _adopt_obligation(db: Session, firm: Firm, o: Obligation) -> Control:
    """Store the approved law in the firm's live compliance record.

    Creates a new Control drafted by the LLM (deterministic fallback if the LLM
    is unavailable). Idempotent: if a Control for this (firm, obligation)
    already exists, returns it unchanged.
    """
    existing = _existing_control_for(db, firm.id, o.id)
    if existing:
        return existing

    draft = propose_control_for_obligation(
        {
            "verbatim_text": o.verbatim_text,
            "normalized_statement": o.normalized_statement,
            "modality": o.modality,
            "deadline_or_periodicity": o.deadline_or_periodicity,
            "threshold": o.threshold,
            "clause_path": o.clause_path,
        }
    )
    control = Control(
        firm_id=firm.id,
        obligation_ids=[o.id],
        description=draft["description"],
        type=draft["type"],
        owner_role=draft["owner_role"],
        frequency=draft["frequency"],
        status="active",
    )
    db.add(control)
    db.flush()
    return control


def _retract_obligation(db: Session, firm_id: str, obligation_id: str) -> str | None:
    """Undo adoption when a previously-approved obligation is rejected.

    Removes the obligation from every one of the firm's Controls that reference
    it. Any Control left with no obligations is retired (status='retired'), not
    deleted — so the audit trail for prior evidence still resolves.
    Returns the id of a modified control (for audit payload) or None.
    """
    controls = db.execute(select(Control).where(Control.firm_id == firm_id)).scalars().all()
    touched: str | None = None
    for c in controls:
        ids = list(c.obligation_ids or [])
        if obligation_id in ids:
            ids = [i for i in ids if i != obligation_id]
            c.obligation_ids = ids
            if not ids:
                c.status = "retired"
            touched = c.id
    return touched


@router.post("/{obligation_id}/decision")
def decide_obligation(
    obligation_id: str,
    body: DecisionIn,
    firm: Firm = Depends(get_current_firm),
    db: Session = Depends(get_db),
):
    """Human-in-the-loop: the compliance officer accepts or rejects an extracted
    obligation.

    On ``approve`` the obligation is written into the firm's live compliance
    record as a Control (drafted by the LLM). Idempotent: repeated approvals
    do not create duplicate Controls. On ``reject`` any Control that had
    previously adopted this obligation is unlinked (and retired if empty)."""
    o = db.get(Obligation, obligation_id)
    if not o:
        raise HTTPException(404, "obligation not found")
    if body.decision not in {"approve", "reject"}:
        raise HTTPException(400, "decision must be approve|reject")

    # Approving writes the obligation into the firm's live compliance record
    # (as a Control), so a data source must be connected first. We gate the
    # whole decision workflow to match the locked Approvals page in the UI.
    if not datasource_service.firm_has_data_source(db, firm.id):
        raise HTTPException(
            403, "Connect your firm's data source (Settings) before approving obligations."
        )

    before = o.status
    o.status = "approved" if body.decision == "approve" else "rejected"

    control_id: str | None = None
    source_write: dict = {"ok": False}
    if body.decision == "approve":
        control = _adopt_obligation(db, firm, o)
        control_id = control.id

        # Write the adopted law into the firm's OWN connected database so their
        # systems see it. Non-fatal: the Control (RuleFlow's record) is kept
        # even if the external write fails; the error is surfaced to the user.
        doc = db.get(Document, o.source_document_id)
        source_ref = (doc.circular_number or doc.title) if doc else ""
        source_write = datasource_service.push_obligation_to_source(
            db,
            firm.id,
            {
                "id": o.id,
                "clause_path": o.clause_path,
                "normalized_statement": o.normalized_statement,
                "verbatim_text": o.verbatim_text,
                "modality": o.modality,
                "deadline_or_periodicity": o.deadline_or_periodicity,
                "threshold": o.threshold,
                "source_document": source_ref,
            },
            {
                "description": control.description,
                "owner_role": control.owner_role,
                "frequency": control.frequency,
            },
        )
        audit.record(
            db,
            action="obligation.adopted",
            payload={
                "obligation_id": o.id,
                "clause_path": o.clause_path,
                "control_id": control.id,
                "control_description": control.description,
                "written_to_firm_database": source_write.get("ok", False),
                "firm_database_table": source_write.get("table"),
                "firm_database_error": source_write.get("error"),
            },
            firm_id=firm.id,
            actor=firm.name,
            before_hash=before,
            after_hash=o.status,
        )
    else:
        touched = _retract_obligation(db, firm.id, o.id)
        source_write = datasource_service.remove_obligation_from_source(db, firm.id, o.id)
        audit.record(
            db,
            action="obligation.rejected",
            payload={
                "obligation_id": o.id,
                "clause_path": o.clause_path,
                "retracted_control_id": touched,
                "removed_from_firm_database": source_write.get("ok", False),
            },
            firm_id=firm.id,
            actor=firm.name,
            before_hash=before,
            after_hash=o.status,
        )

    db.commit()
    return {
        "id": o.id,
        "status": o.status,
        "control_id": control_id,
        "stored_in_your_database": bool(source_write.get("ok")),
        "database_table": source_write.get("table"),
        "database_error": source_write.get("error"),
    }


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
