import json

import pytest

from omni_academic.recon.engine import PaperMetadata, ReconEngine
from omni_academic.store.run_store import RunStore
from omni_academic.supervisor.router import (
    OmniSupervisorRouter,
    _list_lenses,
    _resolve_document,
    _resolve_run_dir,
    _run_next_steps,
    _verify_run,
)


def test_noise_filter_drops_editorial_keeps_substring_safe():
    engine = ReconEngine()
    papers = [
        PaperMetadata(title="Editorial: welcome", authors=["X"]),
        PaperMetadata(title="Index Theory in Topology", authors=["Y"]),
    ]
    clean = engine._smart_noise_filter(papers)
    titles = [p.title for p in clean]
    assert "Editorial: welcome" not in titles
    assert "Index Theory in Topology" in titles  # 'index' 부분문자열 오탐 금지


def test_resolve_document_reads_file(tmp_path):
    f = tmp_path / "paper.md"
    f.write_text("real content", encoding="utf-8")
    assert _resolve_document(str(f)) == "real content"


def test_example_sample_exists_and_mock_ontology_passes(tmp_path):
    sample = "examples/sample.md"
    text = _resolve_document(sample)
    assert "Planning under uncertainty" in text

    store = RunStore.create("sample.md", "general", mock=True, base=str(tmp_path))
    router = OmniSupervisorRouter(use_mock=True)
    router._run_ontology(store, text)
    run_dir = store.finalize()

    assert store._meta["audit_passed"] is True
    assert (run_dir / "report.md").is_file()


def test_resolve_document_inline_passthrough():
    assert _resolve_document("not a path, just a query") == "not a path, just a query"


def test_mock_ontology_path_passes_audit(tmp_path):
    store = RunStore.create("fixture", "general", mock=True, base=str(tmp_path))
    router = OmniSupervisorRouter(use_mock=True)

    router._run_ontology(store, "Alpha claim appears here.\n\nBeta method follows.")

    store.finalize()
    assert store._meta["audit_passed"] is True
    assert (store.dir / "paragraphs.json").is_file()
    assert (store.dir / "ontology.json").is_file()
    assert (store.dir / "audit.json").is_file()


def test_analyze_module_writes_lens_brief_artifact(tmp_path):
    store = RunStore.create("analysis fixture", "general", mock=False, base=str(tmp_path))
    router = OmniSupervisorRouter()

    router._run_analyze(store, "Alpha claim appears here.\n\nBeta method follows.", "general")
    store.note("status", "completed")
    run_dir = store.finalize()

    brief = (run_dir / "lens_brief.md").read_text(encoding="utf-8")
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    assert "# Lens Briefing Scaffold" in brief
    assert "P_0001" in brief
    assert "lens_brief.md" in manifest["artifacts"]
    assert manifest["artifact_manifest"]["lens_brief.md"]["exists"] is True


def test_analyze_module_writes_mock_llm_analysis_artifacts(tmp_path):
    store = RunStore.create("analysis fixture", "general", mock=True, base=str(tmp_path))
    router = OmniSupervisorRouter(use_mock=True)

    router._run_analyze(
        store,
        "Alpha claim appears here.\n\nBeta method follows.",
        "general",
        llm_analysis=True,
    )
    store.note("status", "completed")
    run_dir = store.finalize()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    assert (run_dir / "lens_analysis.json").is_file()
    assert (run_dir / "lens_analysis.md").is_file()
    assert (run_dir / "lens_audit.json").is_file()
    assert manifest["lens_audit_passed"] is True
    assert "lens_analysis.json" in manifest["artifacts"]
    assert "lens_audit.json" in manifest["artifacts"]
    assert manifest["artifact_manifest"]["lens_analysis.md"]["exists"] is True
    assert manifest["artifact_manifest"]["lens_audit.json"]["exists"] is True


def test_analyze_module_writes_mock_llm_critic_artifacts(tmp_path):
    store = RunStore.create("analysis fixture", "general", mock=True, base=str(tmp_path))
    router = OmniSupervisorRouter(use_mock=True)

    router._run_analyze(
        store,
        "Alpha claim appears here.\n\nBeta method follows.",
        "general",
        llm_analysis=True,
        llm_critic=True,
    )
    store.note("status", "completed")
    run_dir = store.finalize()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    assert (run_dir / "lens_critic.json").is_file()
    assert (run_dir / "lens_critic.md").is_file()
    assert (run_dir / "lens_critic_audit.json").is_file()
    assert manifest["lens_critic_passed"] is True
    assert manifest["lens_critic_audit_passed"] is True
    assert "lens_critic.json" in manifest["artifacts"]
    assert "lens_critic_audit.json" in manifest["artifacts"]


def test_list_lenses_reads_registry():
    lenses = _list_lenses("lenses")
    ids = {row["id"] for row in lenses}
    assert {"general", "theology", "economics"}.issubset(ids)
    general = next(row for row in lenses if row["id"] == "general")
    assert "crossref" in general["clients"]


def test_resolve_run_dir_accepts_run_id_and_slug_latest(tmp_path):
    run_dir = tmp_path / "runs" / "q" / "MOCK-20260519T000000Z"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "q/MOCK-20260519T000000Z"}),
        encoding="utf-8",
    )
    (tmp_path / "runs" / "q" / "latest").symlink_to("MOCK-20260519T000000Z")

    assert _resolve_run_dir("q/MOCK-20260519T000000Z", str(tmp_path / "runs")) == run_dir
    assert _resolve_run_dir("q", str(tmp_path / "runs")) == run_dir


def test_resolve_run_dir_accepts_direct_relative_path(tmp_path, monkeypatch):
    run_dir = tmp_path / "runs" / "q" / "MOCK-20260519T000000Z"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "q/MOCK-20260519T000000Z"}),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    assert _resolve_run_dir("runs/q/MOCK-20260519T000000Z", "runs") == run_dir


def test_resolve_run_dir_missing_raises(tmp_path):
    with pytest.raises(ValueError):
        _resolve_run_dir("missing", str(tmp_path / "runs"))


def test_verify_run_detects_artifact_tampering(tmp_path):
    store = RunStore.create("fixture", "general", mock=True, base=str(tmp_path / "runs"))
    router = OmniSupervisorRouter(use_mock=True)
    router._run_ontology(store, "Alpha claim appears here.\n\nBeta method follows.")
    run_dir = store.finalize()

    ok, issues = _verify_run(store._meta["run_id"], str(tmp_path / "runs"))
    assert ok
    assert issues == []

    (run_dir / "report.md").write_text("tampered", encoding="utf-8")
    ok, issues = _verify_run(store._meta["run_id"], str(tmp_path / "runs"))
    assert not ok
    assert any("report.md" in issue for issue in issues)


def test_run_next_steps_for_review_grounding_failure(tmp_path):
    run_dir = tmp_path / "runs" / "q" / "MOCK-20260524T000000Z"
    manifest = {
        "status": "blocked_by_review_grounding",
        "has_failure_artifact": True,
    }

    steps = _run_next_steps("blocked_by_review_grounding", manifest, run_dir)

    assert any("failure.json" in step for step in steps)
    assert any("review.json" in step and "intentionally absent" in step for step in steps)
    assert str(run_dir / "report.md") in steps[-1]


def test_run_next_steps_for_completed_is_empty(tmp_path):
    assert _run_next_steps("completed", {}, tmp_path) == []
