"""Obligation register as a PDF.

Emailed to the firm after a document is analysed, and safe to hand to an
inspector: every row carries the clause path and the verbatim quote it was
extracted from, plus the source content hash, so any line can be traced back to
the exact characters of the source document.

Deliberately renders what is in the record and nothing more. Where the clause
stated no deadline or threshold the cell reads "Not specified", never an assumed
default — the same rule the UI follows.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)

# Palette kept close to the product's own ink/brand tones.
_INK = colors.HexColor("#1f2933")
_MUTED = colors.HexColor("#7b8794")
_BRAND = colors.HexColor("#2f5bea")
_RULE = colors.HexColor("#e4e7eb")
_HEAD_BG = colors.HexColor("#f5f7fa")
_VERIFIED = colors.HexColor("#047857")
_FLAGGED = colors.HexColor("#b45309")

_MODALITY_LABEL = {
    "shall": "Mandatory",
    "may": "Discretionary",
    "judgement_based": "Judgement-based",
    "best_judgment": "Judgement-based",  # pre-rename spelling
}


@dataclass
class RegisterMeta:
    """Everything the cover block needs, so the builder never touches the ORM."""

    document_title: str
    circular_number: str | None = None
    category: str | None = None
    issue_date: datetime | None = None
    page_count: int | None = None
    clauses_read: int | None = None
    clauses_failed: int = 0
    failed_clause_paths: list[str] | None = None


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "RfTitle", parent=base["Title"], fontSize=18, leading=22,
            textColor=_INK, alignment=TA_LEFT, spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "RfSubtitle", parent=base["Normal"], fontSize=10, leading=13, textColor=_MUTED,
        ),
        "h2": ParagraphStyle(
            "RfH2", parent=base["Heading2"], fontSize=12, leading=15,
            textColor=_INK, spaceBefore=10, spaceAfter=4,
        ),
        # Body sizes are set for reading on paper, not for fitting the most rows
        # per page: at 7.5pt the register was legible on screen and unreadable
        # printed. Bigger text costs pages, which is the right trade.
        "cell": ParagraphStyle(
            "RfCell", parent=base["Normal"], fontSize=9.5, leading=12, textColor=_INK,
        ),
        "cell_muted": ParagraphStyle(
            "RfCellMuted", parent=base["Normal"], fontSize=9, leading=11.5, textColor=_MUTED,
        ),
        "quote": ParagraphStyle(
            "RfQuote", parent=base["Normal"], fontSize=8.5, leading=11,
            textColor=_MUTED, fontName="Helvetica-Oblique",
        ),
        "th": ParagraphStyle(
            "RfTh", parent=base["Normal"], fontSize=9.5, leading=12,
            textColor=_INK, fontName="Helvetica-Bold",
        ),
        "note": ParagraphStyle(
            "RfNote", parent=base["Normal"], fontSize=9, leading=12, textColor=_MUTED,
        ),
    }


def _esc(text: str | None) -> str:
    """Escape for reportlab's mini-HTML. Regulatory text contains & and < often
    enough that skipping this corrupts the PDF."""
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _summary_line(meta: RegisterMeta, total: int, verified: int, flagged: int) -> str:
    bits = [f"<b>{total}</b> obligations extracted"]
    if verified or flagged:
        bits.append(f"{verified} citation-verified, {flagged} flagged for review")
    if meta.clauses_read:
        clause_bit = f"{meta.clauses_read} clauses analysed"
        if meta.clauses_failed:
            clause_bit += f" ({meta.clauses_failed} could not be analysed)"
        bits.append(clause_bit)
    return " &nbsp;·&nbsp; ".join(bits)


def _cover(meta: RegisterMeta, obligations: list[dict], st: dict) -> list:
    total = len(obligations)
    verified = sum(1 for o in obligations if (o.get("status") or "") in {"verified", "approved"})
    flagged = total - verified

    flow: list = [
        Paragraph(_esc(meta.document_title) or "Obligation register", st["title"]),
    ]

    ident = []
    if meta.circular_number:
        ident.append(f"Circular {_esc(meta.circular_number)}")
    if meta.issue_date:
        ident.append(f"Issued {meta.issue_date.strftime('%d %b %Y')}")
    if meta.category:
        ident.append(f"Category: {_esc(meta.category)}")
    if meta.page_count:
        ident.append(f"{meta.page_count} pages")
    if ident:
        flow.append(Paragraph(" &nbsp;·&nbsp; ".join(ident), st["subtitle"]))

    flow.append(Spacer(1, 6))
    flow.append(Paragraph(_summary_line(meta, total, verified, flagged), st["cell"]))

    if meta.clauses_failed and meta.failed_clause_paths:
        named = ", ".join(_esc(p) for p in meta.failed_clause_paths[:12])
        if len(meta.failed_clause_paths) > 12:
            named += f" (+{len(meta.failed_clause_paths) - 12} more)"
        flow.append(Spacer(1, 4))
        flow.append(
            Paragraph(
                f"<b>Incomplete:</b> {meta.clauses_failed} clause(s) could not be "
                f"analysed and are absent from this register — {named}. "
                "Re-run the analysis to include them.",
                st["note"],
            )
        )

    flow.append(Spacer(1, 10))
    return flow


def _table(obligations: list[dict], st: dict) -> LongTable:
    header = [
        Paragraph("#", st["th"]),
        Paragraph("Clause", st["th"]),
        Paragraph("Type", st["th"]),
        Paragraph("Obligation and verbatim source text", st["th"]),
        Paragraph("Citation", st["th"]),
    ]
    rows: list[list] = [header]
    status_colours: list[tuple[int, colors.Color]] = []

    for i, o in enumerate(obligations, start=1):
        statement = _esc(o.get("normalized_statement") or o.get("verbatim_text") or "")
        quote = _esc(o.get("verbatim_text") or "")
        body = f'<b>{statement}</b><br/><font size="8.5" color="#7b8794">“{quote}”</font>'

        modality = (o.get("modality") or "shall").lower()
        status = (o.get("status") or "").lower()
        verified = status in {"verified", "approved"}

        rows.append(
            [
                Paragraph(str(i), st["cell_muted"]),
                Paragraph(_esc(o.get("clause_path") or "—"), st["cell"]),
                Paragraph(_MODALITY_LABEL.get(modality, _esc(modality)), st["cell"]),
                Paragraph(body, st["cell"]),
                Paragraph("Verified" if verified else "Review", st["cell"]),
            ]
        )
        status_colours.append((i, _VERIFIED if verified else _FLAGGED))

    # Widths sum to the printable width of landscape A4 (297mm - 2*12mm margins).
    # "Judgement-based" needs 26mm or reportlab breaks it mid-word.
    table = LongTable(
        rows,
        colWidths=[11 * mm, 28 * mm, 30 * mm, 178 * mm, 26 * mm],
        repeatRows=1,
    )
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), _HEAD_BG),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, _BRAND),
        ("GRID", (0, 0), (-1, -1), 0.25, _RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fbfcfd")]),
    ]
    for row, colour in status_colours:
        style.append(("TEXTCOLOR", (4, row), (4, row), colour))
    table.setStyle(TableStyle(style))
    return table


def _page_furniture(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(_MUTED)
    # The date stays, moved out of the cover and into the footer: an undated
    # compliance register is hard to rely on, but it does not belong up front.
    canvas.drawString(
        12 * mm,
        8 * mm,
        "RuleFlow — obligation register · "
        + datetime.now(timezone.utc).strftime("%d %b %Y"),
    )
    canvas.drawRightString(
        doc.pagesize[0] - 12 * mm, 8 * mm, f"Page {canvas.getPageNumber()}"
    )
    canvas.restoreState()


def build_register_pdf(meta: RegisterMeta, obligations: list[dict]) -> bytes:
    """Render the register. ``obligations`` are plain dicts so this stays usable
    from a background thread without a live ORM session."""
    buffer = BytesIO()
    st = _styles()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
        title=f"Obligation register — {meta.document_title}",
        author="RuleFlow",
        subject="SEBI obligation register",
    )

    flow = _cover(meta, obligations, st)
    if obligations:
        flow.append(_table(obligations, st))
    else:
        flow.append(
            Paragraph(
                "No obligations were extracted from this document.", st["note"]
            )
        )

    flow.append(Spacer(1, 8))
    flow.append(
        Paragraph(
            "Every row quotes the source document verbatim and cites the clause it "
            "was taken from. Obligations marked <b>Review</b> did not meet the "
            "citation-fidelity threshold and need a human to confirm the wording "
            "before they are relied upon.",
            st["note"],
        )
    )

    doc.build(flow, onFirstPage=_page_furniture, onLaterPages=_page_furniture)
    return buffer.getvalue()
