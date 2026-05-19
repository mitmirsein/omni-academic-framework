---
tags:
  - project
  - architecture
  - ai-agent
  - harness
  - ontology
created: 2026-05-19
status: Draft/V3-Palantir
---

# Omni-Academic Framework Initiative (v3.0 - Palantir Paradigm)

**Omni-Academic Framework** is a Palantir-style academic information-warfare engine designed to bypass the inefficiency of linear reading. It deconstructs research papers, extracts core ontologies (knowledge networks), and validates them via a multi-layered mechanical audit system to rapidly grasp academic insights.

> [!WARNING]
> **Status: Prototype (v0.6.0).** This document outlines the target architecture (vision). Parts of it remain a blueprint.
> - **Implemented**: Recon (arXiv client, Crossref/EconBiz/PubMed/OpenAlex live APIs; KCI adapter scaffold; EconBiz=Econ, PubMed=Medical, OpenAlex=Theology/Humanities lenses), config-driven lens registry, Paragraph-ID assignment, AuditGate paragraph grounding, Gate 2 ForensicAuditor (DOI validation + live ping, URL liveness), AnthropicProvider (tool-use + prompt caching), LightpandaScraper (subprocess browser; `OMNI_LIGHTPANDA_BIN` or PATH), unified tool resolver, E2E HITL-Scraper-Ontology-Audit pipeline, RunStore persistence (`runs/<id>/` typed JSON + self-attesting manifest + SQLite index; optional `--export-vault` export to Obsidian Inbox/Drafts), PdfExtractorScraper (pypdf/pdftotext), ReconCache (.cache/recon.sqlite with 24h TTL), Snowball (OpenAlex citation network recon). **System Diagnostics & Auto-Setup Dashboard (auto-generates `.env` and checks key/binary liveness)**.
> - **`[BLUEPRINT]` (Unimplemented)**: Gate 3 Schema/Lens self-redteaming (LLM-based), stealth browser-dependent runners in `skills/`.
> - **Prerequisites**: Post-cloning, run **`uv run omni --setup`** in your terminal to launch the interactive setup wizard, which helps you bootstrap and configure API Keys and local paths in your `.env` file easily. Live extraction requires configured API Keys. `skills/*` runners require optional extras.

## 1. Philosophy & Core Values

Rather than linearly 'reading' papers, this framework is designed to deconstruct and dominate research papers as a multi-dimensional information network.

1. **Ontology-First**: Before analyzing text, we map the terrain (Entity-Relation) to fundamentally prevent LLM hallucinations.
2. **Ruthless Audit System**: Mechanical cross-referencing and validation are prioritized over fluent generation. This is the cornerstone of the framework.

## 2. On-Demand Architecture (Simple & Soft)

We discard heavy and fragile 'waterfall' pipelines. The single entrypoint, **Supervisor**, dynamically selects and invokes modules as independent lego blocks based on demand, keeping the codebase extremely simple.

### 🧩 Independent Tool Pool
1. **`Recon Engine`**: Quickly fetches metadata and APIs without full-text parsing to report digests (lightweight reconnaissance).
2. **`Ontology Extractor`**: Extracts the core knowledge network (Entity-Relation) as JSON.
3. **`Lens Analyzers` (`Epistemic`, `Translator`, etc.)**: Receives both the ontology map and the original text to target specific segments.

### 🌊 Soft & Progressive Workflow
- **Simple is Best**: If requested to scan a journal issue, the pipeline stops at Recon.
- **Flexible Audit**: We do not force heavy audits on light tasks. Simple tasks bypass heavy gates, reducing operational overhead and token costs.

## 🚀 Built-in Elite Tools Integration `[BLUEPRINT partial]`

The framework integrates web scraping and recon tools natively. (See prerequisites above for optional external extra runner setup).

1. **Recon Phase**:
   - `insane-search`: Scans broad trends and keyword contexts prior to metadata harvesting.
2. **Full-Text Scraping (Post-HITL Approval)**:
   - When a target paper URL is approved by the user via HITL, the original text is scraped.
   - `Jina Reader API`: Instantly parses text/HTML into clean Markdown (`https://r.jina.ai/`).
   - `lightpanda` (Headless Browser): Handles JS-rendered or complex web portals.

## 3. The Multi-Layered Audit Gates

All outputs must pass through three gates before returning (Fail-Fast & Retry):
* **Gate 1: I/O Envelope Audit (Structure)** — `[Partial]` Verifies paragraph grounding (`paragraph_id` matching source text), self-loops, and dangling/orphan nodes. Formula/token ratios are `[BLUEPRINT]`.
* **Gate 2: Forensic Search Audit (Empirical)** — `[Implemented]` `ForensicAuditor`: DOI grammar validation + live HEAD ping to block dead URLs or hallucinated/ghost citations.
* **Gate 3: Schema Compliance Audit (Schema)** — `[BLUEPRINT]` Lens guidelines self-redteaming.

## 4. Milestones

- [ ] **Step 1: Supervisor & Ontology Core**
  - Prompt engineering for the entrypoint and establishing the `Ontology Extractor` flow.
- [ ] **Step 2: Sub-Nodes Tooling**
  - Deconstructing analyzers/translators into callable tool schemas.
- [ ] **Step 3: Domain Lenses Setup**
  - Defining CS, Medical, and Theological schemas in the `lenses/` registry.
- [ ] **Step 4: Integrated End-to-End Stress Test**
  - Testing the complete flow: Extraction ➔ Domain Analysis ➔ 3-Layered Audit.

## 5. API Environment Configuration Guide
This framework relies on several external APIs to parse, enrich, and audit academic literature. You can easily configure them in your terminal via the interactive wizard by running **`uv run omni --setup`**.

| Env Variable Name | Purpose / Usage | Recommended Status | Acquisition & References |
| :--- | :--- | :--- | :--- |
| **`ANTHROPIC_API_KEY`** | Claude models for ontology parsing and lens analysis | **Required (for Live run)** | [Anthropic Console](https://console.anthropic.com/) |
| **`OPENAI_API_KEY`** | ChatGPT models for document processing and rendering | Optional | [OpenAI Platform](https://platform.openai.com/) |
| **`GEMINI_API_KEY`** | Gemini models for multi-dimensional analysis and summarization | Optional | [Google AI Studio](https://aistudio.google.com/) |
| **`SEMANTIC_SCHOLAR_API_KEY`** | High-performance academic search & citation graph retrieval | Optional (falls back to 3s/req rate-limiting) | [Semantic Scholar API](https://www.semanticscholar.org/product/api) |
| **`SERPAPI_API_KEY`** | SerpAPI-based Google Scholar keyword literature search | Optional (falls back to disabling Google Scholar searches) | [SerpAPI](https://serpapi.com/) |
| **`JINA_API_KEY`** | Extracting high-fidelity Markdown from raw web pages or PDF URLs | Optional (falls back to public reader mode) | [Jina Reader API](https://jina.ai/reader/) |
| **`MS_BRAIN_VAULT`** | Absolute path to local Obsidian vault (e.g. `/Users/username/Desktop/MS_Brain.nosync`) | Optional (for automatic Obsidian export) | Your local vault root path |

---
*Omni-Academic Framework | MS_Dev Third Gen Standard*
