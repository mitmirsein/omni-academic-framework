import json
import sqlite3

import pytest

from src.audit.gate import AuditFinding, AuditReport
from src.ontology.extractor import (
    Edge,
    EntityClass,
    Node,
    OntologyMap,
    RelationPredicate,
)
from src.recon.engine import PaperMetadata
from src.store.run_store import RunStore, export_to_vault


def _ontology():
    return OntologyMap(
        nodes=[Node(id="n1", label="A", entity_class=EntityClass.CONCEPT,
                    paragraph_id="P_0001", source_quote="first claim")],
        edges=[Edge(source_id="n1", target_id="n1",
                    predicate=RelationPredicate.IS_A, reasoning="x" * 12,
                    source_quote="first claim")],
    )


def test_run_store_writes_artifacts_and_manifest(tmp_path):
    store = RunStore.create("Inflation Targeting!", "economics",
                            mock=False, base=str(tmp_path))
    store.write_digest([PaperMetadata(title="P", authors=["A"])])
    store.write_paragraphs({"P_0001": "first", "P_0002": "second"})
    store.write_ontology(_ontology())
    store.write_audit(AuditReport(passed=True, score=100, findings=[],
                                  checked_at="2026-05-19T00:00:00+00:00"))
    run_dir = store.finalize()

    assert (run_dir / "digest.json").is_file()
    assert json.loads((run_dir / "paragraphs.json").read_text()) == {
        "P_0001": "first",
        "P_0002": "second",
    }
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["mock"] is False
    assert manifest["audit_passed"] is True
    assert manifest["query"] == "Inflation Targeting!"
    assert set(manifest["artifacts"]) >= {"digest.json", "ontology.json", "audit.json"}
    artifact_manifest = manifest["artifact_manifest"]
    assert artifact_manifest["digest.json"]["exists"] is True
    assert artifact_manifest["digest.json"]["bytes"] > 0
    assert len(artifact_manifest["digest.json"]["sha256"]) == 64
    assert "manifest.json" not in artifact_manifest

    # SQLite 인덱스 등재 확인
    conn = sqlite3.connect(tmp_path / "index.db")
    row = conn.execute(
        "SELECT mock, audit_passed, status, forensic_passed, artifacts_count FROM runs"
    ).fetchone()
    conn.close()
    assert row == (0, 1, "unknown", None, 5)


def test_run_store_index_migrates_status_columns(tmp_path):
    conn = sqlite3.connect(tmp_path / "index.db")
    conn.execute(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, created_at TEXT, query TEXT, "
        "lens TEXT, mock INTEGER, audit_passed INTEGER, dir TEXT)"
    )
    conn.commit()
    conn.close()

    store = RunStore.create("q", "cs", mock=False, base=str(tmp_path))
    store.note("status", "completed")
    store.note("forensic_passed", True)
    store.write_audit(AuditReport(passed=True, score=100, findings=[],
                                  checked_at="2026-05-19T00:00:00+00:00"))
    store.finalize()

    conn = sqlite3.connect(tmp_path / "index.db")
    cols = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
    row = conn.execute(
        "SELECT status, forensic_passed, artifacts_count FROM runs"
    ).fetchone()
    conn.close()
    assert {"status", "forensic_passed", "artifacts_count"}.issubset(cols)
    assert row == ("completed", 1, 2)


def test_mock_run_is_branded(tmp_path):
    store = RunStore.create("q", "cs", mock=True, base=str(tmp_path))
    run_dir = store.finalize()
    assert run_dir.name.startswith("MOCK-")
    assert json.loads((run_dir / "manifest.json").read_text())["mock"] is True


def test_vault_export_refuses_without_path(tmp_path):
    store = RunStore.create("q", "cs", base=str(tmp_path))
    with pytest.raises(ValueError):
        export_to_vault(store, "")


def test_vault_export_refuses_mock(tmp_path):
    store = RunStore.create("q", "cs", mock=True, base=str(tmp_path))
    store.finalize()
    with pytest.raises(ValueError, match="mock"):
        export_to_vault(store, str(tmp_path))


def test_vault_export_writes_draft_when_approved(tmp_path):
    vault = tmp_path / "vault"
    (vault / "000 System" / "Inbox" / "Drafts").mkdir(parents=True)
    store = RunStore.create("q", "cs", mock=False, base=str(tmp_path / "runs"))
    store.write_audit(AuditReport(passed=True, score=100, findings=[],
                                  checked_at="2026-05-19T00:00:00+00:00"))
    store.finalize()
    out = export_to_vault(store, str(vault), ontology=_ontology())
    assert out.exists()
    assert out.parent.name == "Drafts"
    draft = out.read_text(encoding="utf-8")
    assert "Omni-Academic 산출물" in draft
    assert "## Ontology Nodes" in draft
    assert "## Audit Findings" in draft
    assert "first claim" in draft


def test_report_includes_audit_and_forensic_findings(tmp_path):
    store = RunStore.create("q", "cs", mock=False, base=str(tmp_path))
    finding = AuditFinding(
        severity="warning",
        code="MISSING_QUOTE",
        message="source_quote 누락",
        source_ref="n1",
    )
    store.write_audit(AuditReport(
        passed=True,
        score=90,
        findings=[finding],
        checked_at="2026-05-19T00:00:00+00:00",
    ))
    store.write_forensic([AuditFinding(
        severity="error",
        code="DEAD_URL",
        message="URL 응답 없음",
        source_ref="paper[0]",
    )])
    run_dir = store.finalize()

    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "## Executive Summary" in report
    assert "### Audit Findings" in report
    assert "`MISSING_QUOTE`: source_quote 누락 (`n1`)" in report
    assert "### Forensics (Gate 2)" in report
    assert "`DEAD_URL`: URL 응답 없음 (`paper[0]`)" in report


def test_report_includes_provenance_artifacts_and_cache(tmp_path):
    store = RunStore.create("q", "cs", mock=False, base=str(tmp_path))
    store.write_digest([
        PaperMetadata(
            title="Paper",
            authors=["A"],
            abstract="This is a long enough abstract for report rendering.",
            citation_count=3,
            venue="Journal",
        )
    ])
    store.note("status", "completed")
    store.note("recon_cache", {"CrossrefClient": {"hit": True, "age_sec": 12}})
    store.write_audit(AuditReport(
        passed=True,
        score=100,
        findings=[],
        checked_at="2026-05-19T00:00:00+00:00",
    ))
    run_dir = store.finalize()

    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "## Provenance" in report
    assert "[`digest.json`](./digest.json)" in report
    assert "`CrossrefClient`: HIT, age=12s" in report
    assert "### [1] Paper" in report
    assert "- No audit findings." in report
