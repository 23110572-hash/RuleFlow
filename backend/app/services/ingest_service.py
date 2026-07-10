"""Ingestion service (Flow A, step 1).

Ingests a SEBI document into the CANONICAL layer:
  1. content_hash -> reuse if this exact document was ingested before.
  2. parse (structure tree + offsets).
  3. run the LangGraph + Groq extraction pipeline (self-corrected by the citation kernel).
  4. persist verified obligations; flagged ones are kept for human review.
  5. compile crisp obligations into Obligation Tests (kernel).
  6. build the Coverage Certificate (kernel) over accepted obligation spans.
  7. write an audit entry.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import threading

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.graph import run_extraction_pipeline
from app.db.models import CoverageReport, Document, Obligation, ObligationTest
from app.ingest.parser import ParsedDocument, parse_pdf_bytes, parse_text
from app.kernel.coverage import build_coverage_certificate
from app.kernel.hashing import content_hash
from app.kernel.obligation_tests import compile_obligation
from app.services import audit
from app.services import change_service
from app.services import progress


def find_by_hash(db: Session, chash: str) -> Document | None:
    return db.execute(select(Document).where(Document.content_hash == chash)).scalars().first()


def _persist_extraction(
    db: Session, document: Document, parsed: ParsedDocument, extraction
) -> list[Obligation]:
    obligations: list[Obligation] = []
    for po in extraction.obligations:
        ob = Obligation(
            source_document_id=document.id,
            clause_path=po.clause_path,
            verbatim_text=po.verbatim_text,
            normalized_statement=po.normalized_statement,
            modality=po.modality,
            trigger_condition=po.trigger_condition,
            deadline_or_periodicity=po.deadline_or_periodicity,
            threshold=po.threshold,
            applies_to=getattr(po, "applies_to", []) or [],
            citation=po.citation,
            citation_fidelity=po.citation_fidelity,
            status="verified" if po.status == "verified" else "flagged",
            valid_from=document.issue_date,
        )
        db.add(ob)
        db.flush()
        obligations.append(ob)

        # Compile crisp obligations into Obligation Tests (best_judgment/may -> None).
        spec = compile_obligation(
            {
                "modality": ob.modality,
                "deadline_or_periodicity": ob.deadline_or_periodicity,
                "threshold": ob.threshold,
            }
        )
        db.add(
            ObligationTest(
                obligation_id=ob.id,
                spec=spec,
                evaluator="kernel" if spec else "human",
            )
        )
    return obligations


def _persist_coverage(
    db: Session, document: Document, parsed: ParsedDocument, obligations: list[Obligation]
) -> CoverageReport:
    spans = [
        (o.citation["char_start"], o.citation["char_end"])
        for o in obligations
        if o.status == "verified" and o.citation.get("char_start") is not None
    ]
    cert = build_coverage_certificate(parsed.text, spans, document_id=document.id)
    report = CoverageReport(
        document_id=document.id,
        signals_total=cert.signals_total,
        extracted=cert.extracted,
        not_applicable=cert.not_applicable,
        unaccounted=cert.unaccounted,
        coverage_ratio=cert.coverage_ratio,
        detail=cert.to_dict(include_signals=True),
    )
    db.add(report)
    return report


def ingest_text(
    db: Session,
    *,
    title: str,
    text: str,
    circular_number: str | None = None,
    category: str | None = None,
    issue_date: datetime | None = None,
    source_url: str | None = None,
    is_public: bool = True,
    max_clauses: int | None = None,
    reuse: bool = True,
) -> tuple[Document, bool]:
    """Ingest raw text. Returns (document, created)."""
    chash = content_hash(text)
    if reuse:
        existing = find_by_hash(db, chash)
        if existing:
            return existing, False

    parsed = parse_text(text)
    document = Document(
        circular_number=circular_number,
        content_hash=chash,
        title=title,
        issue_date=issue_date,
        category=category,
        source_url=source_url,
        is_public=is_public,
        page_count=parsed.page_count,
        status="extracting",
    )
    db.add(document)
    db.flush()

    extraction = run_extraction_pipeline(
        parsed.text,
        parsed.clauses,
        document_category=category,
        max_clauses=max_clauses,
        enrich_applicability=True,
    )
    obligations = _persist_extraction(db, document, parsed, extraction)
    _persist_coverage(db, document, parsed, obligations)
    document.status = "ingested"

    audit.record(
        db,
        action="document.ingested",
        payload={
            "document_id": document.id,
            "content_hash": chash,
            "obligations": len(obligations),
            "flagged": extraction.flagged,
        },
        after_hash=chash,
    )
    db.commit()
    db.refresh(document)

    # Auto-trigger change detection (diff + impact) if a prior version exists.
    try:
        change_service.auto_change_detection(db, document)
    except Exception:
        import traceback
        traceback.print_exc()  # non-fatal: don't fail ingestion

    return document, True


def ingest_pdf(
    db: Session,
    *,
    title: str,
    data: bytes,
    circular_number: str | None = None,
    category: str | None = None,
    issue_date: datetime | None = None,
    source_url: str | None = None,
    is_public: bool = True,
    max_clauses: int | None = None,
    reuse: bool = True,
) -> tuple[Document, bool]:
    parsed = parse_pdf_bytes(data)
    return ingest_text(
        db,
        title=title,
        text=parsed.text,
        circular_number=circular_number,
        category=category,
        issue_date=issue_date,
        source_url=source_url,
        is_public=is_public,
        max_clauses=max_clauses,
        reuse=reuse,
    )


def ingest_pdf_async(
    db: Session,
    *,
    title: str,
    data: bytes,
    circular_number: str | None = None,
    category: str | None = None,
    issue_date: datetime | None = None,
    source_url: str | None = None,
    is_public: bool = True,
    max_clauses: int | None = None,
) -> tuple[Document, bool]:
    """Queue a PDF for extraction. Parsing + LLM extraction run entirely in a
    background thread so the HTTP request returns immediately.

    Returns (document, created) where ``created`` is False when an identical
    document (same content hash) was already ingested.
    """
    chash = hashlib.sha256(data).hexdigest()

    # Check for existing document with same content
    existing = find_by_hash(db, chash)
    if existing:
        return existing, False

    document = Document(
        circular_number=circular_number,
        content_hash=chash,
        title=title,
        issue_date=issue_date,
        category=category,
        source_url=source_url,
        is_public=is_public,
        page_count=0,
        status="parsing",
    )
    db.add(document)
    db.commit()
    # id/recorded_at are Python-side defaults populated on flush, so no refresh
    # round-trip is needed to read document.id below.
    document_id = document.id

    # Start progress tracking
    prog = progress.start(document_id)
    prog.status = "parsing"

    # Launch background extraction thread
    from app.db.base import SessionLocal
    thread = threading.Thread(
        target=_background_ingest,
        args=(SessionLocal, document_id, data, category, max_clauses),
        daemon=True,
    )
    thread.start()
    return document, True


def _background_ingest(
    db_factory,
    document_id: str,
    data: bytes,
    category: str | None,
    max_clauses: int | None,
) -> None:
    """Parse PDF and run LLM extraction in a background thread with progress updates."""
    db = db_factory()
    try:
        document = db.get(Document, document_id)
        if not document:
            return

        prog = progress.get(document_id)

        # 1. Parse PDF in the background
        parsed = parse_pdf_bytes(data)
        document.page_count = parsed.page_count
        db.commit()

        if prog:
            prog.status = "extracting"
            prog.total_clauses = len(parsed.clauses)

        # 2. Run extraction with progress callback
        from app.agents.graph import run_extraction_pipeline_with_progress
        extraction = run_extraction_pipeline_with_progress(
            parsed.text,
            parsed.clauses,
            document_category=category,
            max_clauses=max_clauses,
            enrich_applicability=True,
            on_clause_done=lambda done, total, obs: _update_progress(document_id, done, total, obs),
        )

        if prog:
            prog.status = "enriching"

        # 3. Persist results
        obligations = _persist_extraction(db, document, parsed, extraction)

        if prog:
            prog.status = "coverage"

        # 4. Coverage certificate
        _persist_coverage(db, document, parsed, obligations)
        document.status = "ingested"

        audit.record(
            db,
            action="document.ingested",
            payload={
                "document_id": document.id,
                "content_hash": document.content_hash,
                "obligations": len(obligations),
                "flagged": extraction.flagged,
            },
            after_hash=document.content_hash,
        )
        db.commit()

        if prog:
            prog.status = "done"
            prog.obligations_found = len(obligations)

        # Auto-trigger change detection (diff + impact) if a prior version exists.
        try:
            action_items = change_service.auto_change_detection(db, document)
            if prog:
                prog.action_items_generated = len(action_items)
        except Exception:
            import traceback
            traceback.print_exc()  # non-fatal: don't fail ingestion

    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            document = db.get(Document, document_id)
            if document:
                document.status = "error"
                db.commit()
        except Exception:
            pass
        prog = progress.get(document_id)
        if prog:
            prog.status = "error"
            prog.error = str(e)
    finally:
        db.close()


def _update_progress(document_id: str, done: int, total: int, obs_count: int) -> None:
    prog = progress.get(document_id)
    if prog:
        prog.processed_clauses = done
        prog.total_clauses = total
        prog.obligations_found = obs_count
