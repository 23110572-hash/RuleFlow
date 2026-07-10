# RuleFlow — Agentic Compliance Platform

**SEBI TechSprint 2026 · Theme 2 — Agentic Compliance: From Regulatory Text to Operational Action**

RuleFlow reads a SEBI circular the way a compliance officer would, turns every duty it finds into a checkable rule anchored to the exact sentence it came from, writes the rules a firm accepts straight into that firm's own database, and then keeps watch — so when SEBI changes something, the firm knows what it means for them before an inspector does.

This is the full story of what I built, why I built it this way, and how every layer works.

---

## Table of Contents

1. [The problem I set out to solve](#1-the-problem-i-set-out-to-solve)
2. [The one idea everything is built on](#2-the-one-idea-everything-is-built-on)
3. [What RuleFlow actually does](#3-what-ruleflow-actually-does)
4. [The journey of a regulation, end to end](#4-the-journey-of-a-regulation-end-to-end)
5. [Architecture — every layer](#5-architecture--every-layer)
6. [The data model — two layers, two clocks](#6-the-data-model--two-layers-two-clocks)
7. [The Agent Layer — where the reading happens](#7-the-agent-layer--where-the-reading-happens)
8. [The Verification Kernel — where the trust lives](#8-the-verification-kernel--where-the-trust-lives)
9. [The three features that carry the product](#9-the-three-features-that-carry-the-product)
10. [Connecting a firm's own database](#10-connecting-a-firms-own-database)
11. [What makes this different](#11-what-makes-this-different)
12. [Tech stack](#12-tech-stack)
13. [Running it locally](#13-running-it-locally)
14. [Repository layout](#14-repository-layout)
15. [My integrity promise](#15-my-integrity-promise)

---

## 1. The problem I set out to solve

Every SEBI-regulated intermediary — a stockbroker, a depository participant, an investment adviser, an AMC — lives under a constant stream of regulatory text. SEBI publishes circulars, master circulars, and amendments continuously, and each one can create a new obligation, tighten an existing one, or quietly retire one.

When a new circular lands, a compliance team has to do four hard things, by hand:

1. Read pages of dense legal language and understand it precisely.
2. Work out exactly which duties it creates, changes, or removes.
3. Figure out which of their own internal controls and evidence processes are affected.
4. Fix those controls before the next inspection finds the gap.

I looked at this and saw three problems that no amount of "work harder" fixes. It's **slow** — a long circular can take days to digest. It's **inconsistent** — two officers reading the same clause reach different conclusions, and there is no way to prove you caught everything. And it's **risky** — when a duty slips through, the result is a regulatory finding, with real financial and reputational cost.

Theme 2 of SEBI TechSprint 2026 asks for a system that dynamically translates regulatory text into operational action — taking raw regulation and turning it into machine-actionable, auditable compliance workflows, without losing the rigor a regulator expects. That last part is the whole game. Anyone can throw a PDF at a language model and get a summary. Doing it in a way a regulator would trust is the actual challenge, and it's the thing I designed RuleFlow around from the first line of code.

## 2. The one idea everything is built on

Here is the decision that shapes the entire system:

> **Agents propose. A deterministic kernel verifies. A human approves.**
> Nothing enters a firm's compliance record without a real citation into the source document *and* a human sign-off.

I trust language models to do exactly one kind of work: read messy legal prose and suggest structure. They are genuinely good at that. But they are also confidently wrong in ways that are unacceptable here — they will paraphrase a quote, invent a deadline that isn't written anywhere, or misjudge how serious a clause is. In compliance, a hallucinated rule is *worse* than a missing one, because it manufactures false confidence.

So I refused to let the model's word be final. I split RuleFlow into two halves that never blur together:

- **The Agent Layer** does the thinking — reading clauses, proposing obligations, judging applicability, drafting findings, scoring readiness. Everything it produces is a *proposal*, and I treat it as unproven until checked.
- **The Verification Kernel** is plain, deterministic Python with zero LLM calls. It re-reads the exact span of source text the agent claims to be quoting and mathematically checks whether the quote is really there. It computes version diffs with string algorithms instead of asking a model "what changed?". It classifies severity from a fixed table, not a vibe. Give it the same input and it returns the same answer every single time.

When the kernel rejects a proposal, that proposal is flagged for a human — never silently kept, never silently thrown away. And the human compliance officer is the final authority on every obligation, every change, every gap. This is why I can safely run a fast, cheap open model over legal text: the model is allowed to be creative, but a claim only survives if the citation holds up word for word.

## 3. What RuleFlow actually does

Three things, end to end:

- **It reads.** Give it a real SEBI PDF and it produces a structured obligation register where every obligation is tied to the precise clause and character range it came from — with a fidelity score proving the quote is genuine.
- **It adopts and remembers.** When an officer approves an obligation, RuleFlow writes that rule into the firm's *own connected database*, so the firm's systems and team hold the exact set of duties they've committed to — not a copy locked inside my app.
- **It stays in sync.** When a new circular arrives, RuleFlow diffs it against what the firm has already adopted and tells them, in plain language, which of their live rules just changed — and it continuously tests their real evidence against those rules so gaps surface before an inspector finds them.

## 4. The journey of a regulation, end to end

The clearest way to explain RuleFlow is to follow one document through the whole system.

```
  SEBI PDF
     │
     ▼
 [ Parse ]      strip Hindi pages, extract text, segment into a clause tree
     │
     ▼
 [ Extract ]    an agent reads each clause and proposes obligations + verbatim quotes
     │
     ▼
 [ Verify ]     the kernel re-reads the cited span and scores the quote (≥ 0.95 or it's flagged)
     │
     ▼
 [ Cover ]      the kernel sweeps every "shall/must" in the doc to prove nothing was missed
     │
     ▼
 Obligation Register  ──►  officer reviews in Approvals
                                     │
                          approve ───┼─── reject
                                     ▼
                     Control created  +  row written into the FIRM'S OWN database
                                     │
                                     ▼
                     Compliance tests run against the firm's real evidence
                                     │
              new circular arrives ──▼──  Action Items: "this change hits a rule you adopted"
```

Nothing in that chain is a shortcut. Every arrow is real code doing real work on real input, and every step drops a tamper-evident entry into the Activity log.

## 5. Architecture — every layer

```
┌──────────────────────────────────────────────────────────────┐
│  Frontend  — React SPA, the compliance officer's workbench     │
│  upload · review · approve · watch the live compliance picture │
└───────────────────────────────┬────────────────────────────────┘
                                 │  typed REST (Bearer auth)
┌───────────────────────────────▼────────────────────────────────┐
│  API Layer — FastAPI, thin & stateless                          │
│  authenticate → resolve the caller's firm → delegate to a service│
└───────────────────────────────┬────────────────────────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        ▼                        ▼                        ▼
┌───────────────┐      ┌──────────────────┐      ┌────────────────┐
│  Agent Layer  │      │ Verification      │      │   Services     │
│  (LLM here    │─────►│ Kernel            │─────►│  orchestrate   │
│   only)       │ props│ (zero LLM, pure   │verify│  kernel+agents │
│               │      │  deterministic)   │      │  +db per flow  │
└───────────────┘      └──────────────────┘      └───────┬────────┘
                                                          │
                              ┌───────────────────────────┼──────────────┐
                              ▼                                           ▼
                   ┌────────────────────┐                    ┌────────────────────────┐
                   │  RuleFlow database  │                    │  The FIRM'S OWN database │
                   │  (Neon Postgres):   │                    │  connected by the firm:  │
                   │  canonical + overlay│                    │  evidence read IN,       │
                   │  bitemporal         │                    │  adopted rules written OUT│
                   └────────────────────┘                    └────────────────────────┘
```

Let me walk each layer.

**The frontend** is where a compliance officer actually works. It's a React single-page app — upload a regulation, watch it get extracted live, review and approve obligations, see action items when things change, and read a real-time compliance dashboard. Pages that depend on the firm's own data (Approvals, Action items, Compliance) are locked behind a "connect your database first" gate, because those features are meaningless — and, in the case of approvals, actively wrong — without a place to write to.

**The API layer** is deliberately thin. FastAPI routers authenticate the Bearer token, resolve which firm the caller belongs to, and hand off to a service. No business logic lives in the routes. This keeps the surface area honest and testable.

**The Agent Layer** is the *only* part of the system allowed to talk to an LLM. I fenced it off on purpose. If a feature needs language understanding, it goes here; if it needs a guaranteed-correct answer, it does not.

**The Verification Kernel** sits between the agents and the database like a checkpoint. Every agent proposal has to pass through it before it can be persisted as "verified." It is pure deterministic Python — no network, no randomness.

**The Services layer** is where the flows are assembled: ingestion wires parse → extract → verify → cover; change management wires diff → impact → human decision; compliance wires test → classify → score. Services are the glue that turns individual capabilities into a product.

**Two databases, and this distinction matters a lot.** RuleFlow has its own Postgres (Neon) for the regulatory knowledge and each firm's overlay. Separately, a firm connects *their* existing database. I read evidence *in* from it, and — this is the part I care about most — when an obligation is approved, I write the adopted rule *out* into it. The firm's compliance duties end up living in the firm's own systems, not trapped inside mine.

## 6. The data model — two layers, two clocks

The schema (`backend/app/db/models.py`) is split into two conceptual layers.

**The canonical regulatory layer** is shared across every firm and deduplicated by document content hash. It is the single authoritative reading of what SEBI's text says:

- `Document` — an ingested circular: content hash, title, category, page count, status.
- `Obligation` — one extracted duty: clause path, verbatim quote, normalized statement, modality (`shall` / `may` / `best_judgment`), trigger condition, deadline or periodicity, threshold, who it applies to, the citation (page + character offsets + source hash), a citation-fidelity score, and a lifecycle status (`proposed → verified → approved / rejected → superseded`).
- `ObligationTest` — the compiled, executable check for an obligation (or `None` when it needs human judgement).
- `CoverageReport` — the completeness certificate for a document.
- `ChangeEvent` — a structural diff record (added / amended / removed) between two versions.

**The firm overlay** is private to each tenant, scoped strictly by `firm_id`. This is where a specific firm's reality lives:

- `Firm`, `User`, `DataSource` — the account and the firm's connected external database.
- `Control` — an internal control the firm runs, linked to the obligation(s) it satisfies. **This is the record that gets created when an officer approves an obligation.**
- `Evidence` — a captured artifact or metric proving a control operated.
- `Gap` — an open deficiency (missing / stale / weak / contradictory) with a severity.
- `ChangeRequest` — a drafted, cited action item waiting for a human decision.
- `Interpretation` — a firm's own notes on an obligation.
- `AuditEntry` — a hash-chained, tamper-evident log entry (this is what the Activity page shows).

And every row that matters carries **two independent clocks**:

- **Valid time** (`valid_from` / `valid_to`) — when the rule or evidence was actually in force.
- **Transaction time** (`recorded_at`) — when RuleFlow found out about it.

Keeping both is what powers the **Time Machine**: I can reconstruct exactly what was required, and what evidence existed, as of any past date — in a single query, with no separate history tables. That's the difference between "we think we were compliant last March" and being able to *show* it.

## 7. The Agent Layer — where the reading happens

The agents (`backend/app/agents/`) are a small set of narrow specialists. None of them roam free — each gets a bounded input and must return strict JSON. All their prompts live in one file (`prompts.py`) so the system's "instructions to the model" are auditable in one place.

- **Extraction Agent** — reads a single clause and proposes every obligation in it, *with a verbatim quote*. This is the only agent whose output feeds the canonical register directly, so it's the most heavily guarded. If its quote doesn't ground cleanly on the first try, it gets exactly one retry with a blunt "quote exactly what's in the text" instruction. If it still fails, the obligation is `flagged` for a human — never silently accepted, never silently dropped.
- **Applicability Agent** — decides which intermediary categories and tiers an obligation binds. If it's ambiguous, it is required to say so rather than guess, and the ambiguity goes to a human.
- **Cross-Reference Agent** — lists the references a clause makes ("para 3.2", "Schedule II"), then a deterministic filter throws away any reference whose text doesn't literally appear in the clause.
- **Control Draft Agent** — the moment an obligation is approved, this drafts the operational control that satisfies it: a concise instruction, an owner role, and a cadence. If the model is unavailable it falls back to a deterministic draft built from the obligation's own text, so approval never breaks.
- **Inspector Agent** — drafts SEBI-style findings from the firm's real compliance status, with a kernel guard that discards any finding citing an out-of-scope obligation or inventing a gap where the test is actually green.
- **Scoring Agent** — rates overall Compliance Readiness (0–100) with a plain-language reason, and falls back to a transparent computed score if the model is down, so the dashboard is never blank and never lies about how the number was produced.

**Orchestration** (`graph.py`) is a real LangGraph state machine, not a single prompt-and-done call. An `extract` node self-loops clause by clause via a conditional edge, then an `enrich` node runs applicability over every verified obligation. SEBI documents can run to hundreds of clauses, so the graph checkpoints progress as it goes — which is exactly what lets the upload screen show live, clause-by-clause progress.

**The LLM is swappable** (`llm/client.py`) through LiteLLM — one config value picks the model. I run it against fast hosted models (Groq's Llama or any OpenRouter model) because the kernel makes speed safe. And if no key is configured, the client fails loudly instead of quietly faking data — because pretending is the one thing a compliance tool must never do.

## 8. The Verification Kernel — where the trust lives

This is the part I'm proudest of. The kernel (`backend/app/kernel/`) is pure, deterministic Python — no LLM, no network, no randomness. A regulator could re-run any of it and get the identical answer. Six pieces:

- **Citation Fidelity Gate (`citation.py`)** — the single most important mechanism in the whole platform. Every obligation carries a verbatim quote and a citation (page, character offsets, source hash). The gate re-reads *that exact span* from the authoritative text and computes an in-order similarity score between the quote and the span. If it's below the threshold (default **0.95**) or the source hash doesn't match the document version, the obligation is rejected as ungrounded. This is the reason a cheap fast model is safe here: it can propose anything, but only claims the source actually supports survive.
- **Coverage Certificate (`coverage.py`)** — sweeps the entire document for every obligation signal ("shall", "must", "is required to", "no person shall", "shall not"...) and accounts for every occurrence as extracted, not-applicable, or unaccounted. The output is something a human can literally read: here is every "shall" sentence, and here is exactly which ones we did not capture. That's *provable* completeness, not a confidence claim — no summary can offer that.
- **Version Diff Engine (`diff.py`)** — a three-pass, obligation-level comparison between two document versions: exact clause-path matches first, then similarity matching for clauses that got renumbered or moved, then whatever's left is genuinely added or removed. It computes the diff; it never asks a model to guess it.
- **Gap Ledger (`gaps.py`)** — a fixed table maps `(modality, reason)` to a severity, an amber test result softens severity by exactly one rank, and a documented formula turns open gaps into a 0–100 health score. Every number traces back to a rule you can read.
- **Obligation Tests (`obligation_tests.py`)** — compliance as continuous integration. Quantitative obligations compile into an executable spec (`presence`, `recency`, `periodicity`, `deadline`, `threshold`) that runs against the firm's real evidence, honoring the `as_of` time so point-in-time answers are honest. Anything needing human judgement compiles to nothing on purpose — the kernel refuses to auto-decide what a person must decide.
- **Hashing & the audit chain (`hashing.py`)** — document dedup plus a tamper-evident audit chain where each entry hashes the previous one (`chain_hash = SHA256(prev + payload + timestamp)`). Re-deriving the chain proves nothing in the compliance history was altered after the fact.

## 9. The three features that carry the product

Everything above exists to make three everyday actions trustworthy. These are the features a compliance officer touches.

### Approvals — decide, then it's written into your database

An officer opens Approvals and sees each extracted obligation with its verbatim SEBI quote. They **Accept** or **Reject**. Accept does two things at once:

1. It creates a `Control` in RuleFlow — the firm's live record that this duty is now owned, with an auto-drafted control description, owner, and cadence.
2. It writes the adopted rule **into the firm's own connected database**, in a dedicated `ruleflow_adopted_obligations` table (portable SQL that works on Postgres, MySQL, or SQLite). It never touches the firm's existing tables, and it's idempotent — re-approving updates the same row instead of duplicating it. Reject removes that row again.

Because approving literally writes to the firm's database, I **gate the whole Approvals workflow behind a connected data source** — the page is locked, and the backend refuses the decision with a clear message, until a database is connected. After each approval the UI confirms exactly what happened: "written into your database (table …)", or a plain warning if the external write failed (in which case RuleFlow still keeps its own record, so nothing is lost).

### Action items — when a new circular hits a rule you already adopted

This is the feature that earns its keep over time. When a new document is ingested, RuleFlow diffs it against **the obligations this firm has already adopted** (not against everything — only what they actually committed to). Wherever a rule they follow was amended or removed, it raises a cited action item that shows the adopted version and the new version side by side, plus a plain-English note on what to do. Newly *added* duties don't clutter this list — those show up as suggestions on the Compliance page instead. There's also a one-click "Rescan for impact" that re-checks every document, and it's idempotent so it never creates duplicates. The officer approves, escalates, or rejects each item; nothing is auto-applied to their systems.

### Compliance — what to add next, and where you stand

The Compliance page has two halves. On top, **Suggestions**: RuleFlow looks at the firm's category and recommends grounded obligations that apply to them but they haven't adopted yet, each with a one-click **Adopt** (which runs the exact same approve-and-write-back path). Below that, **the live picture** of everything they *have* adopted — each obligation's test run against their real evidence, colour-coded green/amber/red, with classified gaps and an overall readiness score. And the **Time Machine** answers "what did this look like on date X?" against the bitemporal history. Crucially, this page only scores what the firm has genuinely adopted — it never inflates or deflates the numbers with rules they never accepted.

Every one of these actions writes a tamper-evident entry to the **Activity** log, shown in plain English ("Approved an obligation and added the control: …", "Recalculated compliance — found 3 open gaps"), never as raw IDs.

## 10. Connecting a firm's own database

A firm connects its existing database from Settings, and the connection is real — RuleFlow opens it, tests it, and reflects the schema. From there the integration runs both ways:

- **Reading in:** it can pull rows from the firm's tables and map them into `Evidence`, so compliance tests run against data that already exists in the firm's systems instead of asking anyone to re-key it. It even uses the model to help classify which tables look like controls versus evidence.
- **Writing out:** when an obligation is approved, the adopted rule and its control are written into the firm's `ruleflow_adopted_obligations` table, as described above.

I kept the writes namespaced to a single, clearly-named table and made them idempotent and non-fatal on purpose — connecting RuleFlow should never put a firm's existing data at risk.

## 11. What makes this different

- **The citation gate.** Most "AI compliance" tools ask you to trust the model. I don't. Every single obligation is re-verified against the source text, in order, word for word, or it doesn't enter the record. That one mechanism is what makes the rest safe.
- **Provable completeness.** The Coverage Certificate lists, by name, every "shall" sentence in a document and whether it was captured. That's a checkable guarantee, not "I'm fairly confident I got everything."
- **The rules live in the firm's own database.** Approving a duty writes it back into the firm's systems. RuleFlow isn't a walled garden that hoards your compliance state — it hands it to you.
- **Impact is scoped to what you actually adopted.** Action items don't fire on every regulatory tremor; they fire when something you specifically committed to just changed.
- **Determinism where it counts.** Diffs, coverage, severity, scoring, and tests are all fixed formulas. Same input, same output, every time — which is the only way a regulator can re-run and agree.
- **Two clocks, so history is honest.** Bitemporal records mean I can reconstruct any past compliance state exactly, instead of guessing from the present.
- **The human is never optional.** Nothing lands in the record without an explicit approve or reject. The system advises; the officer decides.

## 12. Tech stack

**Backend** — Python 3.12, FastAPI, SQLAlchemy 2.0, `psycopg` for Postgres, pydantic-settings for config, LangGraph for agent orchestration, LiteLLM for provider-agnostic model calls (Groq / OpenRouter), PyMuPDF for PDF parsing, structlog for logging, pytest for tests.

**Frontend** — React 18, TypeScript, Vite, Tailwind CSS, React Router 6, TanStack Query 5, Framer Motion, Recharts, lucide-react.

**Data & infra** — PostgreSQL (Neon, serverless) as the primary store, SQLite for zero-setup local dev and tests, Render for the backend, Vercel for the frontend.

## 13. Running it locally

**Backend**

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt

# create backend/.env
#   DATABASE_URL=sqlite:///./ruleflow.db      # or a Postgres URL
#   GROQ_API_KEY=...    (or OPENROUTER_API_KEY=... and set LLM_MODEL=openrouter/...)

uvicorn app.main:app --reload
```

Tables are created automatically on startup, so SQLite gives you a working instance with zero infrastructure. The API comes up at `http://localhost:8000` (`/health` to confirm, `/docs` for the interactive API).

**Frontend**

```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173
```

Point it at the backend with `VITE_API_URL` if you're not on the default.

**Tests**

```bash
cd backend
pytest
```

The suite covers the kernel (citation, coverage, diff, gaps, tests) and full service-level flows end to end, all on SQLite with no network calls — the deterministic parts are tested deterministically.

## 14. Repository layout

```text
backend/
  app/
    agents/       cognition — LangGraph pipeline + reasoning agents
      extraction.py    Extraction Agent + citation self-correction + de-dup
      graph.py         LangGraph orchestration (extract → enrich)
      reasoning.py     applicability, cross-reference, control drafting
      inspector.py     Inspector Agent (kernel-guarded findings)
      scoring.py       readiness scoring (AI + transparent fallback)
      prompts.py       every system prompt, in one place
    kernel/       trust — deterministic verification, zero LLM
      citation.py      Citation Fidelity Gate
      coverage.py      Coverage Certificate
      diff.py          Version Diff Engine (3-pass)
      gaps.py          Gap Ledger + health score
      obligation_tests.py  compiled executable tests
      hashing.py       content hash + audit hash chain
    ingest/       PDF parsing + clause-tree segmentation
    llm/          LiteLLM wrapper (Groq / OpenRouter)
    db/           SQLAlchemy models — two-layer, bitemporal
    schemas/      Pydantic request/response models
    api/          FastAPI routers (thin — delegate to services)
    services/     business logic tying kernel + agents + db together
    scripts/      utilities (e.g. reset_db.py)
  tests/          pytest — kernel + service integration + auth
frontend/         React + Vite + TypeScript + Tailwind
render.yaml       backend deployment blueprint
vercel.json       frontend SPA routing
```

## 15. My integrity promise

Every number this platform shows is computed live from real input. There is no demo mode and no scripted path.

- Uploading a real SEBI master circular runs the real parser, the real clause segmenter, the real extraction agent, the real citation gate, and writes real rows.
- Citation fidelity is a genuine similarity computation against the source text, re-read at verification time — not a field the model fills in.
- The Coverage Certificate is a real sweep of the actual document; the unaccounted sentences it lists are real sentences from that document.
- Approving an obligation really does write into the firm's connected database, and rejecting really removes it.

The synthetic firm I use in demos is fictional, but every computation applied to it — evidence matching, gap classification, scoring, diffing, write-back — is the exact same code that runs against a real firm's real data. I built it this way because a compliance tool that fakes even one number isn't a compliance tool. That was the whole point.
