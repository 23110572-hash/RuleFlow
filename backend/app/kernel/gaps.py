"""Gap ledger (deterministic).

Rule-based classification of the delta between what an obligation requires and
what evidence exists. Reproducible -> inspection-grade. Never guesses.

reason  ∈ missing | stale | weak | contradictory
severity ∈ critical | high | medium | low  (driven by modality + reason)
"""
from __future__ import annotations

from dataclasses import dataclass

# modality × reason -> severity. Data-driven; not category-specific.
_SEVERITY = {
    ("shall", "missing"): "critical",
    ("shall", "contradictory"): "critical",
    ("shall", "stale"): "high",
    ("shall", "weak"): "medium",
    ("may", "missing"): "low",
    ("may", "stale"): "low",
    ("may", "weak"): "low",
    ("may", "contradictory"): "medium",
}
_SEVERITY_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}


@dataclass
class GapFinding:
    obligation_id: str
    reason: str  # missing | stale | weak | contradictory
    severity: str
    detail: str
    clause_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "obligation_id": self.obligation_id,
            "reason": self.reason,
            "severity": self.severity,
            "detail": self.detail,
            "clause_path": self.clause_path,
        }


def _severity(modality: str, reason: str) -> str:
    modality = "shall" if (modality or "").lower() not in {"may", "best_judgment"} else modality.lower()
    return _SEVERITY.get((modality, reason), "medium")


def classify_gap(
    obligation: dict,
    test_status: str,
    test_detail: str,
    has_control: bool,
    evidence_count: int,
) -> GapFinding | None:
    """Classify a single obligation's compliance gap, or None if satisfied.

    obligation: needs id, modality, optionally clause_path.
    test_status: green | amber | red | not_compilable (from evaluate_test).
    """
    oid = str(obligation.get("id"))
    modality = (obligation.get("modality") or "shall").lower()
    clause = obligation.get("clause_path")

    # Best-judgment / uncodifiable: a gap only if there is no human attestation
    # (modelled as absence of control/evidence). Never auto-red on the metric.
    if test_status == "not_compilable" or modality == "best_judgment":
        if not has_control and evidence_count == 0:
            return GapFinding(oid, "missing", "medium",
                              "uncodifiable obligation lacks human attestation", clause)
        return None

    if test_status == "green":
        return None

    # Determine reason.
    if not has_control or evidence_count == 0:
        reason = "missing"
    elif "stale" in test_detail or "lapsed" in test_detail or "old" in test_detail:
        reason = "stale"
    elif "violate" in test_detail or "contradict" in test_detail:
        reason = "contradictory"
    else:
        reason = "weak"

    severity = _severity(modality, reason)
    # Amber softens severity by one rank (at-risk, not yet breached).
    if test_status == "amber":
        ranked = sorted(_SEVERITY_RANK, key=lambda k: _SEVERITY_RANK[k])
        idx = max(0, _SEVERITY_RANK[severity] - 1)
        severity = ranked[idx]

    return GapFinding(oid, reason, severity, test_detail or reason, clause)


def classify_gaps(items: list[dict]) -> list[GapFinding]:
    """Classify a batch. Each item:
    {obligation, test_status, test_detail, has_control, evidence_count}
    Returns findings sorted by severity (worst first)."""
    findings: list[GapFinding] = []
    for it in items:
        g = classify_gap(
            it["obligation"],
            it.get("test_status", "red"),
            it.get("test_detail", ""),
            it.get("has_control", False),
            it.get("evidence_count", 0),
        )
        if g:
            findings.append(g)
    findings.sort(key=lambda g: _SEVERITY_RANK[g.severity], reverse=True)
    return findings


def health_score(total_obligations: int, findings: list[GapFinding]) -> int:
    """A 0-100 compliance health score. Deterministic and explainable:
    start at 100, subtract weighted penalties per open gap, floor at 0."""
    if total_obligations <= 0:
        return 100
    penalty_weight = {"critical": 12, "high": 7, "medium": 3, "low": 1}
    raw = sum(penalty_weight[f.severity] for f in findings)
    # Normalise penalty against obligation count so large corpora aren't over-penalised.
    scaled = raw / max(1, total_obligations) * 20
    return max(0, min(100, round(100 - scaled)))
