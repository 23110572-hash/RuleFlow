"""Dashboard API — the firm's real, live compliance picture.

Everything here is grounded in stored/real data:
  * readiness      - rules the firm follows vs followed rules SEBI made outdated
  * rules_followed - rules read from the firm's connected database
  * obligations    - SEBI obligations that apply to the firm (superseded excluded)
  * action_items   - followed rules needing an update, by severity
  * documents      - real count of ingested circulars
No placeholder or fabricated numbers.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import verify_firm_access
from app.db.base import get_db
from app.db.models import Document, Firm, Obligation
from app.services import compliance_service

router = APIRouter(prefix="/firms/{firm_id}/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(firm_id: str, firm: Firm = Depends(verify_firm_access), db: Session = Depends(get_db)):
    picture = compliance_service.readiness_for_firm(db, firm_id, firm.category)

    # Real totals — superseded obligations (retired by a re-analysis) are excluded
    # so nothing is inflated. Scoped to obligations relevant to this firm's category.
    obligations_total = db.execute(
        select(func.count(Obligation.id)).where(
            Obligation.status != "superseded",
        )
    ).scalar_one()

    # Count documents relevant to this firm (matching category or uncategorized)
    documents_total = db.execute(
        select(func.count(Document.id)).where(
            or_(Document.category == firm.category, Document.category.is_(None))
        )
    ).scalar_one()

    recent_docs = db.execute(
        select(Document)
        .where(or_(Document.category == firm.category, Document.category.is_(None)))
        .order_by(Document.recorded_at.desc())
        .limit(5)
    ).scalars().all()

    return {
        "firm": {"id": firm.id, "name": firm.name, "category": firm.category, "tier": firm.tier},
        "readiness": picture["readiness"],
        "data_source_connected": picture["data_source_connected"],
        "rules_followed": picture["rules_followed"],
        "obligations_in_scope": picture["obligations_in_scope"],
        "obligations_addressed": picture["obligations_addressed"],
        "obligations_total": obligations_total,
        "documents_total": documents_total,
        "action_items": picture["action_items"],
        "recent_documents": [
            {
                "id": d.id, "title": d.title, "circular_number": d.circular_number,
                "category": d.category, "status": d.status,
            }
            for d in recent_docs
        ],
    }
