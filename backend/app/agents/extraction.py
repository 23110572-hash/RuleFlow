"""Extraction Agent (Groq).

For each clause, the agent proposes structured obligations WITH a verbatim
quote. The deterministic citation kernel then re-reads the cited span and
verifies grounding. Self-correction: if fidelity < threshold, the agent gets
one retry with an explicit "quote exactly" instruction; if it still fails, the
obligation is dropped or flagged for human review — never silently accepted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

import structlog

from app.agents.prompts import EXTRACTION_SYSTEM
from app.config import settings
from app.ingest.structure import ClauseUnit
from app.kernel.citation import citation_fidelity, verify_citation
from app.kernel.hashing import content_hash, normalize_text
from app.llm.client import get_llm

log = structlog.get_logger(__name__)


@dataclass
class ProposedObligation:
    clause_path: str
    verbatim_text: str
    normalized_statement: str
    modality: str
    trigger_condition: str | None
    deadline_or_periodicity: str | None
    threshold: str | None
    citation: dict
    citation_fidelity: float
    status: str  # verified | flagged
    reason: str = ""
    #: Which intermediary categories the obligation binds, as
    #: ``[{"category": ..., "tier": ...}]``. An EMPTY list is meaningful: it
    #: means "binds every category", which is how the compliance layer treats a
    #: generic obligation. We deliberately leave it empty whenever the model is
    #: unsure, because a wrongly narrowed category would hide the obligation
    #: from a firm that must comply with it.
    applies_to: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "clause_path": self.clause_path,
            "verbatim_text": self.verbatim_text,
            "normalized_statement": self.normalized_statement,
            "modality": self.modality,
            "trigger_condition": self.trigger_condition,
            "deadline_or_periodicity": self.deadline_or_periodicity,
            "threshold": self.threshold,
            "citation": self.citation,
            "citation_fidelity": round(self.citation_fidelity, 4),
            "status": self.status,
            "reason": self.reason,
            "applies_to": self.applies_to,
        }


@dataclass
class ExtractionResult:
    obligations: list[ProposedObligation] = field(default_factory=list)
    clauses_processed: int = 0
    flagged: int = 0
    #: clauses whose extraction raised (LLM/network failure), not clauses that
    #: legitimately contained no obligation. A run where this equals
    #: clauses_processed is a FAILED run, not an empty document.
    clauses_failed: int = 0
    last_error: str = ""
    #: clause_path of every clause that raised, so a reviewer is told WHICH part
    #: of the regulation is missing from the register rather than only how many.
    failed_clause_paths: list[str] = field(default_factory=list)

    def verified(self) -> list[ProposedObligation]:
        return [o for o in self.obligations if o.status == "verified"]

    @property
    def totally_failed(self) -> bool:
        return self.clauses_processed > 0 and self.clauses_failed >= self.clauses_processed


def _locate_in_clause(document_text: str, clause: ClauseUnit, quote: str) -> tuple[int, int]:
    """Find the char offsets of `quote` within the clause span of the full doc.
    Falls back to the whole clause span if the exact quote can't be located."""
    hay = document_text[clause.char_start:clause.char_end]
    norm_hay = normalize_text(hay)
    norm_q = normalize_text(quote)
    idx = norm_hay.find(norm_q)
    if idx != -1:
        # Map normalized index roughly back to raw offsets via first token.
        probe = quote.strip().split()[0] if quote.strip() else quote[:10]
        raw_idx = hay.lower().find(probe.lower())
        if raw_idx == -1:
            raw_idx = 0
        start = clause.char_start + raw_idx
        end = min(clause.char_end, start + len(quote) + 10)
        return start, end
    return clause.char_start, clause.char_end


def extract_from_clause(
    document_text: str,
    clause: ClauseUnit,
    source_hash: str,
    threshold: float | None = None,
    document_category: str | None = None,
) -> list[ProposedObligation]:
    """Extract + verify obligations from a single clause.

    One LLM call per clause (plus at most one self-correction retry). The call
    also returns applicability, so there is no second enrichment pass over the
    obligations — see ``_norm_applies_to`` for the conservative policy applied
    to the model's answer.
    """
    threshold = threshold if threshold is not None else settings.citation_fidelity_threshold
    llm = get_llm()
    clause_text = document_text[clause.char_start:clause.char_end].strip()
    if len(clause_text) < 12:
        return []

    user_prompt = (
        f"Document category: {document_category or 'unknown'}\n"
        f"Clause path: {clause.clause_path}\n"
        f"Clause text:\n\"\"\"\n{clause_text}\n\"\"\""
    )
    budget = _output_budget(len(clause_text))
    payload = llm.complete_json(EXTRACTION_SYSTEM, user_prompt, max_tokens=budget)
    raw_obs = (payload or {}).get("obligations", []) if isinstance(payload, dict) else []

    results: list[ProposedObligation] = []
    for raw in raw_obs:
        quote = (raw.get("verbatim_text") or "").strip()
        if not quote:
            continue
        start, end = _locate_in_clause(document_text, clause, quote)
        check = verify_citation(document_text, start, end, quote, threshold, source_hash)

        # Self-correction: one retry to quote exactly if not grounded.
        if not check.grounded:
            retry = llm.complete_json(
                EXTRACTION_SYSTEM,
                (
                    f"{user_prompt}\n\n"
                    f"Your previous quote was not found verbatim in the clause: {quote!r}. "
                    "Re-extract, quoting EXACTLY the characters that appear in the clause text."
                ),
                max_tokens=budget,
            )
            retry_obs = (retry or {}).get("obligations", []) if isinstance(retry, dict) else []
            if retry_obs:
                quote2 = (retry_obs[0].get("verbatim_text") or "").strip()
                if quote2:
                    s2, e2 = _locate_in_clause(document_text, clause, quote2)
                    check2 = verify_citation(document_text, s2, e2, quote2, threshold, source_hash)
                    if check2.fidelity > check.fidelity:
                        raw, quote, start, end, check = retry_obs[0], quote2, s2, e2, check2

        status = "verified" if check.grounded else "flagged"
        results.append(
            ProposedObligation(
                clause_path=clause.clause_path,
                verbatim_text=quote,
                normalized_statement=(raw.get("normalized_statement") or quote).strip(),
                modality=_norm_modality(raw.get("modality")),
                trigger_condition=raw.get("trigger_condition") or None,
                deadline_or_periodicity=raw.get("deadline_or_periodicity") or None,
                threshold=raw.get("threshold") or None,
                citation={
                    "page": check.located_span and clause.page or clause.page,
                    "char_start": start,
                    "char_end": end,
                    "source_hash": source_hash,
                },
                citation_fidelity=check.fidelity,
                status=status,
                reason=check.reason,
                applies_to=_norm_applies_to(raw),
            )
        )
    return _dedup_obligations(results)


def _output_budget(clause_chars: int) -> int:
    """Output ceiling for a clause of ``clause_chars`` characters.

    Response size tracks clause size: for every obligation the model returns a
    verbatim quote FROM the clause plus a restatement OF it, so the text it
    writes is roughly twice the duty content it read (~4 chars per token, hence
    a term of one token per character). The constant covers JSON field names.

    Never goes below ``llm_max_tokens``, so this can only give a clause more room
    than before, never less. Raising the ceiling costs nothing on its own —
    billing is on tokens generated, not on the cap.
    """
    proportional = 600 + clause_chars
    return max(
        settings.llm_max_tokens,
        min(settings.llm_max_tokens_ceiling, proportional),
    )


#: Renamed from "best_judgment", which read as an invented category next to two
#: real legal modal verbs. The old spelling is still accepted on the way in: it
#: appears in older records and a model may echo it back from the prior prompt.
_LEGACY_MODALITY = {"best_judgment": "judgement_based"}


def _norm_modality(value: str | None) -> str:
    v = (value or "shall").strip().lower()
    v = _LEGACY_MODALITY.get(v, v)
    return v if v in {"shall", "may", "judgement_based"} else "shall"


#: Upper bound on categories kept for one obligation. A longer list is the model
#: listing every category it can think of, which is noise, not scope.
_MAX_APPLIES_TO = 8


def _norm_applies_to(raw: dict) -> list[dict]:
    """Normalise the model's applicability answer, biased towards safety.

    The compliance layer reads an EMPTY list as "this obligation binds every
    category" and a populated list as a hard filter. A filter built on a guess
    would hide obligations from firms that must comply, so we only keep the
    model's list when it committed to it:

    - ``applicability_ambiguous`` is truthy  -> [] (treated as: binds everyone)
    - a category of "all"/"any"              -> [] (same meaning, canonical form)
    - anything unparseable or empty          -> [] (binds everyone)
    """
    if not isinstance(raw, dict):
        return []
    if raw.get("applicability_ambiguous"):
        return []

    entries = raw.get("applies_to")
    if not isinstance(entries, list):
        return []

    normalized: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        category = str(entry.get("category") or "").strip().lower()
        if not category:
            continue
        # "all"/"any" is exactly what an empty list already means downstream.
        if category in {"all", "any", "unknown", "n/a", "none"}:
            return []
        tier_raw = entry.get("tier")
        tier = str(tier_raw).strip() if tier_raw not in (None, "") else None
        key = (category, tier or "")
        if key in seen:
            continue
        seen.add(key)
        normalized.append({"category": category, "tier": tier})

    if len(normalized) > _MAX_APPLIES_TO:
        return []
    return normalized


def _dedup_obligations(obs: list[ProposedObligation]) -> list[ProposedObligation]:
    """Collapse near-identical obligations extracted from the same clause.

    The model often emits the same duty two or three times with minor wording
    changes ("may invest funds in..." vs "may invest in..."). We treat two
    obligations with the SAME modality and a >=0.88 similar normalized
    statement as duplicates, keeping the better-grounded one (verified over
    flagged, then higher citation fidelity, then the longer statement)."""
    kept: list[ProposedObligation] = []
    for o in obs:
        norm = normalize_text(o.normalized_statement)
        is_dup = False
        for i, k in enumerate(kept):
            if k.modality != o.modality:
                continue
            kn = normalize_text(k.normalized_statement)
            if norm == kn or SequenceMatcher(None, norm, kn).ratio() >= 0.88:
                is_dup = True
                better = (
                    o.status == "verified",
                    o.citation_fidelity,
                    len(o.normalized_statement),
                ) > (
                    k.status == "verified",
                    k.citation_fidelity,
                    len(k.normalized_statement),
                )
                if better:
                    kept[i] = o
                break
        if not is_dup:
            kept.append(o)
    return kept


def extract_document(
    document_text: str,
    clauses: list[ClauseUnit],
    threshold: float | None = None,
    max_clauses: int | None = None,
) -> ExtractionResult:
    """Run extraction over all clauses of a document."""
    source_hash = content_hash(document_text)
    result = ExtractionResult()
    targets = clauses[:max_clauses] if max_clauses else clauses
    for clause in targets:
        try:
            obs = extract_from_clause(document_text, clause, source_hash, threshold)
        except Exception as exc:  # a hard LLM failure must surface, not fake data
            log.error("extraction_failed", clause=clause.clause_path, error=str(exc))
            raise
        result.obligations.extend(obs)
        result.clauses_processed += 1
    result.flagged = sum(1 for o in result.obligations if o.status == "flagged")
    return result
