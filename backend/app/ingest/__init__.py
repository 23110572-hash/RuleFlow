"""Ingest layer — real SEBI document parsing (structure tree, tables, OCR)."""
from app.ingest.parser import ParsedDocument, parse_pdf_bytes, parse_text  # noqa: F401
from app.ingest.structure import ClauseUnit, segment_clauses  # noqa: F401
