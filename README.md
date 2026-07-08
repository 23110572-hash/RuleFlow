# RuleFlow — Agentic Compliance Platform

> SEBI TechSprint 2026 · Theme 2 — *Agentic Compliance: From Regulatory Text to Operational Action*

RuleFlow ingests **real SEBI regulatory documents**, extracts machine-actionable
obligations with exact citations, keeps a firm's compliance state continuously in
sync as regulation changes, and proves compliance to inspection standard.

It is built on one core principle:

> **Agents propose. A deterministic Verification Kernel owns the truth. A human approves.**
> Nothing enters the compliance record without (a) a real SEBI citation and (b) a human sign-off.

## Integrity principle

- Everything is **real and computed at runtime**. No hardcoded outputs, no scripted demo paths.
- The **regulatory side is 100% real** — real SEBI master circulars, real parsing, extraction, diffs, gaps, coverage numbers.
- The **test firm is synthetic but honest** — a realistic fictional stockbroker tenant; every computation on it is genuine.
- **No category is hardcoded.** Applicability is data (`applies_to[{category, tier}]`), not code.

## Architecture at a glance

```
React SPA (Vite, Vercel) ─REST/stream─►  FastAPI (Render Web Service)
                                        │
                    ┌───────────────────┼─────────────────────┐
                    ▼                   ▼                     ▼
              Agent Layer         Verification Kernel      Ingest
              (LangGraph +        (deterministic,          (PyMuPDF +
               Groq via           independently tested)     OCR fallback)
               LiteLLM)                 │
                    └──────────────► PostgreSQL + pgvector
                                    (bitemporal register + hash-chained audit)

  Render Background Workers run LangGraph agents + Temporal workflows.
```

See `Architecture.md` for the full specification.

## Repository layout

```
backend/          FastAPI + kernel + agents + ingest + workflows + db
  app/
    kernel/       deterministic verification kernel (the trust layer)
    ingest/       real SEBI document parsing (structure tree, tables, OCR)
    llm/          LiteLLM abstraction over Groq (model swappable)
    agents/       LangGraph agents (extraction, cross-ref, applicability, ...)
    db/           SQLAlchemy models (bitemporal, two-layer) + Alembic
    schemas/      Pydantic request/response models
    api/          FastAPI routers
    workflows/    Temporal workflows
  tests/          deterministic unit tests for the kernel
frontend/         React + Vite + TypeScript + Tailwind CSS
docker-compose.yml
.env.example
```

## Quickstart (local dev)

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -e ".[dev]"
copy ..\.env.example .env          # then edit GROQ_API_KEY etc.
uvicorn app.main:app --reload      # http://localhost:8000  (docs at /docs)
```

By default the backend runs against **SQLite** so it works with zero infra.
Set `DATABASE_URL` to a Postgres/pgvector URL for the full experience.

Run the deterministic kernel tests (no external services needed):

```bash
cd backend
pytest -q
```

### Frontend

```bash
cd frontend
npm install
npm run dev                        # http://localhost:5173 (Vite)
```

### Full stack with Docker (Postgres + Temporal + workers)

```bash
docker compose up --build
```

## Deployment

- **Frontend → Vercel**: import `frontend/` (Vite static build), set `VITE_API_URL` to the Render API URL.
- **Backend API → Render Web Service**: root `backend/`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- **Agents/Workflows → Render Background Worker**: start `python -m app.workflows.worker`.
- **DB → Neon or Supabase** (Postgres + pgvector).

See `.env.example` for all configuration.

## Proving it works

- Kernel is deterministic and unit-tested: citation gate, coverage certificate, diff, obligation tests, gap ledger, hash-chained audit.
- Extraction precision/recall is measured against a hand-annotated ground-truth set (`backend/tests/ground_truth/`).
- Citation fidelity target ≥ 0.95, enforced by the kernel before anything is recorded.
