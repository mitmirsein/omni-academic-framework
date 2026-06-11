# Release Notes

## v0.7.0 - Fidelity Chain Completion and Quality Hardening

This release implements all 14 findings of `QUALITY_IMPROVEMENT_PLAN.md` across three phases: the grounding policy is now uniform, the gate chain has no provenance gaps, the constitution's token-ratio defense and dynamic-glossary mechanisms exist in code, and robustness/observability gaps found by review are closed.

### Highlights

- **Unified quote grounding** (`text/grounding.py`): one normalization policy (NFKC, curly-quote/soft-hyphen folding, whitespace collapse, case-preserving) shared by every gate and retry verifier; normalization-rescued matches are traceable as `QUOTE_NORMALIZED_MATCH`.
- **Chain of custody for reviews**: `--module review` verifies the source run manifest; drafts that failed their compliance audit are blocked with `blocked_by_source_audit`, and `source_run_id`/`source_mock`/`source_provenance` are recorded.
- **Token-ratio defense** (`coverage.json`): paragraph/tail coverage and token ratio for every ontology/draft/LLM-analyze run, with optional lens-injected warning thresholds.
- **Truncation hard fail**: `max_tokens`-cut LLM responses raise instead of silently losing content; `OMNI_LLM_MODEL`/`OMNI_LLM_MAX_TOKENS` tune the live provider.
- **Self-correcting ontology extraction** and oversized-paragraph subdivision keep verification power on PDF-style inputs.
- **Forensic verdict matrix**: only 404/410 prove a ghost citation; bot-blocked (403/429) DOIs become `UNVERIFIABLE_*` warnings instead of false positives.
- **`--independent-panel`**: isolated per-panelist review calls plus Chief Editor synthesis (opt-in, ~5x cost).
- **`--glossary`** (constitution §4 MVP): source-bound dynamic glossary, deterministically audited, injected only when it passes (fail-closed).
- **Recon clients package**: nine search adapters split into `recon/clients/` behind the `CLIENT_FACTORY` registry; import paths unchanged.
- **Observability**: per-call LLM `usage_log` with token totals in manifests; lens YAML schema validation with a `--list-lenses` Validation column; CI coverage report (73%).

### Verification

```bash
uv run ruff check
uv run python -m pytest -q --cov=omni_academic
```

Result: `243 passed` with dev+scholar-browser extras (`223 passed, 2 skipped` without the parser extra), coverage 73%. Mock CLI smoke verified for `--module draft --glossary`, `--module review --independent-panel`, and `--verify-run`.

### Upgrade Notes

- New terminal status: `blocked_by_source_audit`. Consumers should keep treating any non-`completed` status as not passed.
- New optional manifest fields: `review_mode`, `source_*`, `paragraph_coverage`/`tail_coverage`/`token_ratio`, `glossary_audit_passed`, and per-step `llm_usage` call logs.
- Lens YAML files with type-violating known fields now fail loudly (`LensConfigError`); unknown keys are warnings only.
- The ontology gate no longer forgives case differences in quotes (the old lowercase comparison was overly lenient).
- `from omni_academic.recon.engine import <Client>` still works; new code should import from `omni_academic.recon.clients`.

## v0.6.0 - Source-Grounded Draft and Review Gates

This release makes the framework stricter about what counts as a successful run. Ontology, draft, and peer-review outputs now fail closed when their grounding checks fail.

### Highlights

- Added `--module draft` for source-grounded draft generation.
- Added `--module review` for panel-based peer review of generated drafts.
- Added hard grounding validation for peer-review quotes.
- Added explicit blocked statuses for failed gates.
- Added CI smoke coverage for mock ontology generation and artifact verification.
- Simplified the public documentation for standalone project use.
- Added architecture and changelog documents.

### Gate Semantics

Runs are no longer marked `completed` just because a module returned. Completion now depends on the relevant gate:

- Ontology audit failure -> `blocked_by_audit`
- Draft compliance failure -> `blocked_by_draft_audit`
- Peer-review quote grounding failure -> `blocked_by_review_grounding`
- Chief Editor reject decision -> `review_rejected`

Peer-review grounding failures write `failure.json` and do not produce `review.json` or `review.md`.

### Documentation

The documentation set is now split by purpose:

- `README.md`: short project entrypoint
- `README.en.md`: English README
- `USER_GUIDE.md`: practical command guide
- `ARCHITECTURE.md`: module and gate design
- `CHANGELOG.md`: versioned change list
- `RELEASE_NOTES.md`: release summary

### Verification

Verified locally:

```bash
uv run ruff check
uv run python -m pytest -q
```

Result:

```text
121 passed, 2 skipped
```

CLI smoke paths were also checked with mock draft, review, and `--verify-run`.

The GitHub Actions CI gate runs lint, offline tests, a mock ontology CLI smoke, artifact verification, and byte-compile.

### Upgrade Notes

- Review panel configuration now uses `panelists` plus `chief_editor`.
- `DevilsAdvocate` was normalized to the display name `Devil's Advocate` with the id `devils_advocate`.
- `OPENAI_API_KEY` and `GEMINI_API_KEY` are not required for the default live path.
- Existing local `runs/` remain local artifacts and are not part of the package.
