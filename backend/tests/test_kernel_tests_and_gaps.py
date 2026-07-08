"""Deterministic tests for Obligation Tests + Gap ledger + audit chain."""
from datetime import datetime, timedelta, timezone

from app.kernel.gaps import classify_gap, classify_gaps, health_score
from app.kernel.hashing import GENESIS_HASH, chain_hash, content_hash, verify_chain
from app.kernel.obligation_tests import compile_obligation, evaluate_test

NOW = datetime(2026, 7, 7, tzinfo=timezone.utc)


# ---- compile_obligation --------------------------------------------------

def test_best_judgment_not_compilable():
    assert compile_obligation({"modality": "best_judgment"}) is None
    assert compile_obligation({"modality": "may"}) is None


def test_periodicity_compiles():
    spec = compile_obligation({"modality": "shall", "deadline_or_periodicity": "monthly"})
    assert spec == {"kind": "periodicity", "period_days": 30, "label": "monthly"}


def test_threshold_compiles():
    spec = compile_obligation({"modality": "shall", "threshold": ">= 20%"})
    assert spec["kind"] == "threshold"
    assert spec["op"] == ">="
    assert spec["value"] == 20.0


def test_bare_shall_requires_presence():
    assert compile_obligation({"modality": "shall"}) == {"kind": "presence"}


# ---- evaluate_test -------------------------------------------------------

def test_presence_red_when_no_evidence():
    out = evaluate_test({"kind": "presence"}, [], as_of=NOW)
    assert out.status == "red"


def test_periodicity_green_within_period():
    ev = [{"id": "e1", "captured_at": (NOW - timedelta(days=10)).isoformat()}]
    out = evaluate_test({"kind": "periodicity", "period_days": 30}, ev, as_of=NOW)
    assert out.status == "green"


def test_periodicity_red_when_lapsed():
    ev = [{"id": "e1", "captured_at": (NOW - timedelta(days=60)).isoformat()}]
    out = evaluate_test({"kind": "periodicity", "period_days": 30}, ev, as_of=NOW)
    assert out.status == "red"


def test_threshold_red_on_violation():
    ev = [{"id": "e1", "captured_at": NOW.isoformat(), "metrics": {"pct": 12}}]
    out = evaluate_test({"kind": "threshold", "metric": "pct", "op": ">=", "value": 20}, ev, as_of=NOW)
    assert out.status == "red"


def test_bitemporal_evidence_ignored_if_future():
    # Evidence recorded in the future is not usable for an as-of-now query.
    ev = [{"id": "e1", "captured_at": (NOW + timedelta(days=5)).isoformat()}]
    out = evaluate_test({"kind": "presence"}, ev, as_of=NOW)
    assert out.status == "red"


# ---- gaps ----------------------------------------------------------------

def test_missing_shall_is_critical():
    g = classify_gap({"id": "o1", "modality": "shall"}, "red", "no evidence linked", False, 0)
    assert g.reason == "missing"
    assert g.severity == "critical"


def test_green_produces_no_gap():
    assert classify_gap({"id": "o1", "modality": "shall"}, "green", "", True, 3) is None


def test_stale_shall_is_high():
    g = classify_gap({"id": "o1", "modality": "shall"}, "red", "stale: 60d old", True, 1)
    assert g.reason == "stale"
    assert g.severity == "high"


def test_health_score_decreases_with_gaps():
    obs = 10
    findings = classify_gaps([
        {"obligation": {"id": "o1", "modality": "shall"}, "test_status": "red",
         "test_detail": "no evidence", "has_control": False, "evidence_count": 0},
    ])
    score_with_gap = health_score(obs, findings)
    assert score_with_gap < 100
    assert health_score(obs, []) == 100


# ---- audit chain ---------------------------------------------------------

def test_content_hash_dedup_stable():
    a = "The broker SHALL collect margin.\n\n"
    b = "the broker shall collect margin."
    assert content_hash(a) == content_hash(b)  # normalization -> same canonical doc


def test_hash_chain_verifies_and_detects_tampering():
    entries = []
    prev = GENESIS_HASH
    for i in range(3):
        payload = {"action": "approve", "n": i}
        ts = f"2026-07-0{i+1}T00:00:00+00:00"
        ch = chain_hash(prev, payload, ts)
        entries.append({"prev_chain_hash": prev, "payload": payload, "ts": ts, "chain_hash": ch})
        prev = ch
    ok, idx = verify_chain(entries)
    assert ok is True and idx is None
    # Tamper with the middle payload.
    entries[1]["payload"]["action"] = "reject"
    ok2, idx2 = verify_chain(entries)
    assert ok2 is False
    assert idx2 == 1
