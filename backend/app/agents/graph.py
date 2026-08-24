"""LangGraph orchestration of the extraction + enrichment pipeline.

Genuine agentic control flow: the graph advances through the clause list via the
Extraction Agent (which self-corrects against the citation kernel), then runs an
enrichment pass over the verified obligations.

Two properties matter here and are load-bearing:

* Clauses are independent, so each step dispatches a bounded window of them
  concurrently (``settings.llm_concurrency``). A 500-clause circular is
  hundreds of LLM round-trips; running them one at a time is what made ingest
  take tens of minutes. Concurrency is bounded because providers rate-limit.
* Results are reassembled in CLAUSE ORDER regardless of completion order. The
  coverage certificate, diff, and audit hashes are computed over this sequence,
  so a non-deterministic order would produce a different record for the same
  document.

Applicability is answered by the extraction call itself, so there is no second
LLM pass over every obligation.

LangGraph is imported lazily so the core API/kernel run without the optional
`agents` extra installed. If it is missing, `run_extraction_pipeline` raises a
clear, actionable error (never a silent fallback).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, TypedDict

import structlog

from app.agents.extraction import ExtractionResult, extract_from_clause
from app.config import settings
from app.ingest.structure import ClauseUnit
from app.kernel.hashing import content_hash

log = structlog.get_logger(__name__)


def _extract_many(
    document_text: str,
    clauses: list[ClauseUnit],
    source_hash: str,
    threshold: float,
    document_category: str | None = None,
    on_clause_done: Callable | None = None,
    processed_offset: int = 0,
    total_override: int | None = None,
) -> tuple[list[dict], list[str], str]:
    """Extract from ``clauses`` concurrently.

    Returns (obligations, failed_clause_paths, last_error).

    Obligations come back in clause order, not completion order. A single flaky
    clause is recorded rather than raised, so one bad clause cannot destroy a
    500-clause run; the failures are returned so the caller can distinguish "this
    document contains no obligations" from "every LLM call failed", and can name
    the clauses a reviewer needs to look at.
    """
    total = len(clauses)
    if total == 0:
        return [], [], ""

    # One slot per clause, filled by exactly one worker -> order is preserved
    # and no lock is needed to write into it.
    per_clause: list[list[dict]] = [[] for _ in range(total)]
    failed_paths: list[str] = []
    last_error = ""
    workers = max(1, min(settings.llm_concurrency, total))
    reported_total = total_override if total_override is not None else total

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="extract") as pool:
        futures = {
            pool.submit(
                extract_from_clause,
                document_text,
                clause,
                source_hash,
                threshold,
                document_category,
            ): i
            for i, clause in enumerate(clauses)
        }
        # as_completed() yields in the calling thread, so the progress callback
        # is never invoked concurrently.
        done = 0
        for future in as_completed(futures):
            i = futures[future]
            try:
                per_clause[i] = [o.to_dict() for o in future.result()]
            except Exception as exc:
                failed_paths.append(clauses[i].clause_path)
                last_error = str(exc)
                log.warning(
                    "clause_extraction_failed",
                    clause=clauses[i].clause_path,
                    error=last_error,
                )
            done += 1
            if on_clause_done:
                found = sum(len(chunk) for chunk in per_clause)
                on_clause_done(
                    processed_offset + done, reported_total, found, len(failed_paths)
                )

    obligations = [ob for chunk in per_clause for ob in chunk]
    # Report in clause order, not completion order, so the list a reviewer sees
    # follows the regulation.
    order = {c.clause_path: n for n, c in enumerate(clauses)}
    failed_paths.sort(key=lambda p: order.get(p, 0))
    return obligations, failed_paths, last_error


def _apply_applicability_policy(obligations: list[dict], enabled: bool) -> None:
    """Applicability now arrives with the extraction call. When enrichment is
    switched off, drop it so the caller gets the same shape as before (an empty
    list, which the compliance layer reads as "binds every category")."""
    for ob in obligations:
        if not enabled:
            ob["applies_to"] = []
        elif not isinstance(ob.get("applies_to"), list):
            ob["applies_to"] = []


class PipelineState(TypedDict, total=False):
    document_text: str
    clauses: list[ClauseUnit]
    source_hash: str
    threshold: float
    document_category: str | None
    cursor: int
    obligations: list[dict]
    enrich_applicability: bool


def _extract_node(state: PipelineState) -> PipelineState:
    """Advance the cursor by one bounded, concurrent window of clauses."""
    i = state["cursor"]
    window = state["clauses"][i : i + max(1, settings.llm_concurrency)]
    obligations, failed_paths, last_error = _extract_many(
        state["document_text"],
        window,
        state["source_hash"],
        state["threshold"],
        state.get("document_category"),
    )
    # This entry point has always failed loudly on a bad clause; keep it that
    # way rather than silently degrading a synchronous ingest.
    if failed_paths:
        raise RuntimeError(
            f"Extraction failed on {len(failed_paths)} of {len(window)} clause(s) "
            f"({', '.join(failed_paths)}). Last error: {last_error}"
        )
    state["obligations"].extend(obligations)
    state["cursor"] = i + len(window)
    return state


def _should_continue(state: PipelineState) -> str:
    return "extract" if state["cursor"] < len(state["clauses"]) else "enrich"


def _enrich_node(state: PipelineState) -> PipelineState:
    """Deterministic: applicability was already returned by the extraction call,
    so this node only enforces the policy (no LLM call, no second pass)."""
    _apply_applicability_policy(
        state["obligations"], bool(state.get("enrich_applicability"))
    )
    return state


def build_graph():
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError(
            "LangGraph is required for the agent pipeline. "
            "Install with: pip install -e \".[agents]\""
        ) from exc

    g = StateGraph(PipelineState)
    g.add_node("extract", _extract_node)
    g.add_node("enrich", _enrich_node)
    g.add_edge(START, "extract")
    g.add_conditional_edges("extract", _should_continue, {"extract": "extract", "enrich": "enrich"})
    g.add_edge("enrich", END)
    return g.compile()


def run_extraction_pipeline(
    document_text: str,
    clauses: list[ClauseUnit],
    threshold: float | None = None,
    document_category: str | None = None,
    max_clauses: int | None = None,
    enrich_applicability: bool = False,
) -> ExtractionResult:
    """Execute the LangGraph pipeline and return a normalized ExtractionResult."""
    targets = clauses[:max_clauses] if max_clauses else clauses
    if not targets:
        return ExtractionResult()

    graph = build_graph()
    initial: PipelineState = {
        "document_text": document_text,
        "clauses": targets,
        "source_hash": content_hash(document_text),
        "threshold": threshold if threshold is not None else settings.citation_fidelity_threshold,
        "document_category": document_category,
        "cursor": 0,
        "obligations": [],
        "enrich_applicability": enrich_applicability,
    }
    # Each extract step consumes a window of `llm_concurrency` clauses, so the
    # graph needs one step per window plus enrichment. Kept generous.
    steps = -(-len(targets) // max(1, settings.llm_concurrency))
    final: dict[str, Any] = graph.invoke(initial, {"recursion_limit": steps * 2 + 10})

    result = ExtractionResult()
    from app.agents.extraction import ProposedObligation

    for od in final["obligations"]:
        result.obligations.append(
            ProposedObligation(
                clause_path=od["clause_path"],
                verbatim_text=od["verbatim_text"],
                normalized_statement=od["normalized_statement"],
                modality=od["modality"],
                trigger_condition=od.get("trigger_condition"),
                deadline_or_periodicity=od.get("deadline_or_periodicity"),
                threshold=od.get("threshold"),
                citation=od["citation"],
                citation_fidelity=od["citation_fidelity"],
                status=od["status"],
                reason=od.get("reason", ""),
                applies_to=od.get("applies_to") or [],
            )
        )
    result.clauses_processed = len(targets)
    result.flagged = sum(1 for o in result.obligations if o.status == "flagged")
    return result


def run_extraction_pipeline_with_progress(
    document_text: str,
    clauses: list[ClauseUnit],
    threshold: float | None = None,
    document_category: str | None = None,
    max_clauses: int | None = None,
    enrich_applicability: bool = False,
    on_clause_done: callable | None = None,
) -> ExtractionResult:
    """Like run_extraction_pipeline but with a progress callback.

    on_clause_done(processed: int, total: int, obligations_so_far: int, failed: int)

    Clauses run concurrently (bounded by ``settings.llm_concurrency``) and are
    reassembled in clause order, so progress may arrive in bursts while the
    resulting record stays deterministic.
    """
    from app.agents.extraction import ProposedObligation

    targets = clauses[:max_clauses] if max_clauses else clauses
    if not targets:
        return ExtractionResult()

    source_hash = content_hash(document_text)
    thr = threshold if threshold is not None else settings.citation_fidelity_threshold

    all_obligations, failed_paths, last_error = _extract_many(
        document_text,
        targets,
        source_hash,
        thr,
        document_category,
        on_clause_done=on_clause_done,
    )

    # Every clause failed: this is a provider/config failure, not an empty
    # document. Surface it so the ingest is recorded as an error instead of a
    # clean run with zero obligations.
    if targets and len(failed_paths) >= len(targets):
        raise RuntimeError(
            f"Extraction failed on all {len(failed_paths)} clause(s). Last error: {last_error}"
        )

    # Applicability came back with the extraction call; only the policy is left.
    _apply_applicability_policy(all_obligations, enrich_applicability)

    result = ExtractionResult(
        clauses_failed=len(failed_paths),
        last_error=last_error,
        failed_clause_paths=failed_paths,
    )
    for od in all_obligations:
        result.obligations.append(
            ProposedObligation(
                clause_path=od["clause_path"],
                verbatim_text=od["verbatim_text"],
                normalized_statement=od["normalized_statement"],
                modality=od["modality"],
                trigger_condition=od.get("trigger_condition"),
                deadline_or_periodicity=od.get("deadline_or_periodicity"),
                threshold=od.get("threshold"),
                citation=od["citation"],
                citation_fidelity=od["citation_fidelity"],
                status=od["status"],
                reason=od.get("reason", ""),
                applies_to=od.get("applies_to") or [],
            )
        )
    result.clauses_processed = len(targets)
    result.flagged = sum(1 for o in result.obligations if o.status == "flagged")
    return result
