"""Citation-fidelity gate (deterministic).

Every obligation must be grounded in the exact source span it cites. The gate
re-reads the cited span from the *authoritative* document text and measures how
much of the obligation's verbatim quote is actually supported there. If the
model fabricated wording that is not in the span, fidelity drops below the
threshold and the obligation is rejected/flagged.

This is what makes a fast open model (Groq/Llama) safe for legal text: the
model may propose, but a claim only survives if the citation supports it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.kernel.hashing import normalize_text, sha256_hex

_TOKEN = re.compile(r"\w+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(normalize_text(text))


@dataclass
class CitationResult:
    fidelity: float
    grounded: bool
    threshold: float
    span_text: str
    reason: str = ""
    source_hash_ok: bool | None = None
    located_span: tuple[int, int] | None = None
    unsupported_tokens: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "fidelity": round(self.fidelity, 4),
            "grounded": self.grounded,
            "threshold": self.threshold,
            "reason": self.reason,
            "source_hash_ok": self.source_hash_ok,
            "located_span": list(self.located_span) if self.located_span else None,
            "unsupported_tokens": self.unsupported_tokens[:20],
        }


def citation_fidelity(verbatim_text: str, span_text: str) -> float:
    """Fraction of the quoted obligation text that is supported, in order, by
    the cited span. 1.0 = fully grounded quote, 0.0 = nothing supported.

    Uses in-order token matching (difflib) so that reordered or fabricated
    wording is penalised, not just bag-of-words presence.
    """
    v = _tokens(verbatim_text)
    s = _tokens(span_text)
    if not v:
        return 0.0
    if not s:
        return 0.0
    matcher = SequenceMatcher(None, v, s, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return matched / len(v)


def _unsupported(verbatim_text: str, span_text: str) -> list[str]:
    v = _tokens(verbatim_text)
    s = set(_tokens(span_text))
    return [t for t in v if t not in s]


def locate_span(document_text: str, verbatim_text: str, window: int = 40) -> tuple[int, int] | None:
    """Best-effort locate the quote inside the full document (for self-checks
    and to repair a missing/incorrect char span). Returns (start, end) char
    offsets into the ORIGINAL document_text, or None."""
    norm_doc = normalize_text(document_text)
    norm_v = normalize_text(verbatim_text)
    if not norm_v:
        return None
    # Fast path: exact normalized containment.
    idx = norm_doc.find(norm_v)
    if idx != -1:
        # Map normalized index back approximately to original by proportional scan.
        return _approx_original_span(document_text, norm_v, idx)
    # Fuzzy path: slide a window over document tokens.
    doc_tokens = _tokens(document_text)
    v_tokens = _tokens(verbatim_text)
    n = len(v_tokens)
    if n == 0 or not doc_tokens:
        return None
    best_ratio, best_i = 0.0, -1
    step = max(1, n // 4)
    for i in range(0, max(1, len(doc_tokens) - n + 1), step):
        cand = doc_tokens[i : i + n + window]
        r = SequenceMatcher(None, v_tokens, cand, autojunk=False).ratio()
        if r > best_ratio:
            best_ratio, best_i = r, i
    if best_i >= 0 and best_ratio >= 0.6:
        return _approx_original_span(document_text, norm_v, None)
    return None


def _approx_original_span(document_text: str, norm_v: str, norm_idx: int | None) -> tuple[int, int]:
    """Map a normalized match back onto original offsets. Conservative: returns
    a span that covers the matched region in the original text."""
    lowered = document_text.lower()
    # Try to find the first meaningful token run in the original text.
    first_tokens = norm_v.split(" ")[:3]
    probe = first_tokens[0] if first_tokens else norm_v[:10]
    start = lowered.find(probe)
    if start == -1:
        start = 0
    end = min(len(document_text), start + len(norm_v) + 20)
    return start, end


def verify_citation(
    document_text: str,
    char_start: int | None,
    char_end: int | None,
    verbatim_text: str,
    threshold: float = 0.95,
    source_hash: str | None = None,
) -> CitationResult:
    """The gate. Reads the cited span from the authoritative document text and
    scores whether the obligation's quote is grounded there.

    If char offsets are missing or clearly wrong, attempts to locate the quote
    so the caller can repair the citation before deciding.
    """
    located = None
    if char_start is not None and char_end is not None and 0 <= char_start < char_end <= len(
        document_text
    ):
        span_text = document_text[char_start:char_end]
    else:
        located = locate_span(document_text, verbatim_text)
        if located:
            span_text = document_text[located[0] : located[1]]
        else:
            return CitationResult(
                fidelity=0.0,
                grounded=False,
                threshold=threshold,
                span_text="",
                reason="cited span invalid and quote not locatable in document",
                source_hash_ok=None,
                located_span=None,
                unsupported_tokens=_tokens(verbatim_text)[:20],
            )

    fidelity = citation_fidelity(verbatim_text, span_text)

    # If the provided span does not ground the quote, try to relocate the true
    # span so the caller can repair the citation. If the relocated span scores
    # higher, report it (but keep the caller-provided fidelity honest).
    if fidelity < threshold and located is None:
        relocated = locate_span(document_text, verbatim_text)
        if relocated:
            relocated_text = document_text[relocated[0]:relocated[1]]
            if citation_fidelity(verbatim_text, relocated_text) > fidelity:
                located = relocated

    source_hash_ok: bool | None = None
    if source_hash is not None:
        source_hash_ok = sha256_hex(normalize_text(document_text)) == source_hash

    grounded = fidelity >= threshold and (source_hash_ok is not False)
    reason = "grounded" if grounded else f"fidelity {fidelity:.3f} < threshold {threshold}"
    if source_hash_ok is False:
        reason = "source hash mismatch: citation points at a different document version"

    return CitationResult(
        fidelity=fidelity,
        grounded=grounded,
        threshold=threshold,
        span_text=span_text,
        reason=reason,
        source_hash_ok=source_hash_ok,
        located_span=located,
        unsupported_tokens=_unsupported(verbatim_text, span_text),
    )
