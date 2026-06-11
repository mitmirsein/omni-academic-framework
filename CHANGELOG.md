# Changelog

All notable changes to this project are documented here.

This project uses pragmatic version notes rather than a strict release calendar. Dates are written in ISO format.

## [Unreleased]

### Added

- Added a self-correcting retry loop to `OntologyExtractor` (same pattern as draft/review): grounding violations are fed back as a CORRECTION block before the formal `AuditGate` runs; `llm_usage.ontology_attempts` is recorded in the manifest.
- Added `CoverageAuditor` ("token-ratio defense"): every ontology/draft/LLM-analyze run now writes `coverage.json` with paragraph/tail coverage and token ratio, mirrored into the manifest and `report.md`; lenses may define `coverage_thresholds` to surface warning findings. Diagnostic only — it never blocks a run.
- Added review source provenance (chain of custody): `--module review` now verifies the source run manifest and blocks drafts that did not pass their compliance audit (`blocked_by_source_audit`); review manifests record `source_run_id`, `source_draft_passed`, `source_mock`, and `source_provenance`.
- Added `omni_academic/text/grounding.py` as the single quote-grounding policy (NFKC + curly-quote/soft-hyphen normalization + whitespace collapse, case-preserving) shared by every gate and retry verifier.
- Added `QUOTE_NORMALIZED_MATCH` info findings so quotes rescued by normalization stay traceable.
- Added `SCHEMAS.md` to document artifact contracts for downstream consumers.
- Added golden fixture tests for ontology, audit, draft, review, failure, manifest, and status contracts.
- Added `--show-run` next-step guidance for blocked and failed run statuses.
- Added regression coverage for reserved provider boundaries.

### Changed

- `AnthropicProvider` now hard-fails when a response is truncated at the `max_tokens` budget (`stop_reason=max_tokens`), instead of silently passing a partially lost structured output downstream; the error points to `OMNI_LLM_MAX_TOKENS`.
- Unified quote matching across `AuditGate`, `DraftComplianceAuditor`, `LensComplianceAuditor`, `ScribeAgent`, `LensAnalyzer`, and `PeerReviewPanel`: non-destructive variants (NBSP, curly quotes, line-break collapse) now match everywhere, while case differences are no longer forgiven by the ontology gate.
- Clarified provider boundaries in setup/status output, `.env.example`, and provider placeholder errors.
- Centralized the current supported/reserved LLM provider contract in code-level constants.
- Split setup questions and diagnostics rows into small typed helpers for easier maintenance.

## [0.6.0] - 2026-05-24

### Added

- Added the peer review module (`--module review`) with four reviewer personas and Chief Editor synthesis.
- Added deterministic grounding validation for peer review `source_quotes`.
- Added review panel configuration through `lenses/review_panel.yaml`.
- Added draft generation (`--module draft`) with a source-bound claims ledger and `DraftComplianceAuditor`.
- Added run integrity metadata through `artifact_manifest` and `--verify-run`.
- Added CI smoke coverage for mock ontology generation and artifact verification.

### Changed

- Simplified `README.md`, `README.en.md`, and `USER_GUIDE.md` for use as an independent public project.
- Added `ARCHITECTURE.md` to keep design details out of the quickstart README.
- Added `RELEASE_NOTES.md` as a ready-to-use v0.6.0 release summary.
- Updated package metadata description to emphasize source-grounded academic text processing.
- Standardized review panel configuration as `panelists` plus `chief_editor`.
- Clarified that `OPENAI_API_KEY` and `GEMINI_API_KEY` are not required for the default live path.

### Fixed

- Prevented ontology audit failures from being reported as `completed`.
- Prevented draft generation when ontology audit fails.
- Prevented peer review grounding failures from being promoted to `review.json` or `review.md`.
- Added terminal statuses for blocked gate paths:
  - `blocked_by_audit`
  - `blocked_by_draft_audit`
  - `blocked_by_review_grounding`
  - `review_rejected`
- Fixed run resolution for direct relative paths such as `runs/<slug>/<timestamp>`.

### Verified

- `uv run ruff check`
- `uv run python -m pytest -q` (`121 passed, 2 skipped`)
- Mock CLI smoke for draft, review, and `--verify-run`
