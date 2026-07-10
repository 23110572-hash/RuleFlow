"""Compliance service (Flow C).

Runs the compiled Obligation Tests against the firm's evidence, classifies gaps
deterministically, computes a health score, and answers point-in-time queries
using the bitemporal register.

Also produces adoption Suggestions: canonical obligations that fit the firm's
category but have not yet been approved into its live compliance record. This
is what turns the platform from a passive checker into an active recommender.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agents.scoring import score_readiness
from app.db.models import Control, Document, Evidence, Gap, Obligation, ObligationTest
from app.kernel.gaps import GapFinding, classify_gaps, health_score
from app.kernel.obligation_tests import evaluate_test
from app.services import audit


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _active_firm_controls(db: Session, firm_id: str) -> list[Control]:
    """Return the firm's active Controls (skip retired) — one DB call."""
    return db.execute(
        select(Control).where(Control.firm_id == firm_id, Control.status == "active")
    ).scalars().all()


def _controls_by_obligation(controls: list[Control]) -> dict[str, list[Control]]:
    """Build an obligation_id -> [Control, ...] index from an already-fetched
    list of the firm's controls."""
    idx: dict[str, list[Control]] = {}
    for c in controls:
        for oid in c.obligation_ids or []:
            idx.setdefault(oid, []).append(c)
    return idx


def firm_obligations(
    db: Session,
    firm_id: str,
    category: str,  # kept for signature compat; scope is now Control-driven
    as_of: datetime | None = None,
) -> list[Obligation]:
    """Return every obligation this firm has ADOPTED into its live compliance
    record.

    Adopted = there is an active Control for the firm whose ``obligation_ids``
    list includes the obligation. The canonical library plus applies_to
    matching is now surfaced separately through the Compliance Suggestions
    endpoint — it does not silently enter Compliance & Tests any more.

    ``as_of`` still applies the bitemporal valid-time window so the Time
    Machine reconstructs what was in force at that instant.
    """
    controls = _active_firm_controls(db, firm_id)
    linked_ids: set[str] = set()
    for c in controls:
        linked_ids.update(c.obligation_ids or [])
    if not linked_ids:
        return []

    stmt = select(Obligation).where(Obligation.id.in_(list(linked_ids)))
    if as_of:
        # Valid-time reconstruction: which rule was IN FORCE as of `as_of`.
        stmt = stmt.where(or_(Obligation.valid_from.is_(None), Obligation.valid_from <= as_of))
        stmt = stmt.where(or_(Obligation.valid_to.is_(None), Obligation.valid_to > as_of))
    return list(db.execute(stmt).scalars().all())


def _evidence_dicts(db: Session, firm_id: str, control_ids: list[str], as_of: datetime | None) -> list[dict]:
    if not control_ids:
        return []
    stmt = select(Evidence).where(Evidence.firm_id == firm_id, Evidence.control_id.in_(control_ids))
    if as_of:
        stmt = stmt.where(Evidence.recorded_at <= as_of)
    rows = db.execute(stmt).scalars().all()
    return [
        {
            "id": e.id,
            "captured_at": e.captured_at,
            "valid_from": e.valid_from,
            "valid_to": e.valid_to,
            "metrics": e.metrics or {},
        }
        for e in rows
    ]


def evaluate_firm(db: Session, firm_id: str, category: str, as_of: datetime | None = None) -> dict:
    """Evaluate every in-scope obligation's test against evidence as of a time.
    Returns {results, gaps, readiness, total, as_of}."""
    as_of = as_of or _now()
    obligations = firm_obligations(db, firm_id, category, as_of)

    # Fetch the firm's controls ONCE and build an obligation->controls index,
    # instead of hitting the DB per obligation.
    all_controls = _active_firm_controls(db, firm_id)
    ctrl_index = _controls_by_obligation(all_controls)

    results: list[dict] = []
    gap_inputs: list[dict] = []

    for ob in obligations:
        test = db.execute(
            select(ObligationTest).where(ObligationTest.obligation_id == ob.id)
        ).scalars().first()
        spec = test.spec if test else None

        controls = ctrl_index.get(ob.id, [])
        control_ids = [c.id for c in controls]
        evidence = _evidence_dicts(db, firm_id, control_ids, as_of)

        outcome = evaluate_test(spec, evidence, as_of=as_of)

        # Persist last status on the test (only for live 'now' runs).
        if test is not None and as_of is not None and abs((as_of - _now()).total_seconds()) < 5:
            test.last_status = outcome.status
            test.last_detail = outcome.detail
            test.last_run_at = _now()

        results.append(
            {
                "obligation_id": ob.id,
                "clause_path": ob.clause_path,
                "modality": ob.modality,
                "status": outcome.status,
                "detail": outcome.detail,
                "spec": spec,
            }
        )
        gap_inputs.append(
            {
                "obligation": {"id": ob.id, "modality": ob.modality, "clause_path": ob.clause_path},
                "test_status": outcome.status,
                "test_detail": outcome.detail,
                "has_control": bool(controls),
                "evidence_count": len(evidence),
            }
        )

    findings: list[GapFinding] = classify_gaps(gap_inputs)

    # AI-rated Compliance Readiness (with a transparent computed fallback).
    status_counts = {"green": 0, "amber": 0, "red": 0, "not_compilable": 0}
    for r in results:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
    sev_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        sev_counts[f.severity] = sev_counts.get(f.severity, 0) + 1

    summary = {
        "obligations_total": len(obligations),
        "satisfied": status_counts["green"],
        "at_risk": status_counts["amber"],
        "failing": status_counts["red"],
        "attested": status_counts["not_compilable"],
        "gaps": sev_counts,
    }
    readiness = score_readiness(summary, fallback_score=health_score(len(obligations), findings))

    return {
        "results": results,
        "gaps": [f.to_dict() for f in findings],
        "readiness": readiness,
        "total": len(obligations),
        "as_of": as_of.isoformat(),
    }


def refresh_gaps(db: Session, firm_id: str, category: str) -> dict:
    """Recompute gaps live and persist them (replacing prior open gaps)."""
    evaluation = evaluate_firm(db, firm_id, category)
    db.query(Gap).filter(Gap.firm_id == firm_id, Gap.status == "open").delete()
    for g in evaluation["gaps"]:
        db.add(
            Gap(
                firm_id=firm_id,
                obligation_id=g["obligation_id"],
                reason=g["reason"],
                severity=g["severity"],
                detail=g["detail"],
                status="open",
            )
        )
    audit.record(
        db,
        action="compliance.gaps_refreshed",
        payload={"firm_id": firm_id, "open_gaps": len(evaluation["gaps"]), "readiness": evaluation["readiness"].get("score")},
        firm_id=firm_id,
    )
    db.commit()
    return evaluation


def point_in_time(db: Session, firm_id: str, category: str, as_of: datetime) -> dict:
    """Answer: 'what was required and what evidence existed as of date X?'"""
    return evaluate_firm(db, firm_id, category, as_of=as_of)



def _obligation_applies_to_firm(obligation: Obligation, firm_category: str) -> bool:
    """True when the obligation binds a firm of ``firm_category``.

    Rules:
    - Empty applies_to list => generic obligation, applies to everyone.
    - "all"/"any" category entry => applies to everyone.
    - Otherwise, the firm's own category (case-insensitive) must appear.
    """
    entries = obligation.applies_to or []
    if not entries:
        return True
    cats = {str(a.get("category", "")).lower() for a in entries}
    if "all" in cats or "any" in cats:
        return True
    return firm_category.lower() in cats


def suggest_obligations(
    db: Session,
    firm_id: str,
    firm_category: str,
    limit: int = 100,
) -> list[dict]:
    """Return canonical obligations RuleFlow recommends the firm adopt next.

    Selection criteria:
    1. Obligation is grounded (status in {'verified','approved'}) — flagged and
       rejected are excluded.
    2. applies_to includes the firm's category (or is generic).
    3. The firm has no active Control referencing this obligation yet.

    Ordered by clause_path so it reads like a table of contents. The response
    embeds the source document title/circular so the UI can render it directly
    without a second call.
    """
    # 1. Grounded obligations only.
    stmt = (
        select(Obligation)
        .where(Obligation.status.in_(["verified", "approved"]))
        .order_by(Obligation.clause_path)
        .limit(max(limit, 1) * 4)  # room for post-filter shrinkage
    )
    candidates = list(db.execute(stmt).scalars().all())
    if not candidates:
        return []

    # 2. What has the firm already adopted?
    adopted: set[str] = set()
    for c in _active_firm_controls(db, firm_id):
        adopted.update(c.obligation_ids or [])

    # 3. Preload source documents in one call.
    doc_ids = {o.source_document_id for o in candidates}
    docs = {
        d.id: d
        for d in db.execute(select(Document).where(Document.id.in_(list(doc_ids)))).scalars().all()
    }

    suggestions: list[dict] = []
    for o in candidates:
        if o.id in adopted:
            continue
        if not _obligation_applies_to_firm(o, firm_category):
            continue
        doc = docs.get(o.source_document_id)
        suggestions.append(
            {
                "obligation_id": o.id,
                "clause_path": o.clause_path,
                "verbatim_text": o.verbatim_text,
                "normalized_statement": o.normalized_statement,
                "modality": o.modality,
                "deadline_or_periodicity": o.deadline_or_periodicity,
                "threshold": o.threshold,
                "applies_to": o.applies_to or [],
                "citation": o.citation or {},
                "citation_fidelity": o.citation_fidelity,
                "status": o.status,
                "source_document": {
                    "id": doc.id if doc else o.source_document_id,
                    "title": doc.title if doc else None,
                    "circular_number": doc.circular_number if doc else None,
                    "category": doc.category if doc else None,
                }
                if doc
                else None,
            }
        )
        if len(suggestions) >= limit:
            break
    return suggestions
