"""Compliance Readiness scoring (Groq AI judge + deterministic fallback).

The score answers one real question: of the rules this firm actually follows and
the SEBI obligations that apply to it, how much is covered and how much is
currently at risk because a followed rule is out of date?

Inputs are all real and grounded:
  * rules_followed      - rules read from the firm's connected database
  * obligations_in_scope- SEBI obligations that apply to the firm's category
  * obligations_addressed - in-scope obligations the firm has adopted a control for
  * open_action_items   - followed rules a SEBI change has made outdated (risk)
  * open_weighted       - those items weighted by the modality of the cited rule

If the model is unavailable we fall back to a transparent, reproducible score
computed from the same numbers, so the dashboard is honest and never blank.
"""
from __future__ import annotations

from app.llm.client import get_llm

SCORING_SYSTEM = """You are a senior SEBI compliance audit judge evaluating a financial market intermediary.

You are given, as real data:
1. The firm's category.
2. The rules the firm ACTUALLY follows (read from its connected database).
3. How many applicable SEBI obligations it covers vs how many apply to it.
4. The followed rules that a recent SEBI change has made outdated or insufficient (open risks).

Judge overall COMPLIANCE READINESS on a 0-100 scale:
- 85-100 strong: broad coverage of applicable obligations and no outstanding risks.
- 65-84 moderate: mostly covered, a few followed rules need updating.
- 40-64 at risk: partial coverage or several followed rules out of date.
- below 40 critical: little coverage or many unresolved risks.

Base the score ONLY on the numbers given. Do not invent facts.

Return JSON:
{
  "score": <integer 0-100>,
  "band": "strong" | "moderate" | "at_risk" | "critical",
  "rationale": "<two clear sentences: what the firm covers, and the main risk to fix next>"
}"""


def _band(score: int) -> str:
    if score >= 85:
        return "strong"
    if score >= 65:
        return "moderate"
    if score >= 40:
        return "at_risk"
    return "critical"


def computed_readiness_score(
    *,
    rules_followed: int,
    obligations_in_scope: int,
    obligations_addressed: int,
    open_action_items: int,
    open_weighted: float,
) -> int | None:
    """Transparent, reproducible readiness score from real inputs.

    Returns None when there is genuinely nothing to score (no followed rules and
    nothing adopted). Otherwise blends coverage (how much of what applies to you
    you actually address) with health (how few of your followed rules are out of
    date). Missing *evidence* never forces the score to zero — that was the old
    behaviour that pinned every un-onboarded firm at 0/100.
    """
    if rules_followed == 0 and obligations_addressed == 0:
        return None

    if obligations_in_scope > 0:
        coverage = obligations_addressed / obligations_in_scope
    else:
        # Nothing in scope to cover; following any rule at all is full coverage.
        coverage = 1.0 if (rules_followed or obligations_addressed) else 0.0
    coverage = max(0.0, min(1.0, coverage))

    engaged = max(rules_followed, obligations_addressed, 1)
    risk = min(1.0, open_weighted / engaged)

    score = round(100 * (0.55 * coverage + 0.45 * (1.0 - risk)))
    return max(0, min(100, score))


def score_readiness(
    *,
    firm_category: str,
    rules_followed: int,
    obligations_in_scope: int,
    obligations_addressed: int,
    open_action_items: int,
    open_weighted: float,
    followed_rule_names: list[str] | None = None,
    risk_summaries: list[str] | None = None,
) -> dict:
    """Rate Compliance Readiness. Tries the AI judge on the real numbers, then
    falls back to :func:`computed_readiness_score`. Never fabricates inputs."""
    fallback = computed_readiness_score(
        rules_followed=rules_followed,
        obligations_in_scope=obligations_in_scope,
        obligations_addressed=obligations_addressed,
        open_action_items=open_action_items,
        open_weighted=open_weighted,
    )

    if fallback is None:
        return {
            "score": None,
            "band": "no_data",
            "rationale": (
                "No rules or obligations to evaluate yet. Connect your database so we "
                "can read the rules you follow, and adopt the SEBI obligations that "
                "apply to you."
            ),
            "method": "none",
        }

    computed_rationale = (
        f"You follow {rules_followed} database rule(s) and address "
        f"{obligations_addressed} of {obligations_in_scope} SEBI obligation(s) that apply to you. "
        + (
            f"{open_action_items} followed rule(s) need updating for recent SEBI changes."
            if open_action_items
            else "No followed rule is currently out of date with SEBI."
        )
    )

    llm = get_llm()
    if llm.enabled:
        try:
            import json

            payload = llm.complete_json(
                SCORING_SYSTEM,
                json.dumps(
                    {
                        "firm_category": firm_category,
                        "rules_followed_count": rules_followed,
                        "rules_followed_examples": (followed_rule_names or [])[:10],
                        "obligations_in_scope": obligations_in_scope,
                        "obligations_addressed": obligations_addressed,
                        "open_action_items": open_action_items,
                        "open_risks": (risk_summaries or [])[:10],
                    },
                    default=str,
                ),
            )
            if isinstance(payload, dict) and isinstance(payload.get("score"), (int, float)):
                score = max(0, min(100, int(round(payload["score"]))))
                return {
                    "score": score,
                    "band": payload.get("band") or _band(score),
                    "rationale": payload.get("rationale") or computed_rationale,
                    "method": "ai",
                }
        except Exception:
            pass  # fall through to the transparent computed score

    return {
        "score": fallback,
        "band": _band(fallback),
        "rationale": computed_rationale,
        "method": "computed",
    }
