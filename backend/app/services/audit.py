"""Hash-chained audit log service.

Every state-changing action appends a tamper-evident entry:
    chain_hash = SHA256(prev_chain_hash + payload + ts)
The chain can be re-derived and verified at any time (see kernel.verify_chain).
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditEntry
from app.kernel.hashing import GENESIS_HASH, chain_hash, verify_chain

# The chain is ordered by recorded_at, with the primary key as tiebreak. That key
# is a random uuid4, so when two entries share a timestamp the tiebreak is
# arbitrary and the order entries were WRITTEN in can differ from the order they
# sort in — which makes verify() report a break in a chain nobody touched.
#
# Entries routinely share a millisecond: an upload, the change analysis it
# triggers and a gaps refresh all happen inside one request. So hand out strictly
# increasing timestamps and the ordering becomes total, leaving the random
# tiebreak with nothing to decide.
#
# Single-process only. Behind several server workers, use a database sequence.
_clock_lock = threading.Lock()
_last_issued: datetime | None = None


def _monotonic_now() -> datetime:
    global _last_issued
    with _clock_lock:
        now = datetime.now(timezone.utc)
        if _last_issued is not None and now <= _last_issued:
            now = _last_issued + timedelta(microseconds=1)
        _last_issued = now
        return now


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
    now = _monotonic_now()
    ts = now.isoformat()
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
        # Set explicitly rather than left to the column default, so the stored
        # order matches the ts that went into the hash.
        recorded_at=now,
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
