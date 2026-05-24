import json

from omni_academic.audit.draft_gate import DraftComplianceAuditor
from omni_academic.draft.scribe import (
    DraftClaim,
    DraftReport,
    DraftSection,
    ScribeAgent,
)
from omni_academic.llm.provider import MockProvider
from omni_academic.ontology.extractor import OntologyMap
from omni_academic.store.run_store import RunStore
from omni_academic.supervisor.router import OmniSupervisorRouter

DOC = (
    "First paragraph about transformers and attention mechanisms in models.\n\n"
    "Second paragraph discussing scalability limits and reproducibility concerns.\n\n"
    "Third paragraph on empirical validation methodology and results."
)


def test_scribe_mock_produces_grounded_draft_that_passes_gate():
    ontology = OntologyMap(nodes=[], edges=[])
    draft = ScribeAgent().build_draft(DOC, ontology, "cs", MockProvider())
    assert draft.claims, "mock draft must register at least one claim"
    # 모든 claim이 실존 문단·verbatim 인용에 묶여야 한다
    audit = DraftComplianceAuditor().verify(draft, DOC, ontology)
    errors = [f.code for f in audit.findings if f.severity == "error"]
    assert audit.passed, f"unexpected blocking findings: {errors}"


def test_draft_gate_flags_ungrounded_claim():
    report = DraftReport(
        title="T", thesis="th",
        sections=[DraftSection(
            section_type="introduction", heading="I", body="x [C1]", claim_ids=["C1"]
        )],
        claims=[DraftClaim(claim_id="C1", paragraph_id="P_9999", source_quote="nope")],
        open_tensions=["t"],
    )
    audit = DraftComplianceAuditor().verify(report, DOC, OntologyMap(nodes=[], edges=[]))
    assert not audit.passed
    assert any(f.code == "UNGROUNDED_DRAFT_CLAIM" for f in audit.findings)


def test_draft_gate_flags_ungrounded_quote():
    report = DraftReport(
        title="T", thesis="th",
        sections=[DraftSection(
            section_type="introduction", heading="I", body="x [C1]", claim_ids=["C1"]
        )],
        claims=[DraftClaim(
            claim_id="C1", paragraph_id="P_0001",
            source_quote="this exact text does not appear in paragraph one",
        )],
        open_tensions=["t"],
    )
    audit = DraftComplianceAuditor().verify(report, DOC, OntologyMap(nodes=[], edges=[]))
    assert not audit.passed
    assert any(f.code == "UNGROUNDED_DRAFT_QUOTE" for f in audit.findings)


def test_draft_gate_flags_undeclared_anchor():
    report = DraftReport(
        title="T", thesis="th",
        sections=[DraftSection(
            section_type="introduction", heading="I",
            body="see [C5] which was never declared", claim_ids=[],
        )],
        claims=[DraftClaim(
            claim_id="C1", paragraph_id="P_0001",
            source_quote="First paragraph about transformers",
        )],
        open_tensions=["t"],
    )
    audit = DraftComplianceAuditor().verify(report, DOC, OntologyMap(nodes=[], edges=[]))
    assert not audit.passed
    assert any(f.code == "UNDECLARED_CLAIM_ANCHOR" for f in audit.findings)


def test_draft_gate_warns_on_missing_open_tensions():
    # open_tensions 비면 평탄화 의심 경고(에러 아님 → passed 유지)
    report = DraftReport(
        title="T", thesis="th",
        sections=[DraftSection(
            section_type="introduction", heading="I", body="x [C1]", claim_ids=["C1"]
        )],
        claims=[DraftClaim(
            claim_id="C1", paragraph_id="P_0001",
            source_quote="First paragraph about transformers",
        )],
        open_tensions=[],
    )
    audit = DraftComplianceAuditor().verify(report, DOC, OntologyMap(nodes=[], edges=[]))
    assert audit.passed
    assert any(f.code == "MISSING_OPEN_TENSIONS" for f in audit.findings)


def test_draft_module_mock_e2e(tmp_path):
    store = RunStore.create("draft topic", "cs", mock=True, base=str(tmp_path))
    OmniSupervisorRouter(use_mock=True)._run_draft(store, DOC, "cs")
    run_dir = store.finalize()

    assert (run_dir / "draft.json").is_file()
    assert (run_dir / "draft.md").is_file()
    m = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert m["draft_passed"] is True
    assert "draft.md" in m["artifacts"]
    # report.md에 Draft Compliance 섹션이 렌더되는지
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "### Draft Compliance" in report
