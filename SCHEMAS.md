# Artifact Schemas

This document describes the stable artifact contracts produced by Omni-Academic Framework runs.

The source of truth is the Pydantic models and `RunStore` implementation in `omni_academic/`. This file is a user-facing contract for reading and integrating the generated JSON/Markdown files.

## Run Layout

Each run is stored under:

```text
runs/<query-slug>/<timestamp>/
```

Mock runs use a `MOCK-` timestamp prefix.

Common files:

| File | Required | Purpose |
|---|---:|---|
| `manifest.json` | yes | Run metadata, status, provenance, artifact hashes |
| `report.md` | yes | Human-readable run summary |
| `failure.json` | no | Diagnostic payload for blocked or failed paths |

Module files are written only when that module reaches the relevant step.

## `manifest.json`

`manifest.json` is the top-level contract for a finalized run.

Stable fields:

| Field | Type | Meaning |
|---|---|---|
| `run_id` | string | `<query-slug>/<timestamp>` |
| `created_at` | string | ISO timestamp in UTC |
| `query` | string | Original query or document path |
| `lens` | string | Lens id used by the run |
| `mock` | boolean | Whether mock provider mode was requested |
| `git_commit` | string or null | Short git commit recorded at run time |
| `status` | string | Terminal run status |
| `audit_passed` | boolean or null | Ontology audit result when available |
| `artifacts` | array[string] | Artifact names written before manifest finalization |
| `artifact_manifest` | object | Integrity data for each artifact |

Common optional fields:

| Field | Type | Written When |
|---|---|---|
| `forensic_passed` | boolean | `--forensic` was used |
| `forensic_blocked_count` | integer | forensic findings blocked candidates |
| `lens_audit_passed` | boolean | `--llm-analysis` generated a lens audit |
| `lens_critic_passed` | boolean | `--llm-critic` generated a critic report |
| `lens_critic_audit_passed` | boolean | critic grounding audit ran |
| `draft_passed` | boolean | draft compliance audit ran |
| `draft_blocked_by_audit` | boolean | draft was skipped after ontology audit failure |
| `review_grounding_passed` | boolean | peer-review grounding validator ran |
| `review_passed` | boolean | review decision was `Accept` or `Major Revision` |
| `review_score` | integer | review final score |
| `source_provenance` | string | review module: `manifest` (source run manifest verified) or `unverified` (standalone draft.json input) |
| `source_run_id` | string | review module: `run_id` of the source draft run |
| `source_draft_passed` | boolean or null | review module: `draft_passed` recorded in the source run manifest |
| `source_mock` | boolean | review module: source draft run was generated with `--mock` |
| `llm_usage` | object | provider/model/usage metadata for LLM-backed steps |
| `error_message` | string | exception or blocked-path diagnostic |
| `has_failure_artifact` | boolean | `failure.json` was written |
| `recon_cache` | object | recon cache provenance |

### `artifact_manifest`

Each key is an artifact filename. Each value has:

| Field | Type | Meaning |
|---|---|---|
| `exists` | boolean | File existed at finalization |
| `bytes` | integer | File size in bytes |
| `sha256` | string or null | SHA-256 hash when file exists |

Use:

```bash
uv run omni --verify-run <run>
```

to recompute and compare these values.

## Status Values

Canonical values are defined in `omni_academic/supervisor/run_status.py`.

| Status | Meaning |
|---|---|
| `running` | Internal in-progress state before finalization |
| `completed` | Required gate for the selected path passed |
| `failed` | Unhandled exception |
| `no_papers_found` | Recon returned no candidates |
| `cancelled_by_user` | User stopped at HITL selection |
| `invalid_choice` | HITL selection did not match a candidate |
| `scraper_detection_failed` | No supported scraper could be selected |
| `scraping_failed` | Scraper returned no Markdown |
| `analysis_failed` | Lens, provider, or input failure before completion |
| `blocked_by_audit` | Ontology audit failed |
| `blocked_by_draft_audit` | Draft compliance audit failed |
| `blocked_by_review_grounding` | Peer-review quote grounding failed |
| `blocked_by_source_audit` | Review source draft run did not pass its draft compliance audit |
| `review_rejected` | Peer review ran but Chief Editor rejected |
| `unknown` | Legacy/default value when no status was recorded |

Consumers should treat any status other than `completed` as not fully passed.

## `paragraphs.json`

Object mapping paragraph IDs to source paragraph text.

Example:

```json
{
  "P_0001": "First paragraph text...",
  "P_0002": "Second paragraph text..."
}
```

Contract:

- Keys use `P_XXXX` format.
- Values are the paragraph strings used by grounding gates.
- `paragraph_id` fields in other artifacts must refer to these keys.

## `ontology.json`

Model: `OntologyMap`

```json
{
  "nodes": [
    {
      "id": "n1",
      "label": "Concept label",
      "entity_class": "Concept",
      "paragraph_id": "P_0001",
      "source_quote": "verbatim source quote"
    }
  ],
  "edges": [
    {
      "source_id": "n1",
      "target_id": "n2",
      "predicate": "builds_on",
      "reasoning": "short relation rationale",
      "source_quote": "verbatim source quote"
    }
  ]
}
```

### `entity_class`

Allowed values:

- `Concept`
- `Actor`
- `Method`
- `Claim/Data`
- `Artifact/System`
- `Context/Setting`
- `Limitation/Gap`

### `predicate`

Allowed values:

- `is_a`
- `part_of`
- `builds_on`
- `is_derived_from`
- `causes`
- `correlates_with`
- `supports`
- `conflicts_with`
- `in_tension_with`
- `addresses`
- `uses_method`

Contract:

- Every node must include a real `paragraph_id`.
- Every node `source_quote` should appear in that paragraph.
- Every edge endpoint should refer to an existing node id.
- Every edge `source_quote` should appear in the source corpus.

## `audit.json`, `draft_audit.json`, `lens_audit.json`

Model: `AuditReport`

```json
{
  "passed": true,
  "score": 100,
  "findings": [],
  "checked_at": "2026-05-24T00:00:00Z"
}
```

### Findings

Model: `AuditFinding`

```json
{
  "severity": "error",
  "code": "UNGROUNDED_QUOTE",
  "message": "Human-readable diagnostic",
  "source_ref": "n1"
}
```

Allowed `severity` values:

- `error`
- `warning`
- `info`

Contract:

- `passed=false` whenever at least one `error` finding is present.
- `score` is a bounded integer from 0 to 100.
- Consumers should prefer `passed` over interpreting `score`.

## `lens_analysis.json`

Model: `LensAnalysisReport`

```json
{
  "lens": "theology",
  "executive_summary": "summary",
  "findings": [
    {
      "focus_area": "focus area",
      "paragraph_id": "P_0001",
      "source_quote": "verbatim source quote",
      "analysis": "source-bound analysis"
    }
  ],
  "limitations": ["known limitation"]
}
```

Contract:

- Each finding must cite a real `paragraph_id`.
- Each `source_quote` must appear in that paragraph.
- `lens_audit.json` records deterministic compliance checks.

## `lens_critic.json`

Model: `LensCriticReport`

```json
{
  "passed": true,
  "risk_level": "low",
  "summary": "critic summary",
  "critiques": [
    {
      "severity": "warning",
      "issue_type": "weak_focus_coverage",
      "paragraph_id": "P_0001",
      "source_quote": "verbatim source quote",
      "critique": "critique text",
      "recommendation": "recommended fix"
    }
  ]
}
```

Allowed `risk_level` values:

- `low`
- `medium`
- `high`

Contract:

- Critiques may omit `paragraph_id` when the critique is structural.
- If `paragraph_id` and `source_quote` are present, the quote should be grounded.
- `lens_critic_audit.json` records quote grounding checks.

## `draft.json`

Model: `DraftReport`

```json
{
  "title": "Draft title",
  "thesis": "Draft thesis",
  "sections": [
    {
      "section_type": "introduction",
      "heading": "Introduction",
      "body": "Source-grounded prose [C1].",
      "claim_ids": ["C1"]
    }
  ],
  "claims": [
    {
      "claim_id": "C1",
      "paragraph_id": "P_0001",
      "source_quote": "verbatim source quote",
      "node_id": "n1"
    }
  ],
  "open_tensions": ["unresolved tension"]
}
```

Allowed `section_type` values:

- `introduction`
- `related_work`
- `methodology`
- `discussion`
- `conclusion`

Contract:

- Every claim must have a unique `claim_id`.
- Every claim must cite a real `paragraph_id`.
- Every claim `source_quote` must appear in that paragraph.
- Section prose should cite factual claims with `[C#]`.
- `draft_audit.json` records compliance.
- If ontology audit fails first, `draft.json` is not written.

## `review.json`

Model: `ReviewReport`

```json
{
  "reviews": [
    {
      "panelist": "Ella",
      "score": 90,
      "feedback": "critique",
      "source_quotes": ["verbatim draft quote"]
    }
  ],
  "editor_decision": "Accept",
  "editor_summary": "synthesis",
  "final_score": 90
}
```

Allowed `panelist` values:

- `Ella`
- `Miranda`
- `Methodologist`
- `Devil's Advocate`

Allowed `editor_decision` values:

- `Accept`
- `Major Revision`
- `Reject`

Contract:

- Each panelist `source_quotes[]` entry must appear verbatim in the draft text.
- `review_passed=true` only for `Accept` or `Major Revision`.
- `review_score` mirrors `final_score`.
- If quote grounding fails after retry, `review.json` and `review.md` are not written.

## `failure.json`

`failure.json` is a diagnostic artifact. It is intentionally flexible by stage.

Common fields:

| Field | Meaning |
|---|---|
| `recorded_at` | ISO timestamp |
| `stage` | Failing stage, such as `scraping` or `peer_review_grounding` |
| `error_message` | Human-readable failure message |

Stage-specific fields may include:

- `url`
- `scraper`
- `http_status`
- `content_type`
- `final_url`
- `raw_excerpt`
- `review_attempts`

Contract:

- Consumers should not require every optional field.
- Use `stage` and `error_message` first.
- `manifest.json` sets `has_failure_artifact=true` when this file is written.

## Markdown Artifacts

Markdown artifacts are intended for human reading:

- `report.md`
- `fulltext.md`
- `lens_brief.md`
- `lens_analysis.md`
- `lens_critic.md`
- `draft.md`
- `review.md`

Programmatic integrations should prefer JSON artifacts.

## Compatibility Notes

- Fields may be added over time.
- Existing fields documented here should not change meaning without a version note.
- Consumers should ignore unknown fields.
- Consumers should treat missing optional artifacts as normal when the corresponding module or gate did not run.

