"""Change-management service (Flow B).

new SEBI doc -> canonical DIFF (regulation vs regulation) -> operational-impact
analysis on the firm overlay -> HIL approval -> cited Change Request (no direct
write-back). On approval the firm applies it and marks it done; the platform
tracks to closure and audits every step.
"""
from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ChangeEvent,
    ChangeRequest,
    Control,
    DataSource,
    Document,
    Firm,
    Obligation,
    ObligationTest,
)
from app.kernel.diff import ObligationChange, diff_obligations
from app.services import audit


def _ob_dict(o: Obligation) -> dict:
    return {
        "id": o.id,
        "clause_path": o.clause_path,
        "verbatim_text": o.verbatim_text,
        "normalized_statement": o.normalized_statement,
        "modality": o.modality,
        "trigger_condition": o.trigger_condition,
        "deadline_or_periodicity": o.deadline_or_periodicity,
        "threshold": o.threshold,
        "citation": o.citation,
    }


def diff_documents(db: Session, from_document_id: str, to_document_id: str) -> dict:
    """Deterministic canonical diff between two ingested documents; persists
    ChangeEvents. Returns the diff summary + change lists."""
    old = db.execute(
        select(Obligation).where(
            Obligation.source_document_id == from_document_id,
            Obligation.status != "superseded",
        )
    ).scalars().all()
    new = db.execute(
        select(Obligation).where(
            Obligation.source_document_id == to_document_id,
            Obligation.status != "superseded",
        )
    ).scalars().all()

    result = diff_obligations([_ob_dict(o) for o in old], [_ob_dict(n) for n in new])

    events: list[ChangeEvent] = []
    for change in result.changes:
        ev = ChangeEvent(
            obligation_id=change.new_id or change.old_id,
            from_document_id=from_document_id,
            to_document_id=to_document_id,
            type=change.type,
            old_version={"id": change.old_id, "text": change.old_text} if change.old_id else None,
            new_version={"id": change.new_id, "text": change.new_text} if change.new_id else None,
            similarity=change.similarity,
            field_changes=change.field_changes,
        )
        db.add(ev)
        events.append(ev)
    db.flush()

    audit.record(
        db,
        action="regulation.diffed",
        payload={"from": from_document_id, "to": to_document_id, "summary": result.summary()},
        # Scope it to the firm that owns the documents, or the comparison is
        # written to the global chain and never shows on the Activity page.
        firm_id=getattr(db.get(Document, to_document_id), "firm_id", None),
    )
    db.commit()
    return {"summary": result.summary(), "diff": result.to_dict(), "change_event_ids": [e.id for e in events]}


def _action_text(change: ObligationChange | ChangeEvent) -> str:
    t = change.type
    old_txt = (change.old_version or {}).get("text", "") if hasattr(change, "old_version") else ""
    new_txt = (change.new_version or {}).get("text", "") if hasattr(change, "new_version") else ""

    try:
        from app.llm.client import get_llm
        llm = get_llm()
        if llm.enabled and (old_txt or new_txt):
            prompt = (
                f"Regulation rule change ({t}).\n"
                f"Old Requirement: {old_txt}\n"
                f"New Requirement: {new_txt}\n"
                "In 1 or 2 concise sentences, tell the compliance officer at a SEBI broker firm "
                "what changed and what operational action they must take."
            )
            resp = llm.complete_json(
                "You are a SEBI regulatory compliance expert.",
                prompt
            )
            if resp and isinstance(resp, dict) and "action" in resp:
                return str(resp["action"])
    except Exception:
        pass

    if t == "added":
        return "New obligation introduced. Establish a control and begin collecting evidence."
    if t == "removed":
        return "Obligation removed/superseded. Retire the mapped control after retention period; retain historical evidence."
    return "Obligation amended. Review the mapped control, update the obligation test, and re-attest evidence against the new requirement."



def operational_impact(db: Session, firm_id: str, change_event_ids: list[str]) -> list[dict]:
    """For each canonical change, compute the impact on THIS firm's overlay and
    draft a pending, cited Change Request. Human approves before anything moves.

    Only creates action items for changes that ACTUALLY affect the firm:
    - Amended/removed: only if the firm has controls linked to the old obligation
    - Added: always (firm needs to decide whether to create a new control)
    """
    controls = db.execute(select(Control).where(Control.firm_id == firm_id)).scalars().all()

    drafts: list[dict] = []
    for ce_id in change_event_ids:
        ce = db.get(ChangeEvent, ce_id)
        if not ce:
            continue
        old_ob_id = (ce.old_version or {}).get("id")
        new_ob_id = (ce.new_version or {}).get("id")
        target_ob_id = old_ob_id or new_ob_id

        affected_controls = [c.id for c in controls if target_ob_id in (c.obligation_ids or [])]
        # Also check if controls reference the NEW obligation (for amended cases)
        if new_ob_id and new_ob_id != target_ob_id:
            affected_controls += [c.id for c in controls if new_ob_id in (c.obligation_ids or [])]
            affected_controls = list(set(affected_controls))

        affected_tests = []
        citation = {}
        if target_ob_id:
            ob = db.get(Obligation, target_ob_id)
            if ob:
                citation = ob.citation or {}
            test = db.execute(
                select(ObligationTest).where(ObligationTest.obligation_id == target_ob_id)
            ).scalars().first()
            if test:
                affected_tests = [test.id]

        # Skip changes that don't impact this firm — UNLESS it's a new obligation
        # (firm may need to create a control for it).
        if not affected_controls and not affected_tests and ce.type != "added":
            continue

        cr = ChangeRequest(
            firm_id=firm_id,
            change_event_id=ce.id,
            affected_controls=affected_controls,
            affected_evidence=[],
            affected_tests=affected_tests,
            operational_action_text=_action_text(ce),
            citation=citation,
            status="pending",
        )
        db.add(cr)
        db.flush()
        drafts.append(
            {
                "change_request_id": cr.id,
                "change_event_id": ce.id,
                "firm_id": firm_id,
                "type": ce.type,
                "affected_controls": affected_controls,
                "affected_tests": affected_tests,
                "operational_action_text": cr.operational_action_text,
                "citation": citation,
            }
        )

    if drafts:
        audit.record(
            db,
            action="change.impact_analyzed",
            payload={"firm_id": firm_id, "change_requests": len(drafts)},
            firm_id=firm_id,
        )
    db.commit()
    return drafts


def decide_change_request(
    db: Session, change_request_id: str, decision: str, approver: str, note: str = ""
) -> ChangeRequest:
    """HIL decision: approve | escalate | reject. Approval emits the cited
    action ticket the firm applies (status -> approved)."""
    cr = db.get(ChangeRequest, change_request_id)
    if not cr:
        raise ValueError("change request not found")
    if decision not in {"approve", "escalate", "reject"}:
        raise ValueError("decision must be approve|escalate|reject")

    before = cr.status
    cr.status = {"approve": "approved", "escalate": "escalated", "reject": "rejected"}[decision]
    if decision == "approve":
        cr.approved_by = approver
        cr.approved_at = datetime.now(timezone.utc)

    audit.record(
        db,
        action=f"change_request.{decision}",
        payload={"change_request_id": cr.id, "note": note, "citation": cr.citation},
        firm_id=cr.firm_id,
        actor=approver,
        before_hash=before,
        after_hash=cr.status,
    )
    db.commit()
    db.refresh(cr)
    return cr


def mark_applied(db: Session, change_request_id: str, actor: str) -> ChangeRequest:
    """Firm applied the change in their own systems and marks it done."""
    cr = db.get(ChangeRequest, change_request_id)
    if not cr:
        raise ValueError("change request not found")
    cr.status = "applied"
    audit.record(
        db,
        action="change_request.applied",
        payload={"change_request_id": cr.id},
        firm_id=cr.firm_id,
        actor=actor,
    )
    db.commit()
    db.refresh(cr)
    return cr


def mark_applied(db: Session, change_request_id: str, actor: str) -> ChangeRequest:
    """Firm applied the change in their own systems and marks it done.
    Automatically updates the firm's controls to point to the new obligation
    version if the obligation was amended, or removes it if retired.
    """
    cr = db.get(ChangeRequest, change_request_id)
    if not cr:
        raise ValueError("change request not found")

    # Apply the modification to the controls ("did u want to modify if yes ok modify")
    if cr.change_event_id:
        ce = db.get(ChangeEvent, cr.change_event_id)
        if ce:
            old_ob_id = (ce.old_version or {}).get("id")
            new_ob_id = (ce.new_version or {}).get("id")

            if ce.type == "amended" and old_ob_id and new_ob_id:
                for ctrl_id in cr.affected_controls:
                    ctrl = db.get(Control, ctrl_id)
                    if ctrl and ctrl.obligation_ids:
                        ctrl.obligation_ids = [
                            new_ob_id if oid == old_ob_id else oid
                            for oid in ctrl.obligation_ids
                        ]
            elif ce.type == "removed" and old_ob_id:
                for ctrl_id in cr.affected_controls:
                    ctrl = db.get(Control, ctrl_id)
                    if ctrl and ctrl.obligation_ids:
                        ctrl.obligation_ids = [
                            oid for oid in ctrl.obligation_ids
                            if oid != old_ob_id
                        ]

    cr.status = "applied"
    audit.record(
        db,
        action="change_request.applied",
        payload={"change_request_id": cr.id},
        firm_id=cr.firm_id,
        actor=actor,
    )
    db.commit()
    db.refresh(cr)
    return cr


DB_RULE_SYSTEM = """You are the Database Rule Extraction Agent for a SEBI compliance platform.

You are given the REAL schema and sample rows of a SEBI-regulated firm's own
operational database. Your job is to state which compliance rules, policies,
limits and controls this firm is ALREADY enforcing, based only on what the data
actually shows.

Hard rules:
- Ground every rule in the data. Only describe a rule if a table, column or
  value in the supplied context evidences it.
- "source_table" MUST be one of the table names supplied to you. Never invent a
  table name.
- "evidence" MUST name the specific column(s) or value(s) that led you to the
  rule, so a human can go and look at them.
- NEVER invent a SEBI circular number, regulation number or clause reference. If
  the data itself does not contain one, set "mapped_clause" to null. A wrong
  citation is worse than no citation.
- If the database holds no compliance-relevant rules (e.g. it is only trade or
  price data), return an empty list. Returning nothing is a correct answer.
- Prefer a few well-evidenced rules over many speculative ones.

Return JSON:
{"rules": [
  {
    "rule_name": "<short name of the rule the firm enforces>",
    "source_table": "<one of the supplied table names>",
    "evidence": "<the column(s)/value(s) that show this>",
    "parameter_value": "<the actual limit/threshold/cadence found, or 'present'>",
    "mapped_clause": "<a citation ONLY if it literally appears in the data, else null>"
  }
]}"""


def _reflect_connected_database(
    data_source: DataSource, max_tables: int = 12, max_rows: int = 5
) -> tuple[dict, str | None]:
    """Read the firm's OWN database: {table: {columns, sample_rows}}.

    Read-only reflection plus a small sample of rows, which is what the LLM needs
    to tell a compliance table apart from a price feed. Returns (context, error).
    """
    from sqlalchemy import inspect, text

    from app.services.datasource_service import _create_db_engine

    context: dict[str, dict] = {}
    engine = None
    try:
        engine = _create_db_engine(data_source.kind, data_source.connection_uri)
        inspector_obj = inspect(engine)
        with engine.connect() as conn:
            for table in inspector_obj.get_table_names()[:max_tables]:
                columns = [c["name"] for c in inspector_obj.get_columns(table)]
                # Table names come from the driver's own reflection, not user
                # input, so they cannot carry injected SQL.
                rows = conn.execute(
                    text(f'SELECT * FROM "{table}" LIMIT :n'), {"n": max_rows}
                ).mappings().all()
                context[table] = {
                    "columns": columns[:25],
                    "sample_rows": [
                        {k: str(v)[:120] for k, v in dict(r).items()} for r in rows
                    ],
                }
        return context, None
    except Exception as exc:
        log = structlog.get_logger(__name__)
        log.warning("connected_db_reflection_failed", error=str(exc)[:300])
        return {}, str(exc)[:300]
    finally:
        if engine is not None:
            engine.dispose()


def _llm_rules_from_database(
    firm_category: str, source_name: str, context: dict
) -> list[dict]:
    """Ask the LLM which rules the firm already enforces, then verify grounding.

    Any rule naming a table that is not actually in the schema is dropped, and a
    citation is only kept when the model was able to point at real data.
    """
    import json

    from app.llm.client import get_llm

    llm = get_llm()
    if not llm.enabled or not context:
        return []

    payload = llm.complete_json(
        DB_RULE_SYSTEM,
        (
            f"Firm category: {firm_category}\n"
            f"Database: {source_name}\n"
            f"Tables available: {list(context)}\n\n"
            f"Schema and sample rows:\n{json.dumps(context, default=str)[:12000]}"
        ),
    )
    raw = (payload or {}).get("rules", []) if isinstance(payload, dict) else []

    known_tables = {t.lower() for t in context}
    rules: list[dict] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        name = str(item.get("rule_name") or "").strip()
        table = str(item.get("source_table") or "").strip()
        # Grounding gate: the agent proposes, we verify the table is real.
        if not name or table.lower() not in known_tables:
            continue
        evidence = str(item.get("evidence") or "").strip()
        clause = item.get("mapped_clause")
        clause = str(clause).strip() if clause else ""
        rules.append(
            {
                "id": f"db_{table}_{idx}",
                "rule_name": name,
                "source_system": f"{source_name} · {table}",
                "parameter_value": str(item.get("parameter_value") or "present").strip(),
                "mapped_clause": clause or "not mapped to a circular yet",
                "status": "active",
                "origin": "connected_database",
                "evidence": evidence,
            }
        )
    return rules


# Read a firm's explicit rule/policy tables deterministically — one grounded
# rule per row, no sampling, no LLM loss. This is what makes a broker_rules table
# with 20 rows yield 20 rules instead of the 5 that per-table sampling returned.
_RULE_TABLE_HINTS = ("rule", "policy", "control", "mandate", "compliance", "limit", "threshold")
# Names that carry a rule word but are really logs/data, not rule definitions.
_NON_RULE_HINTS = ("breach", "log", "event", "history", "txn", "transaction", "trade",
                   "settlement", "audit", "ledger", "customer", "client", "account", "kyc")
_NAME_COLS = ("rule_name", "name", "description", "rule", "policy", "requirement",
              "statement", "title", "detail", "details", "particulars")
_PARAM_COLS = ("parameter_value", "parameter", "value", "threshold", "limit",
               "cadence", "frequency", "periodicity", "requirement_value")
_CLAUSE_COLS = ("mapped_clause", "clause", "clause_path", "circular", "circular_number",
                "regulation", "reference", "sebi_ref", "sebi_reference")
_STATUS_COLS = ("status", "state", "enabled", "active", "is_active")


def _match_col(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    """First column whose name equals (then contains) one of candidates."""
    lower = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand in lower:
            return lower[cand]
    for cand in candidates:
        for lc, orig in lower.items():
            if cand in lc:
                return orig
    return None


def _looks_like_rule_table(name: str, columns: list[str]) -> bool:
    n = name.lower()
    if n.startswith("ruleflow_"):  # our own mirror of adopted obligations
        return False
    if any(h in n for h in _NON_RULE_HINTS):  # breach/txn/kyc/settlement logs are not rules
        return False
    if any(h in n for h in _RULE_TABLE_HINTS):
        return True
    has_name = _match_col(columns, _NAME_COLS) is not None
    has_meta = any(_match_col(columns, c) for c in (_PARAM_COLS, _CLAUSE_COLS, _STATUS_COLS))
    return has_name and has_meta


def _rules_from_connected_database(
    data_source, max_tables: int = 25, max_rows_per_table: int = 500
) -> tuple[list[dict], list[str], list[str], str | None]:
    """Read EVERY row of the firm's rule/policy tables and turn each into one
    grounded rule. Returns (rules, tables_read, rule_tables, error)."""
    from sqlalchemy import inspect, text

    from app.services.datasource_service import _create_db_engine

    rules: list[dict] = []
    tables_read: list[str] = []
    rule_tables: list[str] = []
    engine = None
    try:
        engine = _create_db_engine(data_source.kind, data_source.connection_uri)
        insp = inspect(engine)
        with engine.connect() as conn:
            for table in insp.get_table_names()[:max_tables]:
                tables_read.append(table)
                columns = [c["name"] for c in insp.get_columns(table)]
                if not _looks_like_rule_table(table, columns):
                    continue
                name_col = _match_col(columns, _NAME_COLS)
                if not name_col:
                    continue
                rule_tables.append(table)
                param_col = _match_col(columns, _PARAM_COLS)
                clause_col = _match_col(columns, _CLAUSE_COLS)
                status_col = _match_col(columns, _STATUS_COLS)
                # Identifier comes from the driver's own reflection, not user input.
                rows = conn.execute(
                    text(f'SELECT * FROM "{table}" LIMIT :n'), {"n": max_rows_per_table}
                ).mappings().all()
                seen: set[str] = set()
                for i, row in enumerate(rows):
                    d = dict(row)
                    name = str(d.get(name_col) or "").strip()
                    if not name or name.lower() in seen:
                        continue
                    seen.add(name.lower())
                    status = str(d.get(status_col) or "").strip().lower() if status_col else ""
                    active = status in ("", "active", "enabled", "true", "1", "yes", "on")
                    rules.append(
                        {
                            "id": f"db_{table}_{i}",
                            "rule_name": name[:200],
                            "source_system": f"{data_source.name} \u00b7 {table}",
                            "parameter_value": (
                                str(d.get(param_col)).strip()
                                if param_col and d.get(param_col)
                                else "present"
                            ),
                            "mapped_clause": (
                                str(d.get(clause_col)).strip()
                                if clause_col and d.get(clause_col)
                                else "not mapped to a circular yet"
                            ),
                            "status": "active" if active else (status or "review"),
                            "origin": "connected_database",
                            "evidence": f"{table}.{name_col}",
                        }
                    )
        return rules, tables_read, rule_tables, None
    except Exception as exc:
        structlog.get_logger(__name__).warning("connected_db_read_failed", error=str(exc)[:300])
        return [], tables_read, [], str(exc)[:300]
    finally:
        if engine is not None:
            engine.dispose()


def get_connected_database_rules(db: Session, firm_id: str) -> dict:
    """The rules this firm ALREADY follows, read from its CONNECTED DATABASE.

    Adopted RuleFlow controls are intentionally NOT included in this list (they
    live on the Compliance page); they are only counted for context. This panel
    answers a different question: "what is my own database actually enforcing?"

    We read every row of the firm's explicit rule/policy tables so a 20-row
    ``broker_rules`` table yields 20 rules — not the 5 that per-table sampling
    used to return, and not 88 (which was 83 controls mixed in with 5 sampled
    rules). If there is no obvious rule table we fall back to the LLM reading the
    schema. Nothing is fabricated.
    """
    from app.db.models import Control, DataSource, Firm

    log = structlog.get_logger(__name__)
    firm = db.get(Firm, firm_id)
    firm_category = (firm.category if firm else "").lower().strip()

    # Controls are counted for context only, never mixed into the rule list.
    controls = db.execute(
        select(Control).where(Control.firm_id == firm_id, Control.status == "active")
    ).scalars().all()

    ds = db.execute(
        select(DataSource).where(DataSource.firm_id == firm_id)
    ).scalars().first()

    rules: list[dict] = []
    connected = False
    tables_read: list[str] = []
    rule_tables: list[str] = []
    message = ""

    if not ds or not ds.connection_uri:
        message = (
            "No database connected. Connect your firm's database in Settings and "
            "we will read it to list the rules you already enforce."
        )
    else:
        # 1. Deterministic: read every row of explicit rule/policy tables.
        rules, tables_read, rule_tables, error = _rules_from_connected_database(ds)
        if error:
            message = f"Could not read {ds.name}: {error}"
        else:
            connected = True

        # 2. Fallback: no obvious rule table — let the LLM read the schema.
        if connected and not rules:
            context, ctx_error = _reflect_connected_database(ds)
            if ctx_error:
                message = f"Could not read {ds.name}: {ctx_error}"
            elif not context:
                message = f"{ds.name} is connected but contains no tables to read."
            else:
                tables_read = list(context)
                try:
                    rules = _llm_rules_from_database(firm_category, ds.name, context)
                    if not rules:
                        message = (
                            f"Read {len(tables_read)} table(s) in {ds.name} but found no "
                            "compliance rules in them."
                        )
                except Exception as exc:
                    log.warning("database_rule_extraction_failed", error=str(exc)[:300])
                    message = (
                        "We reached your database but the AI extraction step failed: "
                        f"{str(exc)[:200]}"
                    )
        elif connected and not message:
            message = (
                f"Read {len(rules)} rule(s) from {len(rule_tables)} rule table(s) in {ds.name}."
            )

    return {
        "rules": rules,
        "connected": connected,
        "data_source": ds.name if ds else None,
        "tables_read": tables_read,
        "rule_tables": rule_tables,
        "controls_count": len(controls),
        "database_rules_count": len(rules),
        "message": message,
    }


FOLLOWED_RULE_IMPACT_SYSTEM = """You compare the compliance rules a SEBI-regulated firm ALREADY follows against current SEBI obligations, and flag ONLY the followed rules that must change.

You are given:
- FOLLOWED RULES: what the firm currently enforces in its own systems (a name and its current parameter/value).
- SEBI OBLIGATIONS: current SEBI requirements (each with a clause_path and a statement).

For each followed rule, decide whether any SEBI obligation makes that rule outdated, insufficient, or contradictory (e.g. the firm enforces a weaker threshold, a longer timeline, or a rule SEBI has since tightened). Flag it ONLY when there is a genuine mismatch. If a followed rule already satisfies SEBI, do NOT flag it.

Hard rules:
- Every flagged item MUST cite a real obligation from the list, by its EXACT clause_path.
- "followed_rule" MUST be copied exactly from the FOLLOWED RULES list.
- "action" is one concise sentence telling the compliance officer what to change in their system.
- Never invent obligations, clause numbers or rules.
- Return an empty list if every followed rule is already compliant.

Return JSON: {"impacts": [
  {"followed_rule": "<name from FOLLOWED RULES>", "clause_path": "<clause_path from SEBI OBLIGATIONS>", "what_changed": "<why the rule must change>", "action": "<what to do>"}
]}"""


def detect_impact_on_followed_rules(
    db: Session, firm_id: str, regenerate: bool = True, document_id: str | None = None
) -> list[dict]:
    """Action items grounded in the rules the firm ACTUALLY follows.

    Compares "Rules you follow" (read from the firm's connected database) against
    SEBI obligations and raises an action item ONLY where a SEBI requirement
    makes one of those followed rules outdated or insufficient. This replaces the
    old behaviour that compared every adopted control against every document
    (which produced dozens of ungrounded items).

    document_id restricts the comparison to a single circular ("compare my rules
    against THIS document"). When omitted, every ingested obligation is in scope.

    regenerate=True (the user-driven "Sync") clears existing PENDING items so the
    list reflects the current picture. When a document is chosen, only that
    document's pending items are cleared, so items from other circulars survive.
    Approved/applied/rejected history is never touched.
    """
    import json

    from app.llm.client import get_llm

    log = structlog.get_logger(__name__)

    firm = db.get(Firm, firm_id)
    if not firm:
        return []

    # The rules the firm follows, from its connected database.
    followed = get_connected_database_rules(db, firm_id).get("rules", [])

    if regenerate:
        pending = db.execute(
            select(ChangeRequest).where(
                ChangeRequest.firm_id == firm_id, ChangeRequest.status == "pending"
            )
        ).scalars().all()
        for cr in pending:
            # Scoped rescan: only clear pending items for the chosen document so
            # a per-circular re-check doesn't wipe items from other circulars.
            if document_id and (cr.citation or {}).get("document_id") != document_id:
                continue
            db.delete(cr)
        db.flush()

    # No followed rules => nothing to compare. Action items only exist once we
    # know what the firm actually enforces.
    if not followed:
        db.commit()
        return []

    # Current SEBI obligations relevant to this firm's category, optionally
    # restricted to the single circular the user chose to compare against.
    ob_stmt = select(Obligation).where(
        Obligation.status.in_(["verified", "approved", "flagged"])
    )
    if document_id:
        ob_stmt = ob_stmt.where(Obligation.source_document_id == document_id)
    obs = db.execute(ob_stmt).scalars().all()
    relevant: list[Obligation] = []
    for ob in obs:
        cats = {str(a.get("category", "")).lower() for a in (ob.applies_to or [])}
        if not cats or firm.category.lower() in cats or "all" in cats or "any" in cats:
            relevant.append(ob)
    if not relevant:
        db.commit()
        return []

    by_clause: dict[str, Obligation] = {}
    for ob in relevant:
        if ob.clause_path:
            by_clause.setdefault(ob.clause_path.strip().lower(), ob)

    # Don't duplicate items that already exist for the same (rule, obligation),
    # whatever their status (pending survivors when regenerate=False, plus any
    # already approved/applied/rejected).
    existing = db.execute(
        select(ChangeRequest).where(ChangeRequest.firm_id == firm_id)
    ).scalars().all()
    existing_pairs = {
        (
            str((cr.citation or {}).get("followed_rule", "")).strip().lower(),
            str((cr.citation or {}).get("obligation_id", "")),
        )
        for cr in existing
    }

    llm = get_llm()
    if not llm.enabled:
        db.commit()
        return []

    rules_txt = [
        {"followed_rule": r["rule_name"], "current_parameter": r.get("parameter_value", "")}
        for r in followed
    ]
    obs_txt = [
        {
            "clause_path": ob.clause_path,
            "statement": (ob.normalized_statement or ob.verbatim_text or "")[:240],
        }
        for ob in relevant[:80]
    ]

    try:
        payload = llm.complete_json(
            FOLLOWED_RULE_IMPACT_SYSTEM,
            f"FOLLOWED RULES:\n{json.dumps(rules_txt, ensure_ascii=False)}\n\n"
            f"SEBI OBLIGATIONS:\n{json.dumps(obs_txt, ensure_ascii=False)}",
        )
    except Exception as exc:
        log.warning("followed_rule_impact_failed", error=str(exc)[:300])
        db.commit()
        return []

    impacts = (payload or {}).get("impacts", []) if isinstance(payload, dict) else []
    followed_names = {r["rule_name"].strip().lower() for r in followed}

    drafts: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in impacts:
        if not isinstance(item, dict):
            continue
        rule_name = str(item.get("followed_rule") or "").strip()
        clause = str(item.get("clause_path") or "").strip()
        action = str(item.get("action") or "").strip()
        what = str(item.get("what_changed") or "").strip()
        if not rule_name or not clause or not action:
            continue
        # Grounding: the rule must be one the firm really follows.
        if rule_name.lower() not in followed_names:
            continue
        # Grounding: the clause must map to a real obligation.
        ob = by_clause.get(clause.lower())
        if ob is None:
            for k, v in by_clause.items():
                if clause.lower() in k or k in clause.lower():
                    ob = v
                    break
        if ob is None:
            continue
        key = (rule_name.lower(), ob.id)
        if key in seen or key in existing_pairs:
            continue
        seen.add(key)

        cr = ChangeRequest(
            change_event_id=None,
            firm_id=firm_id,
            operational_action_text=action,
            citation={
                "obligation_id": ob.id,
                "clause_path": ob.clause_path,
                "document_id": ob.source_document_id,
                "followed_rule": rule_name,
                "what_changed": what,
            },
            status="pending",
        )
        db.add(cr)
        db.flush()
        drafts.append(
            {
                "change_request_id": cr.id,
                "firm_id": firm_id,
                "type": "amended",
                "operational_action_text": action,
                "citation": cr.citation,
            }
        )

    if drafts:
        audit.record(
            db,
            action="followed_rules.impact_analyzed",
            payload={"firm_id": firm_id, "action_items": len(drafts)},
            firm_id=firm_id,
        )
    db.commit()
    return drafts


def scan_firm_database_for_changes(
    db: Session, firm_id: str, document_id: str | None = None
) -> list[dict]:
    """Real-time live database inspection comparing the rules in the broker's
    connected database against SEBI regulations.
    """
    from sqlalchemy import select
    from app.db.models import (
        Control,
        DataSource,
        Firm,
        Obligation,
        ChangeRequest,
    )

    firm = db.get(Firm, firm_id)
    if not firm:
        return []

    # Fetch live rules from connected DB & controls
    connected_rules = get_connected_database_rules(db, firm_id)["rules"]

    # Fetch SEBI obligations for this firm category
    stmt = select(Obligation).where(
        Obligation.status.in_(["verified", "approved", "flagged"])
    )
    if document_id:
        stmt = stmt.where(Obligation.source_document_id == document_id)
    sebi_obs = db.execute(stmt).scalars().all()

    relevant_obs = []
    for ob in sebi_obs:
        cats = {str(a.get("category", "")).lower() for a in (ob.applies_to or [])}
        if (
            not cats
            or firm.category.lower() in cats
            or "all" in cats
            or "any" in cats
        ):
            relevant_obs.append(ob)

    existing_crs = db.execute(
        select(ChangeRequest).where(
            ChangeRequest.firm_id == firm_id,
            ChangeRequest.status.in_(["pending", "approved"]),
        )
    ).scalars().all()
    existing_citations = {
        str((cr.citation or {}).get("obligation_id")) for cr in existing_crs
    }

    controls = db.execute(
        select(Control).where(Control.firm_id == firm_id)
    ).scalars().all()

    drafts: list[dict] = []
    # Generate action items only for relevant obligations with actionable guidance
    for ob in relevant_obs[:5]:
        if ob.id in existing_citations:
            continue

        guidance = (
            f"SEBI requirement [{ob.clause_path}]: {ob.verbatim_text[:160]}... "
            "Verify your connected database parameters and re-attest control compliance."
        )
        try:
            from app.llm.client import get_llm

            llm = get_llm()
            if llm.enabled:
                prompt = (
                    f"SEBI Circular Clause: {ob.clause_path}\n"
                    f"Requirement: {ob.verbatim_text}\n"
                    "In 1 clear sentence, explain what operational change the broker must verify in their connected database."
                )
                resp = llm.complete_json(
                    "You are a SEBI regulatory compliance advisor.", prompt
                )
                if resp and isinstance(resp, dict) and "action" in resp:
                    guidance = str(resp["action"])
        except Exception:
            pass

        cr = ChangeRequest(
            change_event_id=None,
            firm_id=firm_id,
            operational_action_text=guidance,
            citation={
                "obligation_id": ob.id,
                "clause_path": ob.clause_path,
                "document_id": ob.source_document_id,
                "live_rules_checked": len(connected_rules),
            },
            status="pending",
        )
        db.add(cr)
        db.flush()
        drafts.append(
            {
                "change_request_id": cr.id,
                "change_event_id": None,
                "firm_id": firm_id,
                "type": "amended",
                "affected_controls": [c.id for c in controls[:3]],
                "affected_tests": [],
                "operational_action_text": cr.operational_action_text,
                "citation": cr.citation,
            }
        )

    db.commit()
    return drafts


def _adopted_obligations_for_firm(db: Session, firm_id: str) -> list[Obligation]:
    """Return the obligations this firm has adopted (via active Controls)."""
    controls = db.execute(
        select(Control).where(Control.firm_id == firm_id, Control.status == "active")
    ).scalars().all()
    ob_ids: set[str] = set()
    for c in controls:
        if c.obligation_ids:
            ob_ids.update(c.obligation_ids)
    if not ob_ids:
        return []
    return list(
        db.execute(select(Obligation).where(Obligation.id.in_(list(ob_ids)))).scalars().all()
    )


def _existing_impact_event(
    db: Session,
    *,
    from_document_id: str | None,
    to_document_id: str,
    old_ob_id: str | None,
    new_ob_id: str | None,
) -> ChangeEvent | None:
    """Idempotency: has a ChangeEvent for this exact (from_doc, to_doc,
    old_ob, new_ob) pair already been recorded?"""
    stmt = select(ChangeEvent).where(ChangeEvent.to_document_id == to_document_id)
    if from_document_id is not None:
        stmt = stmt.where(ChangeEvent.from_document_id == from_document_id)
    for ev in db.execute(stmt).scalars().all():
        if (ev.old_version or {}).get("id") == old_ob_id and (ev.new_version or {}).get("id") == new_ob_id:
            return ev
    return None


def cleanup_spurious_change_requests(db: Session, firm_id: str) -> int:
    """Clean up invalid ChangeRequests generated by cross-document 'removed' false positives."""
    crs = db.execute(
        select(ChangeRequest).where(ChangeRequest.firm_id == firm_id)
    ).scalars().all()

    deleted_count = 0
    for cr in crs:
        cit = cr.citation or {}

        # Action items are now ONLY "rules you follow vs SEBI obligation"
        # comparisons, which always carry citation.followed_rule. Any PENDING
        # request without it is a leftover from the earlier adopted-obligation /
        # document-diff logic — e.g. the generic "Obligation amended. Review the
        # mapped control..." items — and is purged so the list shows only real,
        # grounded action items. Decided items (approved/applied/rejected/
        # escalated) are kept for the audit record.
        if cr.status == "pending" and not cit.get("followed_rule"):
            db.delete(cr)
            deleted_count += 1
            continue

        if not cr.change_event_id:
            # Followed-rule action items are grounded in a real obligation but
            # have no doc-to-doc ChangeEvent. Keep those; only delete genuinely
            # orphaned requests.
            if cit.get("obligation_id") or cit.get("followed_rule"):
                continue
            db.delete(cr)
            deleted_count += 1
            continue

        ce = db.get(ChangeEvent, cr.change_event_id)
        if not ce:
            db.delete(cr)
            deleted_count += 1
            continue

        if ce.type == "removed":
            from_doc = db.get(Document, ce.from_document_id) if ce.from_document_id else None
            to_doc = db.get(Document, ce.to_document_id) if ce.to_document_id else None

            is_same_series = False
            if from_doc and to_doc:
                c1 = (from_doc.circular_number or "").strip().lower()
                c2 = (to_doc.circular_number or "").strip().lower()
                t1 = (from_doc.title or "").strip().lower()
                t2 = (to_doc.title or "").strip().lower()
                if c1 and c2 and c1 == c2:
                    is_same_series = True
                elif t1 and t2 and (t1 in t2 or t2 in t1):
                    is_same_series = True

            if not is_same_series:
                db.delete(cr)
                deleted_count += 1

    if deleted_count > 0:
        db.commit()
    return deleted_count


def detect_impact_on_adopted_obligations(
    db: Session, new_document_id: str, firm_id: str
) -> list[dict]:
    """Compare a newly ingested document's obligations against everything the
    firm has already ADOPTED (i.e. has an active Control for) and raise an
    action item wherever a followed rule is amended or removed.

    This is the core Action Items behaviour: "does this new law affect any of
    my existing followed laws?". Newly *added* obligations are intentionally
    NOT surfaced here — they show up as adoption Suggestions on the Compliance
    page instead. Idempotent: re-running for the same (document, firm) pair
    will not create duplicate ChangeEvents or ChangeRequests.
    """
    document = db.get(Document, new_document_id)
    if document is None:
        return []

    new_obs = db.execute(
        select(Obligation).where(
            Obligation.source_document_id == new_document_id,
            Obligation.status != "superseded",
        )
    ).scalars().all()
    if not new_obs:
        return []

    adopted = _adopted_obligations_for_firm(db, firm_id)
    if not adopted:
        return []

    diff_result = diff_obligations(
        [_ob_dict(o) for o in adopted], [_ob_dict(n) for n in new_obs]
    )

    changes = diff_result.amended + diff_result.removed
    if not changes:
        return []

    old_by_id = {o.id: o for o in adopted}
    new_change_event_ids: list[str] = []

    for change in changes:
        old_ob = old_by_id.get(change.old_id) if change.old_id else None
        if not old_ob:
            continue

        from_doc_id = old_ob.source_document_id

        # Skip comparing an obligation against its exact same source document
        if from_doc_id == new_document_id:
            continue

        if change.type == "removed":
            from_doc = db.get(Document, from_doc_id) if from_doc_id else None
            # An adopted obligation is ONLY "removed" if new_document is a replacement / newer version
            # of the same circular/document series. Unrelated documents do NOT remove old obligations.
            is_same_series = False
            if from_doc and document:
                c1 = (from_doc.circular_number or "").strip().lower()
                c2 = (document.circular_number or "").strip().lower()
                t1 = (from_doc.title or "").strip().lower()
                t2 = (document.title or "").strip().lower()
                if c1 and c2 and c1 == c2:
                    is_same_series = True
                elif t1 and t2 and (t1 in t2 or t2 in t1):
                    is_same_series = True

            if not is_same_series:
                continue

        elif change.type == "amended":
            # Must actually have field changes or significant difference
            if not change.field_changes and change.similarity >= 0.995:
                continue

        existing = _existing_impact_event(
            db,
            from_document_id=from_doc_id,
            to_document_id=document.id,
            old_ob_id=change.old_id,
            new_ob_id=change.new_id,
        )
        if existing is not None:
            continue  # already tracked; don't duplicate

        ev = ChangeEvent(
            obligation_id=change.new_id or change.old_id,
            from_document_id=from_doc_id,
            to_document_id=document.id,
            type=change.type,
            old_version={"id": change.old_id, "text": change.old_text} if change.old_id else None,
            new_version={"id": change.new_id, "text": change.new_text} if change.new_id else None,
            similarity=change.similarity,
            field_changes=change.field_changes,
        )
        db.add(ev)
        db.flush()
        new_change_event_ids.append(ev.id)

    if not new_change_event_ids:
        return []

    return operational_impact(db, firm_id, new_change_event_ids)


def auto_change_detection(db: Session, document: Document) -> list[dict]:
    """Multi-firm fan-out of ``detect_impact_on_adopted_obligations``.

    Runs the impact check for every firm in the tenant so a single new upload
    populates Action Items across all firms that already follow related rules.
    Firms with no adopted obligations are skipped cheaply.
    """
    import structlog
    log = structlog.get_logger()

    all_drafts: list[dict] = []
    firms = db.execute(select(Firm)).scalars().all()
    for firm in firms:
        # Grounded in the rules the firm actually follows (connected database)
        # vs the obligations of THIS newly ingested circular. regenerate=False so
        # an upload only ADDS new grounded items; it never wipes items already
        # awaiting a decision.
        drafts = detect_impact_on_followed_rules(
            db, firm.id, regenerate=False, document_id=document.id
        )
        if drafts:
            all_drafts.extend(drafts)
            log.info(
                "auto_change_detection.impact_generated",
                firm_id=firm.id,
                firm_name=firm.name,
                action_items=len(drafts),
            )

    log.info(
        "auto_change_detection.complete",
        document_id=document.id,
        total_action_items=len(all_drafts),
    )
    return all_drafts



