"""Obligation Tests (deterministic) — compliance-as-CI.

Crisp, quantitative obligations are compiled into executable checks that run
against the firm's evidence. Green = satisfied, red = gap, amber = at-risk.

Best-judgment obligations are intentionally NOT compilable — they return None
from compile_obligation() and must stay human-attested. The kernel never
auto-decides an uncodifiable obligation.

A test SPEC is a plain dict (so it is storable, diffable, and inspectable):
  {"kind": "presence"}                       evidence must simply exist
  {"kind": "recency", "max_age_days": 90}    newest evidence within window
  {"kind": "periodicity", "period_days": 30} evidence in the last full period
  {"kind": "deadline", "due": "2024-08-01"}  evidence captured on/before due
  {"kind": "threshold", "metric": "margin_pct", "op": ">=", "value": 20}
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

# ---- periodicity vocabulary (data, not category logic) -------------------
_PERIOD_DAYS = {
    "daily": 1,
    "weekly": 7,
    "fortnightly": 14,
    "monthly": 30,
    "quarterly": 91,
    "half-yearly": 182,
    "half yearly": 182,
    "semi-annual": 182,
    "annually": 365,
    "annual": 365,
    "yearly": 365,
}

_NUM = re.compile(r"(\d+(?:\.\d+)?)")


@dataclass
class TestOutcome:
    status: str  # green | amber | red | not_compilable
    detail: str
    spec: dict[str, Any] = field(default_factory=dict)
    evidence_used: list[str] = field(default_factory=list)
    as_of: str | None = None

    @property
    def passed(self) -> bool:
        return self.status == "green"

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "detail": self.detail,
            "spec": self.spec,
            "evidence_used": self.evidence_used,
            "as_of": self.as_of,
        }


def _to_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(value.replace("Z", "+0000"), fmt)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def compile_obligation(obligation: dict) -> dict | None:
    """Derive an executable test spec from an obligation's structured fields.

    Returns None when the obligation is not codifiable (best_judgment or 'may'),
    signalling that it must be handled as a human-attested checklist item.
    """
    modality = (obligation.get("modality") or "").lower()
    if modality in {"best_judgment", "may"}:
        return None

    threshold = obligation.get("threshold")
    if threshold:
        parsed = _parse_threshold(str(threshold))
        if parsed:
            return parsed

    periodicity = (obligation.get("deadline_or_periodicity") or "").lower().strip()
    if periodicity:
        for word, days in _PERIOD_DAYS.items():
            if word in periodicity:
                return {"kind": "periodicity", "period_days": days, "label": word}
        # An explicit date -> deadline test.
        if _to_dt(periodicity):
            return {"kind": "deadline", "due": periodicity}
        m = _NUM.search(periodicity)
        if m and "day" in periodicity:
            return {"kind": "recency", "max_age_days": int(float(m.group(1)))}

    # A hard 'shall' with no quantitative hook -> require evidence presence.
    if modality == "shall":
        return {"kind": "presence"}
    return None


def _parse_threshold(text: str) -> dict | None:
    m = re.search(r"(<=|>=|<|>|=)?\s*(\d+(?:\.\d+)?)\s*(%|percent|days|hours)?", text)
    if not m:
        return None
    op = m.group(1) or ">="
    value = float(m.group(2))
    metric_guess = "value"
    if m.group(3) in {"%", "percent"}:
        metric_guess = "pct"
    return {"kind": "threshold", "metric": metric_guess, "op": op, "value": value}


# ---- evaluators ----------------------------------------------------------

def _newest(evidence: list[dict]) -> dict | None:
    dated = [(e, _to_dt(e.get("captured_at") or e.get("valid_from"))) for e in evidence]
    dated = [(e, d) for e, d in dated if d is not None]
    if not dated:
        return None
    return max(dated, key=lambda x: x[1])[0]


def _compare(actual: float, op: str, expected: float) -> bool:
    return {
        ">=": actual >= expected,
        "<=": actual <= expected,
        ">": actual > expected,
        "<": actual < expected,
        "=": actual == expected,
    }.get(op, False)


def evaluate_test(
    spec: dict | None,
    evidence: list[dict],
    as_of: datetime | None = None,
) -> TestOutcome:
    """Run a compiled test spec against evidence as of a point in time."""
    now = as_of or datetime.now(timezone.utc)
    now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    as_of_s = now.isoformat()

    if spec is None:
        return TestOutcome("not_compilable", "human-attested obligation", {}, as_of=as_of_s)

    # Only consider evidence known/valid as of `now` (bitemporal honesty).
    valid_ev = [
        e for e in evidence
        if (_to_dt(e.get("captured_at") or e.get("valid_from")) or now) <= now
    ]

    kind = spec.get("kind")
    ids = lambda es: [str(e.get("id")) for e in es if e.get("id") is not None]  # noqa: E731

    if kind == "presence":
        if valid_ev:
            return TestOutcome("green", "evidence present", spec, ids(valid_ev), as_of_s)
        return TestOutcome("red", "no evidence linked", spec, [], as_of_s)

    if kind == "recency":
        newest = _newest(valid_ev)
        if not newest:
            return TestOutcome("red", "no evidence to date", spec, [], as_of_s)
        age = (now - _to_dt(newest.get("captured_at") or newest.get("valid_from"))).days
        max_age = int(spec.get("max_age_days", 90))
        if age <= max_age:
            return TestOutcome("green", f"latest evidence {age}d old", spec, ids([newest]), as_of_s)
        if age <= max_age * 1.25:
            return TestOutcome("amber", f"evidence {age}d old (limit {max_age}d)", spec, ids([newest]), as_of_s)
        return TestOutcome("red", f"stale: {age}d old (limit {max_age}d)", spec, ids([newest]), as_of_s)

    if kind == "periodicity":
        period = int(spec.get("period_days", 30))
        newest = _newest(valid_ev)
        if not newest:
            return TestOutcome("red", "no periodic evidence", spec, [], as_of_s)
        age = (now - _to_dt(newest.get("captured_at") or newest.get("valid_from"))).days
        if age <= period:
            return TestOutcome("green", f"within period ({age}d/{period}d)", spec, ids([newest]), as_of_s)
        if age <= period * 1.25:
            return TestOutcome("amber", f"period nearly lapsed ({age}d/{period}d)", spec, ids([newest]), as_of_s)
        return TestOutcome("red", f"period lapsed ({age}d/{period}d)", spec, ids([newest]), as_of_s)

    if kind == "deadline":
        due = _to_dt(spec.get("due"))
        if not due:
            return TestOutcome("red", "invalid deadline spec", spec, [], as_of_s)
        on_time = [e for e in valid_ev if (_to_dt(e.get("captured_at")) or now) <= due]
        if on_time:
            return TestOutcome("green", f"met by {due.date()}", spec, ids(on_time), as_of_s)
        if now <= due:
            return TestOutcome("amber", f"due {due.date()}, not yet evidenced", spec, [], as_of_s)
        return TestOutcome("red", f"deadline {due.date()} missed", spec, [], as_of_s)

    if kind == "threshold":
        metric, op, expected = spec.get("metric", "value"), spec.get("op", ">="), float(spec.get("value", 0))
        readings = []
        for e in valid_ev:
            metrics = e.get("metrics") or {}
            if metric in metrics:
                readings.append((e, float(metrics[metric])))
            elif "value" in metrics:
                readings.append((e, float(metrics["value"])))
        if not readings:
            return TestOutcome("red", f"no reading for metric '{metric}'", spec, [], as_of_s)
        failing = [(e, v) for e, v in readings if not _compare(v, op, expected)]
        if not failing:
            return TestOutcome("green", f"all readings satisfy {op} {expected}", spec, ids([e for e, _ in readings]), as_of_s)
        return TestOutcome(
            "red",
            f"{len(failing)} reading(s) violate {op} {expected} (e.g. {failing[0][1]})",
            spec, ids([e for e, _ in failing]), as_of_s,
        )

    return TestOutcome("not_compilable", f"unknown spec kind '{kind}'", spec, as_of=as_of_s)
