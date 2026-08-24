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

from bisect import bisect_right
from datetime import datetime, timezone
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
            # Empty list is meaningful: the compliance layer reads it as
            # "binds every category". The extraction agent leaves it empty
            # whenever applicability was ambiguous.
            applies_to=po.applies_to or [],
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


def _supersede_previous_extraction(db: Session, document: Document) -> int:
    """Retire the results of an earlier analysis of this same document.

    Obligations are marked ``superseded`` (and closed in valid-time) rather than
    deleted: Controls, Gaps, Interpretations and Findings hold loose references
    to obligation ids, and every scope query already filters on
    ``verified|approved|flagged``, so superseded rows drop out of the live
    register while remaining auditable. Coverage reports are pure derived data
    and are replaced outright.
    """
    previous = db.execute(
        select(Obligation).where(Obligation.source_document_id == document.id)
    ).scalars().all()
    now = datetime.now(timezone.utc)
    retired = 0
    for ob in previous:
        if ob.status == "superseded":
            continue
        ob.status = "superseded"
        if ob.valid_to is None:
            ob.valid_to = now
        retired += 1

    for report in db.execute(
        select(CoverageReport).where(CoverageReport.document_id == document.id)
    ).scalars().all():
        db.delete(report)

    db.flush()
    return retired


def _persist_coverage(
    db: Session, document: Document, parsed: ParsedDocument, obligations: list[Obligation]
) -> CoverageReport:
    """Build the review checklist: which duty sentences did nobody account for?

    A signal counts as accounted for when the CLAUSE it lives in produced an
    obligation — not merely when it falls inside the model's short verbatim
    quote. A clause containing three "shall"s that yielded one obligation was
    genuinely read, so flagging the other two as missed was wrong and was the
    main reason a correct run reported ~45%.

    ``flagged`` obligations count too: a low citation-fidelity score means the
    quote needs a human eye, not that the clause went unread.

    Clauses are matched by CITATION OFFSET, not by ``clause_path``. Paths are
    not unique — schedules and annexures restart numbering, so a single document
    can contain "Ch.XI 1" a dozen times — and keying a dict by path silently
    collapsed them onto one span, crediting coverage to the wrong region of the
    document. The citation's char offset identifies the clause unambiguously.
    """
    clause_spans = sorted(
        (c.char_start, c.char_end) for c in parsed.clauses if c.char_end > c.char_start
    )
    clause_starts = [s for s, _ in clause_spans]

    def containing_clause(pos: int) -> tuple[int, int] | None:
        """The clause span that physically contains ``pos``. Clause spans tile
        the document in order and never overlap, so the candidate is the last
        clause starting at or before ``pos``."""
        i = bisect_right(clause_starts, pos) - 1
        if i >= 0:
            start, end = clause_spans[i]
            if start <= pos < end:
                return start, end
        return None

    # Fallback only, for obligations with no usable citation offset. First
    # occurrence wins; see the docstring on why this cannot be the primary key.
    span_by_path: dict[str, tuple[int, int]] = {}
    for c in parsed.clauses:
        if c.char_end > c.char_start:
            span_by_path.setdefault(c.clause_path, (c.char_start, c.char_end))

    spans: list[tuple[int, int]] = []
    for o in obligations:
        if o.status == "superseded":
            continue
        citation = o.citation or {}
        pos = citation.get("char_start")
        span = containing_clause(pos) if pos is not None else None
        if span is None:
            span = span_by_path.get(o.clause_path)
        if span is None and pos is not None and citation.get("char_end") is not None:
            span = (pos, citation["char_end"])
        if span:
            spans.append(span)

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
    firm_id: str | None = None,
) -> tuple[Document, bool]:
    """Ingest raw text. Returns (document, created)."""
    chash = content_hash(text)

    # Each firm gets its own copy — no sharing between accounts
    if firm_id:
        existing = db.execute(
            select(Document).where(Document.content_hash == chash, Document.firm_id == firm_id)
        ).scalars().first()
    elif reuse:
        existing = find_by_hash(db, chash)
    else:
        existing = None

    if existing:
        return existing, False

    parsed = parse_text(text)
    document = Document(
        firm_id=firm_id,
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
    firm_id: str | None = None,
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
        firm_id=firm_id,
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
    firm_id: str | None = None,
) -> tuple[Document, bool]:
    """Queue a PDF for extraction. Parsing + LLM extraction run entirely in a
    background thread so the HTTP request returns immediately.

    Returns (document, created) where ``created`` is False when an identical
    document (same content hash) was already ingested by this firm.
    """
    chash = hashlib.sha256(data).hexdigest()

    # Check for existing document scoped to THIS firm only
    existing = None
    if firm_id:
        existing = db.execute(
            select(Document).where(Document.content_hash == chash, Document.firm_id == firm_id)
        ).scalars().first()
    else:
        existing = find_by_hash(db, chash)

    if existing:
        document = existing
        document.title = title or document.title
        document.circular_number = circular_number or document.circular_number
        document.category = category or document.category
        document.source_url = source_url or document.source_url
        if issue_date:
            document.issue_date = issue_date
        document.page_count = 0
        document.status = "parsing"
    else:
        document = Document(
            firm_id=firm_id,
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
    # Always True: a run was started, so the caller must show the live analysis
    # flow rather than a cached summary.
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

        if not parsed.clauses:
            raise ValueError(
                "The document was read but no clauses or paragraphs could be "
                "identified in it. Please check that this is a SEBI circular or "
                "master circular."
            )

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
            on_clause_done=lambda done, total, obs, failed: _update_progress(
                document_id, done, total, obs, failed
            ),
        )

        if prog:
            prog.status = "enriching"
            prog.failed_clauses = extraction.clauses_failed

        # 3. Persist results. This upload replaces any earlier analysis of the
        #    same document — we only reach here once extraction actually
        #    succeeded, so the previous register is never dropped for nothing.
        _supersede_previous_extraction(db, document)
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
                "clauses_failed": extraction.clauses_failed,
            },
            after_hash=document.content_hash,
        )
        db.commit()

        if prog:
            prog.status = "done"
            prog.obligations_found = len(obligations)
            prog.failed_clauses = extraction.clauses_failed
            if extraction.clauses_failed:
                prog.error = (
                    f"{extraction.clauses_failed} of {extraction.clauses_processed} "
                    f"clauses could not be analysed. Last error: {extraction.last_error[:200]}"
                )

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
            db.rollback()
            document = db.get(Document, document_id)
            if document:
                # A failed analysis is recorded as an error, never as a clean
                # "ingested" run with zero obligations. Any earlier successful
                # extraction of this document is left untouched.
                document.status = "error"
                db.commit()
        except Exception:
            pass
        prog = progress.get(document_id)
        if prog:
            prog.status = "error"
            prog.error = _friendly_error(e)
    finally:
        db.close()


def _friendly_error(exc: Exception) -> str:
    """Turn provider/parser failures into something a compliance officer can act on."""
    msg = str(exc)
    low = msg.lower()
    if "402" in msg or "more credits" in low or "insufficient" in low:
        return (
            "The AI provider rejected the request for billing reasons (no credits "
            "or the request exceeded the key's limit). Please top up or update the "
            "API key, then upload again."
        )
    if "429" in msg or "rate limit" in low:
        return "The AI provider is rate limiting this key. Please wait a moment and upload again."
    if "401" in msg or "invalid api key" in low or "not configured" in low:
        return "The AI provider rejected the API key. Please check the key configuration."
    if "timeout" in low or "timed out" in low:
        return "The AI provider timed out. Please upload again."
    return msg[:400]


def _update_progress(
    document_id: str, done: int, total: int, obs_count: int, failed: int = 0
) -> None:
    prog = progress.get(document_id)
    if prog:
        prog.processed_clauses = done
        prog.total_clauses = total
        prog.obligations_found = obs_count
        prog.failed_clauses = failed
