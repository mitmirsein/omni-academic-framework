# Release Notes

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
