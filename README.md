# RuleFlow — Agentic Compliance Platform

> SEBI TechSprint 2026 · Theme 2 — *Agentic Compliance: From Regulatory Text to Operational Action*

## The Problem Statement
SEBI intermediaries (like stockbrokers, investment advisers, AMCs, etc.) struggle to keep up with the constant stream of regulatory changes. Every time SEBI releases a new circular or master circular, compliance teams have to manually read through pages of dense legal text, interpret what it means for their specific operations, figure out what internal controls need to change, and update their compliance checklists. This manual process is slow, prone to human error, and leads to divergent interpretations of the rules. 

We need a system that can take raw regulatory text, understand it, map it to a firm's operational processes, and ensure that they remain compliant without missing any critical obligations.

## What is RuleFlow?
I built RuleFlow to solve this exact problem. RuleFlow is an agentic compliance engine that ingests real SEBI regulatory documents (like PDFs of master circulars), extracts machine-actionable obligations from them, and keeps a firm's compliance state continuously in sync as regulations change. 

My core philosophy when building this was simple:
> **Agents propose. A deterministic Verification Kernel owns the truth. A human approves.**
> Nothing enters the compliance record without (a) a real SEBI citation and (b) a human sign-off.

I wanted to ensure that the AI doesn't just hallucinate compliance rules. Every single obligation extracted by RuleFlow is anchored to an exact citation in the original SEBI document.

## How it works (The Three Flows)
1. **Onboarding:** When a firm starts using RuleFlow, we ingest the current Master Circular for their category (e.g., Stock Brokers). The system extracts all the baseline obligations and creates a "Canonical Regulatory Layer" (the single source of truth). We then map the firm's existing internal controls and evidence to these obligations.
2. **Change Management (The Core Magic):** When SEBI publishes a new or amended circular, RuleFlow ingests it, extracts the new obligations, and runs a structural DIFF against the canonical layer. It then analyzes the *operational impact* on the specific firm—telling the compliance officer exactly which internal controls or evidence requirements are affected. The human reviews it side-by-side with the source text, approves it, and RuleFlow emits a Change Request.
3. **Ongoing Compliance & Inspection:** RuleFlow continuously maps obligations to evidence. It acts like an automated red-team inspector, running deterministic checks to detect gaps (missing evidence, stale policies, etc.) before a real SEBI inspector finds them.

## Integrity Principle
I made sure that everything in this platform is real. There are no hardcoded demo paths. 
- The regulatory documents are real SEBI PDFs.
- The extraction, chunking, gap detection, and coverage numbers are all computed live. 
- While the test firm I use for the demo is a synthetic stockbroker, all the mathematical computations and compliance logic applied to it are 100% genuine.

## Repository Layout
```text
backend/          FastAPI + kernel + agents + ingest + workflows + db
  app/
    kernel/       deterministic verification kernel (the trust layer)
    ingest/       real SEBI document parsing (structure tree, tables, OCR)
    llm/          LiteLLM abstraction over Groq/OpenRouter
    agents/       LangGraph agents (extraction, cross-ref, applicability)
    db/           SQLAlchemy models (bitemporal, two-layer) + Alembic
    schemas/      Pydantic request/response models
    api/          FastAPI routers
frontend/         React + Vite + TypeScript + Tailwind CSS
render.yaml       Render Blueprint for backend deployment
vercel.json       Vercel SPA routing
```


