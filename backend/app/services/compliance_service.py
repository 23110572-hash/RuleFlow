"""Compliance service (Flow C).

Runs the compiled Obligation Tests against the firm's evidence, classifies gaps
deterministically, computes a health score, and answers point-in-time queries
using the bitemporal register.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agents.scoring import score_readiness
from app.db.models import Control, Evidence, Gap, Obligation, ObligationTest
from app.kernel.gaps import GapFinding, classify_gaps, health_score
from app.kernel.obligation_tests import evaluate_test
from app.services import audit


def _now() -> datetime:
    return datetime.now(timezone.utc)


def firm_obligations(db: Session, firm_id: str, category: str, as_of: datetime | None = None) -> list[Obligation]:
    """Obligations in the firm's scope: those referenced by its controls, plus
    canonical obligations whose applies_to includes the firm's category. Only
    obligations valid/known as of `as_of` (bitemporal)."""
    controls = db.execute(select(Control).where(Control.firm_id == firm_id)).scalars().all()
    linked_ids: set[str] = set()
    for c in controls:
        linked_ids.update(c.obligation_ids or [])

    stmt = select(Obligation).where(Obligation.status.in_(["verified", "approved"]))
    if as_of:
        # Valid-time reconstruction: which rule was IN FORCE as of `as_of`.
        stmt = stmt.where(or_(Obligation.valid_from.is_(None), Obligation.valid_from <= as_of))
        stmt = stmt.where(or_(Obligation.valid_to.is_(None), Obligation.valid_to > as_of))
    obligations = db.execute(stmt).scalars().all()

    scoped = []
    for o in obligations:
        cats = {a.get("category") for a in (o.applies_to or [])}
        if o.id in linked_ids or category in cats:
            scoped.append(o)
    return scoped


def _controls_for_obligation(db: Session, firm_id: str, obligation_id: str) -> list[Control]:
    controls = db.execute(select(Control).where(Control.firm_id == firm_id)).scalars().all()
    return [c for c in controls if obligation_id in (c.obligation_ids or [])]


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
    Returns {results, gaps, health, total}."""
    as_of = as_of or _now()
    obligations = firm_obligations(db, firm_id, category, as_of)

    results: list[dict] = []
    gap_inputs: list[dict] = []

    for ob in obligations:
        test = db.execute(
            select(ObligationTest).where(ObligationTest.obligation_id == ob.id)
        ).scalars().first()
        spec = test.spec if test else None

        controls = _controls_for_obligation(db, firm_id, ob.id)
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
