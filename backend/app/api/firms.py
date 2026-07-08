"""Firms API — the tenant overlay: firm, controls, evidence."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import Control, Evidence, Firm
from app.kernel.hashing import sha256_hex
from app.schemas.models import (
    ControlIn,
    ControlOut,
    EvidenceIn,
    EvidenceOut,
    FirmIn,
    FirmOut,
)
from app.services import audit

router = APIRouter(prefix="/firms", tags=["firms"])


@router.get("", response_model=list[FirmOut])
def list_firms(db: Session = Depends(get_db)):
    firms = db.execute(select(Firm).order_by(Firm.recorded_at)).scalars().all()
    return [FirmOut(id=f.id, name=f.name, category=f.category, tier=f.tier, profile=f.profile or {}) for f in firms]


@router.post("", response_model=FirmOut)
def create_firm(body: FirmIn, db: Session = Depends(get_db)):
    firm = Firm(name=body.name, category=body.category, tier=body.tier, profile=body.profile)
    db.add(firm)
    db.flush()
    audit.record(db, "firm.created", {"firm_id": firm.id, "name": firm.name}, firm_id=firm.id)
    db.commit()
    db.refresh(firm)
    return FirmOut(id=firm.id, name=firm.name, category=firm.category, tier=firm.tier, profile=firm.profile or {})


@router.get("/{firm_id}", response_model=FirmOut)
def get_firm(firm_id: str, db: Session = Depends(get_db)):
    f = db.get(Firm, firm_id)
    if not f:
        raise HTTPException(404, "firm not found")
    return FirmOut(id=f.id, name=f.name, category=f.category, tier=f.tier, profile=f.profile or {})


# ---- controls ----

@router.get("/{firm_id}/controls", response_model=list[ControlOut])
def list_controls(firm_id: str, db: Session = Depends(get_db)):
    controls = db.execute(select(Control).where(Control.firm_id == firm_id)).scalars().all()
    return [
        ControlOut(
            id=c.id, firm_id=c.firm_id, obligation_ids=c.obligation_ids or [],
            description=c.description, type=c.type, owner_role=c.owner_role,
            frequency=c.frequency, status=c.status,
        )
        for c in controls
    ]


@router.post("/{firm_id}/controls", response_model=ControlOut)
def create_control(firm_id: str, body: ControlIn, db: Session = Depends(get_db)):
    if not db.get(Firm, firm_id):
        raise HTTPException(404, "firm not found")
    c = Control(
        firm_id=firm_id, obligation_ids=body.obligation_ids, description=body.description,
        type=body.type, owner_role=body.owner_role, frequency=body.frequency,
    )
    db.add(c)
    db.flush()
    audit.record(db, "control.created", {"control_id": c.id, "obligations": body.obligation_ids}, firm_id=firm_id)
    db.commit()
    db.refresh(c)
    return ControlOut(
        id=c.id, firm_id=c.firm_id, obligation_ids=c.obligation_ids or [], description=c.description,
        type=c.type, owner_role=c.owner_role, frequency=c.frequency, status=c.status,
    )


# ---- evidence ----

@router.get("/{firm_id}/evidence", response_model=list[EvidenceOut])
def list_evidence(firm_id: str, db: Session = Depends(get_db)):
    rows = db.execute(select(Evidence).where(Evidence.firm_id == firm_id)).scalars().all()
    return [
        EvidenceOut(
            id=e.id, firm_id=e.firm_id, control_id=e.control_id, description=e.description,
            source_system=e.source_system, hash=e.hash, metrics=e.metrics or {}, captured_at=e.captured_at,
        )
        for e in rows
    ]


@router.post("/{firm_id}/evidence", response_model=EvidenceOut)
def add_evidence(firm_id: str, body: EvidenceIn, db: Session = Depends(get_db)):
    if not db.get(Firm, firm_id):
        raise HTTPException(404, "firm not found")
    captured = body.captured_at or datetime.now(timezone.utc)
    ehash = sha256_hex(f"{firm_id}{body.control_id}{body.description}{captured.isoformat()}")
    e = Evidence(
        firm_id=firm_id, control_id=body.control_id, description=body.description,
        source_system=body.source_system, metrics=body.metrics, hash=ehash,
        captured_at=captured, valid_from=body.valid_from or captured, valid_to=body.valid_to,
    )
    db.add(e)
    db.flush()
    audit.record(db, "evidence.captured", {"evidence_id": e.id, "hash": ehash}, firm_id=firm_id, after_hash=ehash)
    db.commit()
    db.refresh(e)
    return EvidenceOut(
        id=e.id, firm_id=e.firm_id, control_id=e.control_id, description=e.description,
        source_system=e.source_system, hash=e.hash, metrics=e.metrics or {}, captured_at=e.captured_at,
    )
