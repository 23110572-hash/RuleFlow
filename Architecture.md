# Agentic Compliance — Architecture Specification

## 1. The Problem We Are Solving
For the SEBI TechSprint 2026 (Theme 2: *Agentic Compliance: From Regulatory Text to Operational Action*), the challenge is to dynamically translate regulatory text into operational compliance workflows. 

When SEBI issues a new regulation, intermediaries have to manually read it, interpret the operational impact, and update their controls. This leads to delays and divergent interpretations. Our goal is to automate this process—from ingesting the raw regulatory text to generating concrete operational change requests for the compliance team.

## 2. Our Approach: The "Agentic" Compliance Engine
I designed this architecture around one central thesis:
> Build a **living, versioned, citation-grounded Compliance Knowledge Base** with a **deterministic verification kernel**. 
> **Agents do the reasoning; the kernel owns the truth; the human compliance officer approves.**

I realized early on that pure LLMs (Agents) are too unpredictable for strict regulatory compliance. They hallucinate. To solve this, I split the system into two distinct halves:
1. **The Agent Layer (Cognition):** Powered by LangGraph and LLMs, these agents read the text, extract obligations, determine applicability, and propose changes.
2. **The Verification Kernel (Trust):** A deterministic, rule-based engine that enforces strict rules. For example, it ensures that every extracted obligation perfectly matches a real citation in the source document. If an agent hallucinated a rule that isn't in the text, the kernel rejects it.

## 3. The Two-Layer Data Model
To prevent divergent interpretations, I built a two-layer data model backed by a bitemporal PostgreSQL database:
- **Canonical Regulatory Layer:** This is the shared, single source of truth. Every SEBI document is parsed and its obligations are extracted here *once*. Everyone sees the exact same regulatory interpretation.
- **Firm Overlay:** This is a private layer for each specific tenant (intermediary). It maps their internal controls, policies, and evidence onto the canonical obligations. 

## 4. How the System Operates (The Three Flows)

### Flow A: Onboarding
When we first set up the system for an intermediary, we feed it their governing SEBI Master Circular. The system extracts all the baseline obligations into the Canonical Layer and produces a **Coverage Certificate** to prove that no sentence containing "shall/must" was missed. We then map the firm's existing evidence to these obligations.

### Flow B: Change Management (Handling New Circulars)
When a new SEBI circular drops, here is exactly what happens:
1. The **Extraction Agent** reads the new PDF and pulls out structured, cited obligations.
2. The **Version DIFF Engine** (part of the deterministic kernel) compares these new obligations against the existing Canonical Layer to find exactly what changed.
3. The system runs an **Operational-Impact Analysis** on the firm's private Overlay to figure out which specific internal controls are broken by this new rule.
4. The system presents the human Compliance Officer with a side-by-side view of the original SEBI text and the proposed operational changes.
5. Once approved, it emits a **Change Request** for the firm to execute.

### Flow C: Ongoing Inspection (The "Red Team")
I also built an **Inspector Agent**. Instead of waiting for a real SEBI audit, this agent continuously scans the firm's mapped evidence against the canonical obligations. If a policy is stale, or if evidence is missing, it flags the gap immediately. It essentially acts as an automated red-team auditor.

## 5. The Tech Stack
I chose this stack to balance rapid development with robust production capability:
- **Frontend:** Next.js / React (deployed on Vercel) - Provides the compliance officer workbench.
- **Backend API:** FastAPI (deployed on Render) - Handles the REST architecture and background threads.
- **Database:** PostgreSQL + pgvector (hosted on Neon) - We need relational data for the bitemporal register and vector storage for similarity search, so Postgres was the perfect all-in-one choice.
- **Agent Orchestration:** LangGraph - Allows us to build complex, looping, self-correcting agent workflows.
- **LLM Inference:** LiteLLM wrapping Groq / OpenRouter - Keeps the underlying AI models completely swappable so we aren't locked into one provider.
- **Document Parsing:** PyMuPDF - To handle the messy reality of raw SEBI PDFs (tables, complex layouts, etc.).

## 6. Proving It Works (The Integrity Principle)
I didn't want this to be a scripted demo. Everything in this platform computes live.
If I upload a real SEBI Master Circular, the system genuinely parses the PDF, calculates the hashes, extracts the text, passes it through the LLM, verifies the citations, and stores it in the database. 

To prove accuracy, I implemented strict metrics:
- **Citation Fidelity:** Every obligation must have a citation score ≥ 0.95 against the raw text.
- **Coverage Reports:** The system explicitly lists every mandatory phrase it *didn't* extract so a human can manually review them.

This architecture ensures that while the AI accelerates the heavy lifting, the final compliance state is deterministic, auditable, and firmly anchored in reality.
