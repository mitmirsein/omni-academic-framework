# Changelog

All notable changes to this project are documented here.

This project uses pragmatic version notes rather than a strict release calendar. Dates are written in ISO format.

## [Unreleased]

### Added

- Added `SCHEMAS.md` to document artifact contracts for downstream consumers.
- Added golden fixture tests for ontology, audit, draft, review, failure, manifest, and status contracts.
- Added `--show-run` next-step guidance for blocked and failed run statuses.
- Added regression coverage for reserved provider boundaries.

### Changed

- Clarified provider boundaries in setup/status output, `.env.example`, and provider placeholder errors.
- Centralized the current supported/reserved LLM provider contract in code-level constants.

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
