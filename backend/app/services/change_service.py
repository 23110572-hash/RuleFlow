"""Change-management service (Flow B).

new SEBI doc -> canonical DIFF (regulation vs regulation) -> operational-impact
analysis on the firm overlay -> HIL approval -> cited Change Request (no direct
write-back). On approval the firm applies it and marks it done; the platform
tracks to closure and audits every step.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ChangeEvent,
    ChangeRequest,
    Control,
    Obligation,
    ObligationTest,
)
from app.kernel.diff import ObligationChange, diff_obligations
from app.services import audit


def _ob_dict(o: Obligation) -> dict:
    return {
        "id": o.id,
        "clause_path": o.clause_path,
        "verbatim_text": o.verbatim_text,
        "normalized_statement": o.normalized_statement,
        "modality": o.modality,
        "trigger_condition": o.trigger_condition,
        "deadline_or_periodicity": o.deadline_or_periodicity,
        "threshold": o.threshold,
        "citation": o.citation,
    }


def diff_documents(db: Session, from_document_id: str, to_document_id: str) -> dict:
    """Deterministic canonical diff between two ingested documents; persists
    ChangeEvents. Returns the diff summary + change lists."""
    old = db.execute(
        select(Obligation).where(Obligation.source_document_id == from_document_id)
    ).scalars().all()
    new = db.execute(
        select(Obligation).where(Obligation.source_document_id == to_document_id)
    ).scalars().all()

    result = diff_obligations([_ob_dict(o) for o in old], [_ob_dict(n) for n in new])

    events: list[ChangeEvent] = []
    for change in result.changes:
        ev = ChangeEvent(
            obligation_id=change.new_id or change.old_id,
            from_document_id=from_document_id,
            to_document_id=to_document_id,
            type=change.type,
            old_version={"id": change.old_id, "text": change.old_text} if change.old_id else None,
            new_version={"id": change.new_id, "text": change.new_text} if change.new_id else None,
            similarity=change.similarity,
            field_changes=change.field_changes,
        )
        db.add(ev)
        events.append(ev)
    db.flush()

    audit.record(
        db,
        action="regulation.diffed",
        payload={"from": from_document_id, "to": to_document_id, "summary": result.summary()},
    )
    db.commit()
    return {"summary": result.summary(), "diff": result.to_dict(), "change_event_ids": [e.id for e in events]}


def _action_text(change: ObligationChange | ChangeEvent) -> str:
    t = change.type
    if t == "added":
        return "New obligation introduced. Establish a control and begin collecting evidence."
    if t == "removed":
        return "Obligation removed/superseded. Retire the mapped control after retention period; retain historical evidence."
    return "Obligation amended. Review the mapped control, update the obligation test, and re-attest evidence against the new requirement."


def operational_impact(db: Session, firm_id: str, change_event_ids: list[str]) -> list[dict]:
    """For each canonical change, compute the impact on THIS firm's overlay and
    draft a pending, cited Change Request. Human approves before anything moves."""
    controls = db.execute(select(Control).where(Control.firm_id == firm_id)).scalars().all()

    drafts: list[dict] = []
    for ce_id in change_event_ids:
        ce = db.get(ChangeEvent, ce_id)
        if not ce:
            continue
        target_ob_id = (ce.old_version or {}).get("id") or (ce.new_version or {}).get("id")

        affected_controls = [c.id for c in controls if target_ob_id in (c.obligation_ids or [])]
        affected_tests = []
        citation = {}
        if target_ob_id:
            ob = db.get(Obligation, target_ob_id)
            if ob:
                citation = ob.citation or {}
            test = db.execute(
                select(ObligationTest).where(ObligationTest.obligation_id == target_ob_id)
            ).scalars().first()
            if test:
                affected_tests = [test.id]

        cr = ChangeRequest(
            firm_id=firm_id,
            change_event_id=ce.id,
            affected_controls=affected_controls,
            affected_evidence=[],
            affected_tests=affected_tests,
            operational_action_text=_action_text(ce),
            citation=citation,
            status="pending",
        )
        db.add(cr)
        db.flush()
        drafts.append(
            {
                "change_request_id": cr.id,
                "change_event_id": ce.id,
                "type": ce.type,
                "affected_controls": affected_controls,
                "affected_tests": affected_tests,
                "operational_action_text": cr.operational_action_text,
                "citation": citation,
            }
        )

    audit.record(
        db,
        action="change.impact_analyzed",
        payload={"firm_id": firm_id, "change_requests": len(drafts)},
        firm_id=firm_id,
    )
    db.commit()
    return drafts


def decide_change_request(
    db: Session, change_request_id: str, decision: str, approver: str, note: str = ""
) -> ChangeRequest:
    """HIL decision: approve | escalate | reject. Approval emits the cited
    action ticket the firm applies (status -> approved)."""
    cr = db.get(ChangeRequest, change_request_id)
    if not cr:
        raise ValueError("change request not found")
    if decision not in {"approve", "escalate", "reject"}:
        raise ValueError("decision must be approve|escalate|reject")

    before = cr.status
    cr.status = {"approve": "approved", "escalate": "escalated", "reject": "rejected"}[decision]
    if decision == "approve":
        cr.approved_by = approver
        cr.approved_at = datetime.now(timezone.utc)

    audit.record(
        db,
        action=f"change_request.{decision}",
        payload={"change_request_id": cr.id, "note": note, "citation": cr.citation},
        firm_id=cr.firm_id,
        actor=approver,
        before_hash=before,
        after_hash=cr.status,
    )
    db.commit()
    db.refresh(cr)
    return cr


def mark_applied(db: Session, change_request_id: str, actor: str) -> ChangeRequest:
    """Firm applied the change in their own systems and marks it done."""
    cr = db.get(ChangeRequest, change_request_id)
    if not cr:
        raise ValueError("change request not found")
    cr.status = "applied"
    audit.record(
        db,
        action="change_request.applied",
        payload={"change_request_id": cr.id},
        firm_id=cr.firm_id,
        actor=actor,
    )
    db.commit()
    db.refresh(cr)
    return cr
