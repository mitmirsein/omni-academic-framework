import json
import re
from pathlib import Path

from omni_academic.analyze.peer_review import PeerReviewPanel, ReviewReport
from omni_academic.audit.gate import AuditReport
from omni_academic.draft.scribe import DraftReport
from omni_academic.ontology.extractor import OntologyMap
from omni_academic.supervisor import run_status

FIXTURES = Path(__file__).parent / "fixtures" / "golden"
CLAIM_REF_RE = re.compile(r"\[(C\d+)\]")


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_golden_ontology_contract_is_grounded():
    paragraphs = _load("paragraphs.json")
    ontology = OntologyMap.model_validate(_load("ontology.json"))
    node_ids = {node.id for node in ontology.nodes}

    for node in ontology.nodes:
        assert node.paragraph_id in paragraphs
        assert node.source_quote in paragraphs[node.paragraph_id]

    source_corpus = "\n".join(paragraphs.values())
    for edge in ontology.edges:
        assert edge.source_id in node_ids
        assert edge.target_id in node_ids
        assert edge.source_quote in source_corpus


def test_golden_audit_report_contract():
    report = AuditReport.model_validate(_load("audit_passed.json"))

    assert report.passed is True
    assert 0 <= report.score <= 100
    assert report.findings == []


def test_golden_draft_contract_is_grounded():
    paragraphs = _load("paragraphs.json")
    ontology = OntologyMap.model_validate(_load("ontology.json"))
    draft = DraftReport.model_validate(_load("draft.json"))

    ontology_node_ids = {node.id for node in ontology.nodes}
    claim_ids = {claim.claim_id for claim in draft.claims}
    assert len(claim_ids) == len(draft.claims)

    for claim in draft.claims:
        assert claim.paragraph_id in paragraphs
        assert claim.source_quote in paragraphs[claim.paragraph_id]
        assert claim.node_id in ontology_node_ids

    referenced_claims = set()
    for section in draft.sections:
        for anchor in CLAIM_REF_RE.findall(section.body):
            referenced_claims.add(anchor)
            assert anchor in claim_ids
        assert set(section.claim_ids).issubset(claim_ids)

    assert claim_ids == referenced_claims
    assert draft.open_tensions


def test_golden_review_contract_is_grounded_to_draft():
    draft = DraftReport.model_validate(_load("draft.json"))
    review = ReviewReport.model_validate(_load("review.json"))

    PeerReviewPanel._verify_review_grounding(review, draft)
    assert review.editor_decision == "Accept"
    assert review.final_score == 89


def test_golden_failure_artifact_contract():
    failure = _load("failure_review_grounding.json")

    assert failure["stage"] == "peer_review_grounding"
    assert failure["error_message"]
    assert failure["review_attempts"] == 2
    assert "recorded_at" in failure


def test_golden_manifest_contract_shape():
    manifest = _load("manifest_completed_review.json")

    assert manifest["status"] == run_status.COMPLETED
    assert manifest["audit_passed"] is True
    assert manifest["draft_passed"] is True
    assert manifest["review_grounding_passed"] is True
    assert manifest["review_passed"] is True
    assert manifest["review_score"] == 89
    assert "review.json" in manifest["artifacts"]

    artifact_manifest = manifest["artifact_manifest"]
    for name, integrity in artifact_manifest.items():
        assert name.endswith((".json", ".md"))
        assert set(integrity) == {"exists", "bytes", "sha256"}
        assert integrity["exists"] is True
        assert isinstance(integrity["bytes"], int)
        assert len(integrity["sha256"]) == 64


def test_run_status_contract_contains_blocking_statuses():
    values = set(run_status.RUN_STATUS_VALUES)

    assert run_status.BLOCKED_BY_AUDIT in values
    assert run_status.BLOCKED_BY_DRAFT_AUDIT in values
    assert run_status.BLOCKED_BY_REVIEW_GROUNDING in values
    assert run_status.REVIEW_REJECTED in values
    assert set(run_status.TERMINAL_RUN_STATUS_VALUES) <= values
