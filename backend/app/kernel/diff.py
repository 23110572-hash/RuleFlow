"""Version Diff engine (deterministic).

Structural, obligation-level comparison between two canonical versions of a
document. This is the centrepiece of the change-management flow: exact,
repeatable, near-zero hallucination. It never asks an LLM "what changed?" — it
computes it.

Matching strategy (two-pass):
  1. Exact match on clause_path (Chapter/Section/Clause path).
  2. Residual match on high text similarity (catches renumbered/moved clauses).
  3. Anything left over: added (only in new) or removed (only in old).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.kernel.hashing import normalize_text

# Fields we track for amendment detail.
_TRACKED_FIELDS = (
    "normalized_statement",
    "modality",
    "trigger_condition",
    "deadline_or_periodicity",
    "threshold",
)


@dataclass
class ObligationChange:
    type: str  # added | amended | removed | unchanged
    clause_path: str
    old_id: str | None = None
    new_id: str | None = None
    similarity: float = 0.0
    field_changes: dict[str, dict[str, str | None]] = field(default_factory=dict)
    old_text: str | None = None
    new_text: str | None = None

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "clause_path": self.clause_path,
            "old_id": self.old_id,
            "new_id": self.new_id,
            "similarity": round(self.similarity, 4),
            "field_changes": self.field_changes,
            "old_text": self.old_text,
            "new_text": self.new_text,
        }


@dataclass
class DiffResult:
    added: list[ObligationChange] = field(default_factory=list)
    amended: list[ObligationChange] = field(default_factory=list)
    removed: list[ObligationChange] = field(default_factory=list)
    unchanged: list[ObligationChange] = field(default_factory=list)

    @property
    def changes(self) -> list[ObligationChange]:
        return self.added + self.amended + self.removed

    def summary(self) -> dict:
        return {
            "added": len(self.added),
            "amended": len(self.amended),
            "removed": len(self.removed),
            "unchanged": len(self.unchanged),
        }

    def to_dict(self) -> dict:
        return {
            "summary": self.summary(),
            "added": [c.to_dict() for c in self.added],
            "amended": [c.to_dict() for c in self.amended],
            "removed": [c.to_dict() for c in self.removed],
        }


def _text_of(ob: dict) -> str:
    return ob.get("normalized_statement") or ob.get("verbatim_text") or ""


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_text(a), normalize_text(b), autojunk=False).ratio()


def _field_changes(old: dict, new: dict) -> dict[str, dict[str, str | None]]:
    changes: dict[str, dict[str, str | None]] = {}
    for f in _TRACKED_FIELDS:
        ov, nv = old.get(f), new.get(f)
        if normalize_text(str(ov or "")) != normalize_text(str(nv or "")):
            changes[f] = {"old": ov, "new": nv}
    return changes


def diff_obligations(
    old_obligations: list[dict],
    new_obligations: list[dict],
    amend_threshold: float = 0.995,
    match_threshold: float = 0.80,
) -> DiffResult:
    """Compare two sets of obligation dicts.

    Each dict should carry: id, clause_path, verbatim_text/normalized_statement,
    and optionally the tracked modality/trigger/deadline/threshold fields.
    """
    result = DiffResult()

    old_by_path: dict[str, dict] = {o["clause_path"]: o for o in old_obligations if o.get("clause_path")}
    new_by_path: dict[str, dict] = {n["clause_path"]: n for n in new_obligations if n.get("clause_path")}

    matched_old: set[str] = set()
    matched_new: set[str] = set()

    # Pass 1 — exact clause_path match.
    for path, old in old_by_path.items():
        new = new_by_path.get(path)
        if new is None:
            continue
        matched_old.add(old["id"])
        matched_new.add(new["id"])
        sim = _similarity(_text_of(old), _text_of(new))
        fc = _field_changes(old, new)
        if sim >= amend_threshold and not fc:
            result.unchanged.append(
                ObligationChange("unchanged", path, old["id"], new["id"], sim)
            )
        else:
            result.amended.append(
                ObligationChange(
                    "amended", path, old["id"], new["id"], sim,
                    field_changes=fc, old_text=_text_of(old), new_text=_text_of(new),
                )
            )

    # Pass 2 — residual similarity match (renumbered / moved clauses).
    residual_old = [o for o in old_obligations if o["id"] not in matched_old]
    residual_new = [n for n in new_obligations if n["id"] not in matched_new]

    for old in residual_old:
        best, best_sim = None, 0.0
        for new in residual_new:
            if new["id"] in matched_new:
                continue
            sim = _similarity(_text_of(old), _text_of(new))
            if sim > best_sim:
                best, best_sim = new, sim
        if best is not None and best_sim >= match_threshold:
            matched_old.add(old["id"])
            matched_new.add(best["id"])
            result.amended.append(
                ObligationChange(
                    "amended",
                    best.get("clause_path") or old.get("clause_path", ""),
                    old["id"], best["id"], best_sim,
                    field_changes=_field_changes(old, best),
                    old_text=_text_of(old), new_text=_text_of(best),
                )
            )

    # Pass 3 — leftovers.
    for old in old_obligations:
        if old["id"] not in matched_old:
            result.removed.append(
                ObligationChange(
                    "removed", old.get("clause_path", ""), old_id=old["id"],
                    old_text=_text_of(old),
                )
            )
    for new in new_obligations:
        if new["id"] not in matched_new:
            result.added.append(
                ObligationChange(
                    "added", new.get("clause_path", ""), new_id=new["id"],
                    new_text=_text_of(new),
                )
            )

    return result
