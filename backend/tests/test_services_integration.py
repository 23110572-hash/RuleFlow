"""End-to-end integration of the deterministic service layer (no LLM needed).

We insert obligations DIRECTLY to simulate 'already-extracted canonical data'
(real extraction requires Groq and is exercised separately). This proves the
change-management and ongoing-compliance flows compute correctly and that the
audit chain is tamper-evident — all without any network calls.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

NOW = datetime.now(timezone.utc)


@pytest.fixture()
def seeded(db):
    """A synthetic stockbroker firm + two real-shaped obligations + tests."""
    from app.db.models import Document, Firm, Obligation, ObligationTest
    from app.kernel.obligation_tests import compile_obligation

    doc = Document(circular_number="TEST/1", content_hash="h1", title="Master Circular v1", category="stockbroker")
    db.add(doc)
    db.flush()

    o1 = Obligation(
        source_document_id=doc.id, clause_path="3.1",
        verbatim_text="The stock broker shall report client margin monthly",
        normalized_statement="report client margin monthly", modality="shall",
        deadline_or_periodicity="monthly", applies_to=[{"category": "stockbroker", "tier": None}],
        citation={"char_start": 0, "char_end": 50, "source_hash": "h1"},
        citation_fidelity=1.0, status="verified", valid_from=NOW - timedelta(days=365),
    )
    o2 = Obligation(
        source_document_id=doc.id, clause_path="3.2",
        verbatim_text="The stock broker shall maintain minimum net worth of 20%",
        normalized_statement="maintain minimum net worth 20%", modality="shall",
        threshold=">= 20%", applies_to=[{"category": "stockbroker", "tier": None}],
        citation={"char_start": 60, "char_end": 120, "source_hash": "h1"},
        citation_fidelity=1.0, status="verified", valid_from=NOW - timedelta(days=365),
    )
    db.add_all([o1, o2])
    db.flush()
    for o in (o1, o2):
        db.add(ObligationTest(obligation_id=o.id,
                              spec=compile_obligation({"modality": o.modality,
                                                       "deadline_or_periodicity": o.deadline_or_periodicity,
                                                       "threshold": o.threshold})))
    firm = Firm(name="Synthetic Securities Pvt Ltd", category="stockbroker", tier="non-QSB")
    db.add(firm)
    db.flush()
    from app.db.models import DataSource
    ds = DataSource(firm_id=firm.id, name="Test DB", kind="sqlite", connection_uri="sqlite://", status="connected")
    db.add(ds)
    db.commit()
    return {"firm_id": firm.id, "doc_id": doc.id, "o1": o1.id, "o2": o2.id}


def test_compliance_flow_detects_and_closes_gaps(client, seeded):
    firm_id, o1, o2 = seeded["firm_id"], seeded["o1"], seeded["o2"]

    # No controls/evidence yet -> both obligations are gaps (missing, critical).
    ev = client.get(f"/firms/{firm_id}/compliance/evaluate").json()
    assert ev["total"] == 2
    assert ev["readiness"]["score"] < 100  # computed fallback when no LLM key in tests
    assert all(g["reason"] == "missing" for g in ev["gaps"])

    # Add a control for the monthly-margin obligation + fresh evidence -> green.
    ctrl = client.post(f"/firms/{firm_id}/controls", json={
        "obligation_ids": [o1], "description": "Monthly margin report job", "frequency": "monthly",
    }).json()
    client.post(f"/firms/{firm_id}/evidence", json={
        "control_id": ctrl["id"], "description": "March margin report",
        "captured_at": (NOW - timedelta(days=5)).isoformat(),
    })
    # Add control + evidence for net-worth threshold, but FAILING the >=20% test.
    ctrl2 = client.post(f"/firms/{firm_id}/controls", json={
        "obligation_ids": [o2], "description": "Net worth monitor", "frequency": "daily",
    }).json()
    client.post(f"/firms/{firm_id}/evidence", json={
        "control_id": ctrl2["id"], "description": "Net worth snapshot",
        "captured_at": NOW.isoformat(), "metrics": {"pct": 12},
    })

    ev2 = client.get(f"/firms/{firm_id}/compliance/evaluate").json()
    by_ob = {r["obligation_id"]: r for r in ev2["results"]}
    assert by_ob[o1]["status"] == "green"          # monthly report satisfied
    assert by_ob[o2]["status"] == "red"            # threshold violated
    reasons = {g["obligation_id"]: g["reason"] for g in ev2["gaps"]}
    assert reasons.get(o2) == "contradictory"


def test_time_machine_reconstructs_past(client, seeded):
    firm_id, o1 = seeded["firm_id"], seeded["o1"]
    ctrl = client.post(f"/firms/{firm_id}/controls", json={
        "obligation_ids": [o1], "description": "Monthly margin report", "frequency": "monthly",
    }).json()
    # Evidence captured 5 days ago.
    client.post(f"/firms/{firm_id}/evidence", json={
        "control_id": ctrl["id"], "description": "recent report",
        "captured_at": (NOW - timedelta(days=5)).isoformat(),
    })
    # As of 60 days ago, that evidence did not yet exist -> not green.
    past = (NOW - timedelta(days=60)).isoformat()
    snap = client.get(f"/firms/{firm_id}/compliance/time-machine", params={"as_of": past}).json()
    by_ob = {r["obligation_id"]: r for r in snap["results"]}
    assert by_ob[o1]["status"] != "green"


def test_change_diff_and_hil_change_request(client, seeded, db):
    firm_id, doc1 = seeded["firm_id"], seeded["doc_id"]
    from app.db.models import Document, Obligation

    # A new version tightens the monthly obligation to weekly, drops the threshold one.
    doc2 = Document(circular_number="TEST/2", content_hash="h2", title="Master Circular v2", category="stockbroker")
    db.add(doc2)
    db.flush()
    db.add(Obligation(
        source_document_id=doc2.id, clause_path="3.1",
        verbatim_text="The stock broker shall report client margin weekly",
        normalized_statement="report client margin weekly", modality="shall",
        deadline_or_periodicity="weekly", citation={"char_start": 0, "char_end": 50},
        citation_fidelity=1.0, status="verified",
    ))
    db.commit()

    diff = client.post(f"/documents/{doc1}/diff/{doc2.id}").json()
    assert diff["summary"]["amended"] == 1
    assert diff["summary"]["removed"] == 1

    impact = client.post(f"/firms/{firm_id}/change-impact",
                         json={"change_event_ids": diff["change_event_ids"]}).json()
    assert len(impact) == 2
    cr_id = impact[0]["change_request_id"]

    # HIL approves -> cited change request; then firm applies it.
    decided = client.post(f"/change-requests/{cr_id}/decision",
                          json={"decision": "approve", "approver": "officer_a"}).json()
    assert decided["status"] == "approved"
    applied = client.post(f"/change-requests/{cr_id}/applied", json={"actor": "officer_a"}).json()
    assert applied["status"] == "applied"


def test_audit_chain_is_intact_after_operations(client, seeded):
    firm_id, o1 = seeded["firm_id"], seeded["o1"]
    client.post(f"/firms/{firm_id}/controls", json={"obligation_ids": [o1], "description": "c"})
    client.post(f"/firms/{firm_id}/compliance/refresh-gaps")
    verify = client.get("/audit/verify", params={"firm_id": firm_id}).json()
    assert verify["intact"] is True
    entries = client.get("/audit", params={"firm_id": firm_id}).json()
    assert len(entries) >= 2
