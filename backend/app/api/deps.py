"""Shared API dependencies — current user / firm from the bearer token."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import Firm, User
from app.security import decode_token


def get_current_user(
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    payload = decode_token(authorization.split(" ", 1)[1])
    if not payload:
        raise HTTPException(401, "invalid or expired token")
    user = db.get(User, payload["sub"])
    if not user:
        raise HTTPException(401, "user not found")
    return user


def get_current_firm(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Firm:
    if not user.firm_id:
        raise HTTPException(400, "user has no firm")
    firm = db.get(Firm, user.firm_id)
    if not firm:
        raise HTTPException(404, "firm not found")
    return firm


def require_firm_data_source(firm_id: str, db: Session = Depends(get_db)) -> None:
    """Gate for features that need the firm's own database (compliance
    evaluation, self-inspection, operational-impact edits). Returns 403 when no
    data source is connected, so a firm that skipped connection at signup is
    blocked until it connects one from Settings. `firm_id` is taken from the
    route path."""
    from app.services import datasource_service

    if not datasource_service.firm_has_data_source(db, firm_id):
        raise HTTPException(
            403, "Connect your firm's data source (Settings) to use this feature."
        )
