"""Cross-Reference, Applicability, and Control & Evidence agents (Groq).

Each is a focused reasoning step. Proposals are advisory until the kernel and/or
a human accepts them (controls/evidence are promoted by a human; applicability
ambiguity is routed to the human).
"""
from __future__ import annotations

from app.agents.prompts import (
    APPLICABILITY_SYSTEM,
    CONTROL_DRAFT_SYSTEM,
    CONTROL_EVIDENCE_SYSTEM,
    CROSSREF_SYSTEM,
    EXPLAIN_OBLIGATION_SYSTEM,
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


# Deterministic fallback shape when the LLM is unavailable / errors out. Keeps
# the approval flow working even if the model call fails; the officer can edit
# the control from the Compliance page.
_MODALITY_TO_TYPE = {
    "shall": "preventive",
    "may": "detective",
    "judgement_based": "detective",
    "best_judgment": "detective",  # pre-rename spelling
}


def _fallback_control_draft(obligation: dict) -> dict:
    statement = (obligation.get("normalized_statement") or "").strip()
    verbatim = (obligation.get("verbatim_text") or "").strip()
    modality = (obligation.get("modality") or "shall").lower()
    freq = (obligation.get("deadline_or_periodicity") or "").strip() or "per-event"
    desc = statement or verbatim
    if len(desc) > 240:
        desc = desc[:237].rstrip() + "..."
    return {
        "description": desc or "Operate a control that satisfies the approved obligation.",
        "type": _MODALITY_TO_TYPE.get(modality, "preventive"),
        "owner_role": "Compliance Officer",
        "frequency": freq,
    }


def propose_control_for_obligation(obligation: dict) -> dict:
    """Control Draft Agent: given an approved obligation, produce a concise
    operational control ready to insert into the firm's compliance record.

    Uses the LLM when configured; otherwise falls back to a deterministic draft
    built from the obligation's own fields. The caller (approval endpoint) can
    still overwrite any field afterwards.

    Input keys used: verbatim_text, normalized_statement, modality,
    deadline_or_periodicity, threshold, clause_path.
    Output keys (always present): description, type, owner_role, frequency.
    """
    llm = get_llm()
    if not llm.enabled:
        return _fallback_control_draft(obligation)

    user = (
        f"Clause path: {obligation.get('clause_path') or 'unknown'}\n"
        f"Modality: {obligation.get('modality') or 'shall'}\n"
        f"Deadline/periodicity: {obligation.get('deadline_or_periodicity') or 'none'}\n"
        f"Threshold: {obligation.get('threshold') or 'none'}\n"
        f"Verbatim text: {obligation.get('verbatim_text') or ''}\n"
        f"Normalized statement: {obligation.get('normalized_statement') or ''}"
    )
    try:
        payload = llm.complete_json(CONTROL_DRAFT_SYSTEM, user)
    except Exception:
        return _fallback_control_draft(obligation)
    if not isinstance(payload, dict):
        return _fallback_control_draft(obligation)

    fb = _fallback_control_draft(obligation)
    description = str(payload.get("description") or "").strip() or fb["description"]
    if len(description) > 240:
        description = description[:237].rstrip() + "..."
    ctype = str(payload.get("type") or "").strip().lower()
    if ctype not in {"preventive", "detective", "corrective"}:
        ctype = fb["type"]
    owner_role = str(payload.get("owner_role") or "").strip() or fb["owner_role"]
    frequency = str(payload.get("frequency") or "").strip() or fb["frequency"]
    return {
        "description": description,
        "type": ctype,
        "owner_role": owner_role,
        "frequency": frequency,
    }


def _fallback_obligation_explanation(obligation: dict) -> dict:
    statement = (
        obligation.get("normalized_statement")
        or obligation.get("verbatim_text")
        or "Regulatory requirement"
    ).strip()
    modality = (obligation.get("modality") or "shall").lower()
    is_mandatory = modality == "shall"

    clause = obligation.get("clause_path") or "specified clause"
    deadline = obligation.get("deadline_or_periodicity")
    threshold = obligation.get("threshold")

    actions = [
        f"Implement procedures to fulfill the requirements stated in Clause {clause}.",
        "Maintain appropriate evidence, audit trails, and internal documentation.",
    ]
    if deadline and deadline.lower() != "n/a":
        actions.append(f"Adhere to the prescribed periodicity/timeline: {deadline}.")
    if threshold and threshold.lower() != "n/a":
        actions.append(f"Monitor and enforce threshold: {threshold}.")

    return {
        "simple_summary": (
            f"This {'mandatory requirement' if is_mandatory else 'discretionary guideline'} specifies that: {statement}"
        ),
        "key_actions": actions,
        "who_applies": "Regulated entities subject to SEBI oversight (e.g. Depositories, Stock Brokers, AMCs, or DPs as applicable).",
        "why_it_matters": "Ensures regulatory compliance, protects market transparency, and minimizes legal and operational risks.",
    }


def explain_obligation(obligation: dict, doc_title: str | None = None) -> dict:
    """Explain an obligation in plain English using the LLM with deterministic fallback."""
    llm = get_llm()
    if not llm.enabled:
        return _fallback_obligation_explanation(obligation)

    user_prompt = (
        f"Document Title: {doc_title or 'SEBI Circular'}\n"
        f"Clause Path: {obligation.get('clause_path') or 'N/A'}\n"
        f"Modality: {obligation.get('modality') or 'shall'}\n"
        f"Normalized Statement: {obligation.get('normalized_statement') or ''}\n"
        f"Verbatim Text: {obligation.get('verbatim_text') or ''}\n"
        f"Deadline / Periodicity: {obligation.get('deadline_or_periodicity') or 'N/A'}\n"
        f"Threshold: {obligation.get('threshold') or 'N/A'}"
    )

    try:
        payload = llm.complete_json(EXPLAIN_OBLIGATION_SYSTEM, user_prompt)
        if isinstance(payload, dict) and payload.get("simple_summary"):
            actions = payload.get("key_actions")
            if not isinstance(actions, list) or not actions:
                actions = _fallback_obligation_explanation(obligation)["key_actions"]
            return {
                "simple_summary": str(payload.get("simple_summary")),
                "key_actions": [str(a) for a in actions],
                "who_applies": str(payload.get("who_applies") or _fallback_obligation_explanation(obligation)["who_applies"]),
                "why_it_matters": str(payload.get("why_it_matters") or _fallback_obligation_explanation(obligation)["why_it_matters"]),
            }
    except Exception:
        pass

    return _fallback_obligation_explanation(obligation)

