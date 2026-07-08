"""Data Source API — connect the broker's existing database, discover tables,
and import evidence. All scoped to the authenticated firm."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_firm
from app.db.base import get_db
from app.db.models import DataSource, Firm
from app.services import datasource_service

router = APIRouter(prefix="/data-sources", tags=["data-sources"])


class TestIn(BaseModel):
    kind: str = "postgresql"
    connection_uri: str


class ConnectIn(TestIn):
    name: str = ""


class ImportIn(BaseModel):
    table: str
    description_column: str
    captured_column: str | None = None
    control_id: str | None = None
    metric_columns: list[str] = []


@router.post("/test")
def test(body: TestIn, firm: Firm = Depends(get_current_firm)):
    """Test a connection WITHOUT saving. Returns discovered tables or an error."""
    return datasource_service.test_connection(body.kind, body.connection_uri)


@router.get("")
def list_sources(firm: Firm = Depends(get_current_firm), db: Session = Depends(get_db)):
    rows = db.execute(select(DataSource).where(DataSource.firm_id == firm.id)).scalars().all()
    return [
        {"id": d.id, "name": d.name, "kind": d.kind, "status": d.status,
         "tables": (d.detail or {}).get("tables", []), "error": (d.detail or {}).get("error"),
         "last_synced_at": d.last_synced_at.isoformat() if d.last_synced_at else None}
        for d in rows
    ]


@router.post("")
def connect(body: ConnectIn, firm: Firm = Depends(get_current_firm), db: Session = Depends(get_db)):
    ds = datasource_service.save_data_source(db, firm.id, body.name, body.kind, body.connection_uri)
    return {"id": ds.id, "name": ds.name, "kind": ds.kind, "status": ds.status,
            "tables": (ds.detail or {}).get("tables", []), "error": (ds.detail or {}).get("error")}


@router.post("/{data_source_id}/import")
def import_evidence(
    data_source_id: str,
    body: ImportIn,
    firm: Firm = Depends(get_current_firm),
    db: Session = Depends(get_db),
):
    ds = db.get(DataSource, data_source_id)
    if not ds or ds.firm_id != firm.id:
        raise HTTPException(404, "data source not found")
    try:
        return datasource_service.import_evidence(
            db, data_source_id, body.table, body.description_column,
            body.captured_column, body.control_id, body.metric_columns,
        )
    except Exception as e:
        raise HTTPException(400, str(e))
