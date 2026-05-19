from src.analyze.lens_analyzer import (
    LensAnalysisReport,
    LensAnalyzer,
    LensCriticReport,
    LensCritique,
    LensFinding,
)
from src.audit.lens_gate import LensComplianceAuditor
from src.llm.provider import MockProvider

DOC = "Alpha claim appears here.\n\nBeta method follows."


def test_lens_compliance_audit_accepts_grounded_mock_analysis():
    report = LensAnalyzer().build_llm_analysis(DOC, "general", MockProvider())

    audit = LensComplianceAuditor().verify(report, DOC, "general")

    assert audit.passed
    assert not any(f.code == "UNGROUNDED_LENS_QUOTE" for f in audit.findings)


def test_lens_compliance_audit_rejects_unknown_paragraph():
    report = LensAnalysisReport(
        lens="general",
        executive_summary="Grounded enough summary.",
        findings=[
            LensFinding(
                focus_area="Core Claim & Argument Structure",
                paragraph_id="P_9999",
                source_quote="Alpha claim appears here.",
                analysis="This finding points to a missing paragraph anchor.",
            )
        ],
        limitations=["fixture"],
    )

    audit = LensComplianceAuditor().verify(report, DOC, "general")

    assert not audit.passed
    assert any(f.code == "UNGROUNDED_LENS_FINDING" for f in audit.findings)


def test_lens_compliance_audit_rejects_nonverbatim_quote():
    report = LensAnalysisReport(
        lens="general",
        executive_summary="Grounded enough summary.",
        findings=[
            LensFinding(
                focus_area="Core Claim & Argument Structure",
                paragraph_id="P_0001",
                source_quote="Alpha claim is paraphrased here.",
                analysis="This finding uses a quote that is not in the source.",
            )
        ],
        limitations=["fixture"],
    )

    audit = LensComplianceAuditor().verify(report, DOC, "general")

    assert not audit.passed
    assert any(f.code == "UNGROUNDED_LENS_QUOTE" for f in audit.findings)


def test_lens_critic_audit_rejects_inconsistent_passed_flag():
    critic = LensCriticReport(
        passed=True,
        risk_level="low",
        summary="Critic found a blocking issue but marked the report as passed.",
        critiques=[
            LensCritique(
                severity="error",
                issue_type="unsupported_claim",
                paragraph_id="P_0001",
                source_quote="Alpha claim appears here.",
                critique="The analysis overclaims against the cited source.",
                recommendation="Mark the critic report as failed.",
            )
        ],
    )

    audit = LensComplianceAuditor().verify_critic(critic, DOC)

    assert not audit.passed
    assert any(f.code == "CRITIC_ERROR_MARKED_PASSED" for f in audit.findings)


def test_lens_critic_audit_rejects_nonverbatim_quote():
    critic = LensCriticReport(
        passed=False,
        risk_level="high",
        summary="Critic found a grounded issue.",
        critiques=[
            LensCritique(
                severity="error",
                issue_type="unsupported_claim",
                paragraph_id="P_0001",
                source_quote="Alpha claim was paraphrased.",
                critique="The critique quote is not present in the cited paragraph.",
                recommendation="Use a verbatim quote.",
            )
        ],
    )

    audit = LensComplianceAuditor().verify_critic(critic, DOC)

    assert not audit.passed
    assert any(f.code == "UNGROUNDED_CRITIC_QUOTE" for f in audit.findings)
