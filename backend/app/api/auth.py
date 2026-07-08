"""Authentication API — register (account + firm + optional data source), login, me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import Firm, User
from app.security import create_token, hash_password, verify_password
from app.services import audit, datasource_service

router = APIRouter(prefix="/auth", tags=["auth"])


class FirmReg(BaseModel):
    name: str
    category: str
    tier: str | None = None


class DataSourceReg(BaseModel):
    name: str = ""
    kind: str = "postgresql"
    connection_uri: str


class RegisterIn(BaseModel):
    email: str
    password: str = Field(min_length=6)
    full_name: str = ""
    firm: FirmReg
    data_source: DataSourceReg | None = None


class LoginIn(BaseModel):
    email: str
    password: str


def _session_payload(db: Session, user: User) -> dict:
    firm = db.get(Firm, user.firm_id) if user.firm_id else None
    ds = None
    if firm:
        from app.db.models import DataSource

        ds_row = db.execute(select(DataSource).where(DataSource.firm_id == firm.id)).scalars().first()
        if ds_row:
            ds = {"id": ds_row.id, "name": ds_row.name, "kind": ds_row.kind, "status": ds_row.status,
                  "tables": (ds_row.detail or {}).get("tables", [])}
    return {
        "token": create_token(user.id, {"email": user.email}),
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role},
        "firm": {"id": firm.id, "name": firm.name, "category": firm.category, "tier": firm.tier} if firm else None,
        "data_source": ds,
    }


@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    existing = db.execute(select(User).where(User.email == str(body.email))).scalars().first()
    if existing:
        raise HTTPException(409, "an account with this email already exists")

    firm = Firm(name=body.firm.name, category=body.firm.category, tier=body.firm.tier)
    db.add(firm)
    db.flush()

    user = User(
        email=str(body.email),
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        firm_id=firm.id,
    )
    db.add(user)
    db.flush()
    audit.record(db, "account.registered", {"user_id": user.id, "firm_id": firm.id}, firm_id=firm.id, actor=user.email)
    db.commit()

    if body.data_source and body.data_source.connection_uri:
        datasource_service.save_data_source(
            db, firm.id, body.data_source.name, body.data_source.kind, body.data_source.connection_uri
        )

    db.refresh(user)
    return _session_payload(db, user)


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == str(body.email))).scalars().first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "invalid email or password")
    return _session_payload(db, user)


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _session_payload(db, user)
