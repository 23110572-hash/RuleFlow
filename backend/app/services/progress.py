"""In-memory progress tracker for async document ingestion."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class IngestionProgress:
    document_id: str
    status: str = "parsing"  # parsing | extracting | enriching | coverage | done | error
    total_clauses: int = 0
    processed_clauses: int = 0
    obligations_found: int = 0
    error: str | None = None

    @property
    def percent(self) -> int:
        if self.status == "done":
            return 100
        if self.status == "parsing":
            return 5
        if self.total_clauses == 0:
            return 10
        # Extraction is 10-85%, enrichment 85-95%, coverage 95-100%
        if self.status == "extracting":
            return 10 + int((self.processed_clauses / self.total_clauses) * 75)
        if self.status == "enriching":
            return 88
        if self.status == "coverage":
            return 95
        return 0

    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "status": self.status,
            "percent": self.percent,
            "total_clauses": self.total_clauses,
            "processed_clauses": self.processed_clauses,
            "obligations_found": self.obligations_found,
            "error": self.error,
        }


_lock = threading.Lock()
_progress: Dict[str, IngestionProgress] = {}


def start(document_id: str) -> IngestionProgress:
    p = IngestionProgress(document_id=document_id)
    with _lock:
        _progress[document_id] = p
    return p


def get(document_id: str) -> IngestionProgress | None:
    with _lock:
        return _progress.get(document_id)


def remove(document_id: str) -> None:
    with _lock:
        _progress.pop(document_id, None)
