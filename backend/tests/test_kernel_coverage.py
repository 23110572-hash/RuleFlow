"""Deterministic tests for the Coverage Certificate."""
from app.kernel.coverage import build_coverage_certificate, sweep_signals

DOC = (
    "3.1 The broker shall collect upfront margin. "
    "3.2 No person shall manipulate the market. "
    "3.3 The broker may offer margin trading facility. "
    "3.4 Records must be retained for eight years. "
    "3.5 The broker is required to file a monthly report."
)


def test_sweep_finds_all_signals():
    sigs = sweep_signals(DOC)
    phrases = {s.phrase.lower() for s in sigs}
    assert "shall" in phrases
    assert "no person shall" in phrases
    assert "must" in phrases
    assert "is required to" in phrases


def test_longest_signal_wins():
    sigs = sweep_signals("No person shall do X.")
    # "no person shall" should win over the inner "shall".
    assert len(sigs) == 1
    assert sigs[0].phrase.lower() == "no person shall"


def test_coverage_accounts_every_signal():
    sigs = sweep_signals(DOC)
    total = len(sigs)
    # Extract obligations covering the first two signals only.
    ob_spans = [(sigs[0].char_start, sigs[0].char_end + 5), (sigs[1].char_start, sigs[1].char_end + 5)]
    cert = build_coverage_certificate(DOC, ob_spans)
    assert cert.signals_total == total
    assert cert.extracted == 2
    assert cert.unaccounted == total - 2
    assert cert.is_complete is False


def test_not_applicable_with_reason_accounts():
    sigs = sweep_signals(DOC)
    ob_spans = [(sigs[0].char_start, sigs[0].char_end + 5)]
    na = [(sigs[1].char_start, sigs[1].char_end + 5, "market-conduct rule, not a firm control")]
    cert = build_coverage_certificate(DOC, ob_spans, not_applicable_spans=na)
    assert cert.extracted == 1
    assert cert.not_applicable == 1
    na_signal = next(s for s in cert.signals if s.status == "not_applicable")
    assert "market-conduct" in na_signal.reason


def test_full_coverage_is_complete():
    sigs = sweep_signals(DOC)
    ob_spans = [(s.char_start, s.char_end + 1) for s in sigs]
    cert = build_coverage_certificate(DOC, ob_spans)
    assert cert.unaccounted == 0
    assert cert.is_complete is True
    assert cert.coverage_ratio == 1.0
