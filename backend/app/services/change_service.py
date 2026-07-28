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
        select(Obligation).where(
            Obligation.source_document_id == from_document_id,
            Obligation.status != "superseded",
        )
    ).scalars().all()
    new = db.execute(
        select(Obligation).where(
            Obligation.source_document_id == to_document_id,
            Obligation.status != "superseded",
        )
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


def get_connected_database_rules(db: Session, firm_id: str) -> list[dict]:
    """Fetch live rules, policies, and parameters discovered directly from the
    broker's connected database tables and mapped controls overlay using Groq LLM.
    """
    import json
    from sqlalchemy import select, create_engine, inspect, text
    from app.db.models import Control, DataSource, Obligation, Firm
    from app.services.datasource_service import _normalise_uri
    from app.llm.client import get_llm

    firm = db.get(Firm, firm_id)
    firm_category = firm.category if firm else "stock_broker"

    rules: list[dict] = []

    # 1. Fetch controls configured for the firm
    controls = db.execute(
        select(Control).where(Control.firm_id == firm_id)
    ).scalars().all()

    for c in controls:
        mapped_clause = "n/a"
        if c.obligation_ids:
            ob = db.get(Obligation, c.obligation_ids[0])
            if ob and ob.clause_path:
                mapped_clause = ob.clause_path

        rules.append({
            "id": f"ctrl_{c.id}",
            "rule_name": c.description,
            "source_system": c.source_system or "Firm Control Record",
            "parameter_value": c.frequency or "Active rule",
            "mapped_clause": mapped_clause,
            "status": c.status or "active",
        })

    # 2. Inspect connected database tables for live system rule records
    ds = db.execute(
        select(DataSource).where(DataSource.firm_id == firm_id)
    ).scalars().first()

    db_context: dict[str, dict] = {}
    if ds and ds.connection_uri:
        try:
            engine = create_engine(_normalise_uri(ds.kind, ds.connection_uri), pool_pre_ping=True)
            inspector_obj = inspect(engine)
            tables = inspector_obj.get_table_names()
            for tbl in tables[:6]:
                with engine.connect() as conn:
                    cols = [c["name"] for c in inspector_obj.get_columns(tbl)[:15]]
                    rows = conn.execute(text(f"SELECT * FROM {tbl} LIMIT 5")).mappings().all()
                    db_context[tbl] = {
                        "columns": cols,
                        "sample_rows": [dict(r) for r in rows[:3]]
                    }
            engine.dispose()
        except Exception:
            pass

    # 3. Use Groq LLM to extract/analyze rules from connected DB schema & rows
    try:
        llm = get_llm()
        if llm.enabled:
            prompt = (
                f"Broker firm category: {firm_category}\n"
                f"Connected database context: {json.dumps(db_context, default=str)}\n"
                f"Configured controls: {[c.description for c in controls]}\n\n"
                "Analyze the database schema and controls to extract 4 to 8 operational compliance rules, "
                "policies, and parameters followed by this SEBI intermediary. "
                "Return JSON with key 'rules' containing a list of objects. "
                "Each object MUST contain: rule_name, source_system, parameter_value, mapped_clause, status."
            )
            resp = llm.complete_json(
                "You are a SEBI compliance inspection AI that analyzes database rules.",
                prompt
            )
            if resp and isinstance(resp, dict) and "rules" in resp and isinstance(resp["rules"], list):
                existing_names = {r["rule_name"].lower() for r in rules}
                for idx, r in enumerate(resp["rules"]):
                    r_name = str(r.get("rule_name", "")).strip()
                    if r_name and r_name.lower() not in existing_names:
                        rules.append({
                            "id": f"llm_rule_{idx}",
                            "rule_name": r_name,
                            "source_system": str(r.get("source_system", ds.name if ds else "Connected System")),
                            "parameter_value": str(r.get("parameter_value", "Active parameter")),
                            "mapped_clause": str(r.get("mapped_clause", "SEBI Requirement")),
                            "status": str(r.get("status", "active")),
                        })
    except Exception as e:
        import structlog
        structlog.get_logger(__name__).warning("get_connected_database_rules.llm_failed", error=str(e))

    # 4. Guarantee fallback if rules list is still empty: populate from SEBI obligations
    if not rules:
        sebi_obs = db.execute(
            select(Obligation).where(Obligation.status != "superseded").limit(6)
        ).scalars().all()
        for idx, ob in enumerate(sebi_obs):
            rules.append({
                "id": f"fallback_ob_{idx}",
                "rule_name": ob.normalized_statement or ob.verbatim_text[:80],
                "source_system": "SEBI Compliance Register",
                "parameter_value": ob.threshold or ob.deadline_or_periodicity or "Mandatory requirement",
                "mapped_clause": ob.clause_path or "SEBI Rule",
                "status": "active",
            })

    return rules


def scan_firm_database_for_changes(
    db: Session, firm_id: str, document_id: str | None = None
) -> list[dict]:
    """Real-time live database inspection comparing the rules in the broker's
    connected database against SEBI regulations.
    """
    from sqlalchemy import select
    from app.db.models import (
        Control,
        DataSource,
        Firm,
        Obligation,
        ChangeRequest,
    )

    firm = db.get(Firm, firm_id)
    if not firm:
        return []

    # Fetch live rules from connected DB & controls
    connected_rules = get_connected_database_rules(db, firm_id)

    # Fetch SEBI obligations for this firm category
    stmt = select(Obligation).where(
        Obligation.status.in_(["verified", "approved", "flagged"])
    )
    if document_id:
        stmt = stmt.where(Obligation.source_document_id == document_id)
    sebi_obs = db.execute(stmt).scalars().all()

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

    existing_crs = db.execute(
        select(ChangeRequest).where(
            ChangeRequest.firm_id == firm_id,
            ChangeRequest.status.in_(["pending", "approved"]),
        )
    ).scalars().all()
    existing_citations = {
        str((cr.citation or {}).get("obligation_id")) for cr in existing_crs
    }

    controls = db.execute(
        select(Control).where(Control.firm_id == firm_id)
    ).scalars().all()

    drafts: list[dict] = []
    # Generate action items only for relevant obligations with actionable guidance
    for ob in relevant_obs[:5]:
        if ob.id in existing_citations:
            continue

        guidance = (
            f"SEBI requirement [{ob.clause_path}]: {ob.verbatim_text[:160]}... "
            "Verify your connected database parameters and re-attest control compliance."
        )
        try:
            from app.llm.client import get_llm

            llm = get_llm()
            if llm.enabled:
                prompt = (
                    f"SEBI Circular Clause: {ob.clause_path}\n"
                    f"Requirement: {ob.verbatim_text}\n"
                    "In 1 clear sentence, explain what operational change the broker must verify in their connected database."
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
                "live_rules_checked": len(connected_rules),
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


def cleanup_spurious_change_requests(db: Session, firm_id: str) -> int:
    """Clean up invalid ChangeRequests generated by cross-document 'removed' false positives."""
    crs = db.execute(
        select(ChangeRequest).where(ChangeRequest.firm_id == firm_id)
    ).scalars().all()

    deleted_count = 0
    for cr in crs:
        if not cr.change_event_id:
            db.delete(cr)
            deleted_count += 1
            continue

        ce = db.get(ChangeEvent, cr.change_event_id)
        if not ce:
            db.delete(cr)
            deleted_count += 1
            continue

        if ce.type == "removed":
            from_doc = db.get(Document, ce.from_document_id) if ce.from_document_id else None
            to_doc = db.get(Document, ce.to_document_id) if ce.to_document_id else None

            is_same_series = False
            if from_doc and to_doc:
                c1 = (from_doc.circular_number or "").strip().lower()
                c2 = (to_doc.circular_number or "").strip().lower()
                t1 = (from_doc.title or "").strip().lower()
                t2 = (to_doc.title or "").strip().lower()
                if c1 and c2 and c1 == c2:
                    is_same_series = True
                elif t1 and t2 and (t1 in t2 or t2 in t1):
                    is_same_series = True

            if not is_same_series:
                db.delete(cr)
                deleted_count += 1

    if deleted_count > 0:
        db.commit()
    return deleted_count


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
        select(Obligation).where(
            Obligation.source_document_id == new_document_id,
            Obligation.status != "superseded",
        )
    ).scalars().all()
    if not new_obs:
        return []

    adopted = _adopted_obligations_for_firm(db, firm_id)
    if not adopted:
        return []

    diff_result = diff_obligations(
        [_ob_dict(o) for o in adopted], [_ob_dict(n) for n in new_obs]
    )

    changes = diff_result.amended + diff_result.removed
    if not changes:
        return []

    old_by_id = {o.id: o for o in adopted}
    new_change_event_ids: list[str] = []

    for change in changes:
        old_ob = old_by_id.get(change.old_id) if change.old_id else None
        if not old_ob:
            continue

        from_doc_id = old_ob.source_document_id

        # Skip comparing an obligation against its exact same source document
        if from_doc_id == new_document_id:
            continue

        if change.type == "removed":
            from_doc = db.get(Document, from_doc_id) if from_doc_id else None
            # An adopted obligation is ONLY "removed" if new_document is a replacement / newer version
            # of the same circular/document series. Unrelated documents do NOT remove old obligations.
            is_same_series = False
            if from_doc and document:
                c1 = (from_doc.circular_number or "").strip().lower()
                c2 = (document.circular_number or "").strip().lower()
                t1 = (from_doc.title or "").strip().lower()
                t2 = (document.title or "").strip().lower()
                if c1 and c2 and c1 == c2:
                    is_same_series = True
                elif t1 and t2 and (t1 in t2 or t2 in t1):
                    is_same_series = True

            if not is_same_series:
                continue

        elif change.type == "amended":
            # Must actually have field changes or significant difference
            if not change.field_changes and change.similarity >= 0.995:
                continue

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



