# Architecture

Omni-Academic Framework is built as a set of source-grounded academic processing modules. The modules can be run independently through one CLI entrypoint, and each run writes typed artifacts plus provenance under `runs/`.

The main design goal is not fluent generation. The goal is to keep every generated claim, extracted relation, and peer-review quote mechanically tied to source text.

## Core Principles

### Source Grounding First

Every high-value output should carry a source anchor:

- `paragraph_id`: a stable source paragraph ID such as `P_0001`
- `source_quote`: a verbatim substring from the cited source paragraph

If the quote or paragraph cannot be verified, the relevant gate should block completion.

### Modular, Not Waterfall

The CLI does not force a single full pipeline. A user can run only the module needed:

- `recon`
- `ontology`
- `analyze`
- `draft`
- `review`

Each module writes a standalone run with its own `manifest.json`, `report.md`, and typed artifacts.

### Fail Closed

The framework should not silently promote ungrounded output. Important examples:

- ontology audit failure sets `blocked_by_audit`
- draft compliance failure sets `blocked_by_draft_audit`
- peer-review quote grounding failure sets `blocked_by_review_grounding`
- rejected review sets `review_rejected`

## High-Level Flow

```text
query or file
  |
  |-- recon ---------> digest.json
  |       |
  |       +-- HITL selection -> fulltext.md
  |
  |-- paragraphing --> paragraphs.json
  |
  |-- ontology ------> ontology.json
  |       |
  |       +-- AuditGate -> audit.json
  |
  |-- analyze -------> lens_brief.md
  |       |
  |       +-- optional LLM analysis -> lens_analysis.json/md
  |       +-- LensComplianceAuditor -> lens_audit.json
  |
  |-- draft ---------> draft.json/md
  |       |
  |       +-- DraftComplianceAuditor -> draft_audit.json
  |
  |-- review --------> review.json/md
          |
          +-- review grounding validator
```

## Main Components

### Supervisor Router

File: `omni_academic/supervisor/router.py`

The router is the CLI orchestration layer. It:

- parses user intent into a target module
- creates a `RunStore`
- dispatches to the selected module
- records terminal status
- finalizes the run

The router is also responsible for preventing a failed gate from being overwritten as `completed`.
For saved runs, `--show-run` also maps blocked/failed statuses to file-oriented next steps so users know whether to inspect `audit.json`, `draft_audit.json`, `failure.json`, `review.md`, or `report.md`.

### RunStore

File: `omni_academic/store/run_store.py`

`RunStore` owns artifact persistence. It writes:

- typed JSON artifacts
- Markdown artifacts
- `manifest.json`
- `report.md`
- `runs/index.db`

`manifest.json` includes `artifact_manifest`, which records file existence, byte size, and sha256 for integrity verification.

### Lenses

Directory: `lenses/`

Lenses inject domain-specific configuration without hard-coding domains into core logic. They can define:

- display name
- focus areas
- analysis prompt
- ontology directive
- recon clients

Custom lenses can be supplied with `OMNI_LENS_DIR` or `--lens-dir`.

### LLM Providers

File: `omni_academic/llm/provider.py`

Providers expose one common interface:

```python
generate_structured_output(prompt, schema)
```

Currently supported providers:

- `AnthropicProvider`: default live path for ontology, analysis, draft, and review.
- `MockProvider`: deterministic offline path for tests, smoke runs, and demos.

Reserved provider boundary:

- `OpenAIProvider` is a placeholder for future alternate-provider support and raises `NotImplementedError`.
- There is no Gemini provider implementation yet.
- `OPENAI_API_KEY` and `GEMINI_API_KEY` may appear in local environments, but the default live path ignores them.

## Gate Layers

All quote-grounding comparisons share one policy module, `omni_academic/text/grounding.py`:
NFKC normalization, curly-quote/soft-hyphen folding, and whitespace collapse, with case preserved.
Non-destructive extraction artifacts (NBSP, line breaks) therefore never flip a verdict between
gates, and quotes that only match after normalization are reported as `QUOTE_NORMALIZED_MATCH`
info findings.

### AuditGate

File: `omni_academic/audit/gate.py`

Validates ontology output:

- node paragraph IDs exist
- node source quotes appear in the cited paragraph
- edge endpoints exist
- edge source quotes appear in source text
- self-loops and dangling edges are detected

Failure blocks downstream draft generation.

### LensComplianceAuditor

File: `omni_academic/audit/lens_gate.py`

Validates source-bound LLM analysis and critic output:

- finding paragraph IDs exist
- finding quotes appear in the cited paragraph
- lens focus areas are covered
- limitations are recorded

### DraftComplianceAuditor

File: `omni_academic/audit/draft_gate.py`

Validates generated drafts:

- every claim has a real paragraph ID
- every claim quote appears in source text
- every claim is referenced from prose using `[C#]`
- undeclared claim anchors are detected
- unresolved tensions can be preserved in `open_tensions`

### Peer Review Grounding

File: `omni_academic/analyze/peer_review.py`

Peer-review reports include panelist `source_quotes`. Each quote must appear verbatim in the draft text. If the final retry still fails grounding, the router writes `failure.json` and does not create `review.json` or `review.md`.

The review module also enforces source provenance (chain of custody): when the review input
resolves to a saved run, the source run's `manifest.json` must record `draft_passed=true`,
otherwise the review is blocked with `blocked_by_source_audit`. Standalone `draft.json` file
inputs have no manifest and are recorded as `source_provenance=unverified`.

## Status Semantics

Canonical status values live in `omni_academic/supervisor/run_status.py`.

Important terminal statuses:

| Status | Meaning |
|---|---|
| `completed` | Required gate for the selected path passed |
| `failed` | Unhandled exception |
| `analysis_failed` | Input, lens, or provider failure before completion |
| `blocked_by_audit` | Ontology audit failed |
| `blocked_by_draft_audit` | Draft compliance failed |
| `blocked_by_review_grounding` | Peer-review quote grounding failed |
| `blocked_by_source_audit` | Review source draft run did not pass its draft audit |
| `review_rejected` | Review completed, but Chief Editor rejected |
| `no_papers_found` | Recon returned no candidates |
| `cancelled_by_user` | User stopped at HITL selection |
| `scraper_detection_failed` | No scraper could be selected |
| `scraping_failed` | Scraper produced no Markdown |

## Artifact Contract

Every finalized run should include:

- `manifest.json`
- `report.md`
- `artifacts`
- `artifact_manifest`

Module-specific artifacts are optional and depend on the selected module and gate outcome.

Use:

```bash
uv run omni --verify-run <run>
```

to verify artifact integrity against the manifest.

For field-level JSON/Markdown contracts, see [SCHEMAS.md](./SCHEMAS.md).

## Testing Strategy

Tests prefer deterministic mock providers and scripted failure cases. Important behaviors covered by tests include:

- ontology audit failure blocks completed status
- draft is skipped after ontology audit failure
- peer review grounding failure cannot produce a passed review artifact
- direct relative run paths such as `runs/<slug>/<timestamp>` resolve correctly
- run artifact manifests detect tampering
- golden fixture JSON artifacts still satisfy the documented schema contracts

Run:

```bash
uv run ruff check
uv run python -m pytest -q
```
