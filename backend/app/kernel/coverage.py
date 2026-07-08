"""Coverage Certificate (deterministic).

Sweeps every obligation-signal phrase in a document ("shall", "must",
"required to", "no person shall", "shall not", ...) and accounts for each one:

    extracted            -> a proposed obligation's citation span covers it
    not_applicable       -> a human/agent marked this span N/A, WITH a reason
    unaccounted          -> nobody has explained this signal yet

A chatbot cannot offer this. The certificate gives *provable completeness*: a
human can read exactly which "shall" sentences the system did not capture.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Obligation-signal phrases. Order matters: multi-word phrases first so the
# longest signal at a position wins. This list is data, not category logic.
SIGNAL_PATTERNS: list[str] = [
    r"no\s+person\s+shall",
    r"shall\s+not",
    r"shall\s+ensure",
    r"shall\s+be\s+liable",
    r"is\s+required\s+to",
    r"are\s+required\s+to",
    r"required\s+to",
    r"prohibited\s+from",
    r"shall",
    r"must",
    r"may\s+not",
]

_SIGNAL_RE = re.compile("|".join(f"(?:{p})" for p in SIGNAL_PATTERNS), re.IGNORECASE)
_SENT_BOUNDARY = re.compile(r"(?<=[.;:])\s+|\n+")


@dataclass
class Signal:
    phrase: str
    char_start: int
    char_end: int
    sentence: str
    status: str = "unaccounted"  # extracted | not_applicable | unaccounted
    reason: str = ""
    obligation_ref: str | None = None

    def to_dict(self) -> dict:
        return {
            "phrase": self.phrase,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "sentence": self.sentence.strip()[:400],
            "status": self.status,
            "reason": self.reason,
            "obligation_ref": self.obligation_ref,
        }


@dataclass
class CoverageCertificate:
    document_id: str | None
    signals_total: int
    extracted: int
    not_applicable: int
    unaccounted: int
    coverage_ratio: float
    signals: list[Signal] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return self.unaccounted == 0

    def to_dict(self, include_signals: bool = True) -> dict:
        d = {
            "document_id": self.document_id,
            "signals_total": self.signals_total,
            "extracted": self.extracted,
            "not_applicable": self.not_applicable,
            "unaccounted": self.unaccounted,
            "coverage_ratio": round(self.coverage_ratio, 4),
            "is_complete": self.is_complete,
        }
        if include_signals:
            d["signals"] = [s.to_dict() for s in self.signals]
            d["unaccounted_signals"] = [
                s.to_dict() for s in self.signals if s.status == "unaccounted"
            ]
        return d


def _sentence_around(text: str, start: int, end: int) -> str:
    """Return the sentence containing [start,end)."""
    left = text.rfind("\n", 0, start)
    for m in _SENT_BOUNDARY.finditer(text, 0, start):
        left = max(left, m.end())
    right_m = _SENT_BOUNDARY.search(text, end)
    right = right_m.start() if right_m else len(text)
    return text[max(0, left):right]


def sweep_signals(document_text: str) -> list[Signal]:
    """Find every obligation-signal occurrence, de-duplicating overlapping
    matches so the longest signal at a position wins."""
    signals: list[Signal] = []
    last_end = -1
    for m in _SIGNAL_RE.finditer(document_text):
        if m.start() < last_end:  # overlaps previous longer match
            continue
        last_end = m.end()
        signals.append(
            Signal(
                phrase=m.group(0),
                char_start=m.start(),
                char_end=m.end(),
                sentence=_sentence_around(document_text, m.start(), m.end()),
            )
        )
    return signals


def _covered_by(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(s <= pos < e for s, e in spans)


def build_coverage_certificate(
    document_text: str,
    obligation_spans: list[tuple[int, int]],
    not_applicable_spans: list[tuple[int, int, str]] | None = None,
    document_id: str | None = None,
) -> CoverageCertificate:
    """Account for every obligation signal in the document.

    obligation_spans: (char_start, char_end) of each accepted obligation's citation.
    not_applicable_spans: (char_start, char_end, reason) marked N/A by a human/agent.
    """
    not_applicable_spans = not_applicable_spans or []
    signals = sweep_signals(document_text)

    na_spans = [(s, e) for s, e, _ in not_applicable_spans]
    na_reason = {(s, e): r for s, e, r in not_applicable_spans}

    extracted = na = unaccounted = 0
    for sig in signals:
        if _covered_by(sig.char_start, obligation_spans):
            sig.status = "extracted"
            extracted += 1
        else:
            hit = next(((s, e) for s, e in na_spans if s <= sig.char_start < e), None)
            if hit:
                sig.status = "not_applicable"
                sig.reason = na_reason.get(hit, "marked not applicable")
                na += 1
            else:
                sig.status = "unaccounted"
                unaccounted += 1

    total = len(signals)
    coverage_ratio = (extracted + na) / total if total else 1.0
    return CoverageCertificate(
        document_id=document_id,
        signals_total=total,
        extracted=extracted,
        not_applicable=na,
        unaccounted=unaccounted,
        coverage_ratio=coverage_ratio,
        signals=signals,
    )
