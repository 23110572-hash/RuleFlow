"""Deterministic tests for the citation-fidelity gate."""
from app.kernel.citation import citation_fidelity, verify_citation

DOC = (
    "Chapter 3. Margin obligations. 3.1 The stock broker shall collect upfront "
    "the VaR margin and ELM from clients before the execution of trades. "
    "3.2 The stock broker shall report client-wise margin details to the clearing "
    "corporation by the end of the trading day."
)


def test_fully_grounded_quote_passes():
    quote = "The stock broker shall collect upfront the VaR margin and ELM from clients"
    start = DOC.index(quote)
    res = verify_citation(DOC, start, start + len(quote), quote, threshold=0.95)
    assert res.grounded is True
    assert res.fidelity == 1.0


def test_fabricated_quote_fails():
    # Model invents a 7-day deadline that is NOT in the cited span.
    quote = "The stock broker shall collect margin within seven days of quarter end"
    span = DOC[30:120]
    res = verify_citation(DOC, 30, 120, quote, threshold=0.95)
    assert res.grounded is False
    assert res.fidelity < 0.95
    assert any(t in {"seven", "days", "quarter"} for t in res.unsupported_tokens)


def test_wrong_span_still_locatable():
    quote = "report client-wise margin details to the clearing corporation"
    # Provide an obviously wrong span; the gate should relocate the quote.
    res = verify_citation(DOC, 0, 20, quote, threshold=0.9)
    assert res.located_span is not None


def test_source_hash_mismatch_rejects():
    quote = "The stock broker shall collect upfront the VaR margin and ELM from clients"
    start = DOC.index(quote)
    res = verify_citation(
        DOC, start, start + len(quote), quote, threshold=0.95, source_hash="deadbeef"
    )
    assert res.source_hash_ok is False
    assert res.grounded is False


def test_fidelity_is_order_sensitive():
    span = "collect upfront the VaR margin and ELM"
    scrambled = "ELM margin VaR the upfront collect and"
    assert citation_fidelity(span, span) == 1.0
    assert citation_fidelity(scrambled, span) < 1.0
