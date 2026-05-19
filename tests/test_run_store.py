import json
import sqlite3

import pytest

from src.audit.gate import AuditReport
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
                    paragraph_id="P_0001")],
        edges=[Edge(source_id="n1", target_id="n1",
                    predicate=RelationPredicate.IS_A, reasoning="x" * 12)],
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

    # SQLite 인덱스 등재 확인
    conn = sqlite3.connect(tmp_path / "index.db")
    row = conn.execute("SELECT mock, audit_passed FROM runs").fetchone()
    conn.close()
    assert row == (0, 1)


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
    assert "Omni-Academic 산출물" in out.read_text(encoding="utf-8")
