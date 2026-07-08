"""Cross-Reference, Applicability, and Control & Evidence agents (Groq).

Each is a focused reasoning step. Proposals are advisory until the kernel and/or
a human accepts them (controls/evidence are promoted by a human; applicability
ambiguity is routed to the human).
"""
from __future__ import annotations

from app.agents.prompts import (
    APPLICABILITY_SYSTEM,
    CONTROL_EVIDENCE_SYSTEM,
    CROSSREF_SYSTEM,
)
from app.llm.client import get_llm


def resolve_references(obligation_text: str) -> list[dict]:
    """Cross-Reference Agent: list references literally present in the text."""
    payload = get_llm().complete_json(CROSSREF_SYSTEM, obligation_text)
    refs = (payload or {}).get("references", []) if isinstance(payload, dict) else []
    # Deterministic guard: only keep refs whose raw string actually appears.
    lowered = obligation_text.lower()
    return [r for r in refs if (r.get("raw") or "").lower() in lowered]


def decide_applicability(obligation_text: str, document_category: str | None) -> dict:
    """Applicability Agent: which categories/tiers an obligation binds."""
    user = f"Document category: {document_category or 'unknown'}\nObligation: {obligation_text}"
    payload = get_llm().complete_json(APPLICABILITY_SYSTEM, user)
    if not isinstance(payload, dict):
        return {"applies_to": [], "ambiguous": True, "reason": "no structured response"}
    return {
        "applies_to": payload.get("applies_to", []),
        "ambiguous": bool(payload.get("ambiguous", False)),
        "reason": payload.get("reason", ""),
    }


def propose_control_and_evidence(obligation_text: str) -> dict:
    """Control & Evidence Agent: propose one control + proving evidence.
    Proposes only; a human promotes into the firm overlay."""
    payload = get_llm().complete_json(CONTROL_EVIDENCE_SYSTEM, obligation_text)
    if not isinstance(payload, dict):
        return {"control": None, "evidence": []}
    return {"control": payload.get("control"), "evidence": payload.get("evidence", [])}
