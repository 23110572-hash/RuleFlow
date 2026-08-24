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
from app.db.models import (
    GROUNDED_STATUSES,
    ChangeRequest,
    Control,
    Document,
    Evidence,
    Firm,
    Gap,
    Obligation,
    ObligationTest,
)
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

    # Readiness reflects the rules the firm follows vs the followed rules SEBI
    # has made outdated — the same real model the dashboard uses — not the
    # evidence-test pass rate (which is 0 before any evidence is imported).
    readiness = readiness_for_firm(db, firm_id, category)["readiness"]

    return {
        "results": results,
        "gaps": [f.to_dict() for f in findings],
        "readiness": readiness,
        "total": len(obligations),
        "as_of": as_of.isoformat(),
    }


def _followed_rules_safe(db: Session, firm_id: str) -> tuple[list[dict], bool]:
    """Rules the firm follows, read from its connected database. Never raises —
    a dashboard must render even if the external database is briefly unreachable."""
    from app.services import change_service

    try:
        info = change_service.get_connected_database_rules(db, firm_id)
        return info.get("rules", []), bool(info.get("connected"))
    except Exception:
        return [], False


def readiness_for_firm(db: Session, firm_id: str, category: str) -> dict:
    """The one real compliance picture, shared by the dashboard and the
    Compliance page.

    Compares the rules the firm actually follows (connected database) and the
    SEBI obligations it has adopted against the obligations that apply to it, and
    treats open action items (followed rules a SEBI change has made outdated) as
    live risk. Everything here is grounded in stored/real data — no fabricated
    counts, no placeholder scores.
    """
    firm = db.get(Firm, firm_id)
    cat = (firm.category if firm else category) or ""

    followed_rules, connected = _followed_rules_safe(db, firm_id)

    # Obligations the firm has adopted (active controls) = rules it commits to.
    adopted_ids: set[str] = set()
    for c in _active_firm_controls(db, firm_id):
        adopted_ids.update(c.obligation_ids or [])

    # SEBI obligations that apply to this firm's category (grounded, live).
    grounded = db.execute(
        select(Obligation).where(Obligation.status.in_(GROUNDED_STATUSES))
    ).scalars().all()
    relevant = [o for o in grounded if _obligation_applies_to_firm(o, cat)]
    relevant_ids = {o.id for o in relevant}
    obligations_addressed = len(adopted_ids & relevant_ids)
    ob_by_id = {o.id: o for o in grounded}

    # Open action items = followed rules SEBI has made outdated (real risk).
    pending = db.execute(
        select(ChangeRequest).where(
            ChangeRequest.firm_id == firm_id, ChangeRequest.status == "pending"
        )
    ).scalars().all()
    grounded_pending = [cr for cr in pending if (cr.citation or {}).get("followed_rule")]

    def _severity(cr: ChangeRequest) -> str:
        ob = ob_by_id.get((cr.citation or {}).get("obligation_id"))
        modality = (ob.modality if ob else "shall").lower()
        if modality == "shall":
            return "high"
        # "best_judgment" is the pre-rename spelling of "judgement_based".
        if modality in {"judgement_based", "best_judgment"}:
            return "medium"
        return "low"

    weight = {"high": 1.0, "medium": 0.6, "low": 0.3}
    sev_counts = {"high": 0, "medium": 0, "low": 0}
    open_weighted = 0.0
    for cr in grounded_pending:
        s = _severity(cr)
        sev_counts[s] += 1
        open_weighted += weight[s]

    readiness = score_readiness(
        firm_category=cat,
        rules_followed=len(followed_rules),
        obligations_in_scope=len(relevant),
        obligations_addressed=obligations_addressed,
        open_action_items=len(grounded_pending),
        open_weighted=open_weighted,
        followed_rule_names=[str(r.get("rule_name") or "") for r in followed_rules],
        risk_summaries=[
            str((cr.citation or {}).get("what_changed") or cr.operational_action_text or "")
            for cr in grounded_pending
        ],
    )

    return {
        "readiness": readiness,
        "rules_followed": len(followed_rules),
        "data_source_connected": connected,
        "obligations_in_scope": len(relevant),
        "obligations_addressed": obligations_addressed,
        "action_items": {
            "total": len(grounded_pending),
            "high": sev_counts["high"],
            "medium": sev_counts["medium"],
            "low": sev_counts["low"],
        },
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
    document_id: str | None = None,
) -> list[dict]:
    """Return canonical obligations RuleFlow recommends the firm adopt next.

    Selection criteria:
    1. The quote is trusted: status in {'verified', 'human_verified',
       'approved'}. 'flagged' is excluded — an obligation whose wording nobody
       has confirmed should not be proposed for adoption; confirm it on the
       obligation first and it appears here.
    2. applies_to includes the firm's category (or is generic/"all"). Note this
       genuinely filters now that applies_to is populated, so a stock-broker
       regulation will not be suggested to an investment adviser.
    3. The firm has no active Control referencing this obligation yet.
    4. If ``document_id`` is given, only that document's obligations are
       considered, so the UI can offer document-by-document suggestions.

    Ordered by position in the source document, so the list reads in the order a
    reviewer would encounter the provisions. The response embeds the source
    document title/circular so the UI can render it without a second call.
    """
    # Only ever suggest from this firm's own documents (tenant isolation).
    firm_doc_ids = set(
        db.execute(select(Document.id).where(Document.firm_id == firm_id)).scalars().all()
    )
    if not firm_doc_ids:
        return []

    # Optionally narrow to the single document the user selected.
    if document_id is not None:
        if document_id not in firm_doc_ids:
            return []  # not this firm's document
        scope_doc_ids: list[str] = [document_id]
    else:
        scope_doc_ids = list(firm_doc_ids)

    # 1. What has the firm already adopted? Needed BEFORE the query so the
    # exclusion happens in SQL. Previously the query took limit*4 rows and then
    # discarded adopted ones in Python, so a firm that had adopted the first
    # few hundred obligations got an EMPTY list while matches sat just beyond
    # the window.
    adopted: set[str] = set()
    for c in _active_firm_controls(db, firm_id):
        adopted.update(c.obligation_ids or [])

    # 2. Obligations whose wording is trusted, from the in-scope documents.
    stmt = select(Obligation).where(
        Obligation.source_document_id.in_(scope_doc_ids),
        # A reviewer who confirmed the wording has done the same job the
        # kernel does, so those obligations are suggestable too.
        Obligation.status.in_(["verified", "human_verified", "approved"]),
    )
    if adopted:
        stmt = stmt.where(Obligation.id.notin_(list(adopted)))
    candidates = list(db.execute(stmt).scalars().all())
    if not candidates:
        return []

    # Read in document order. clause_path cannot do this: it is a string, so
    # "Ch.II 10" sorts before "Ch.II 2". The citation offset is the position in
    # the source text, which is exactly the order a reviewer reads in.
    candidates.sort(
        key=lambda o: (
            (o.citation or {}).get("char_start", 1 << 62),
            o.clause_path or "",
        )
    )

    # 3. Preload source documents in one call.
    doc_ids = {o.source_document_id for o in candidates}
    docs = {
        d.id: d
        for d in db.execute(select(Document).where(Document.id.in_(list(doc_ids)))).scalars().all()
    }

    suggestions: list[dict] = []
    for o in candidates:
        # Category matching stays in Python: applies_to is a JSON column, so
        # this cannot be expressed portably in SQL.
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
