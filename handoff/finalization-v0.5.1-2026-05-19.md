---
title: Omni-Academic Framework v0.5.1 Finalization Notes
date: 2026-05-19
owner: Codex
based_on:
  - handoff/peer-review-v0.5.1-2026-05-19.md
verification:
  pytest: "56 passed"
  scholar_browser_extra_self_test: "ok"
  semantic_scholar_extra_import: "ok"
---

# Summary

This pass closes the open P0-P5/F6-F8 issues from the v0.5.1 peer review.

The major change is that the framework now has a stronger mechanical grounding path:

1. Paragraph assignment returns a `paragraph_map` (`P_XXXX -> paragraph text`), not just an ID set.
2. `Node` and `Edge` now carry `source_quote`.
3. `AuditGate` verifies both paragraph ID existence and quote-in-source grounding.
4. `MockProvider` is manifest-aware and emits real paragraph IDs plus verbatim source quotes, so the clone-immediate `--mock` path can pass audit.
5. Gate 2 forensic findings now affect HITL candidates and vault export eligibility.
6. Analyze is explicitly downgraded to a `[BLUEPRINT]` lens spec preview instead of claiming fake analysis completion.
7. Skill runner docs and env handling were moved away from machine-local absolute paths.
8. Project version metadata is aligned to `0.5.1`.

# Implemented

## P0 / F1: Mock E2E

- `MockProvider` parses `[P_XXXX]` blocks from the prompt.
- It emits `paragraph_id` values that actually exist in the annotated source.
- It emits `source_quote` values copied from the source text.
- Added regression test: `test_mock_ontology_path_passes_audit`.

## P1 / F2: Forensic Gate Behavior

- `ForensicAuditor.passed()` and `ForensicAuditor.failed_indices()` added.
- Router records:
  - `forensic_passed`
  - `forensic_blocked_count`
  - `forensic_checked_count`
- Error-level forensic findings block those papers from HITL selection.
- `export_to_vault()` refuses `forensic_passed is False`.

## P2 / F3: Source-Quote Grounding

- `Node.source_quote` added.
- `Edge.source_quote` added.
- `AuditGate` accepts legacy `set[str]` manifests but uses `dict[str, str]` manifests for quote-in-source validation.
- Missing quotes are warnings; quotes not found in source are errors.

## P3 / F4: Analyze Truthfulness

- `LensAnalyzer` is now a `[BLUEPRINT]` lens spec preview.
- Router no longer claims final analysis report generation.

## P4 / F6-F8: Skill Portability

- `s2_runner.py` uses `OMNI_ENV_FILE > repo root .env > default dotenv search`.
- `legacy_researcher.py` no longer embeds `/Users/msn/...`; use:
  - `OMNI_THEOLOGY_DATA_ROOT`
  - `OMNI_THEOLOGY_GLOSSARY`
- Semantic Scholar and Google Scholar skill docs use `uv run --extra ...`.
- `scholar_runner.py --self-test` now reports a clear skipped reason if `beautifulsoup4` is missing instead of crashing.
- KCI is described as adapter scaffold / schema-unverified in README.

## P5: Version Hygiene

- `pyproject.toml`: `0.5.1`
- `uv.lock`: `0.5.1`
- `README.md`: `Prototype (v0.5.1)`

# Verification

```text
uv run python -m pytest
56 passed in 0.66s
```

```text
uv run --extra scholar-browser python skills/google-scholar-semantic/scripts/scholar_runner.py --self-test
self_test: ok
```

```text
uv run --extra semantic-scholar python -c "import requests, dotenv; print('semantic-scholar extra ok')"
semantic-scholar extra ok
```

# Remaining Known Limits

- Gate 3 schema/lens self-redteaming remains `[BLUEPRINT]`.
- Google Scholar browser collection still depends on a non-repo stealth browser module.
- KCI XML parsing is still schema-unverified and should receive a real response fixture before being described as production-grade.
- `skills/omni-translator` still contains vault-specific historical SOP references; this pass focused on Omni core plus semantic/google scholar runners.
