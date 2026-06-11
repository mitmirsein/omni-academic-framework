"""grounding 단일 정책 검증 (QUALITY_IMPROVEMENT_PLAN.md F2).

같은 인용 변형(NBSP/curly quote/개행 접기)이 모든 게이트에서 동일하게
판정되는지 고정한다. 게이트별 자체 정규화가 부활하면 여기서 깨진다.
"""

import pytest

from omni_academic.analyze.lens_analyzer import (
    LensAnalysisReport,
    LensAnalyzer,
    LensFinding,
)
from omni_academic.analyze.peer_review import (
    PanelistReview,
    PeerReviewPanel,
    ReviewReport,
)
from omni_academic.audit.draft_gate import DraftComplianceAuditor
from omni_academic.audit.gate import AuditGate
from omni_academic.audit.lens_gate import LensComplianceAuditor
from omni_academic.draft.scribe import (
    DraftClaim,
    DraftReport,
    DraftSection,
    ScribeAgent,
)
from omni_academic.ontology.extractor import EntityClass, Node, OntologyMap
from omni_academic.text.grounding import canon_quote, is_normalized_match, quote_in
from omni_academic.text.paragraphs import assign_paragraph_ids

# (원문 문단, 산출물 인용) — raw로는 불일치하지만 비파괴적 변형이라
# 정규화 후에는 verbatim으로 인정되어야 하는 케이스.
VARIANTS = [
    pytest.param(
        "The quantum\u00a0entanglement effect is measured in repeated trials.",
        "quantum entanglement effect is measured",
        id="nbsp",
    ),
    pytest.param(
        "Scholars call this the “critical” turn of the field today.",
        'call this the "critical" turn of the field',
        id="curly-quotes",
    ),
    pytest.param(
        "Alpha beta\ngamma delta concludes the argument cleanly here.",
        "beta gamma delta concludes the argument",
        id="newline-collapse",
    ),
]


def _doc(source_para: str) -> str:
    return f"Intro paragraph for context.\n\n{source_para}"


def _draft(quote: str) -> DraftReport:
    return DraftReport(
        title="Grounding Test Draft",
        thesis="A thesis sentence for the corpus.",
        sections=[DraftSection(
            section_type="introduction",
            heading="Intro",
            body="The body cites [C1] once.",
            claim_ids=["C1"],
        )],
        claims=[DraftClaim(
            claim_id="C1", paragraph_id="P_0002",
            source_quote=quote, node_id=None,
        )],
        open_tensions=["A preserved tension."],
    )


# --- 정책 함수 자체 ---

def test_canon_quote_normalizes_nonbreaking_variants():
    assert canon_quote("a\u00a0b\n c") == "a b c"
    assert canon_quote("“x” ‘y’") == "\"x\" 'y'"
    assert canon_quote("soft\u00adhyphen") == "softhyphen"


def test_case_difference_is_not_forgiven():
    # 소문자화는 과잉 관대함 — 대소문자 차이는 환각 신호로 유지한다.
    assert not quote_in("Quantum Entanglement", "the quantum entanglement effect")


def test_empty_quote_never_matches():
    assert not quote_in("", "anything")
    assert not quote_in("   ", "anything")


def test_is_normalized_match_requires_raw_mismatch():
    assert is_normalized_match("a  b", "x a b y")
    assert not is_normalized_match("a b", "x a b y")  # raw로도 일치 → False


# --- 게이트 5곳 + 재시도 검증기들의 동일 판정 ---

@pytest.mark.parametrize("source_para,quote", VARIANTS)
def test_audit_gate_accepts_normalized_quote(source_para, quote):
    _, pmap = assign_paragraph_ids(_doc(source_para))
    ontology = OntologyMap(nodes=[Node(
        id="n1", label="Concept", entity_class=EntityClass.CONCEPT,
        paragraph_id="P_0002", source_quote=quote,
    )], edges=[])
    report = AuditGate().verify_ontology(ontology, paragraph_manifest=pmap)
    assert report.passed
    assert any(f.code == "QUOTE_NORMALIZED_MATCH" for f in report.findings)


@pytest.mark.parametrize("source_para,quote", VARIANTS)
def test_draft_gate_accepts_normalized_quote(source_para, quote):
    report = DraftComplianceAuditor().verify(
        _draft(quote), _doc(source_para), OntologyMap(nodes=[], edges=[])
    )
    assert report.passed
    assert any(f.code == "QUOTE_NORMALIZED_MATCH" for f in report.findings)


@pytest.mark.parametrize("source_para,quote", VARIANTS)
def test_lens_gate_accepts_normalized_quote(source_para, quote):
    analysis = LensAnalysisReport(
        lens="general",
        executive_summary="Summary.",
        findings=[LensFinding(
            focus_area="Core claim",
            paragraph_id="P_0002",
            source_quote=quote,
            analysis="A sufficiently long analysis sentence bound to the quote.",
        )],
        limitations=["Limited scope."],
    )
    report = LensComplianceAuditor().verify(analysis, _doc(source_para), "general")
    assert report.passed
    assert any(f.code == "QUOTE_NORMALIZED_MATCH" for f in report.findings)


@pytest.mark.parametrize("source_para,quote", VARIANTS)
def test_retry_verifiers_accept_normalized_quote(source_para, quote):
    _, pmap = assign_paragraph_ids(_doc(source_para))
    draft = _draft(quote)

    # ScribeAgent grounding (raise 없음 = 통과)
    ScribeAgent._verify_grounding(draft, pmap, node_ids=set())

    # LensAnalyzer grounding
    analysis = LensAnalysisReport(
        lens="general", executive_summary="s",
        findings=[LensFinding(
            focus_area="f", paragraph_id="P_0002",
            source_quote=quote, analysis="long enough analysis text",
        )],
        limitations=[],
    )
    LensAnalyzer._verify_analysis_grounding(analysis, pmap)

    # PeerReviewPanel grounding (인용은 draft claim quote에 정규화 일치)
    review = ReviewReport(
        reviews=[PanelistReview(
            panelist="Ella", score=80, feedback="fb", source_quotes=[quote],
        )],
        editor_decision="Accept", editor_summary="s", final_score=80,
    )
    PeerReviewPanel._verify_review_grounding(review, draft)


@pytest.mark.parametrize("source_para,quote", VARIANTS)
def test_truly_absent_quote_still_blocked_everywhere(source_para, quote):
    absent = "this sentence does not exist in the source at all"
    _, pmap = assign_paragraph_ids(_doc(source_para))

    ontology = OntologyMap(nodes=[Node(
        id="n1", label="Concept", entity_class=EntityClass.CONCEPT,
        paragraph_id="P_0002", source_quote=absent,
    )], edges=[])
    assert not AuditGate().verify_ontology(ontology, paragraph_manifest=pmap).passed

    assert not DraftComplianceAuditor().verify(
        _draft(absent), _doc(source_para), OntologyMap(nodes=[], edges=[])
    ).passed

    with pytest.raises(ValueError):
        ScribeAgent._verify_grounding(_draft(absent), pmap, node_ids=set())

    review = ReviewReport(
        reviews=[PanelistReview(
            panelist="Ella", score=80, feedback="fb", source_quotes=[absent],
        )],
        editor_decision="Accept", editor_summary="s", final_score=80,
    )
    with pytest.raises(ValueError):
        PeerReviewPanel._verify_review_grounding(review, _draft(quote))
