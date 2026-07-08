"""LangGraph orchestration of the extraction + enrichment pipeline.

Genuine agentic control flow: the graph loops clause-by-clause through the
Extraction Agent (which self-corrects against the citation kernel), then runs an
enrichment pass (applicability) over the verified obligations.

LangGraph is imported lazily so the core API/kernel run without the optional
`agents` extra installed. If it is missing, `run_extraction_pipeline` raises a
clear, actionable error (never a silent fallback).
"""
from __future__ import annotations

from typing import Any, TypedDict

import structlog

from app.agents.extraction import ExtractionResult, extract_from_clause
from app.agents.reasoning import decide_applicability
from app.config import settings
from app.ingest.structure import ClauseUnit
from app.kernel.hashing import content_hash

log = structlog.get_logger(__name__)


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
    i = state["cursor"]
    clause = state["clauses"][i]
    obs = extract_from_clause(
        state["document_text"], clause, state["source_hash"], state["threshold"]
    )
    state["obligations"].extend(o.to_dict() for o in obs)
    state["cursor"] = i + 1
    return state


def _should_continue(state: PipelineState) -> str:
    return "extract" if state["cursor"] < len(state["clauses"]) else "enrich"


def _enrich_node(state: PipelineState) -> PipelineState:
    if not state.get("enrich_applicability"):
        return state
    for ob in state["obligations"]:
        if ob["status"] != "verified":
            continue
        try:
            app = decide_applicability(ob["verbatim_text"], state.get("document_category"))
            ob["applies_to"] = app.get("applies_to", [])
            ob["applicability_ambiguous"] = app.get("ambiguous", False)
        except Exception as exc:  # pragma: no cover - network path
            log.warning("applicability_failed", error=str(exc))
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
    # Recursion limit must accommodate one step per clause plus enrichment.
    final: dict[str, Any] = graph.invoke(initial, {"recursion_limit": len(targets) * 2 + 10})

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
    """Like run_extraction_pipeline but with a progress callback after each clause.

    on_clause_done(processed: int, total: int, obligations_so_far: int)
    """
    from app.agents.extraction import ProposedObligation

    targets = clauses[:max_clauses] if max_clauses else clauses
    if not targets:
        return ExtractionResult()

    source_hash = content_hash(document_text)
    thr = threshold if threshold is not None else settings.citation_fidelity_threshold

    all_obligations: list[dict] = []

    # Process clauses one by one with progress callbacks
    for i, clause in enumerate(targets):
        try:
            obs = extract_from_clause(document_text, clause, source_hash, thr)
            all_obligations.extend(o.to_dict() for o in obs)
        except Exception as exc:
            log.warning("clause_extraction_failed", clause=clause.clause_path, error=str(exc))

        if on_clause_done:
            on_clause_done(i + 1, len(targets), len(all_obligations))

    # Enrichment pass
    if enrich_applicability:
        for ob in all_obligations:
            if ob["status"] != "verified":
                continue
            try:
                app = decide_applicability(ob["verbatim_text"], document_category)
                ob["applies_to"] = app.get("applies_to", [])
                ob["applicability_ambiguous"] = app.get("ambiguous", False)
            except Exception as exc:
                log.warning("applicability_failed", error=str(exc))

    result = ExtractionResult()
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
            )
        )
    result.clauses_processed = len(targets)
    result.flagged = sum(1 for o in result.obligations if o.status == "flagged")
    return result
