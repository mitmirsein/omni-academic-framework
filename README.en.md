# Omni-Academic Framework

A source-grounded academic text processing pipeline. It can run literature reconnaissance, full-text acquisition, paragraph ID assignment, ontology extraction, audit, draft generation, and peer review as independent modules. Outputs are persisted under `runs/` as JSON/Markdown artifacts.

Current version: prototype `0.6.0`. The core rule is simple: generated claims and reviews must be grounded in source paragraphs and verbatim quotes. If grounding fails, the run is blocked instead of being reported as completed.

## What It Does

- Collects academic candidates through lens-specific clients.
- Assigns stable paragraph IDs such as `P_0001`.
- Generates ontology, draft, and review artifacts with an LLM or mock provider.
- Validates outputs through `AuditGate`, `DraftComplianceAuditor`, and peer-review grounding checks.
- Stores provenance in `manifest.json`, `report.md`, typed JSON artifacts, and `runs/index.db`.

## Install

Install as a global tool:

```bash
uv tool install git+https://github.com/mitmirsein/omni-academic-framework.git
omni --status
omni --list-lenses
```

Run from a development checkout:

```bash
git clone https://github.com/mitmirsein/omni-academic-framework.git
cd omni-academic-framework
uv run omni --status
```

Live LLM runs require the Anthropic extra and an API key:

```bash
uv run --extra llm omni --setup
```

## Quickstart

Run the ontology pipeline on the bundled fixture without API keys:

```bash
uv run omni ./examples/sample.md --module ontology --lens general --mock
```

Generate a draft:

```bash
uv run omni ./examples/sample.md --module draft --lens general --mock
```

Review the generated draft run:

```bash
uv run omni runs/examples-sample-md/latest --module review --lens general --mock
```

Verify artifact integrity:

```bash
uv run omni --verify-run examples-sample-md/latest
```

## Common Commands

| Command | Purpose |
|---|---|
| `omni --status` | Check keys and local tools |
| `omni --setup` | Configure `.env` interactively |
| `omni --list-lenses` | Show available lenses |
| `omni <query> --lens theology` | Run literature reconnaissance |
| `omni ./paper.md --module ontology --mock` | Build and audit an ontology |
| `omni ./paper.md --module analyze --llm-analysis` | Build source-bound lens analysis |
| `omni ./paper.md --module draft` | Generate a grounded draft |
| `omni <draft-run> --module review` | Peer-review a draft |
| `omni --show-run <run>` | Summarize a saved run |
| `omni --verify-run <run>` | Verify artifact hashes |

## Modules

| Module | Output |
|---|---|
| `recon` | `digest.json`, optional `fulltext.md`, `ontology.json`, `audit.json` |
| `ontology` | `paragraphs.json`, `ontology.json`, `audit.json` |
| `analyze` | `lens_brief.md`, optional `lens_analysis.json/md`, `lens_audit.json` |
| `draft` | `draft.json`, `draft.md`, `draft_audit.json` |
| `review` | `review.json`, `review.md` when grounding passes |

## Gate Status

Runs are not marked `completed` unless the required gate for that path passes. Important terminal statuses include:

- `completed`
- `blocked_by_audit`
- `blocked_by_draft_audit`
- `blocked_by_review_grounding`
- `blocked_by_source_audit`
- `review_rejected`
- `analysis_failed`
- `scraping_failed`

Peer-review grounding failure writes `failure.json` and does not promote the failed report to `review.json` or `review.md`.

## Configuration

Most users only need:

| Variable | When Needed |
|---|---|
| `ANTHROPIC_API_KEY` | Live LLM ontology/analyze/draft/review |
| `SERPAPI_API_KEY` | Google Scholar search through SerpAPI |
| `SEMANTIC_SCHOLAR_API_KEY` | Higher Semantic Scholar rate limits |
| `OMNI_LIGHTPANDA_BIN` | Local browser scraping fallback |
| `OMNI_PDF_EXTRACTOR` | External PDF text extraction |
| `OMNI_LENS_DIR` | Custom lens directory |

`OPENAI_API_KEY` and `GEMINI_API_KEY` are reserved for future/alternate providers and are not required for the default live path.

## Documentation

- [USER_GUIDE.md](./USER_GUIDE.md): practical usage guide
- [ARCHITECTURE.md](./ARCHITECTURE.md): module and gate design
- [SCHEMAS.md](./SCHEMAS.md): JSON/Markdown artifact contracts
- [CHANGELOG.md](./CHANGELOG.md): versioned change notes
- [RELEASE_NOTES.md](./RELEASE_NOTES.md): latest release summary
- [lenses/](./lenses): bundled domain lenses
- [examples/](./examples): sample input files

## Development

```bash
uv run ruff check
uv run python -m pytest -q
```

GitHub Actions runs the same basic quality gate: lint, offline tests, CLI ontology smoke, artifact verification, and byte-compile.

Local runtime outputs are ignored by git: `.env`, `.cache/`, `.venv/`, `runs/`, `handoff/`, `scratch/`, `.pytest_cache/`, `__pycache__/`.
