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
        }


@dataclass
class ExtractionResult:
    obligations: list[ProposedObligation] = field(default_factory=list)
    clauses_processed: int = 0
    flagged: int = 0

    def verified(self) -> list[ProposedObligation]:
        return [o for o in self.obligations if o.status == "verified"]


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
) -> list[ProposedObligation]:
    """Extract + verify obligations from a single clause."""
    threshold = threshold if threshold is not None else settings.citation_fidelity_threshold
    llm = get_llm()
    clause_text = document_text[clause.char_start:clause.char_end].strip()
    if len(clause_text) < 12:
        return []

    payload = llm.complete_json(
        EXTRACTION_SYSTEM,
        f"Clause path: {clause.clause_path}\nClause text:\n\"\"\"\n{clause_text}\n\"\"\"",
    )
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
                    f"Clause path: {clause.clause_path}\nClause text:\n\"\"\"\n{clause_text}\n\"\"\"\n\n"
                    f"Your previous quote was not found verbatim in the clause: {quote!r}. "
                    "Re-extract, quoting EXACTLY the characters that appear in the clause text."
                ),
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
            )
        )
    return _dedup_obligations(results)


def _norm_modality(value: str | None) -> str:
    v = (value or "shall").strip().lower()
    return v if v in {"shall", "may", "best_judgment"} else "shall"


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
