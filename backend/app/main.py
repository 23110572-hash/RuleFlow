"""RuleFlow FastAPI application entrypoint."""
from __future__ import annotations

import logging

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import (
    audit,
    auth,
    changes,
    compliance,
    dashboard,
    datasource,
    documents,
    firms,
    inspector,
    obligations,
)
from app.config import settings
from app.db.init_db import init_db

logging.basicConfig(level=logging.INFO)
structlog.configure(processors=[structlog.processors.add_log_level, structlog.processors.JSONRenderer()])

app = FastAPI(
    title="RuleFlow — Agentic Compliance Platform",
    version=__version__,
    description=(
        "Agents propose; a deterministic Verification Kernel owns the truth; a human approves. "
        "Nothing enters the compliance record without a real SEBI citation and a human sign-off."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return unhandled errors as JSON *with* CORS headers.

    A bare ``Exception`` handler runs in Starlette's outermost
    ``ServerErrorMiddleware``, which sits outside ``CORSMiddleware``. A raw 500
    therefore skips the CORS headers and the browser surfaces it only as an
    opaque "Failed to fetch". We re-add the headers by hand so the frontend can
    read the real error message."""
    logging.exception("Unhandled error on %s %s", request.method, request.url.path)
    headers: dict[str, str] = {}
    origin = request.headers.get("origin")
    allowed = settings.cors_origin_list
    if origin and (origin in allowed or "*" in allowed):
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Vary"] = "Origin"
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {exc}"},
        headers=headers,
    )


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "llm_enabled": settings.llm_enabled,
        "llm_model": settings.llm_model if settings.llm_enabled else None,
        "database": "postgres" if not settings.is_sqlite else "sqlite",
        "citation_fidelity_threshold": settings.citation_fidelity_threshold,
    }


for r in (auth, datasource, documents, obligations, firms, compliance, changes, inspector, dashboard, audit):
    app.include_router(r.router)
