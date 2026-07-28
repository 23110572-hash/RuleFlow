"""Documents API — ingest SEBI documents, view coverage certificates."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import CoverageReport, Document, Obligation
from app.schemas.models import CoverageOut, DocumentOut, IngestTextIn
from app.services import ingest_service

router = APIRouter(prefix="/documents", tags=["documents"])


def _doc_out(db: Session, doc: Document) -> DocumentOut:
    ob_count = db.execute(
        select(func.count(Obligation.id)).where(
            Obligation.source_document_id == doc.id,
            # Results of a previous analysis of the same document are retired,
            # not deleted; they must not inflate the live count.
            Obligation.status != "superseded",
        )
    ).scalar_one()
    cov = db.execute(
        select(CoverageReport).where(CoverageReport.document_id == doc.id)
    ).scalars().first()
    coverage = None
    if cov:
        coverage = {
            "signals_total": cov.signals_total,
            "extracted": cov.extracted,
            "not_applicable": cov.not_applicable,
            "unaccounted": cov.unaccounted,
            "coverage_ratio": cov.coverage_ratio,
        }
    return DocumentOut(
        id=doc.id,
        circular_number=doc.circular_number,
        content_hash=doc.content_hash,
        title=doc.title,
        category=doc.category,
        issue_date=doc.issue_date,
        source_url=doc.source_url,
        is_public=doc.is_public,
        page_count=doc.page_count,
        status=doc.status,
        obligation_count=ob_count,
        coverage=coverage,
    )


@router.get("", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)):
    docs = db.execute(select(Document).order_by(Document.recorded_at.desc())).scalars().all()
    return [_doc_out(db, d) for d in docs]


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "document not found")
    return _doc_out(db, doc)


@router.post("/ingest-text", response_model=DocumentOut)
def ingest_document_text(
    body: IngestTextIn,
    max_clauses: int | None = Query(None, description="Cap clauses processed (cost control)"),
    db: Session = Depends(get_db),
):
    doc, _created = ingest_service.ingest_text(
        db,
        title=body.title,
        text=body.text,
        circular_number=body.circular_number,
        category=body.category,
        issue_date=body.issue_date,
        source_url=body.source_url,
        is_public=body.is_public,
        max_clauses=max_clauses,
    )
    return _doc_out(db, doc)


@router.post("/ingest-pdf", response_model=DocumentOut)
def ingest_document_pdf(
    file: UploadFile = File(...),
    title: str = Form(...),
    circular_number: str | None = Form(None),
    category: str | None = Form(None),
    max_clauses: int | None = Form(None),
    db: Session = Depends(get_db),
):
    # Sync endpoint on purpose: FastAPI runs it in a worker thread, so the
    # blocking DB round-trips here never freeze the async event loop (which
    # would otherwise stall the progress polling and make the app feel dead).
    data = file.file.read()
    doc, created = ingest_service.ingest_pdf_async(
        db,
        title=title,
        data=data,
        circular_number=circular_number,
        category=category,
        max_clauses=max_clauses,
    )
    if created:
        # Freshly queued document: no obligations/coverage yet, so skip the
        # extra count/coverage queries and respond immediately.
        return DocumentOut(
            id=doc.id,
            circular_number=doc.circular_number,
            content_hash=doc.content_hash,
            title=doc.title,
            category=doc.category,
            issue_date=doc.issue_date,
            source_url=doc.source_url,
            is_public=doc.is_public,
            page_count=doc.page_count,
            status=doc.status,
            obligation_count=0,
            coverage=None,
        )
    return _doc_out(db, doc)


@router.get("/{document_id}/progress")
def get_progress(document_id: str, db: Session = Depends(get_db)):
    """Live progress for an in-flight analysis.

    The in-memory tracker is per-process and is lost on restart/redeploy, so when
    there is no entry we answer from the database instead of inventing a
    successful-but-empty result (which is what used to make a finished 81
    obligation document report "done, 0 obligations found").
    """
    from app.services import progress

    prog = progress.get(document_id)
    if prog:
        return prog.to_dict()

    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "document not found")

    ob_count = db.execute(
        select(func.count(Obligation.id)).where(
            Obligation.source_document_id == doc.id, Obligation.status != "superseded"
        )
    ).scalar_one()

    if doc.status == "error":
        status, error = "error", "Analysis failed. Please upload the document again."
    elif doc.status in ("parsing", "extracting"):
        # The worker died with the process; nothing is running any more.
        status, error = "error", "Analysis was interrupted (the server restarted). Please upload again."
    else:
        status, error = "done", None

    return {
        "document_id": document_id,
        "status": status,
        "percent": 100,
        "total_clauses": 0,
        "processed_clauses": 0,
        "obligations_found": ob_count,
        "failed_clauses": 0,
        "action_items_generated": 0,
        "error": error,
    }


@router.get("/{document_id}/coverage", response_model=CoverageOut)
def get_coverage(document_id: str, db: Session = Depends(get_db)):
    cov = db.execute(
        select(CoverageReport).where(CoverageReport.document_id == document_id)
    ).scalars().first()
    if not cov:
        raise HTTPException(404, "no coverage report for this document")
    detail = cov.detail or {}
    return CoverageOut(
        document_id=document_id,
        signals_total=cov.signals_total,
        extracted=cov.extracted,
        not_applicable=cov.not_applicable,
        unaccounted=cov.unaccounted,
        coverage_ratio=cov.coverage_ratio,
        is_complete=cov.unaccounted == 0,
        unaccounted_signals=detail.get("unaccounted_signals", []),
    )
