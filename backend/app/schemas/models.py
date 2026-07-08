"""API schemas (Pydantic v2)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class IngestTextIn(BaseModel):
    title: str
    text: str
    circular_number: str | None = None
    category: str | None = None
    issue_date: datetime | None = None
    source_url: str | None = None
    is_public: bool = True


class DocumentOut(BaseModel):
    id: str
    circular_number: str | None
    content_hash: str
    title: str
    category: str | None
    issue_date: datetime | None
    source_url: str | None
    is_public: bool
    page_count: int
    status: str
    obligation_count: int = 0
    coverage: dict | None = None


class CitationOut(BaseModel):
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    source_hash: str | None = None


class ObligationOut(BaseModel):
    id: str
    source_document_id: str
    clause_path: str
    verbatim_text: str
    normalized_statement: str
    modality: str
    trigger_condition: str | None = None
    deadline_or_periodicity: str | None = None
    threshold: str | None = None
    applies_to: list[dict[str, Any]] = Field(default_factory=list)
    version: int
    citation: dict = Field(default_factory=dict)
    citation_fidelity: float
    status: str


class CoverageOut(BaseModel):
    document_id: str
    signals_total: int
    extracted: int
    not_applicable: int
    unaccounted: int
    coverage_ratio: float
    is_complete: bool
    unaccounted_signals: list[dict] = Field(default_factory=list)


class FirmIn(BaseModel):
    name: str
    category: str
    tier: str | None = None
    profile: dict = Field(default_factory=dict)


class FirmOut(BaseModel):
    id: str
    name: str
    category: str
    tier: str | None
    profile: dict


class ControlIn(BaseModel):
    obligation_ids: list[str] = Field(default_factory=list)
    description: str
    type: str | None = None
    owner_role: str | None = None
    frequency: str | None = None


class ControlOut(ControlIn):
    id: str
    firm_id: str
    status: str


class EvidenceIn(BaseModel):
    control_id: str | None = None
    description: str = ""
    source_system: str | None = None
    metrics: dict = Field(default_factory=dict)
    captured_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class EvidenceOut(BaseModel):
    id: str
    firm_id: str
    control_id: str | None
    description: str
    source_system: str | None
    hash: str | None
    metrics: dict
    captured_at: datetime | None


class GapOut(BaseModel):
    id: str
    firm_id: str
    obligation_id: str
    reason: str
    severity: str
    detail: str
    status: str
    clause_path: str | None = None


class TestResultOut(BaseModel):
    obligation_id: str
    clause_path: str
    modality: str
    status: str
    detail: str
    spec: dict | None = None


class DiffOut(BaseModel):
    summary: dict
    added: list[dict]
    amended: list[dict]
    removed: list[dict]


class ChangeRequestOut(BaseModel):
    id: str
    firm_id: str
    change_event_id: str | None
    operational_action_text: str
    citation: dict
    affected_controls: list
    affected_evidence: list
    affected_tests: list
    status: str
    approved_by: str | None
    approved_at: datetime | None
