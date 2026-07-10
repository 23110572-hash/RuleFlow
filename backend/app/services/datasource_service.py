"""Connect a broker's EXISTING database and pull evidence from it.

test_connection() genuinely opens the connection and reflects the schema, so
"Connect your database" in the UI is real, not cosmetic. Evidence import maps a
source table's rows into the firm overlay as Evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from app.db.models import DataSource, Evidence
from app.kernel.hashing import sha256_hex
from app.services import audit


def _normalise_uri(kind: str, uri: str) -> str:
    """Accept friendly URIs and coerce to SQLAlchemy dialects."""
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql+psycopg://", 1)
    elif uri.startswith("postgresql://"):
        uri = uri.replace("postgresql://", "postgresql+psycopg://", 1)
    elif uri.startswith("mysql://"):
        uri = uri.replace("mysql://", "mysql+pymysql://", 1)
    return uri


def test_connection(kind: str, uri: str) -> dict:
    """Open the connection and reflect table names. Returns {ok, tables|error}."""
    try:
        engine = create_engine(_normalise_uri(kind, uri), pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            tables = inspect(engine).get_table_names()
        engine.dispose()
        return {"ok": True, "tables": tables}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:400]}


def firm_has_data_source(db: Session, firm_id: str) -> bool:
    """True if the firm has connected (or attempted to connect) a data source.

    Features that compare against / edit the firm's own data are gated on this —
    a firm that clicked "Skip for now" at signup has no data source and must
    connect one (from Settings) before those features unlock."""
    from sqlalchemy import select

    return (
        db.execute(select(DataSource.id).where(DataSource.firm_id == firm_id)).first()
        is not None
    )


def save_data_source(db: Session, firm_id: str, name: str, kind: str, uri: str) -> DataSource:
    result = test_connection(kind, uri)
    ds = DataSource(
        firm_id=firm_id,
        name=name or kind,
        kind=kind,
        connection_uri=uri,
        status="connected" if result["ok"] else "error",
        detail={"tables": result.get("tables", [])} if result["ok"] else {"error": result.get("error")},
        last_synced_at=None,
    )
    db.add(ds)
    db.flush()

    if result["ok"]:
        try:
            discovery = auto_discover_schema(db, ds)
            ds.detail = {**(ds.detail or {}), "discovery": discovery}
        except Exception as exc:
            import structlog
            structlog.get_logger().warning("auto_discover_schema.failed", error=str(exc))

    audit.record(
        db, "datasource.connected",
        {"data_source_id": ds.id, "kind": kind, "status": ds.status},
        firm_id=firm_id,
    )
    db.commit()
    db.refresh(ds)
    return ds


def auto_discover_schema(db: Session, data_source: DataSource) -> dict:
    """AI-powered schema discovery via Groq LLM + automatic SEBI obligation mapping.

    1. Reflects tables and columns from the broker's connected database.
    2. Uses Groq LLM (when enabled) to inspect the table schemas and classify
       controls vs evidence tables.
    3. Automatically maps active SEBI Obligations into Controls for the firm
       so Compliance & Tests and Action Items work out-of-the-box.
    """
    from sqlalchemy import select
    from app.db.models import Control, Obligation, Firm

    firm = db.get(Firm, data_source.firm_id)
    firm_category = firm.category if firm else "stock_broker"

    # Inspect tables and columns
    schema_summary: dict[str, list[str]] = {}
    try:
        engine = create_engine(_normalise_uri(data_source.kind, data_source.connection_uri), pool_pre_ping=True)
        inspector = inspect(engine)
        for tbl in inspector.get_table_names()[:15]:
            cols = [c["name"] for c in inspector.get_columns(tbl)[:20]]
            schema_summary[tbl] = cols
        engine.dispose()
    except Exception:
        pass

    # Ask Groq LLM to analyze the schema if configured
    llm_analysis = {}
    try:
        from app.llm.client import get_llm
        llm = get_llm()
        if llm.enabled and schema_summary:
            prompt = (
                f"Broker firm category: {firm_category}\n"
                f"Connected database tables & columns: {schema_summary}\n\n"
                "Identify which table represents compliance controls/rules (if any) "
                "and which table represents evidence/logs (if any). Return JSON with keys: "
                "controls_table, evidence_table, description_col."
            )
            llm_analysis = llm.complete_json("You are a database schema inspection AI.", prompt) or {}
    except Exception:
        pass

    # Ensure firm has Controls linked to active SEBI obligations
    existing_controls = db.execute(
        select(Control).where(Control.firm_id == data_source.firm_id)
    ).scalars().all()
    existing_linked_obs = {oid for c in existing_controls for oid in (c.obligation_ids or [])}

    obligations = db.execute(select(Obligation)).scalars().all()
    controls_created = 0

    for ob in obligations:
        if ob.id in existing_linked_obs:
            continue
        # Check if obligation applies to firm category or is generic
        cats = {str(a.get("category", "")).lower() for a in (ob.applies_to or [])}
        if not cats or firm_category.lower() in cats or "all" in cats or "any" in cats:
            ctrl = Control(
                firm_id=data_source.firm_id,
                obligation_ids=[ob.id],
                description=f"Control for {ob.clause_path}: {ob.normalized_statement[:120]}",
                type="automated",
                owner_role="compliance_officer",
                frequency="continuous",
                status="active",
            )
            db.add(ctrl)
            controls_created += 1

    db.flush()
    return {
        "tables_inspected": list(schema_summary.keys()),
        "llm_analysis": llm_analysis,
        "controls_created": controls_created,
    }



def import_evidence(
    db: Session,
    data_source_id: str,
    table: str,
    description_column: str,
    captured_column: str | None = None,
    control_id: str | None = None,
    metric_columns: list[str] | None = None,
    limit: int = 500,
) -> dict:
    """Pull rows from the connected source table into the firm's Evidence."""
    ds = db.get(DataSource, data_source_id)
    if not ds:
        raise ValueError("data source not found")
    engine = create_engine(_normalise_uri(ds.kind, ds.connection_uri), pool_pre_ping=True)
    imported = 0
    with engine.connect() as conn:
        rows = conn.execute(text(f"SELECT * FROM {table} LIMIT :lim"), {"lim": limit}).mappings().all()
    for r in rows:
        captured = None
        if captured_column and r.get(captured_column) is not None:
            val = r[captured_column]
            captured = val if isinstance(val, datetime) else _parse(str(val))
        metrics = {}
        for mc in metric_columns or []:
            if r.get(mc) is not None:
                try:
                    metrics[mc] = float(r[mc])
                except (TypeError, ValueError):
                    pass
        desc = str(r.get(description_column, "imported evidence"))
        ehash = sha256_hex(f"{ds.id}{table}{desc}{captured}")
        db.add(
            Evidence(
                firm_id=ds.firm_id, control_id=control_id, description=desc,
                source_system=f"{ds.name}:{table}", hash=ehash, metrics=metrics,
                captured_at=captured or datetime.now(timezone.utc),
                valid_from=captured, recorded_at=datetime.now(timezone.utc),
            )
        )
        imported += 1
    ds.last_synced_at = datetime.now(timezone.utc)
    engine.dispose()
    audit.record(db, "datasource.imported", {"data_source_id": ds.id, "table": table, "rows": imported}, firm_id=ds.firm_id)
    db.commit()
    return {"imported": imported, "table": table}


def _parse(s: str) -> datetime | None:
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


# ── Writing adopted obligations BACK into the firm's own database ──────────
#
# When a compliance officer approves an obligation, the adopted rule (and the
# control drafted for it) is written into the firm's CONNECTED database so
# their own systems and team can see the rules they've committed to. We use a
# dedicated, namespaced table so we never touch the firm's existing tables.
# Types are kept portable (VARCHAR/TEXT) so this works on PostgreSQL, MySQL and
# SQLite alike. adopted_at is stored as an ISO string to avoid dialect-specific
# timestamp handling.

ADOPTED_OBLIGATIONS_TABLE = "ruleflow_adopted_obligations"

_CREATE_ADOPTED_TABLE = f"""
CREATE TABLE IF NOT EXISTS {ADOPTED_OBLIGATIONS_TABLE} (
    obligation_id VARCHAR(64) PRIMARY KEY,
    clause_path VARCHAR(255),
    obligation TEXT,
    verbatim_text TEXT,
    modality VARCHAR(32),
    deadline_or_periodicity VARCHAR(255),
    threshold VARCHAR(255),
    control TEXT,
    control_owner VARCHAR(128),
    control_frequency VARCHAR(64),
    source_document VARCHAR(255),
    adopted_at VARCHAR(40)
)
"""

_INSERT_ADOPTED = f"""
INSERT INTO {ADOPTED_OBLIGATIONS_TABLE}
    (obligation_id, clause_path, obligation, verbatim_text, modality,
     deadline_or_periodicity, threshold, control, control_owner,
     control_frequency, source_document, adopted_at)
VALUES
    (:obligation_id, :clause_path, :obligation, :verbatim_text, :modality,
     :deadline_or_periodicity, :threshold, :control, :control_owner,
     :control_frequency, :source_document, :adopted_at)
"""


def _firm_source_engine(db: Session, firm_id: str):
    """Return (engine, data_source) for the firm's connected DB, or (None, None)."""
    ds = db.execute(
        select(DataSource).where(DataSource.firm_id == firm_id)
    ).scalars().first()
    if not ds or not ds.connection_uri:
        return None, None
    engine = create_engine(_normalise_uri(ds.kind, ds.connection_uri), pool_pre_ping=True)
    return engine, ds


def push_obligation_to_source(
    db: Session, firm_id: str, obligation: dict, control: dict
) -> dict:
    """Write (upsert) an approved obligation + its control into the firm's own
    connected database, in the ``ruleflow_adopted_obligations`` table.

    Idempotent: an existing row for the same obligation_id is replaced. Returns
    {"ok": True, "table": ...} on success or {"ok": False, "error": ...} — the
    caller decides whether a failure is fatal (approval keeps working either
    way; the error is surfaced to the user)."""
    engine, ds = _firm_source_engine(db, firm_id)
    if engine is None:
        return {"ok": False, "error": "No data source connected."}

    params = {
        "obligation_id": obligation["id"],
        "clause_path": obligation.get("clause_path") or "",
        "obligation": obligation.get("normalized_statement") or "",
        "verbatim_text": obligation.get("verbatim_text") or "",
        "modality": obligation.get("modality") or "",
        "deadline_or_periodicity": obligation.get("deadline_or_periodicity") or "",
        "threshold": obligation.get("threshold") or "",
        "control": control.get("description") or "",
        "control_owner": control.get("owner_role") or "",
        "control_frequency": control.get("frequency") or "",
        "source_document": obligation.get("source_document") or "",
        "adopted_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with engine.begin() as conn:
            conn.execute(text(_CREATE_ADOPTED_TABLE))
        with engine.begin() as conn:
            conn.execute(
                text(f"DELETE FROM {ADOPTED_OBLIGATIONS_TABLE} WHERE obligation_id = :obligation_id"),
                {"obligation_id": params["obligation_id"]},
            )
            conn.execute(text(_INSERT_ADOPTED), params)
        if ds is not None:
            ds.last_synced_at = datetime.now(timezone.utc)
        return {"ok": True, "table": ADOPTED_OBLIGATIONS_TABLE}
    except Exception as exc:  # pragma: no cover - depends on external DB
        return {"ok": False, "error": str(exc)[:300]}
    finally:
        engine.dispose()


def remove_obligation_from_source(db: Session, firm_id: str, obligation_id: str) -> dict:
    """Delete a previously-adopted obligation row from the firm's connected
    database (used when an obligation is rejected). Missing table/row is not an
    error."""
    engine, _ds = _firm_source_engine(db, firm_id)
    if engine is None:
        return {"ok": False, "error": "No data source connected."}
    try:
        with engine.begin() as conn:
            conn.execute(text(_CREATE_ADOPTED_TABLE))
            conn.execute(
                text(f"DELETE FROM {ADOPTED_OBLIGATIONS_TABLE} WHERE obligation_id = :obligation_id"),
                {"obligation_id": obligation_id},
            )
        return {"ok": True, "table": ADOPTED_OBLIGATIONS_TABLE}
    except Exception as exc:  # pragma: no cover - depends on external DB
        return {"ok": False, "error": str(exc)[:300]}
    finally:
        engine.dispose()
