"""Review checklist (deterministic).

Sweeps every obligation-signal phrase in a document ("shall", "must",
"required to", "no person shall", "shall not", ...) and accounts for each one:

    extracted      -> the clause this signal sits in produced an obligation
    unaccounted    -> nobody has explained this signal yet; a human should read it

The output is a *checklist*, not a score. Deliberately NOT a percentage: the
ratio of duty-words that happen to fall inside a captured clause says nothing
useful about extraction quality, and presenting it as "45% coverage" made a
correct run look like a failure. What is genuinely valuable — and what no
chatbot can offer — is the explicit list of duty sentences the system did not
capture, so a compliance officer can read them and decide.

``coverage_ratio`` is still computed because the column exists on
CoverageReport and the diff/dashboard code reads it, but no UI presents it as
a headline accuracy number.
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

# Administrative boilerplate that ends every SEBI circular. These sentences
# contain a duty word but impose no obligation on the intermediary, so counting
# them as "missed obligations" permanently padded the checklist with noise.
# Matched ANYWHERE near the duty word, because none of them begins with it.
# Only constructions that do NOT begin with a duty word belong here, because a
# window search around the duty word can suppress an unrelated obligation that
# merely sits nearby. "unless the context otherwise requires" used to be in this
# list and silently ate two real duties one paragraph below a definitions
# preamble. Anything phrased "shall ..." goes in NON_DUTY_TAIL_PATTERNS instead.
BOILERPLATE_PATTERNS: list[str] = [
    r"this\s+circular\s+(is|shall)\s+(be\s+)?issued",
    r"in\s+exercise\s+of\s+the\s+powers\s+conferred",
    r"may\s+be\s+addressed\s+to",
    r"is\s+available\s+(at|on)\s+www\.sebi\.gov\.in",
    r"under\s+the\s+link\s+.?legal",
]

# Constructions that make the duty word part of a DEFINITION, a SCOPE LIMIT or a
# SAVINGS clause rather than an instruction to anyone.
#
# These are anchored AT the duty word, never merely near it. Searching a window
# suppressed a real obligation - "Every stock broker ... shall be liable to
# furnish such information ... to the Board" - purely because a definition
# happened to sit in the same paragraph. What decides the question is the grammar
# immediately after the duty word.
#
# Structural, not topical: "shall mean" is here, "the Board shall" is not, since
# the latter usually introduces something a firm must then follow.
NON_DUTY_TAIL_PATTERNS: list[str] = [
    # commencement and publication: the circular talking about itself
    r"shall\s+come\s+into\s+force",
    r"shall\s+come\s+into\s+effect",
    r"shall\s+be\s+available\s+on\s+(the\s+)?(sebi\s+)?website",
    # definitions and interpretation: fixing what a word denotes
    r"shall\s+mean",
    r"shall\s+have\s+the\s+(same\s+|respective\s+)?meanings?",
    r"shall\s+be\s+construed",
    r"shall\s+be\s+interpreted",
    r"shall\s+also\s+include\s+amendment",
    # scope limits: stating where the rules do NOT reach
    r"shall\s+not\s+be\s+applicable\s+to",
    r"shall\s+not\s+apply\s+to",
    r"shall\s+mutatis\s+mutandis\s+apply",
    # savings, repeal and validity: preserving the past, directing no one
    r"shall\s+remain\s+valid",
    r"shall\s+remain\s+unaffected",
    r"shall\s+stand\s+repealed",
    r"shall\s+be\s+deemed\s+to\s+have\s+been",
    r"shall\s+be\s+deemed\s+to\s+be\s+a\s+reference",
    r"shall\s+be\s+taken\s+as\s+(a\s+)?reference",
    # Both orderings occur: "shall not be invalid" and, with the negation moved
    # to the subject, "No regulations ... shall be invalid".
    r"shall\s+(not\s+)?be\s+invalid",
]

_SIGNAL_RE = re.compile("|".join(f"(?:{p})" for p in SIGNAL_PATTERNS), re.IGNORECASE)
_BOILERPLATE_RE = re.compile("|".join(f"(?:{p})" for p in BOILERPLATE_PATTERNS), re.IGNORECASE)
_NON_DUTY_TAIL_RE = re.compile("|".join(f"(?:{p})" for p in NON_DUTY_TAIL_PATTERNS), re.IGNORECASE)
_SENT_BOUNDARY = re.compile(r"(?<=[.;:])\s+|\n+")

# A REAL sentence end: closing punctuation, or a blank line. A single newline is
# just PDF line wrapping — treating it as a boundary (as _SENT_BOUNDARY does) cuts
# every quoted sentence at ~90 characters, which is why the review checklist read
# as fragments like 'or clearing member and shall include –'.
_HARD_BOUNDARY = re.compile(r"(?<=[.;:])\s|\n\s*\n")

# Bounds on reconstructing a sentence. SEBI definitions run long, but an
# unpunctuated stretch should not swallow the whole page.
_SENTENCE_LOOKBACK = 700
_SENTENCE_LOOKAHEAD = 700


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
    """The line-bounded window around [start,end).

    Kept as-is because it decides which signals are dropped as boilerplate, and
    widening it would silently change how many signals a document reports. Use
    :func:`_readable_sentence` for anything shown to a person.
    """
    left = text.rfind("\n", 0, start)
    for m in _SENT_BOUNDARY.finditer(text, 0, start):
        left = max(left, m.end())
    right_m = _SENT_BOUNDARY.search(text, end)
    right = right_m.start() if right_m else len(text)
    return text[max(0, left):right]


#: How far either side of a duty word to look when deciding it is a definition,
#: a scope limit or a savings clause. Wide enough to survive the PDF's line
#: wrapping ("shall have the respective\nmeanings assigned"), deliberately narrow
#: enough that a definition elsewhere in the paragraph cannot suppress a genuine
#: duty sitting next to it.
_CONTEXT_RADIUS = 120


def _local_context(text: str, start: int, end: int) -> str:
    """Whitespace-normalised text immediately around [start,end)."""
    left = max(0, start - _CONTEXT_RADIUS)
    right = min(len(text), end + _CONTEXT_RADIUS)
    return " ".join(text[left:right].split())


def _tail_from(text: str, start: int) -> str:
    """Whitespace-normalised text beginning AT the duty word.

    Normalising matters: the phrase being tested often straddles the PDF's line
    wrapping ("shall have the respective\\nmeanings assigned").
    """
    return " ".join(text[start:start + _CONTEXT_RADIUS].split())


def _readable_sentence(text: str, start: int, end: int) -> str:
    """The complete sentence containing [start,end), for a human to read.

    Ignores the hard line breaks a PDF leaves behind and rejoins the wrapped
    lines, so a reviewer sees "'clearing corporation' shall mean a clearing
    corporation as defined in regulation 2(1)(i) of ..." rather than the 90
    characters that happened to fit on one line of the original page.
    """
    window_start = max(0, start - _SENTENCE_LOOKBACK)
    left = window_start
    for m in _HARD_BOUNDARY.finditer(text, window_start, start):
        left = m.end()

    window_end = min(len(text), end + _SENTENCE_LOOKAHEAD)
    boundary = _HARD_BOUNDARY.search(text, end, window_end)
    right = boundary.start() if boundary else window_end

    # Collapse the PDF's line wrapping into flowing text.
    return " ".join(text[left:right].split())


def sweep_signals(document_text: str) -> list[Signal]:
    """Find every obligation-signal occurrence, de-duplicating overlapping
    matches so the longest signal at a position wins.

    Administrative boilerplate ("shall come into force", "is available at
    www.sebi.gov.in", ...) is excluded: it carries a duty word but imposes no
    obligation, so it must not appear on a reviewer's checklist.
    """
    signals: list[Signal] = []
    last_end = -1
    for m in _SIGNAL_RE.finditer(document_text):
        if m.start() < last_end:  # overlaps previous longer match
            continue
        last_end = m.end()
        # Is the duty word itself part of a definition / scope / savings clause?
        if _NON_DUTY_TAIL_RE.match(_tail_from(document_text, m.start())):
            continue
        # Or does administrative boilerplate surround it?
        if _BOILERPLATE_RE.search(_local_context(document_text, m.start(), m.end())):
            continue
        signals.append(
            Signal(
                phrase=m.group(0),
                char_start=m.start(),
                char_end=m.end(),
                sentence=_readable_sentence(document_text, m.start(), m.end()),
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
