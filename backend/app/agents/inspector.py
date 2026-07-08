"""Inspector Agent (Groq).

Plans and runs a thematic self-inspection over the firm's obligations + current
compliance status, and drafts SEBI-style findings. Every finding is validated
against the real obligation list — the kernel drops any finding that cites an
obligation not in scope or that has no supporting gap.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.prompts import INSPECTOR_SYSTEM
from app.llm.client import get_llm


@dataclass
class DraftFinding:
    obligation_id: str
    clause_path: str
    severity: str
    observation: str
    recommendation: str
    citation: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "obligation_id": self.obligation_id,
            "clause_path": self.clause_path,
            "severity": self.severity,
            "observation": self.observation,
            "recommendation": self.recommendation,
            "citation": self.citation,
        }


def run_inspection(theme: str, scoped: list[dict]) -> list[DraftFinding]:
    """theme: inspection theme. scoped: list of
    {obligation_id, clause_path, modality, test_status, test_detail,
     gap_reason, gap_severity, citation}.

    Returns validated draft findings.
    """
    if not scoped:
        return []
    valid_ids = {s["obligation_id"]: s for s in scoped}

    lines = []
    for s in scoped:
        lines.append(
            f"- id={s['obligation_id']} clause={s.get('clause_path')} "
            f"modality={s.get('modality')} status={s.get('test_status')} "
            f"detail={s.get('test_detail','')} gap={s.get('gap_reason','none')}/"
            f"{s.get('gap_severity','')}"
        )
    user = f"Inspection theme: {theme}\nObligations in scope:\n" + "\n".join(lines)

    payload = get_llm().complete_json(INSPECTOR_SYSTEM, user)
    raw = (payload or {}).get("findings", []) if isinstance(payload, dict) else []

    findings: list[DraftFinding] = []
    for f in raw:
        oid = f.get("obligation_id")
        # Kernel guard: finding MUST cite a real, in-scope obligation.
        if oid not in valid_ids:
            continue
        src = valid_ids[oid]
        # Guard: only keep findings where a gap actually exists.
        if src.get("test_status") == "green" and not src.get("gap_reason"):
            continue
        findings.append(
            DraftFinding(
                obligation_id=oid,
                clause_path=src.get("clause_path", f.get("clause_path", "")),
                severity=f.get("severity") or src.get("gap_severity") or "medium",
                observation=f.get("observation", ""),
                recommendation=f.get("recommendation", ""),
                citation=src.get("citation", {}),
            )
        )
    return findings
