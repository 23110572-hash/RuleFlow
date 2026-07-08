"""Document parsing.

PyMuPDF (fitz) for born-digital PDFs; a PaddleOCR fallback path is wired for
scanned pages (import is lazy so the core runs without the heavy OCR stack).
Plain text ingestion is also supported so the pasted/master-circular text can
be processed directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.ingest.structure import ClauseUnit, segment_clauses


@dataclass
class ParsedDocument:
    text: str
    page_count: int
    page_offsets: list[int] = field(default_factory=list)  # char offset at each page start
    clauses: list[ClauseUnit] = field(default_factory=list)
    ocr_used: bool = False

    def clause_dicts(self) -> list[dict]:
        return [c.to_dict() for c in self.clauses]


def parse_text(text: str, page_offsets: list[int] | None = None) -> ParsedDocument:
    clauses = segment_clauses(text, page_offsets)
    return ParsedDocument(
        text=text,
        page_count=len(page_offsets) if page_offsets else 1,
        page_offsets=page_offsets or [0],
        clauses=clauses,
    )


import re

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")


def _strip_hindi(text: str, line_drop_threshold: float = 0.15) -> str:
    """Guarantee zero Devanagari reaches the model.

    Page-level detection (`_is_hindi_page`) drops whole Hindi pages, but SEBI
    PDFs sometimes mix a little Hindi into an otherwise-English page. This
    second pass works line by line:
      * a line that is predominantly Devanagari is dropped entirely, and
      * any stray Devanagari characters left on a surviving (English) line are
        removed.
    Run BEFORE the page text is concatenated so citation char-offsets stay
    consistent with the stored document text.
    """
    out_lines: list[str] = []
    for line in text.split("\n"):
        deva = sum(1 for ch in line if "\u0900" <= ch <= "\u097F")
        if deva:
            letters = sum(1 for ch in line if ch.isalpha())
            if letters and deva / letters > line_drop_threshold:
                continue  # mostly-Hindi line -> drop
            line = _DEVANAGARI_RE.sub("", line)  # strip stray Devanagari
        out_lines.append(line)
    return "\n".join(out_lines)


def _is_hindi_page(text: str, threshold: float = 0.3) -> bool:
    """Detect if a page is predominantly Hindi (Devanagari script).

    SEBI circulars are bilingual — Hindi pages come first, followed by the
    same content in English.  We count Devanagari Unicode characters
    (U+0900–U+097F) and flag the page as Hindi when their share of all
    alphabetic characters exceeds *threshold*.
    """
    if not text or len(text.strip()) < 20:
        return False
    devanagari = sum(1 for ch in text if "\u0900" <= ch <= "\u097F")
    # Count Latin letters as well for the ratio
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    total = devanagari + latin
    if total == 0:
        return False
    return (devanagari / total) > threshold


def parse_pdf_bytes(data: bytes, ocr_threshold_chars: int = 40) -> ParsedDocument:
    """Parse a PDF. Uses PyMuPDF text extraction; if a page yields almost no
    text (likely scanned), falls back to OCR for that page when available.

    SEBI bilingual handling: Hindi (Devanagari) pages are automatically
    detected and skipped — only the English portion is extracted."""
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - depends on optional dep
        raise RuntimeError(
            "PyMuPDF (pymupdf) is required to parse PDFs. Install it or ingest text directly."
        ) from exc

    doc = fitz.open(stream=data, filetype="pdf")
    parts: list[str] = []
    page_offsets: list[int] = []
    ocr_used = False
    running = 0
    for page in doc:
        page_text = page.get_text("text")
        if len(page_text.strip()) < ocr_threshold_chars:
            ocr_text = _ocr_page(page)
            if ocr_text:
                page_text = ocr_text
                ocr_used = True
        # Skip Hindi (Devanagari) pages — SEBI PDFs have Hindi first, then English
        if _is_hindi_page(page_text):
            continue
        # Second pass: strip any Hindi that leaked onto a mostly-English page.
        page_text = _strip_hindi(page_text)
        page_offsets.append(running)
        parts.append(page_text)
        running += len(page_text) + 1  # +1 for the join newline
    full = "\n".join(parts)
    clauses = segment_clauses(full, page_offsets)
    return ParsedDocument(
        text=full,
        page_count=len(page_offsets),
        page_offsets=page_offsets,
        clauses=clauses,
        ocr_used=ocr_used,
    )


def _ocr_page(page) -> str | None:  # pragma: no cover - optional heavy path
    """OCR a single page via PaddleOCR. Lazy import; returns None if unavailable."""
    try:
        import numpy as np
        from paddleocr import PaddleOCR

        global _OCR
        try:
            _OCR
        except NameError:
            _OCR = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        pix = page.get_pixmap(dpi=200)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        result = _OCR.ocr(img, cls=True)
        lines = []
        for block in result or []:
            for line in block or []:
                if line and len(line) > 1 and line[1]:
                    lines.append(line[1][0])
        return "\n".join(lines) if lines else None
    except Exception:
        return None
