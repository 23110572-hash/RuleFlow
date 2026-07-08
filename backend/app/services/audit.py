"""Hash-chained audit log service.

Every state-changing action appends a tamper-evident entry:
    chain_hash = SHA256(prev_chain_hash + payload + ts)
The chain can be re-derived and verified at any time (see kernel.verify_chain).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditEntry
from app.kernel.hashing import GENESIS_HASH, chain_hash, verify_chain


def _latest_chain_hash(db: Session, firm_id: str | None) -> str:
    stmt = (
        select(AuditEntry.chain_hash)
        .where(AuditEntry.firm_id == firm_id)
        .order_by(AuditEntry.recorded_at.desc(), AuditEntry.id.desc())
        .limit(1)
    )
    row = db.execute(stmt).first()
    return row[0] if row else GENESIS_HASH


def record(
    db: Session,
    action: str,
    payload: dict,
    firm_id: str | None = None,
    actor: str = "system",
    before_hash: str | None = None,
    after_hash: str | None = None,
) -> AuditEntry:
    """Append an audit entry to the firm's chain (or the global chain if None)."""
    prev = _latest_chain_hash(db, firm_id)
    ts = datetime.now(timezone.utc).isoformat()
    ch = chain_hash(prev, payload, ts)
    entry = AuditEntry(
        firm_id=firm_id,
        actor=actor,
        action=action,
        payload=payload,
        before_hash=before_hash,
        after_hash=after_hash,
        prev_chain_hash=prev,
        chain_hash=ch,
        ts=ts,
    )
    db.add(entry)
    db.flush()
    return entry


def verify(db: Session, firm_id: str | None) -> tuple[bool, int | None]:
    """Re-derive and verify a firm's (or global) audit chain."""
    stmt = (
        select(AuditEntry)
        .where(AuditEntry.firm_id == firm_id)
        .order_by(AuditEntry.recorded_at.asc(), AuditEntry.id.asc())
    )
    entries = [
        {
            "prev_chain_hash": e.prev_chain_hash,
            "payload": e.payload,
            "ts": e.ts,
            "chain_hash": e.chain_hash,
        }
        for e in db.execute(stmt).scalars().all()
    ]
    return verify_chain(entries)
