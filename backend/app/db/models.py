"""ORM models — the actual product asset: a bitemporal, two-layer,
citation-grounded compliance register.

Two layers:
  CANONICAL  (shared across all firms; deduped by circular_number + content_hash)
    Document, Obligation, ObligationTest, CoverageReport, ChangeEvent
  FIRM OVERLAY (private per tenant, scoped by firm_id)
    Firm, Control, Evidence, Gap, ChangeRequest, Interpretation, AuditEntry

Two time axes everywhere relevant:
  valid_from / valid_to  -> when the rule/evidence is in force
  recorded_at            -> when we knew it (transaction time)
This enables point-in-time reconstruction in a single query.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ────────────────────────── CANONICAL LAYER ──────────────────────────

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    circular_number: Mapped[str | None] = mapped_column(String(255), index=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(Text, default="")
    issue_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    category: Mapped[str | None] = mapped_column(String(128), index=True)
    source_url: Mapped[str | None] = mapped_column(Text)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    artifact_ref: Mapped[str | None] = mapped_column(Text)  # stored PDF path/key
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="ingested")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    obligations: Mapped[list["Obligation"]] = relationship(back_populates="document")


class Obligation(Base):
    __tablename__ = "obligations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    source_document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    clause_path: Mapped[str] = mapped_column(String(255), default="", index=True)
    verbatim_text: Mapped[str] = mapped_column(Text, default="")
    normalized_statement: Mapped[str] = mapped_column(Text, default="")
    modality: Mapped[str] = mapped_column(String(32), default="shall")  # shall|may|best_judgment
    trigger_condition: Mapped[str | None] = mapped_column(Text)
    deadline_or_periodicity: Mapped[str | None] = mapped_column(String(255))
    threshold: Mapped[str | None] = mapped_column(String(255))
    applies_to: Mapped[list] = mapped_column(JSON, default=list)  # [{category, tier}]
    version: Mapped[int] = mapped_column(Integer, default=1)

    # Citation (grounding)
    citation: Mapped[dict] = mapped_column(JSON, default=dict)  # {page,char_start,char_end,source_hash}
    citation_fidelity: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="proposed")  # proposed|verified|approved|rejected|superseded

    # Bitemporal
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    document: Mapped["Document"] = relationship(back_populates="obligations")
    tests: Mapped[list["ObligationTest"]] = relationship(back_populates="obligation")


class ObligationTest(Base):
    __tablename__ = "obligation_tests"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    obligation_id: Mapped[str] = mapped_column(ForeignKey("obligations.id"), index=True)
    spec: Mapped[dict | None] = mapped_column(JSON)   # compiled test spec (None => human-attested)
    evaluator: Mapped[str] = mapped_column(String(64), default="kernel")
    last_status: Mapped[str | None] = mapped_column(String(32))
    last_detail: Mapped[str | None] = mapped_column(Text)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    obligation: Mapped["Obligation"] = relationship(back_populates="tests")


class CoverageReport(Base):
    __tablename__ = "coverage_reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    signals_total: Mapped[int] = mapped_column(Integer, default=0)
    extracted: Mapped[int] = mapped_column(Integer, default=0)
    not_applicable: Mapped[int] = mapped_column(Integer, default=0)
    unaccounted: Mapped[int] = mapped_column(Integer, default=0)
    coverage_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)  # full signal breakdown
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ChangeEvent(Base):
    __tablename__ = "change_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    obligation_id: Mapped[str | None] = mapped_column(String(32), index=True)
    from_document_id: Mapped[str | None] = mapped_column(String(32))
    to_document_id: Mapped[str | None] = mapped_column(String(32))
    type: Mapped[str] = mapped_column(String(16))  # added|amended|removed
    old_version: Mapped[dict | None] = mapped_column(JSON)
    new_version: Mapped[dict | None] = mapped_column(JSON)
    similarity: Mapped[float] = mapped_column(Float, default=0.0)
    field_changes: Mapped[dict] = mapped_column(JSON, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ────────────────────────── ACCOUNTS ──────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255), default="")
    firm_id: Mapped[str | None] = mapped_column(ForeignKey("firms.id"), index=True)
    role: Mapped[str] = mapped_column(String(64), default="compliance_officer")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DataSource(Base):
    """A broker's EXISTING database/system that RuleFlow connects to in order to
    pull compliance evidence. Connection is tested on save; secrets stay server-side."""
    __tablename__ = "data_sources"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    firm_id: Mapped[str] = mapped_column(ForeignKey("firms.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    kind: Mapped[str] = mapped_column(String(32), default="postgresql")  # postgresql|mysql|sqlite|api
    connection_uri: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="pending")  # connected|error|pending
    detail: Mapped[dict] = mapped_column(JSON, default=dict)  # discovered tables, last error, etc.
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ────────────────────────── FIRM OVERLAY ──────────────────────────

class Firm(Base):
    __tablename__ = "firms"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(128), index=True)
    tier: Mapped[str | None] = mapped_column(String(64))
    profile: Mapped[dict] = mapped_column(JSON, default=dict)  # e.g. {is_qsb, is_dp, ...}
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Control(Base):
    __tablename__ = "controls"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    firm_id: Mapped[str] = mapped_column(ForeignKey("firms.id"), index=True)
    obligation_ids: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    type: Mapped[str | None] = mapped_column(String(64))
    owner_role: Mapped[str | None] = mapped_column(String(128))
    frequency: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="active")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    firm_id: Mapped[str] = mapped_column(ForeignKey("firms.id"), index=True)
    control_id: Mapped[str | None] = mapped_column(ForeignKey("controls.id"), index=True)
    artifact_ref: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    source_system: Mapped[str | None] = mapped_column(String(128))
    hash: Mapped[str | None] = mapped_column(String(64))
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)  # numeric readings for threshold tests
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Bitemporal
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Gap(Base):
    __tablename__ = "gaps"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    firm_id: Mapped[str] = mapped_column(ForeignKey("firms.id"), index=True)
    obligation_id: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[str] = mapped_column(String(32))  # missing|stale|weak|contradictory
    severity: Mapped[str] = mapped_column(String(16))
    detail: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="open")  # open|remediating|closed
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ChangeRequest(Base):
    __tablename__ = "change_requests"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    firm_id: Mapped[str] = mapped_column(ForeignKey("firms.id"), index=True)
    change_event_id: Mapped[str | None] = mapped_column(String(32), index=True)
    affected_controls: Mapped[list] = mapped_column(JSON, default=list)
    affected_evidence: Mapped[list] = mapped_column(JSON, default=list)
    affected_tests: Mapped[list] = mapped_column(JSON, default=list)
    operational_action_text: Mapped[str] = mapped_column(Text, default="")
    citation: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|approved|applied|escalated|rejected
    approved_by: Mapped[str | None] = mapped_column(String(128))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Interpretation(Base):
    __tablename__ = "interpretations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    firm_id: Mapped[str] = mapped_column(ForeignKey("firms.id"), index=True)
    obligation_id: Mapped[str] = mapped_column(String(32), index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    sources: Mapped[list] = mapped_column(JSON, default=list)
    author: Mapped[str | None] = mapped_column(String(128))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditEntry(Base):
    __tablename__ = "audit_entries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    firm_id: Mapped[str | None] = mapped_column(String(32), index=True)
    actor: Mapped[str] = mapped_column(String(128), default="system")
    action: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    before_hash: Mapped[str | None] = mapped_column(String(64))
    after_hash: Mapped[str | None] = mapped_column(String(64))
    prev_chain_hash: Mapped[str] = mapped_column(String(64))
    chain_hash: Mapped[str] = mapped_column(String(64))
    ts: Mapped[str] = mapped_column(String(40))  # ISO string, part of chain material
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Finding(Base):
    """Inspector Agent output: a draft finding within an inspection report."""
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    firm_id: Mapped[str] = mapped_column(ForeignKey("firms.id"), index=True)
    report_id: Mapped[str] = mapped_column(String(32), index=True)
    theme: Mapped[str] = mapped_column(String(255), default="")
    obligation_id: Mapped[str | None] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    observation: Mapped[str] = mapped_column(Text, default="")
    citation: Mapped[dict] = mapped_column(JSON, default=dict)
    recommendation: Mapped[str] = mapped_column(Text, default="")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
