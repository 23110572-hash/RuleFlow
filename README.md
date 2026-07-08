# RuleFlow — Agentic Compliance Platform

> Built for SEBI TechSprint 2026 · Theme 2  
*Agentic Compliance: From Regulatory Text to Operational Action*

---

## Table of Contents

1. [The Problem Statement](#1-the-problem-statement)
2. [What RuleFlow Is](#2-what-ruleflow-is)
3. [Core Design Philosophy](#3-core-design-philosophy)
4. [System Architecture](#4-system-architecture)
5. [The Two-Layer, Bitemporal Data Model](#5-the-two-layer-bitemporal-data-model)
6. [The Agent Layer — Cognition](#6-the-agent-layer--cognition)
7. [The Verification Kernel — Trust](#7-the-verification-kernel--trust)
8. [The Three Operating Flows](#8-the-three-operating-flows)
9. [Backend Walkthrough (module by module)](#9-backend-walkthrough-module-by-module)
10. [API Reference](#10-api-reference)
11. [Frontend Walkthrough](#11-frontend-walkthrough)
12. [Tech Stack](#12-tech-stack)
13. [Integrity Principle — Why Nothing Here Is a Demo Trick](#13-integrity-principle--why-nothing-here-is-a-demo-trick)
14. [Repository Layout](#14-repository-layout)

---

## 1. The Problem Statement

SEBI intermediaries — stockbrokers, depository participants, investment advisers, asset management companies, and others — have to keep pace with a constant stream of circulars, master circulars, and amendments. Every time SEBI publishes new regulatory text, a compliance team has to:

1. Read through dense legal language, often dozens of pages long.
2. Figure out exactly what new obligations it creates (or which old ones it changes or removes).
3. Work out which of the firm's internal controls, policies, and evidence collection processes are affected.
4. Update those controls before the next inspection catches a gap.

This process today is manual, slow, and inconsistent. Different compliance officers can read the same circular and draw different conclusions about what it requires. Nothing quantifies "did we catch everything in this document." When a firm gets it wrong, the cost is a regulatory finding — sometimes with financial or reputational consequences.

The challenge posed by SEBI TechSprint 2026's Theme 2 is to build a system that dynamically translates regulatory text into operational action — ingesting raw regulatory language and turning it into machine-actionable, auditable compliance workflows, without losing the rigor a regulator would expect.

## 2. What RuleFlow Is

RuleFlow is an agentic compliance engine. It ingests real SEBI regulatory documents (PDF circulars and master circulars), extracts every obligation those documents impose as structured, citation-grounded data, and keeps a firm's compliance state continuously in sync as new regulations arrive.

Concretely, it does three things end to end:

- **Reads** a SEBI document and produces a structured obligation register where every single obligation is anchored to the exact sentence it came from.
- **Diffs** regulatory versions deterministically, so when SEBI amends a circular, RuleFlow can say precisely what was added, changed, or removed — and what that means operationally for a specific firm.
- **Checks** a firm's actual evidence (pulled from their own database) against those obligations continuously, surfacing gaps before an inspector does.

## 3. Core Design Philosophy

The central design decision in RuleFlow is a strict separation between two kinds of computation:

> **Agents propose. A deterministic Verification Kernel owns the truth. A human approves.**
> Nothing enters the compliance record without (a) a real citation into the source document and (b) a human sign-off.

Large language models are extremely good at reading unstructured legal text and proposing structured obligations. They are also unreliable in a way that is unacceptable for regulatory compliance — they can paraphrase confidently, invent a deadline that isn't in the text, or misclassify an obligation's severity. A hallucinated compliance rule is worse than no rule at all, because it creates false confidence.

So RuleFlow is deliberately split into two halves that never blur together:

- **The Agent Layer** (LangGraph + an LLM via LiteLLM) does the cognitive work: reading clauses, proposing obligations, deciding applicability, drafting inspection findings, scoring readiness. Everything here is probabilistic and advisory.
- **The Verification Kernel** is plain, deterministic Python with zero LLM calls. It re-reads the exact span of source text an agent cited and mathematically checks whether the agent's quote is actually grounded there. It computes diffs with string-similarity algorithms, not "ask the model what changed." It classifies gaps with a fixed severity table, not model judgement. Given the same input, it always produces the same output.

If the kernel rejects an agent's proposal, that proposal is flagged for human review rather than silently discarded or silently accepted. The human compliance officer is the final decision-maker on every obligation, every change request, and every gap — the platform never writes to a firm's live compliance record without an explicit approve/reject.

## 4. System Architecture

![Architecture overview]

At a glance:

- The **frontend** (React SPA) is the compliance officer's workbench — upload documents, review obligations, approve change requests, watch the live compliance dashboard.
- The **API layer** (FastAPI) is a thin, stateless REST layer. It authenticates requests, resolves the current user's firm, and delegates to services.
- The **Agent Layer** sits behind the ingestion and inspection endpoints. It's the only part of the system that talks to an LLM.
- The **Verification Kernel** sits between the Agent Layer and the database. Every agent output passes through it before being persisted as "verified."
- The **database** is a bitemporal, two-layer Postgres schema — described in detail in section 5.
- Optionally, RuleFlow connects directly to **the firm's own database** (their existing broker/AMC systems) to pull real evidence rows rather than asking someone to manually re-enter data that already exists somewhere.

## 5. The Two-Layer, Bitemporal Data Model

![Two-layer data model]

RuleFlow's database (`app/db/models.py`) is split into two conceptual layers:

**Canonical Regulatory Layer** — shared across every firm, deduplicated by document content hash. This is the single, authoritative interpretation of what SEBI's text says. It contains:

- `Document` — an ingested circular/master circular: content hash, title, category, page count, ingestion status.
- `Obligation` — one extracted duty: clause path, verbatim quote, normalized statement, modality (`shall`/`may`/`best_judgment`), trigger condition, deadline/periodicity, threshold, applicability, citation (page + char offsets + source hash), citation fidelity score, and lifecycle status (`proposed → verified → approved/rejected → superseded`).
- `ObligationTest` — the compiled, executable check for an obligation (or `None` if it's a human-judgement item).
- `CoverageReport` — the Coverage Certificate for a document (see section 7).
- `ChangeEvent` — a structural diff record (added/amended/removed) between two document versions.

**Firm Overlay** — private per tenant, scoped strictly by `firm_id`. This is where a specific firm's reality lives:

- `Firm`, `User`, `DataSource` — account/tenant records, including the firm's connected external database.
- `Control` — an internal control the firm runs, linked to one or more canonical `Obligation.id`s.
- `Evidence` — a captured artifact/metric proving a control operated, linked to a `Control`.
- `Gap` — an open compliance gap (missing/stale/weak/contradictory), with severity.
- `ChangeRequest` — a drafted, cited operational action item awaiting human approval.
- `Interpretation` — a firm's own notes/rationale attached to an obligation.
- `AuditEntry` — a hash-chained, tamper-evident log entry.
- `Finding` — a draft finding from a self-inspection run.

Every row that matters carries **two independent time axes**:

- **Valid time** (`valid_from` / `valid_to`) — when the rule or evidence was actually in force.
- **Transaction time** (`recorded_at`) — when RuleFlow learned about it.

This is what makes the **Time Machine** feature possible: `GET /firms/{firm_id}/compliance/time-machine?as_of=<date>` reconstructs exactly what was required and what evidence existed as of any past date, in a single query, without needing separate history tables.

## 6. The Agent Layer — Cognition

![LangGraph extraction pipeline]

The agent layer (`app/agents/`) is a small set of narrowly-scoped agents, each with one job and one system prompt (`app/agents/prompts.py`). None of them are free-roaming — each is called with a specific, bounded input and expected to return strict JSON.

- **Extraction Agent** (`extraction.py`) — given one clause of text, proposes every obligation it contains, *with a verbatim quote*. This is the only agent whose output feeds directly into the canonical register, and it's the most heavily guarded: every quote is checked by the Citation Fidelity Gate (section 7) before acceptance. If the first attempt doesn't ground cleanly, the agent gets exactly one retry with an explicit "quote exactly what's in the text" instruction. If it still fails, the obligation is marked `flagged` for a human to resolve — it is never silently kept or silently dropped.
- **Cross-Reference Agent** (`reasoning.py: resolve_references`) — lists internal/external references an obligation makes (e.g. "para 3.2", "Schedule II"), filtered deterministically to only references whose raw text literally appears in the obligation.
- **Applicability Agent** (`reasoning.py: decide_applicability`) — decides which intermediary categories/tiers an obligation binds to. If it's ambiguous, it says so explicitly rather than guessing, and the ambiguity is surfaced to a human.
- **Control & Evidence Agent** (`reasoning.py: propose_control_and_evidence`) — proposes one operational control and the evidence that would prove it, for a human to promote into the firm's overlay. Advisory only.
- **Inspector Agent** (`inspector.py`) — given a theme and the firm's real obligation/compliance status, drafts SEBI-style findings. A kernel guard drops any finding that cites an obligation not in the provided scope, or that claims a gap where the test status is actually green.
- **Scoring Agent** (`scoring.py`) — rates a firm's overall Compliance Readiness (0–100) with a plain-language rationale. If the LLM is unavailable, it falls back to a transparent computed score (weighted penalty per open gap) so the dashboard is never blank and never lies about how the number was produced.

**Orchestration** (`graph.py`) wires the Extraction Agent into a real LangGraph `StateGraph`: an `extract` node that self-loops over every clause via a conditional edge (`cursor < len(clauses) → loop`), followed by an `enrich` node that runs the Applicability Agent over every verified obligation. This is genuine agentic control flow — not a single prompt-and-done call — because SEBI documents can run into hundreds of clauses and the graph needs to checkpoint progress clause-by-clause (the async ingestion path reports live progress back to the frontend from inside this loop).

**LLM abstraction** (`app/llm/client.py`) wraps [LiteLLM](https://github.com/BerriAI/litellm), so the underlying model is swappable via one config value (`LLM_MODEL`). Today it targets Groq's `llama-3.3-70b-versatile` for speed, or any OpenRouter model, by prefixing the model string with `openrouter/`. If no API key is configured, the client refuses loudly (`RuntimeError`) rather than silently returning fake data — there is no rule-based extraction fallback, because the point of the agent layer is genuine language understanding. The kernel, by contrast, works with zero LLM dependency.

## 7. The Verification Kernel — Trust

The kernel (`app/kernel/`) is pure, deterministic Python. No network calls, no randomness, same input always produces the same output. This is deliberate: a regulator (or a judge, eventually) needs to be able to re-run these checks and get the same answer every time.

- **`citation.py` — Citation Fidelity Gate.** The single most important trust mechanism in the platform. Every obligation carries a verbatim quote and a citation (page, char offsets, source hash). `verify_citation()` re-reads *that exact span* from the authoritative document text and computes an in-order token-similarity score (via `difflib.SequenceMatcher`) between the quote and the span. If the score is below the threshold (default **0.95**, `citation_fidelity_threshold` in config) or the source hash doesn't match the document version, the obligation is rejected as ungrounded. This is what makes it safe to use a fast, cheap open model for legal text — the model can propose anything, but a claim only survives if the citation actually supports it, word for word, in order.
- **`coverage.py` — Coverage Certificate.** Sweeps the entire document text for every obligation-signal phrase ("shall", "must", "is required to", "no person shall", "shall not", etc.) and accounts for every single occurrence as `extracted` (covered by an accepted obligation's citation span), `not_applicable` (explicitly marked N/A with a reason), or `unaccounted`. This produces a certificate a human can literally read — every "shall" sentence the system did not capture is listed out, by name. No chatbot-style summary can offer this; it's provable completeness, not a confidence claim.
- **`diff.py` — Version Diff Engine.** Structural, obligation-level comparison between two canonical document versions. Three-pass matching: (1) exact `clause_path` match, scored by tracked-field + text similarity to classify `unchanged` vs `amended`; (2) residual similarity matching for clauses that got renumbered or moved; (3) whatever's left over is genuinely `added` or `removed`. It never asks an LLM "what changed" — it computes it, so the result is exact and repeatable.
- **`gaps.py` — Gap Ledger.** A fixed lookup table maps `(modality, reason)` → severity (`critical`/`high`/`medium`/`low`), where `reason` ∈ `missing | stale | weak | contradictory`. Amber test results soften the severity by exactly one rank. `health_score()` derives a 0–100 score from weighted, obligation-count-normalized penalties. This never guesses — every score is traceable to a specific formula.
- **`obligation_tests.py` — Obligation Tests (compliance-as-CI).** Quantitative obligations are compiled into an executable test spec (`presence`, `recency`, `periodicity`, `deadline`, `threshold`), and `evaluate_test()` runs that spec against the firm's actual evidence rows, honoring the `as_of` time for bitemporal-honest point-in-time evaluation. Obligations requiring human judgement (`best_judgment`, `may`) intentionally compile to `None` — the kernel refuses to auto-decide something a human needs to judge; it stays a checklist item forever.
- **`hashing.py`** — normalization, `content_hash` (for document dedup) and the audit hash chain (`chain_hash = SHA256(prev_chain_hash + canonical_json(payload) + timestamp)`), plus `verify_chain()` to re-derive and confirm tamper-evidence.

## 8. The Three Operating Flows

![The three operating flows]

**Flow A — Onboarding.** A firm uploads its governing SEBI Master Circular (or pastes text). The Extraction Agent walks every clause, the kernel verifies every citation, and a Coverage Certificate is produced proving no obligation-signal sentence was missed. The firm then maps its existing controls and evidence onto the resulting canonical obligations, and the dashboard immediately reflects a real, live compliance picture.

**Flow B — Change Management.** When SEBI publishes a new or amended circular:
1. The new document is ingested the same way as onboarding.
2. `POST /documents/{from_id}/diff/{to_id}` runs the deterministic Version Diff Engine against the previous canonical version and persists `ChangeEvent` rows.
3. `POST /firms/{firm_id}/change-impact` runs operational-impact analysis: for each change, which of *this specific firm's* controls and tests are affected, and drafts a pending, cited `ChangeRequest`.
4. A human compliance officer reviews the change side-by-side with the original SEBI text and the proposed operational action, then approves, escalates, or rejects it (`POST /change-requests/{id}/decision`).
5. Once approved, the firm applies the change in their own systems and marks it done (`POST /change-requests/{id}/applied`). Nothing is auto-applied.

**Flow C — Ongoing Inspection.** Instead of waiting for a real SEBI audit, the Inspector Agent runs a thematic self-inspection at any time: the kernel evaluates every in-scope obligation's test against current evidence, the Gap Ledger classifies any deficiencies, and the Inspector Agent drafts SEBI-style findings — each one validated against the real obligation list so it can't cite something out of scope or invent a gap that doesn't exist. The result is a Findings Report the compliance team gets to read *before* a real inspector does.

Every step in every flow writes a hash-chained `AuditEntry`. `GET /audit/verify` re-derives the entire chain and reports the first broken link if tampering ever occurred — nothing changes the compliance record silently.

## 9. Backend Walkthrough (module by module)

```
backend/app/
  agents/        Cognition — LangGraph pipeline + individual reasoning agents
    extraction.py    Extraction Agent + citation self-correction + de-dup
    graph.py         LangGraph StateGraph orchestration (extract → enrich)
    reasoning.py     Cross-reference / Applicability / Control & Evidence agents
    inspector.py     Inspector Agent (kernel-guarded findings)
    scoring.py       Compliance Readiness scoring (AI + transparent fallback)
    prompts.py       All system prompts, in one place
  kernel/        Trust — deterministic verification, zero LLM calls
    citation.py      Citation Fidelity Gate
    coverage.py      Coverage Certificate (obligation-signal sweep)
    diff.py          Version Diff Engine (3-pass obligation matching)
    gaps.py          Gap Ledger + health score
    obligation_tests.py  Compiled executable obligation tests
    hashing.py       Normalization, content hash, audit hash chain
  ingest/        Document parsing
    parser.py        PyMuPDF text extraction, Hindi-page filtering, OCR fallback
    structure.py      Clause-tree segmentation (Chapter → 1.1.1 → (a) → (i))
  llm/
    client.py        LiteLLM wrapper (Groq / OpenRouter), strict-JSON completion
  db/
    models.py        SQLAlchemy ORM — the two-layer, bitemporal schema
    base.py, init_db.py   Engine/session setup, table creation
  services/      Business logic orchestrating kernel + agents + db
    ingest_service.py       Flow A: parse → extract → persist → coverage
    change_service.py       Flow B: diff → impact analysis → HIL decision
    compliance_service.py   Flow C core: evaluate obligations, refresh gaps, time machine
    inspector_service.py    Flow C: thematic self-inspection report
    datasource_service.py   Connect + reflect + import from the firm's own DB
    audit.py                Hash-chained audit log record/verify
    progress.py             In-memory async ingestion progress tracker
  api/           FastAPI routers (thin — delegate to services)
  security.py    PBKDF2 password hashing + HMAC-signed compact tokens
  config.py      Environment-driven settings (pydantic-settings)
  main.py        App wiring, CORS, global exception handler, router registration
```

A few implementation details worth calling out:

- **Clause segmentation** (`structure.py`) is regex-driven and deterministic: it recognizes `Chapter`/`Part` headers, dotted numbering (`1`, `1.1`, `1.1.1`, up to 5 levels deep), and lettered/roman sub-clauses (`(a)`, `(i)`), building a resolved `clause_path` like `Ch.III 4.2(a)` with exact character offsets — so every obligation extracted from that clause can cite a precise, verifiable span.
- **Bilingual PDF handling** (`parser.py`) — SEBI PDFs are frequently bilingual with Hindi pages preceding the English translation. The parser detects predominantly-Devanagari pages by character ratio and drops them, then does a second line-level pass to strip any stray Devanagari that leaked onto an English page, so no Hindi text ever reaches the LLM or throws off character offsets.
- **Async ingestion** (`ingest_service.py: ingest_pdf_async`) — PDF parsing and LLM extraction run in a background thread so the upload request returns immediately; the frontend polls `GET /documents/{id}/progress` every 2 seconds and renders a live multi-stage progress UI (`AgentFlow.tsx`).
- **De-duplication** — documents are de-duped by content hash (re-uploading the same PDF returns the existing record, not a duplicate); extracted obligations from the same clause are de-duped by normalized-statement similarity, keeping whichever candidate is better-grounded.

## 10. API Reference

All endpoints are FastAPI routers registered in `main.py`. Authentication is a Bearer token (see section 17); most firm-scoped routes additionally require `require_firm_data_source` (403 until the firm connects a data source from Settings).

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/register` | Create account + firm (+ optional data source) |
| POST | `/auth/login` | Authenticate, get a session token |
| GET | `/auth/me` | Current session (user, firm, data source summary) |
| POST | `/data-sources/test` | Test a DB connection without saving |
| GET | `/data-sources` | List the firm's connected data sources |
| POST | `/data-sources` | Save + test a new data source |
| POST | `/data-sources/{id}/import` | Import evidence rows from a connected table |
| GET | `/documents` | List ingested documents + coverage summary |
| GET | `/documents/{id}` | Single document detail |
| POST | `/documents/ingest-text` | Ingest raw/pasted regulatory text (synchronous) |
| POST | `/documents/ingest-pdf` | Upload + ingest a PDF (async, backgrounded) |
| GET | `/documents/{id}/progress` | Poll live ingestion progress |
| GET | `/documents/{id}/coverage` | Full Coverage Certificate |
| GET | `/obligations` | Search/filter the canonical obligation register |
| GET | `/obligations/{id}` | Obligation detail + source clause + test + linked controls |
| POST | `/obligations/{id}/decision` | Human approve/reject an obligation |
| GET | `/firms` / `POST /firms` / `GET /firms/{id}` | Firm CRUD |
| GET/POST | `/firms/{id}/controls` | List/create firm controls |
| GET/POST | `/firms/{id}/evidence` | List/add firm evidence |
| GET | `/firms/{id}/compliance/evaluate` | Live obligation-test results + gaps + readiness |
| POST | `/firms/{id}/compliance/refresh-gaps` | Recompute + persist the gap ledger |
| GET | `/firms/{id}/compliance/gaps` | List persisted open gaps |
| GET | `/firms/{id}/compliance/time-machine?as_of=` | Point-in-time reconstruction |
| POST | `/documents/{from_id}/diff/{to_id}` | Deterministic canonical version diff |
| POST | `/firms/{id}/change-impact` | Draft operational-impact Change Requests |
| GET | `/firms/{id}/change-requests` | List a firm's change requests |
| POST | `/change-requests/{id}/decision` | HIL approve / escalate / reject |
| POST | `/change-requests/{id}/applied` | Firm marks a change as applied |
| POST | `/firms/{id}/inspector/run` | Run a thematic self-inspection |
| GET | `/firms/{id}/inspector/reports/{report_id}` | Fetch a past inspection report |
| GET | `/firms/{id}/dashboard` | Aggregated dashboard payload |
| GET | `/audit?firm_id=` | Hash-chained audit log |
| GET | `/audit/verify?firm_id=` | Re-derive and verify the audit chain |
| GET | `/health` | Liveness + config summary |

## 11. Frontend Walkthrough

React 18 + Vite + TypeScript + Tailwind + React Router 6 + TanStack Query 5 + Framer Motion.

- **`App.tsx`** — routes: `/` (public landing), `/login`, `/register` are unauthenticated; everything under `/app/*` is wrapped in a `Protected` guard and the `AppLayout` shell. `change-requests`, `compliance`, and `inspector` are additionally wrapped in `RequireDataSource`, which locks those pages behind a "connect your database first" screen if the firm hasn't connected a data source yet.
- **`components/AppLayout.tsx`** — the sidebar shell: firm identity, nav (Regulations, Obligations, Approvals, Action items, Compliance, Self-inspection, Audit trail, Overview), and account menu. Gated nav items show a lock icon when no data source is connected.
- **`components/AgentFlow.tsx`** — the live, multi-stage ingestion progress visualization (parsing → extraction agent → citation check → coverage certificate), driven by polling `IngestionProgress` from the backend.
- **`components/RequireDataSource.tsx`** — the reusable gate component described above.
- **`lib/api.ts`** — the single typed HTTP client; every backend response has a corresponding TypeScript type here.
- **`lib/auth.tsx`** — session context (user/firm/data source), backed by a token in `localStorage`.
- **Pages** (`src/pages/`) — `Dashboard` (readiness ring + gap/test breakdown), `Documents` (upload + coverage), `Obligations` (search/filter/approve register), `Approvals` (pending human decisions), `ChangeRequests` (Flow B review), `Compliance` (live test/gap view + Time Machine), `Inspector` (Flow C self-inspection runner), `Audit` (hash-chain viewer), `Settings` (profile + data source connection), plus public `Landing`/`Login`/`Register`.

## 12. Tech Stack

**Backend**
- Python 3.12, FastAPI ≥0.115, Uvicorn
- SQLAlchemy ≥2.0 + Alembic, `psycopg` (Postgres driver)
- Pydantic ≥2.7 / pydantic-settings for config
- LangGraph ≥0.2 + langchain-core for agent orchestration
- LiteLLM for provider-agnostic LLM calls (Groq `llama-3.3-70b-versatile` by default, or any OpenRouter model)
- PyMuPDF (`fitz`) for PDF parsing; optional PaddleOCR for scanned pages
- structlog for structured logging
- pytest for testing

**Frontend**
- React 18.3, TypeScript 5.5, Vite 5.3
- React Router 6.25, TanStack Query 5.51
- Tailwind CSS 3.4, Framer Motion 11.3
- Recharts for data visualization, lucide-react for icons

**Data & Infra**
- PostgreSQL (Neon, serverless) as the primary datastore; SQLite supported for zero-infra local dev
- pgvector available for future embedding-based similarity search
- Render (backend web service) + Vercel (frontend SPA) for deployment

## 13. Integrity Principle — Why Nothing Here Is a Demo Trick

Every number this platform shows is computed live from real inputs:

- Uploading an actual SEBI Master Circular runs the real PyMuPDF parser, the real clause segmenter, the real Extraction Agent, the real Citation Fidelity Gate, and writes real rows to Postgres. There is no pre-baked "demo mode" or scripted response path.
- Citation Fidelity is a genuine token-similarity computation against the source text re-read at verification time, not a static field the agent fills in.
- The Coverage Certificate is a real regex sweep of the actual document text; the unaccounted signals it lists are real sentences from that document.
- The synthetic test firm used in demos is fictional, but every computation applied to it (evidence matching, gap classification, health scoring, diffing) is the same genuine logic that would run against a real firm's real database.

## 14. Repository Layout

```text
backend/          FastAPI + kernel + agents + ingest + services + db
  app/
    agents/       LangGraph agents (extraction, reasoning, inspector, scoring)
    kernel/       deterministic verification kernel (the trust layer)
    ingest/       PDF/text parsing, clause structure segmentation
    llm/          LiteLLM abstraction over Groq/OpenRouter
    db/           SQLAlchemy models (bitemporal, two-layer)
    schemas/      Pydantic request/response models
    api/          FastAPI routers
    services/     business logic tying kernel + agents + db together
  tests/          pytest suite (kernel + service integration + auth)
frontend/         React + Vite + TypeScript + Tailwind CSS
docs/diagrams/    SVG architecture diagrams referenced by this README
render.yaml       Render Blueprint for backend deployment
vercel.json       Vercel SPA routing
```




