# Examples

This directory contains small, non-private fixtures that can be used to verify the framework without external APIs.

Run the ontology pipeline with the offline mock provider:

```bash
uv run omni ./examples/sample.md --module ontology --lens general --mock
```

Expected behavior:

- A new mock run is written under `runs/examples-sample-md/`.
- `paragraphs.json`, `ontology.json`, `audit.json`, `report.md`, and `manifest.json` are created.
- `audit_passed` should be `true` for the mock path.
