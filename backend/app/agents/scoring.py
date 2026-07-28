"""Compliance Readiness scoring agent (Groq).

The model looks at the firm's obligations and how well each is currently
evidenced, and rates an overall Compliance Readiness score (0-100) with a short
rationale. If the model is unavailable, we fall back to a transparent computed
score so the dashboard is never blank.
"""
from __future__ import annotations

from app.llm.client import get_llm

SCORING_SYSTEM = """You are a senior SEBI compliance audit judge evaluating a financial market intermediary.
You are given:
1. Firm category (e.g. Stockbroker, Investment Adviser, Depository Participant).
2. The rules, policies, and parameters currently active in the firm's connected database & controls.
3. Summary of SEBI obligation coverage and open gaps.

Judge the firm's overall COMPLIANCE READINESS on a 0-100 scale:
- 85 to 100: Strong compliance; database rules cover SEBI requirements with strict operational parameters.
- 65 to 84: Moderate compliance; key rules active, but 1 or 2 parameters need updating.
- 40 to 64: At risk; several mandatory SEBI controls missing or weak in database.
- Below 40: Critical risk; systemic gaps.

Return JSON:
{
  "score": <integer 0-100>,
  "band": "strong" | "moderate" | "at_risk" | "critical",
  "rationale": "<two clear, professional sentences summarizing the firm's database compliance posture and key advice>"
}"""


def _band(score: int) -> str:
    if score >= 85:
        return "strong"
    if score >= 65:
        return "moderate"
    if score >= 40:
        return "at_risk"
    return "critical"


def score_readiness(summary: dict, fallback_score: int, db_rules: list[dict] | None = None) -> dict:
    """summary: {obligations_total, satisfied, at_risk, failing, attested, gaps:{...}, firm_category:...}.
    db_rules: rules fetched from the firm's connected database.
    fallback_score: transparent computed score used if the model is unavailable."""
    total = summary.get("obligations_total", 0)
    rules_count = len(db_rules or [])

    if total == 0 and rules_count == 0:
        return {
            "score": None,
            "band": "no_data",
            "rationale": "No compliance rules or obligations discovered yet. Connect a database or select SEBI obligations to evaluate readiness.",
            "method": "none",
        }

    llm = get_llm()
    if llm.enabled:
        try:
            import json

            eval_payload = {
                "summary": summary,
                "database_rules_followed": [
                    {
                        "rule": r.get("rule_name"),
                        "source": r.get("source_system"),
                        "parameter": r.get("parameter_value"),
                        "clause": r.get("mapped_clause"),
                    }
                    for r in (db_rules or [])[:10]
                ],
            }

            payload = llm.complete_json(SCORING_SYSTEM, json.dumps(eval_payload, default=str))
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
        "rationale": f"Evaluated across {rules_count} active database rules and category SEBI obligations.",
        "method": "computed",
    }
