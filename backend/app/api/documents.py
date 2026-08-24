"""Documents API — ingest SEBI documents, view coverage certificates.
Each document belongs to the firm that uploaded it. No sharing between accounts."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_firm
from app.db.base import get_db
from app.db.models import CoverageReport, Document, Firm, Obligation
from app.schemas.models import CoverageOut, DocumentOut, IngestTextIn
from app.services import ingest_service

router = APIRouter(prefix="/documents", tags=["documents"])


def _doc_out(db: Session, doc: Document) -> DocumentOut:
    ob_count = db.execute(
        select(func.count(Obligation.id)).where(
            Obligation.source_document_id == doc.id,
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
def list_documents(firm: Firm = Depends(get_current_firm), db: Session = Depends(get_db)):
    """List only documents belonging to the authenticated user's firm."""
    docs = db.execute(
        select(Document)
        .where(Document.firm_id == firm.id)
        .order_by(Document.recorded_at.desc())
    ).scalars().all()
    return [_doc_out(db, d) for d in docs]


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, firm: Firm = Depends(get_current_firm), db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "document not found")
    if doc.firm_id and doc.firm_id != firm.id:
        raise HTTPException(403, "access denied")
    return _doc_out(db, doc)


@router.post("/ingest-text", response_model=DocumentOut)
def ingest_document_text(
    body: IngestTextIn,
    max_clauses: int | None = Query(None, description="Cap clauses processed (cost control)"),
    firm: Firm = Depends(get_current_firm),
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
        firm_id=firm.id,
    )
    return _doc_out(db, doc)


@router.post("/ingest-pdf", response_model=DocumentOut)
def ingest_document_pdf(
    file: UploadFile = File(...),
    title: str = Form(...),
    circular_number: str | None = Form(None),
    category: str | None = Form(None),
    max_clauses: int | None = Form(None),
    firm: Firm = Depends(get_current_firm),
    db: Session = Depends(get_db),
):
    data = file.file.read()
    doc, created = ingest_service.ingest_pdf_async(
        db,
        title=title,
        data=data,
        circular_number=circular_number,
        category=category,
        max_clauses=max_clauses,
        firm_id=firm.id,
    )
    if created:
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
def get_progress(document_id: str, firm: Firm = Depends(get_current_firm), db: Session = Depends(get_db)):
    """Live progress for an in-flight analysis."""
    from app.services import progress

    # Verify ownership
    doc = db.get(Document, document_id)
    if doc and doc.firm_id and doc.firm_id != firm.id:
        raise HTTPException(403, "access denied")

    prog = progress.get(document_id)
    if prog:
        return prog.to_dict()

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
        "failed_clause_paths": [],
        "action_items_generated": 0,
        "error": error,
    }


@router.post("/{document_id}/email-register")
def email_register(
    document_id: str,
    firm: Firm = Depends(get_current_firm),
    db: Session = Depends(get_db),
):
    """Email this document's obligation register as a PDF.

    The same send runs automatically when analysis finishes; this is the manual
    resend. Unlike the automatic path it reports failures to the caller, because
    someone is waiting on the result of a button press.
    """
    doc = db.get(Document, document_id)
    if not doc or doc.firm_id != firm.id:
        raise HTTPException(404, "document not found")
    if doc.status == "error":
        raise HTTPException(409, "This document's analysis failed. Re-upload it first.")
    if doc.status != "ingested":
        raise HTTPException(409, "This document is still being analysed.")

    try:
        recipient = ingest_service.email_register(db, doc, force=True)
    except ingest_service.NoRecipientError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        # Surface the provider's reason: "SMTP is not configured", a 502 from the
        # relay, and a missing REPORT_RELAY_URL all need different fixes.
        raise HTTPException(502, f"Could not send the register: {exc}") from exc

    return {"status": "sent", "recipient": recipient, "document_id": document_id}


@router.get("/{document_id}/coverage", response_model=CoverageOut)
def get_coverage(document_id: str, firm: Firm = Depends(get_current_firm), db: Session = Depends(get_db)):
    # Verify ownership
    doc = db.get(Document, document_id)
    if doc and doc.firm_id and doc.firm_id != firm.id:
        raise HTTPException(403, "access denied")

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
