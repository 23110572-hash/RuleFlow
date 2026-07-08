"""Deterministic tests for the Version Diff engine."""
from app.kernel.diff import diff_obligations


def _ob(id, path, text, **kw):
    return {"id": id, "clause_path": path, "normalized_statement": text, **kw}


def test_added_amended_removed():
    old = [
        _ob("o1", "3.1", "broker shall collect upfront VaR margin", modality="shall"),
        _ob("o2", "3.2", "broker shall report margin by end of day", modality="shall"),
        _ob("o3", "3.3", "broker may offer margin trading facility", modality="may"),
    ]
    new = [
        # unchanged
        _ob("n1", "3.1", "broker shall collect upfront VaR margin", modality="shall"),
        # amended (deadline tightened)
        _ob("n2", "3.2", "broker shall report margin by 6 pm same day", modality="shall",
            deadline_or_periodicity="6 pm same day"),
        # 3.3 removed; 3.4 added
        _ob("n4", "3.4", "broker shall segregate client funds daily", modality="shall"),
    ]
    result = diff_obligations(old, new)
    summary = result.summary()
    assert summary["unchanged"] == 1
    assert summary["amended"] == 1
    assert summary["removed"] == 1
    assert summary["added"] == 1
    assert result.amended[0].clause_path == "3.2"
    assert result.removed[0].old_id == "o3"
    assert result.added[0].new_id == "n4"


def test_renumbered_clause_matches_by_similarity():
    old = [_ob("o1", "3.1", "the broker shall maintain a client registration register")]
    new = [_ob("n1", "4.1", "the broker shall maintain a client registration register")]
    result = diff_obligations(old, new)
    # Same text, different clause number -> amended (matched), not add+remove.
    assert result.summary()["added"] == 0
    assert result.summary()["removed"] == 0
    assert result.summary()["amended"] == 1


def test_field_change_detected():
    old = [_ob("o1", "3.1", "retain records", threshold="5 years")]
    new = [_ob("n1", "3.1", "retain records", threshold="8 years")]
    result = diff_obligations(old, new)
    assert result.summary()["amended"] == 1
    fc = result.amended[0].field_changes
    assert "threshold" in fc
    assert fc["threshold"]["old"] == "5 years"
    assert fc["threshold"]["new"] == "8 years"


def test_diff_is_deterministic():
    old = [_ob(f"o{i}", f"3.{i}", f"clause number {i} text") for i in range(5)]
    new = [_ob(f"n{i}", f"3.{i}", f"clause number {i} text") for i in range(5)]
    r1 = diff_obligations(old, new).to_dict()
    r2 = diff_obligations(old, new).to_dict()
    assert r1 == r2
