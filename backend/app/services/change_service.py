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
    Document,
    Firm,
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
    old_txt = (change.old_version or {}).get("text", "") if hasattr(change, "old_version") else ""
    new_txt = (change.new_version or {}).get("text", "") if hasattr(change, "new_version") else ""

    try:
        from app.llm.client import get_llm
        llm = get_llm()
        if llm.enabled and (old_txt or new_txt):
            prompt = (
                f"Regulation rule change ({t}).\n"
                f"Old Requirement: {old_txt}\n"
                f"New Requirement: {new_txt}\n"
                "In 1 or 2 concise sentences, tell the compliance officer at a SEBI broker firm "
                "what changed and what operational action they must take."
            )
            resp = llm.complete_json(
                "You are a SEBI regulatory compliance expert.",
                prompt
            )
            if resp and isinstance(resp, dict) and "action" in resp:
                return str(resp["action"])
    except Exception:
        pass

    if t == "added":
        return "New obligation introduced. Establish a control and begin collecting evidence."
    if t == "removed":
        return "Obligation removed/superseded. Retire the mapped control after retention period; retain historical evidence."
    return "Obligation amended. Review the mapped control, update the obligation test, and re-attest evidence against the new requirement."



def operational_impact(db: Session, firm_id: str, change_event_ids: list[str]) -> list[dict]:
    """For each canonical change, compute the impact on THIS firm's overlay and
    draft a pending, cited Change Request. Human approves before anything moves.

    Only creates action items for changes that ACTUALLY affect the firm:
    - Amended/removed: only if the firm has controls linked to the old obligation
    - Added: always (firm needs to decide whether to create a new control)
    """
    controls = db.execute(select(Control).where(Control.firm_id == firm_id)).scalars().all()

    drafts: list[dict] = []
    for ce_id in change_event_ids:
        ce = db.get(ChangeEvent, ce_id)
        if not ce:
            continue
        old_ob_id = (ce.old_version or {}).get("id")
        new_ob_id = (ce.new_version or {}).get("id")
        target_ob_id = old_ob_id or new_ob_id

        affected_controls = [c.id for c in controls if target_ob_id in (c.obligation_ids or [])]
        # Also check if controls reference the NEW obligation (for amended cases)
        if new_ob_id and new_ob_id != target_ob_id:
            affected_controls += [c.id for c in controls if new_ob_id in (c.obligation_ids or [])]
            affected_controls = list(set(affected_controls))

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

        # Skip changes that don't impact this firm — UNLESS it's a new obligation
        # (firm may need to create a control for it).
        if not affected_controls and not affected_tests and ce.type != "added":
            continue

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
                "firm_id": firm_id,
                "type": ce.type,
                "affected_controls": affected_controls,
                "affected_tests": affected_tests,
                "operational_action_text": cr.operational_action_text,
                "citation": citation,
            }
        )

    if drafts:
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


def mark_applied(db: Session, change_request_id: str, actor: str) -> ChangeRequest:
    """Firm applied the change in their own systems and marks it done.
    Automatically updates the firm's controls to point to the new obligation
    version if the obligation was amended, or removes it if retired.
    """
    cr = db.get(ChangeRequest, change_request_id)
    if not cr:
        raise ValueError("change request not found")

    # Apply the modification to the controls ("did u want to modify if yes ok modify")
    if cr.change_event_id:
        ce = db.get(ChangeEvent, cr.change_event_id)
        if ce:
            old_ob_id = (ce.old_version or {}).get("id")
            new_ob_id = (ce.new_version or {}).get("id")

            if ce.type == "amended" and old_ob_id and new_ob_id:
                for ctrl_id in cr.affected_controls:
                    ctrl = db.get(Control, ctrl_id)
                    if ctrl and ctrl.obligation_ids:
                        ctrl.obligation_ids = [
                            new_ob_id if oid == old_ob_id else oid
                            for oid in ctrl.obligation_ids
                        ]
            elif ce.type == "removed" and old_ob_id:
                for ctrl_id in cr.affected_controls:
                    ctrl = db.get(Control, ctrl_id)
                    if ctrl and ctrl.obligation_ids:
                        ctrl.obligation_ids = [
                            oid for oid in ctrl.obligation_ids
                            if oid != old_ob_id
                        ]

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


def scan_firm_database_for_changes(
    db: Session, firm_id: str, document_id: str | None = None
) -> list[dict]:
    """Real-time live database inspection against SEBI regulation changes.

    1. Connects to the broker's live database table (or active control records)
       to fetch the laws/rules the firm currently follows.
    2. Compares against SEBI circular obligations (from document_id or all
       ingested regulations).
    3. Generates actionable ChangeRequests asking if the broker wants to
       modify their system to match the updated SEBI requirement.
    """
    from sqlalchemy import select
    from app.db.models import (
        Control,
        DataSource,
        Document,
        Firm,
        Obligation,
        ChangeRequest,
    )
    from sqlalchemy import create_engine, inspect, text
    from app.services.datasource_service import _normalise_uri

    firm = db.get(Firm, firm_id)
    if not firm:
        return []

    # Fetch live rules from connected database table if available
    live_rules: list[str] = []
    ds = db.execute(
        select(DataSource).where(DataSource.firm_id == firm_id)
    ).scalars().first()
    if ds and ds.connection_uri:
        try:
            engine = create_engine(
                _normalise_uri(ds.kind, ds.connection_uri), pool_pre_ping=True
            )
            inspector_obj = inspect(engine)
            tables = inspector_obj.get_table_names()
            if tables:
                with engine.connect() as conn:
                    rows = conn.execute(
                        text(f"SELECT * FROM {tables[0]} LIMIT 20")
                    ).mappings().all()
                    for r in rows:
                        for val in r.values():
                            if isinstance(val, str) and len(val) > 15:
                                live_rules.append(val)
            engine.dispose()
        except Exception:
            pass

    # Also include the firm's active Control descriptions as known followed rules
    controls = db.execute(
        select(Control).where(Control.firm_id == firm_id)
    ).scalars().all()
    followed_desc = [c.description for c in controls if c.description]
    all_followed_rules = live_rules + followed_desc

    # Fetch SEBI obligations to check against
    stmt = select(Obligation).where(
        Obligation.status.in_(["verified", "approved", "flagged"])
    )
    if document_id:
        stmt = stmt.where(Obligation.source_document_id == document_id)
    sebi_obs = db.execute(stmt).scalars().all()

    # Filter SEBI obligations relevant to this firm category
    relevant_obs = []
    for ob in sebi_obs:
        cats = {str(a.get("category", "")).lower() for a in (ob.applies_to or [])}
        if (
            not cats
            or firm.category.lower() in cats
            or "all" in cats
            or "any" in cats
        ):
            relevant_obs.append(ob)

    # Check if we already have pending ChangeRequests for this firm
    existing_crs = db.execute(
        select(ChangeRequest).where(
            ChangeRequest.firm_id == firm_id,
            ChangeRequest.status.in_(["pending", "approved"]),
        )
    ).scalars().all()
    existing_citations = {
        str((cr.citation or {}).get("obligation_id")) for cr in existing_crs
    }

    drafts: list[dict] = []
    for ob in relevant_obs:
        if ob.id in existing_citations:
            continue

        # Try to use Groq LLM to explain the rule modification cleanly
        guidance = (
            f"SEBI updated requirement [{ob.clause_path}]: {ob.verbatim_text[:180]}... "
            "Review your database rules and re-attest evidence."
        )
        try:
            from app.llm.client import get_llm

            llm = get_llm()
            if llm.enabled:
                prompt = (
                    f"SEBI Circular Clause: {ob.clause_path}\n"
                    f"Requirement: {ob.verbatim_text}\n"
                    "In 1 clear sentence, explain what changed and ask the broker if they want to modify their database control."
                )
                resp = llm.complete_json(
                    "You are a SEBI regulatory compliance advisor.", prompt
                )
                if resp and isinstance(resp, dict) and "action" in resp:
                    guidance = str(resp["action"])
        except Exception:
            pass

        cr = ChangeRequest(
            change_event_id=None,
            firm_id=firm_id,
            operational_action_text=guidance,
            citation={
                "obligation_id": ob.id,
                "clause_path": ob.clause_path,
                "document_id": ob.source_document_id,
                "live_rules_checked": len(all_followed_rules),
            },
            status="pending",
        )
        db.add(cr)
        db.flush()
        drafts.append(
            {
                "change_request_id": cr.id,
                "change_event_id": None,
                "firm_id": firm_id,
                "type": "amended",
                "affected_controls": [c.id for c in controls[:3]],
                "affected_tests": [],
                "operational_action_text": cr.operational_action_text,
                "citation": cr.citation,
            }
        )

    db.commit()
    return drafts


def _adopted_obligations_for_firm(db: Session, firm_id: str) -> list[Obligation]:
    """Return the obligations this firm has adopted (via active Controls)."""
    controls = db.execute(
        select(Control).where(Control.firm_id == firm_id, Control.status == "active")
    ).scalars().all()
    ob_ids: set[str] = set()
    for c in controls:
        if c.obligation_ids:
            ob_ids.update(c.obligation_ids)
    if not ob_ids:
        return []
    return list(
        db.execute(select(Obligation).where(Obligation.id.in_(list(ob_ids)))).scalars().all()
    )


def _existing_impact_event(
    db: Session,
    *,
    from_document_id: str | None,
    to_document_id: str,
    old_ob_id: str | None,
    new_ob_id: str | None,
) -> ChangeEvent | None:
    """Idempotency: has a ChangeEvent for this exact (from_doc, to_doc,
    old_ob, new_ob) pair already been recorded?"""
    stmt = select(ChangeEvent).where(ChangeEvent.to_document_id == to_document_id)
    if from_document_id is not None:
        stmt = stmt.where(ChangeEvent.from_document_id == from_document_id)
    for ev in db.execute(stmt).scalars().all():
        if (ev.old_version or {}).get("id") == old_ob_id and (ev.new_version or {}).get("id") == new_ob_id:
            return ev
    return None


def detect_impact_on_adopted_obligations(
    db: Session, new_document_id: str, firm_id: str
) -> list[dict]:
    """Compare a newly ingested document's obligations against everything the
    firm has already ADOPTED (i.e. has an active Control for) and raise an
    action item wherever a followed rule is amended or removed.

    This is the core Action Items behaviour: "does this new law affect any of
    my existing followed laws?". Newly *added* obligations are intentionally
    NOT surfaced here — they show up as adoption Suggestions on the Compliance
    page instead. Idempotent: re-running for the same (document, firm) pair
    will not create duplicate ChangeEvents or ChangeRequests.
    """
    document = db.get(Document, new_document_id)
    if document is None:
        return []

    new_obs = db.execute(
        select(Obligation).where(Obligation.source_document_id == new_document_id)
    ).scalars().all()
    if not new_obs:
        return []

    adopted = _adopted_obligations_for_firm(db, firm_id)
    if not adopted:
        return []

    diff_result = diff_obligations(
        [_ob_dict(o) for o in adopted], [_ob_dict(n) for n in new_obs]
    )

    # Only amended or removed rules are "impact on what the firm follows".
    changes = diff_result.amended + diff_result.removed
    if not changes:
        return []

    old_by_id = {o.id: o for o in adopted}
    new_change_event_ids: list[str] = []

    for change in changes:
        old_ob = old_by_id.get(change.old_id) if change.old_id else None
        from_doc_id = old_ob.source_document_id if old_ob else None

        existing = _existing_impact_event(
            db,
            from_document_id=from_doc_id,
            to_document_id=document.id,
            old_ob_id=change.old_id,
            new_ob_id=change.new_id,
        )
        if existing is not None:
            continue  # already tracked; don't duplicate

        ev = ChangeEvent(
            obligation_id=change.new_id or change.old_id,
            from_document_id=from_doc_id,
            to_document_id=document.id,
            type=change.type,
            old_version={"id": change.old_id, "text": change.old_text} if change.old_id else None,
            new_version={"id": change.new_id, "text": change.new_text} if change.new_id else None,
            similarity=change.similarity,
            field_changes=change.field_changes,
        )
        db.add(ev)
        db.flush()
        new_change_event_ids.append(ev.id)

    if not new_change_event_ids:
        return []

    return operational_impact(db, firm_id, new_change_event_ids)


def auto_change_detection(db: Session, document: Document) -> list[dict]:
    """Multi-firm fan-out of ``detect_impact_on_adopted_obligations``.

    Runs the impact check for every firm in the tenant so a single new upload
    populates Action Items across all firms that already follow related rules.
    Firms with no adopted obligations are skipped cheaply.
    """
    import structlog
    log = structlog.get_logger()

    all_drafts: list[dict] = []
    firms = db.execute(select(Firm)).scalars().all()
    for firm in firms:
        drafts = detect_impact_on_adopted_obligations(db, document.id, firm.id)
        if drafts:
            all_drafts.extend(drafts)
            log.info(
                "auto_change_detection.impact_generated",
                firm_id=firm.id,
                firm_name=firm.name,
                action_items=len(drafts),
            )

    log.info(
        "auto_change_detection.complete",
        document_id=document.id,
        total_action_items=len(all_drafts),
    )
    return all_drafts



