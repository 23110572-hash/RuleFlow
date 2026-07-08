# Agentic Compliance — Architecture Specification (v0.2 DRAFT)

**Problem:** SEBI TechSprint 2026 — Theme 2: *Agentic Compliance: From Regulatory Text to Operational Action*
**Intermediary scope:** Category-agnostic — the engine handles **any** SEBI intermediary category (stockbrokers, depositories, AMCs, RTAs, investment advisers, MIIs, etc.). Nothing is hardcoded to a category.
**Document scope:** Any SEBI document (circular, master circular, notification, guideline). Identified by circular number + content hash.
**Validation corpus (real):** Start with SEBI's suggested baseline — the Master Circulars for Stock Brokers and Investment Advisers (real, from sebi.gov.in) — while the engine stays fully general. The concrete demonstrated scenario emerges from the real extracted obligations, not a pre-scripted one.

---

## 0. Integrity principle (non-negotiable)

Everything in this system is real and computed live. No hardcoded outputs, no scripted demo paths.

- **Regulatory side = 100% real.** Real SEBI master circulars from sebi.gov.in. Real extraction, real diffs, real gap detection, real coverage numbers. Nothing about the regulation is faked or pre-baked.
- **Every output is computed by the engine at runtime.** If it appears in a demo, it works because the engine actually produced it.
- **The test firm is a synthetic-but-honest tenant.** Since no real broker will share internal compliance data, we register a *realistic fictional stockbroker* in the app with plausible controls and evidence, then watch the real engine process real SEBI changes against it. The firm is synthetic; every computation on it is genuine.

---

## 1. One-line thesis

> Build a **living, versioned, citation-grounded Compliance Knowledge Base** with a **deterministic verification kernel**. **Agents do the reasoning; the kernel owns the truth; the human compliance officer approves.** Nothing enters the compliance record without a real SEBI citation and a human sign-off.

The problem statement asks for *"operational action"* — so the durable asset is the structured, auditable compliance state. The LLM is a proposer; the value lives in the knowledge base and the workflow around it.

---

## 2. Alignment with the two SEBI challenges

The problem statement defines two challenges. This architecture covers **both**.

| SEBI Challenge | SEBI's words | How we address it |
|---|---|---|
| **1. Dynamic regulatory translation** | "interpreting a new/amended requirement, mapping it to the affected intermediary's operational processes, and updating compliance workflows in a timely and consistent manner" | **Flow B (Change Management):** new SEBI doc → extract → diff on the canonical layer → **operational-impact** analysis on the firm's overlay → HIL approve → emit a cited **Change Request** the firm applies (no direct write-back) |
| **2. Ongoing compliance management** | "mapping each obligation to evidence of fulfilment, maintaining audit trails, and identifying and remediating compliance gaps before they become regulatory findings" | **Flow C (Compliance & Inspection):** obligation → control → evidence linkage, deterministic gap detection, Inspector self-assessment, tamper-evident audit trail |
| **Shared root** | "transforming regulatory intent into programmable, auditable compliance logic" | Structured versioned **Obligation Register** + **Regulation-as-Code** for the codifiable subset + hash-chained audit log |
| **Deliverable rules** | "specify the intermediary category and regulatory corpus" + "demonstrate on at least one concrete regulatory scenario" | Stockbroker + real Master Circular + a concrete scenario (e.g. upfront margin reporting / T+1) |

**Anti-divergence note:** SEBI explicitly names *"divergent interpretations across similarly situated intermediaries"* as a pain. The platform provides **one canonical, cited interpretation** as the default; the HIL officer approves/annotates rather than re-interpreting from scratch — so the platform *reduces* divergence instead of scattering it.

---

## 3. Core design principle: Agents on a Verification Kernel

We name a component an **agent** only if it genuinely reasons, uses tools, loops, and self-corrects. Components that must be trustworthy stay **deterministic** — a purely "agentic" pipeline cannot be inspection-grade.

```
┌───────────────────────────────────────────────────────────────┐
│  COMPLIANCE CO-PILOT AGENT   (orchestrator, human-in-the-loop)  │
│  takes a goal, plans sub-tasks, calls agents/tools, brings HIL  │
└───────────────┬───────────────────────────────┬───────────────┘
   plans & calls │                               │
┌───────────────▼───────────────┐   ┌────────────▼───────────────┐
│  AGENT LAYER (cognition)       │   │  INSPECTOR AGENT (red-team) │
│  • Extraction Agent            │   │  plans a thematic inspection│
│  • Cross-Reference Agent       │   │  reasons over gaps, drafts  │
│  • Applicability Agent         │   │  a SEBI-style Finding Report│
│  • Control & Evidence Agent    │   └────────────┬───────────────┘
└───────────────┬────────────────┘                │
  writes ONLY   │ verified, cited proposals        │
┌───────────────▼─────────────────────────────────▼─────────────┐
│  VERIFICATION KERNEL (deterministic — the trust layer)         │
│  • Citation-fidelity gate    • Version DIFF engine             │
│  • Coverage Certificate      • Gap ledger + Obligation Tests   │
│  • Bitemporal Obligation Register (canonical + firm overlay)   │
│  • Hash-chained audit log                                      │
└────────────────────────────────────────────────────────────────┘
```

**Two-layer data model (locked):**
- **Canonical Regulatory Layer** — each SEBI obligation extracted & verified **once**, shared across all firms, identified by **circular number + content hash**. Any user can add a document; if public it enriches this shared layer, if firm-specific it stays private. Consistent interpretation for everyone.
- **Firm Overlay** — each firm's private controls, evidence, interpretation notes, layered on top of the canonical obligations.

**Pitch line:** *"Agents do the reasoning; a deterministic verification kernel guarantees nothing enters the compliance record without a real citation and human sign-off."*

---

## 4. The three flows

### Flow A — Onboarding (once per intermediary)
1. Ingest the **current** Master Circular into the **canonical layer** (reuse if the circular number/hash already exists; otherwise extract → build the shared, cited, versioned obligations). Produce a **Coverage Certificate**.
2. Register the firm and create its **overlay**; import the firm's **existing controls/evidence** and link them to canonical obligations.
3. Codify the crisp/quantitative obligations into **Obligation Tests**.
> The canonical layer is the shared regulatory truth; the overlay is the firm's private compliance state.

### Flow B — Change Management (recurring — the core idea)
```
SEBI publishes new/amended doc
  → identify by circular number + content hash (already have it? reuse : process)
  → Extraction Agent extracts obligations (structured + cited) + Coverage Certificate
  → DIFF engine compares on the CANONICAL layer (regulation vs regulation)
  → OPERATIONAL-IMPACT analysis on the firm's OVERLAY:
        "which of THIS firm's controls / evidence / tests are affected"
  → HIL: compliance officer reviews each change, source clause shown side-by-side
  → on approval → emit a cited CHANGE REQUEST (what to update + why + citation)
        the firm applies it in their own systems and marks it done  (no direct write-back)
  → cascade: adjust controls, mark evidence "needs re-attestation", update Obligation Tests
  → audit log records who approved what, when, why (bitemporal)
```

### Flow C — Ongoing Compliance & Inspection
1. Continuously map obligations → controls → **evidence of fulfilment**.
2. **Obligation Tests** run against incoming evidence: green = satisfied, red = gap (live dashboard). Best-judgment rules stay human-reviewed checklist items.
3. **Gap detector** (deterministic) classifies each gap: missing / stale / weak / contradictory + severity.
4. **Inspector Agent** runs a thematic self-assessment → draft Finding Report with citations + severity → *catches gaps before they become regulatory findings.*
5. **Point-in-time query:** reconstruct "what was required and what evidence existed as of date X" in one query (bitemporal).
6. Remediation tracked to closure; everything in the audit trail.

All three flows read/write the **same** bitemporal register and the **same** audit log.

---

## 5. Agents (genuine — LangGraph)

| Agent | Job | Key tools | Self-correction |
|---|---|---|---|
| **Extraction Agent** | Parse clause → propose structured obligation with exact source span | doc parser, retrieval | Re-reads cited span; drops claim if span doesn't support it |
| **Cross-Reference Agent** | Resolve "para 3.2 / Reg 74(5) / circular X" to real targets | register lookup, retrieval | Verifies target exists before linking |
| **Applicability Agent** | Decide which category/tier an obligation binds (incl. QSB / DP multi-hop) | intermediary profile, tier rules | Flags ambiguous scope to HIL |
| **Control & Evidence Agent** | Propose the operational control + what evidence proves it | control library | Proposes only; human promotes |
| **Inspector Agent** | Plan + run thematic self-inspection; draft Finding Report | KB queries, gap ledger, past-order patterns | Every finding must cite a real obligation |
| **Compliance Co-Pilot** | Top-level orchestrator; NL goal → plan → tool calls → HIL | all of the above | Escalates on low confidence |

**Modality rule:** obligations are classified `shall` (hard) / `may` (discretion) / `best-judgment` (uncodifiable → always human-attested, never auto-applied).

---

## 6. Verification Kernel (deterministic — NOT agents)

| Component | Why deterministic |
|---|---|
| **Citation-fidelity gate** | Every obligation's text must be grounded in its cited span, or it's rejected/flagged. Target ≥ 0.95. |
| **Coverage Certificate** | Sweeps every obligation-signal phrase ("shall / must / required to / no person shall") and accounts for each: extracted / marked-not-applicable-with-reason / unaccounted. Provable completeness — a chatbot cannot offer this. |
| **Version DIFF engine** | Structural obligation-level comparison between two canonical versions. Exact, repeatable, near-zero hallucination. Highest-utility feature. |
| **Obligation Tests** | Crisp/quantitative obligations compiled into executable checks that run against evidence (compliance-as-CI). Green/red, deterministic. |
| **Gap ledger** | Rule-based classification of obligation vs evidence (missing/stale/weak/contradictory). Reproducible → inspection-grade. |
| **Bitemporal Obligation Register** | Canonical + firm overlay, tracking valid-time (rule in force) and transaction-time (when recorded). Enables point-in-time reconstruction. The product's actual asset. |
| **Hash-chained audit log** | Append-only, `hash = SHA256(prev + payload + ts)`. Tamper-evident. |

---

## 7. Data model (the actual product)

Two layers. Bitemporal on both time axes: `valid_from/valid_to` (rule in force) and `recorded_at` (when we knew it).

**CANONICAL LAYER (shared across all firms)**
```
Document   { id, circular_number, content_hash, title, issue_date, category, source_url, is_public }
Obligation {
  id, source_document_id, clause_path, verbatim_text,
  normalized_statement, modality (shall|may|best_judgment),
  trigger_condition, deadline_or_periodicity, threshold,
  applies_to [{category, tier}], version,
  valid_from, valid_to, recorded_at,          # bitemporal
  citation {page, char_start, char_end, source_hash}
}
ObligationTest { id, obligation_id, spec, evaluator }     # codified crisp obligations
CoverageReport { document_id, signals_total, extracted, not_applicable[{span,reason}], unaccounted }
ChangeEvent    { obligation_id, type (added|amended|removed), old_version, new_version }   # canonical diff
```

**FIRM OVERLAY (private, per tenant)**
```
Firm      { id, name, category, tier }                    # incl. the synthetic test broker
Control   { id, firm_id, obligation_ids[], description, type, owner_role, frequency }
Evidence  { id, firm_id, control_id, artifact_ref, captured_at, source_system, hash,
            valid_from, valid_to, recorded_at }            # bitemporal
Gap       { firm_id, obligation_id, reason (missing|stale|weak|contradictory), severity }  # computed
ChangeRequest { id, firm_id, change_event_id, affected_controls[], affected_evidence[],
                affected_tests[], operational_action_text, citation, status, approved_by, approved_at }
Interpretation { id, firm_id, obligation_id, note, sources[] }   # firm annotations
AuditEntry { firm_id, actor, action, before_hash, after_hash, ts, chain_hash }
```

The **Obligation Register** (auto-extracted, versioned, bitemporal, deterministically diffed, evidence-linked) is the asset no incumbent (TeamLease, Complinity, eQomply) has — theirs are human-entered flat lists.

---

## 8. Real-document handling (this is where the hard engineering is)

Real SEBI master circulars are not clean prose. The architecture must handle:

| Real-doc challenge | Handling |
|---|---|
| Consolidation of dozens of circulars | Structure tree: Chapter → Section → Clause → Sub-clause |
| Dense cross-references | Cross-Reference Agent resolves to real targets |
| Obligations in tables / annexures / formats | Table extraction + annexure parsing |
| Versioning / supersession (May→Aug→Dec 2024) | Version DIFF engine; register is versioned |
| Mixed modality incl. "best-judgment" | Modality classifier → uncodifiable ones go to human |
| Scanned pages / images | OCR fallback (PaddleOCR) |

---

## 9. Tech stack (locked)

| Layer | Choice | Note |
|---|---|---|
| Frontend | **Next.js on Vercel** | Compliance officer workbench |
| Backend API | **FastAPI on Render (Web Service)** | REST/streaming API |
| Agent + workflow runners | **Render Background Workers** | Persistent workers for LangGraph + Temporal (not on serverless) |
| Agent orchestration | **LangGraph** | Graph control flow fits the workflow |
| LLM inference | **Groq** (Llama 3.3 70B / best available) | Fast + cheap; the verification kernel compensates for open-model accuracy |
| Doc parsing | PyMuPDF (born-digital) + PaddleOCR (scanned) + table extractor | |
| Register + vector | **PostgreSQL + pgvector** (Neon or Supabase) | Structured + vector + relational in one DB |
| Embeddings | bge-m3 / bge-large (open) or hosted embedding API | Hybrid search (BM25 + vector) |
| Long-running workflows | Temporal (Temporal Cloud or self-hosted) | Multi-day remediation/change workflows |
| Audit | Hash-chained append-only table in Postgres + object storage (WORM) | Tamper-evident |
| Model access | LiteLLM abstraction over Groq | Keeps LLM swappable |

> **Note on accuracy:** because Groq serves open models (higher legal-text hallucination than Claude/GPT), the deterministic **verification kernel** — citation-fidelity gate, coverage certificate, deterministic diff, obligation tests — is what makes fast/cheap inference safe for compliance. The kernel, not the model, is the source of trust.
> **Note on residency:** Vercel/Render/Groq are non-India regions; acceptable for the build. A production SEBI deployment would need India-region hosting + India-served inference for DPDP — flagged for later, not now.

---

## 10. Ideas carried in from research.md

- **Master Circular Diff Engine** (research Idea 4) — the centerpiece; drives the change-management flow.
- **Obligation → Control → Evidence → Gap → Remediation loop** (Idea 1, SEBI Compliance Grid) — completes Challenge 2.
- **Inspector Agent** (Idea 2) — the differentiator; catches gaps "before they become regulatory findings."
- **Regulation-as-Code / SEBIRuleDSL** (Idea 3) — applied to the crisp/quantitative subset of obligations.
- **Compliance Knowledge Base**, tiered obligations (QSB vs non-QSB), citation enforcement, self-verification, tamper-evident audit trail.

---

## 11. Proving it works on the real document

Since the bar is "run it on real SEBI documents," measurement is built in:
- **Ground-truth set:** hand-annotate ~50–100 clauses of the real Master Circular → measure extraction **precision / recall**.
- **Citation fidelity:** ≥ 0.95 — every obligation's cited span must support it.
- **Coverage report:** list every "shall / must / required to" sentence the system did **not** capture, so a human can confirm nothing critical was missed.
- **Diff correctness:** run against two real successive versions of the Master Circular; verify the changelog by hand.

---

## 12. Decisions

### Locked
1. **Two-layer model** — shared Canonical Regulatory Layer + private Firm Overlay; documents identified by circular number + content hash; users can add any SEBI document.
2. **Bitemporal register** — point-in-time reconstruction ("were you compliant as of date X").
3. **Change Request model** — no direct write-back; system emits a cited action ticket the firm applies and we track to closure.
4. **Operational-impact deltas** — changes expressed as impact on the firm's controls/evidence/tests, not just text diffs.
5. **Coverage Certificate** — provable completeness over every obligation-signal phrase.
6. **Compliance-as-tests** — crisp obligations become continuously-running Obligation Tests; best-judgment rules stay human-reviewed.
7. **Integrity principle** — real SEBI documents, no hardcoded outputs; a synthetic-but-honest test broker is the tenant.
8. **Tech stack** — Vercel (frontend) + Render (backend/workers) + LangGraph (agents) + Groq (LLM) + Postgres/pgvector (Neon/Supabase) + Temporal.

### Locked (continued)
9. **Category-agnostic & document-agnostic** — handles any SEBI intermediary category and any SEBI document; nothing hardcoded. Applicability is data (`applies_to[{category, tier}]`), not code.
10. **Validation approach** — engine is general; proven on real documents starting with SEBI's suggested baseline (Stock Brokers + Investment Advisers master circulars). The demonstrated concrete scenario emerges from real extracted obligations.
11. **Build order** — all three flows (Onboarding, Change Management, Ongoing Compliance & Inspection) built together.
```
