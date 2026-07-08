"""Compliance Readiness scoring agent (Groq).

The model looks at the firm's obligations and how well each is currently
evidenced, and rates an overall Compliance Readiness score (0-100) with a short
rationale. If the model is unavailable, we fall back to a transparent computed
score so the dashboard is never blank.
"""
from __future__ import annotations

from app.llm.client import get_llm

SCORING_SYSTEM = """You are a compliance readiness assessor for SEBI market intermediaries.
You are given a summary of a firm's regulatory obligations and how well each is currently
backed by evidence (satisfied / at-risk / failing / human-attested) plus open gaps by severity.

Rate the firm's overall COMPLIANCE READINESS on a 0-100 scale, where 100 means fully
inspection-ready and 0 means severe, systemic non-compliance. Weigh failing and critical items
much more heavily than minor ones, and consider how many obligations are satisfied out of the total.

Return JSON:
{
  "score": <integer 0-100>,
  "band": "strong" | "moderate" | "at_risk" | "critical",
  "rationale": "<one or two plain sentences a compliance officer would understand>"
}"""


def _band(score: int) -> str:
    if score >= 85:
        return "strong"
    if score >= 65:
        return "moderate"
    if score >= 40:
        return "at_risk"
    return "critical"


def score_readiness(summary: dict, fallback_score: int) -> dict:
    """summary: {obligations_total, satisfied, at_risk, failing, attested, gaps:{...}}.
    fallback_score: transparent computed score used if the model is unavailable."""
    total = summary.get("obligations_total", 0)
    if total == 0:
        return {
            "score": None,
            "band": "no_data",
            "rationale": "No obligations are in scope yet. Add a regulation and accept its obligations to see your readiness.",
            "method": "none",
        }

    llm = get_llm()
    if llm.enabled:
        try:
            import json

            payload = llm.complete_json(SCORING_SYSTEM, json.dumps(summary))
            if isinstance(payload, dict) and isinstance(payload.get("score"), (int, float)):
                score = max(0, min(100, int(round(payload["score"]))))
                return {
                    "score": score,
                    "band": payload.get("band") or _band(score),
                    "rationale": payload.get("rationale", ""),
                    "method": "ai",
                }
        except Exception:
            pass  # fall through to computed score

    return {
        "score": fallback_score,
        "band": _band(fallback_score),
        "rationale": "Computed from your open gaps weighted by severity.",
        "method": "computed",
    }
