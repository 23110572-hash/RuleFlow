"""Inspector API — thematic self-inspection producing a draft Finding Report."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_firm_data_source
from app.db.base import get_db
from app.db.models import Finding, Firm
from app.services import inspector_service

router = APIRouter(
    prefix="/firms/{firm_id}/inspector",
    tags=["inspector"],
    dependencies=[Depends(require_firm_data_source)],
)


@router.post("/run")
def run(firm_id: str, theme: str = Body("", embed=True), db: Session = Depends(get_db)):
    f = db.get(Firm, firm_id)
    if not f:
        raise HTTPException(404, "firm not found")
    return inspector_service.run_inspection_report(db, firm_id, f.category, theme)


@router.get("/reports/{report_id}")
def get_report(firm_id: str, report_id: str, db: Session = Depends(get_db)):
    rows = db.execute(
        select(Finding).where(Finding.firm_id == firm_id, Finding.report_id == report_id)
    ).scalars().all()
    if not rows:
        raise HTTPException(404, "report not found")
    return {
        "report_id": report_id,
        "theme": rows[0].theme,
        "findings": [
            {
                "id": r.id, "obligation_id": r.obligation_id, "severity": r.severity,
                "observation": r.observation, "recommendation": r.recommendation, "citation": r.citation,
            }
            for r in rows
        ],
    }
