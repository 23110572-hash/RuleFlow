"""Inspector service (Flow C) — thematic self-inspection.

Assembles the firm's REAL obligation + compliance status, runs the Inspector
Agent (Groq), validates every finding cites a real in-scope obligation, and
persists a draft Finding Report. Catches gaps before a real SEBI inspection.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.agents.inspector import run_inspection
from app.db.models import Finding, Obligation
from app.services import audit
from app.services.compliance_service import evaluate_firm


def _matches_theme(text: str, theme: str) -> bool:
    if not theme.strip():
        return True
    words = {w for w in theme.lower().split() if len(w) > 3}
    blob = text.lower()
    return any(w in blob for w in words) if words else True


def run_inspection_report(db: Session, firm_id: str, category: str, theme: str) -> dict:
    evaluation = evaluate_firm(db, firm_id, category)
    gaps_by_ob = {g["obligation_id"]: g for g in evaluation["gaps"]}

    scoped: list[dict] = []
    for r in evaluation["results"]:
        ob = db.get(Obligation, r["obligation_id"])
        if not ob:
            continue
        blob = f"{ob.clause_path} {ob.normalized_statement} {ob.verbatim_text}"
        if not _matches_theme(blob, theme):
            continue
        gap = gaps_by_ob.get(ob.id)
        scoped.append(
            {
                "obligation_id": ob.id,
                "clause_path": ob.clause_path,
                "modality": ob.modality,
                "test_status": r["status"],
                "test_detail": r["detail"],
                "gap_reason": gap["reason"] if gap else None,
                "gap_severity": gap["severity"] if gap else None,
                "citation": ob.citation or {},
            }
        )

    draft_findings = run_inspection(theme, scoped)

    report_id = uuid.uuid4().hex
    persisted = []
    for f in draft_findings:
        finding = Finding(
            firm_id=firm_id,
            report_id=report_id,
            theme=theme,
            obligation_id=f.obligation_id,
            severity=f.severity,
            observation=f.observation,
            citation=f.citation,
            recommendation=f.recommendation,
        )
        db.add(finding)
        persisted.append(f.to_dict())

    audit.record(
        db,
        action="inspection.completed",
        payload={"firm_id": firm_id, "report_id": report_id, "theme": theme, "findings": len(persisted)},
        firm_id=firm_id,
    )
    db.commit()
    return {
        "report_id": report_id,
        "theme": theme,
        "scope_size": len(scoped),
        "findings": persisted,
        "readiness": evaluation["readiness"],
    }
