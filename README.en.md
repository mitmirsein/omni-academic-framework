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
> - **Implemented**: Recon (arXiv, DBLP, Crossref, EconBiz, PubMed, OpenAlex, Semantic Scholar, and SerpAPI-based Google Scholar live API clients; KCI 3-path: keyless OAI-PMH harvest / Open API / verified POST web search; EconBiz=Econ, PubMed=Medical, OpenAlex+DBLP across lenses), config-driven lens registry, Paragraph-ID assignment, AuditGate paragraph grounding, Gate 2 ForensicAuditor (DOI validation + live ping, URL liveness), Gate 3 LensComplianceAuditor MVP, AnthropicProvider (tool-use + prompt caching), LightpandaScraper (subprocess browser; `OMNI_LIGHTPANDA_BIN` or PATH), unified tool resolver, E2E HITL-Scraper-Ontology-Audit pipeline, RunStore persistence (`runs/<id>/` typed JSON + self-attesting manifest), PdfExtractorScraper (pypdf/pdftotext), ReconCache (.cache/recon.sqlite with 24h TTL), Snowball (OpenAlex citation network recon), **Drafting module** (`--module draft`: ScribeAgent + DraftComplianceAuditor with a source-bound claims ledger), **aporia-preserving `in_tension_with` predicate**, packaged as `omni_academic` for clean `uv tool install`. **System Diagnostics & Auto-Setup Dashboard (auto-generates `.env` and checks key/binary liveness)**.
> - **`[BLUEPRINT]` (Unimplemented)**: Gate 3 Schema/Lens self-redteaming (LLM-based), stealth browser-dependent runners in `skills/`.
> - **Prerequisites**: Post-cloning, run **`uv run omni --setup`** in your terminal to launch the interactive setup wizard, which helps you bootstrap and configure API Keys and local paths in your `.env` file easily. Live extraction requires configured API Keys. `skills/*` runners require optional extras.

## 1. Philosophy & Core Values

Rather than linearly 'reading' papers, this framework is designed to deconstruct and dominate research papers as a multi-dimensional information network.

1. **Ontology-First**: Before analyzing text, we map the terrain (Entity-Relation) to fundamentally prevent LLM hallucinations.
2. **Ruthless Audit System**: Mechanical cross-referencing and validation are prioritized over fluent generation. This is the cornerstone of the framework.
3. **Fidelity to Aporia**: We do NOT flatten or resolve irreducible paradoxes or logical tensions in the source text. Opposing poles are preserved as separate nodes and connected via the `in_tension_with` predicate (distinct from `conflicts_with`, which implies one defeats the other). Domain-specific emphasis (e.g., *vere Deus / vere homo* in Christology) is injected via the lens adapter (`lenses/theology.yaml`) rather than the core, keeping the core engine domain-neutral.

## 2. On-Demand Architecture (Simple & Soft)

We discard heavy and fragile 'waterfall' pipelines. The single entrypoint, **Supervisor**, dynamically selects and invokes modules as independent lego blocks based on demand, keeping the codebase extremely simple.

### 🧩 Independent Tool Pool
1. **`Recon Engine`**: Quickly fetches metadata and APIs without full-text parsing to report digests (lightweight reconnaissance).
2. **`Ontology Extractor`**: Extracts the core knowledge network (Entity-Relation) as JSON. Irreducible paradoxes are preserved via the `in_tension_with` predicate (no flattening).
3. **`Lens Analyzers` (`Epistemic`, etc.)**: Receives both the ontology map and the original text to target specific segments.
4. **`Scribe Agent` (Drafting)**: Receives the ontology map and paragraph grounding to generate section-by-section drafts. It blocks hallucinations via a structured claims ledger that ties every factual claim to an existing paragraph and a verbatim quote.

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
* **Gate 3: Lens Compliance Audit (Lens)** — `[MVP Implemented]` `LensComplianceAuditor`: Evaluates whether the LLM lens analysis is properly grounded in paragraph IDs, direct quotes, and focus area coverage. Optional LLM self-redteaming is executed via `--llm-critic` (storing `lens_critic.json/md`).
* **Draft Compliance Audit (Draft)** — `[Implemented]` `DraftComplianceAuditor`: Deterministically verifies that all claims in the generated draft are bound to existing paragraphs, verbatim quotes, and matching `[C#]` anchors in the prose, and that unresolved tensions are preserved in `open_tensions`.

## 4. Milestones

- [x] **Step 1: Supervisor & Ontology Core**
  - Prompt engineering for the entrypoint and establishing the `Ontology Extractor` flow.
- [x] **Step 2: Sub-Nodes Tooling & Multi-Client Integration**
  - Deconstructing analyzers into callable tool schemas and integrating Google Scholar/Semantic Scholar clients.
- [x] **Step 3: Domain Lenses Setup**
  - Defining CS, Medical, and Theological schemas in the `lenses/` registry.
- [x] **Step 4: Integrated End-to-End Stress Test**
  - Testing the complete flow: Extraction ➔ Domain Analysis ➔ 3-Layered Audit.
- [x] **Step 5a: Gate 3 Lens Compliance Audit MVP**
  - Automatically checking that the `--llm-analysis` output is grounded to the source document's paragraph IDs and direct quotes.
- [x] **Step 5b: Gate 3 LLM Self-Redteaming Critic**
  - Criticizing the analysis output via a separate red-team pass and auditing the critic's own quotes.
- [ ] **Step 5c: Critic-Based Auto-Correction Loop `[BLUEPRINT]`**
  - Implementing a bounded retry loop that feeds back critic findings into correction prompts.
- [x] **Step 6: Drafting Module (Drafting)**
  - Supporting the `--module draft` mode with `ScribeAgent` and `DraftComplianceAuditor` (introducing a source-bound claims ledger).
- [x] **Step 7: Aporia-Preserving Predicate**
  - Supporting the `in_tension_with` predicate and ontology directives to preserve irreducible paradoxes without flattening.
- [x] **Step 8: Portable Clean Packaging**
  - Packaging the framework as `omni_academic` to support clean global installations via `uv tool install` (untangled from local personal vaults/scripts).

## 🔧 Installation

**Global Installation** (no clone required, registers `omni` as a global command in an isolated environment):

```bash
uv tool install git+https://github.com/mitmirsein/omni-academic-framework.git
omni --status        # Diagnostics & Setup
omni --list-lenses   # View bundled lenses (runs from any directory)
```

The default lenses (`cs`, `medical`, `theology`, etc.) are bundled inside the package and resolved automatically. If you want to use your own custom lenses directory, set the `$OMNI_LENS_DIR` environment variable or use the `--lens-dir` option.

**Development Mode** (clone and run):

```bash
git clone https://github.com/mitmirsein/omni-academic-framework.git
cd omni-academic-framework
uv run omni --setup   # Interactive .env setup
uv run omni "your query" --lens cs
```

---

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
| **`ACADEMIC_VAULT_PATH`** | Absolute path to local knowledge vault root | Optional (for exporting verified outputs) | User-defined local vault root path |

---
*Omni-Academic Framework | Portable Local Research Standard*
