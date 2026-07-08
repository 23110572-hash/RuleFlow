"""Structure tree extraction.

Real SEBI master circulars consolidate dozens of circulars into a deep clause
hierarchy: Chapter -> Section -> Clause -> Sub-clause, with mixed numbering
(1, 1.1, 1.1.1, (a), (i), Chapter III). This module segments raw document text
into clause units, each with a resolved clause_path and exact char offsets so
every extracted obligation can cite its precise span.

Deterministic: same input -> same segmentation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Numbering patterns, most specific first.
_CHAPTER = re.compile(r"^\s*(chapter|part)\s+([IVXLC]+|\d+)\b", re.IGNORECASE)
_DOTTED = re.compile(r"^\s*(\d+(?:\.\d+){0,5})\.?\s+(.*\S)?", re.DOTALL)
_ALPHA = re.compile(r"^\s*\(([a-z])\)\s+", re.IGNORECASE)
_ROMAN = re.compile(r"^\s*\(([ivxlc]+)\)\s+", re.IGNORECASE)


@dataclass
class ClauseUnit:
    clause_path: str
    text: str
    char_start: int
    char_end: int = 0
    page: int | None = None
    depth: int = 0
    children_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "clause_path": self.clause_path,
            "text": self.text.strip(),
            "char_start": self.char_start,
            "char_end": self.char_end,
            "page": self.page,
            "depth": self.depth,
        }


def _page_for_offset(offset: int, page_offsets: list[int] | None) -> int | None:
    if not page_offsets:
        return None
    page = 1
    for i, po in enumerate(page_offsets):
        if offset >= po:
            page = i + 1
        else:
            break
    return page


def segment_clauses(text: str, page_offsets: list[int] | None = None) -> list[ClauseUnit]:
    """Segment document text into clause units with resolved paths + offsets.

    page_offsets: optional list of char offsets at which each page starts, to
    map clauses back to page numbers.
    """
    lines = text.splitlines(keepends=True)
    units: list[ClauseUnit] = []

    offset = 0
    chapter = ""
    path_stack: list[str] = []  # dotted numeric context
    current: ClauseUnit | None = None

    def close(unit: ClauseUnit | None, end: int) -> None:
        if unit is not None:
            unit.char_end = end
            unit.text = text[unit.char_start:end]
            units.append(unit)

    for line in lines:
        line_start = offset
        offset += len(line)
        stripped = line.strip()
        if not stripped:
            continue

        m_ch = _CHAPTER.match(stripped)
        if m_ch:
            close(current, line_start)
            current = None
            chapter = f"Ch.{m_ch.group(2).upper()}"
            continue

        m_dot = _DOTTED.match(stripped)
        if m_dot and _looks_like_number(m_dot.group(1)):
            close(current, line_start)
            number = m_dot.group(1)
            path = f"{chapter} {number}".strip() if chapter else number
            depth = number.count(".")
            current = ClauseUnit(
                clause_path=path,
                text="",
                char_start=line_start,
                page=_page_for_offset(line_start, page_offsets),
                depth=depth,
            )
            continue

        m_alpha = _ALPHA.match(stripped)
        m_roman = _ROMAN.match(stripped)
        if (m_alpha or m_roman) and current is not None:
            # Sub-clause of the current clause.
            close(current, line_start)
            label = (m_alpha or m_roman).group(1)
            path = f"{current.clause_path}({label})"
            current = ClauseUnit(
                clause_path=path,
                text="",
                char_start=line_start,
                page=_page_for_offset(line_start, page_offsets),
                depth=current.depth + 1,
            )
            continue

        # Continuation of the current clause; keep accumulating.

    close(current, len(text))
    return units


def _looks_like_number(tok: str) -> bool:
    """Guard against matching sentences that merely start with a digit."""
    parts = tok.split(".")
    return all(p.isdigit() for p in parts) and len(parts[0]) <= 3
