"""Dashboard API — aggregated compliance health for a firm."""
from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import ChangeRequest, Document, Firm, Obligation
from app.services import compliance_service

router = APIRouter(prefix="/firms/{firm_id}/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(firm_id: str, db: Session = Depends(get_db)):
    firm = db.get(Firm, firm_id)
    if not firm:
        raise HTTPException(404, "firm not found")

    evaluation = compliance_service.evaluate_firm(db, firm_id, firm.category)
    status_counts = Counter(r["status"] for r in evaluation["results"])
    gap_sev = Counter(g["severity"] for g in evaluation["gaps"])

    pending_cr = db.execute(
        select(func.count(ChangeRequest.id)).where(
            ChangeRequest.firm_id == firm_id, ChangeRequest.status == "pending"
        )
    ).scalar_one()

    recent_docs = db.execute(
        select(Document).order_by(Document.recorded_at.desc()).limit(5)
    ).scalars().all()

    total_obligations = db.execute(select(func.count(Obligation.id))).scalar_one()

    return {
        "firm": {"id": firm.id, "name": firm.name, "category": firm.category, "tier": firm.tier},
        "readiness": evaluation["readiness"],
        "obligations_in_scope": evaluation["total"],
        "canonical_obligations": total_obligations,
        "tests": {
            "green": status_counts.get("green", 0),
            "amber": status_counts.get("amber", 0),
            "red": status_counts.get("red", 0),
            "not_compilable": status_counts.get("not_compilable", 0),
        },
        "gaps": {
            "total": len(evaluation["gaps"]),
            "critical": gap_sev.get("critical", 0),
            "high": gap_sev.get("high", 0),
            "medium": gap_sev.get("medium", 0),
            "low": gap_sev.get("low", 0),
        },
        "pending_change_requests": pending_cr,
        "recent_documents": [
            {
                "id": d.id, "title": d.title, "circular_number": d.circular_number,
                "category": d.category, "status": d.status,
            }
            for d in recent_docs
        ],
    }
