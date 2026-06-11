from datetime import datetime, timezone
from typing import Dict, List

from omni_academic.analyze.lens_analyzer import LensAnalysisReport, LensCriticReport
from omni_academic.audit.gate import AuditFinding, AuditReport
from omni_academic.config.lens import LensNotFoundError, load_lens
from omni_academic.text.grounding import canon_quote, is_normalized_match, quote_in
from omni_academic.text.paragraphs import assign_paragraph_ids


def _norm(text: str) -> str:
    """렌즈 이름/focus area 대조용(quote grounding에는 grounding 모듈 사용)."""
    return " ".join((text or "").casefold().split())


def _quote_len(text: str) -> int:
    return len("".join((text or "").split()))


class LensComplianceAuditor:
    """Gate 3 deterministic lens compliance audit.

    This is not LLM self-redteaming yet. It enforces the mechanical invariants
    that a lens analysis must satisfy before a more expensive critic pass is
    worth running: real paragraph anchors, verbatim quotes, non-empty analysis,
    and visible coverage of configured lens focus areas.
    """

    def __init__(self, lens_dir: str = "lenses"):
        self.lens_dir = lens_dir

    def verify(
        self,
        report: LensAnalysisReport,
        target_document: str,
        lens_name: str,
    ) -> AuditReport:
        findings: List[AuditFinding] = []
        try:
            lens_config = load_lens(lens_name, self.lens_dir)
        except LensNotFoundError:
            findings.append(AuditFinding(
                severity="error",
                code="LENS_NOT_FOUND",
                message=f"렌즈 설정을 찾을 수 없음: {lens_name}",
            ))
            return self._report(findings)

        _, paragraph_map = assign_paragraph_ids(target_document)
        configured_focus = [
            str(area) for area in (lens_config.get("focus_areas", []) or [])
        ]
        configured_norm = {_norm(area): area for area in configured_focus}

        if _norm(report.lens) not in {_norm(lens_name), _norm(lens_config.get("name", ""))}:
            findings.append(AuditFinding(
                severity="warning",
                code="LENS_ID_MISMATCH",
                message=(
                    f"분석 report.lens가 요청 렌즈와 다름: "
                    f"{report.lens} != {lens_name}"
                ),
            ))

        if not report.executive_summary.strip():
            findings.append(AuditFinding(
                severity="warning",
                code="EMPTY_LENS_SUMMARY",
                message="렌즈 분석 executive_summary가 비어 있음",
            ))

        if not report.findings:
            findings.append(AuditFinding(
                severity="error",
                code="NO_LENS_FINDINGS",
                message="렌즈 분석 finding이 하나도 없음",
            ))

        seen_quotes: Dict[str, List[str]] = {}
        observed_focus: set[str] = set()
        for idx, item in enumerate(report.findings, 1):
            ref = f"finding[{idx}]"
            focus_norm = _norm(item.focus_area)
            if focus_norm:
                observed_focus.add(focus_norm)
            if configured_norm and focus_norm not in configured_norm:
                findings.append(AuditFinding(
                    severity="warning",
                    code="UNKNOWN_FOCUS_AREA",
                    message=f"렌즈 설정에 없는 focus_area 사용: {item.focus_area}",
                    source_ref=ref,
                ))
            if item.paragraph_id not in paragraph_map:
                findings.append(AuditFinding(
                    severity="error",
                    code="UNGROUNDED_LENS_FINDING",
                    message=f"존재하지 않는 paragraph_id 참조: {item.paragraph_id}",
                    source_ref=ref,
                ))
                continue

            quote = item.source_quote
            para_text = paragraph_map[item.paragraph_id]
            if not quote.strip():
                findings.append(AuditFinding(
                    severity="error",
                    code="MISSING_LENS_QUOTE",
                    message="렌즈 분석 source_quote 누락",
                    source_ref=ref,
                ))
            elif not quote_in(quote, para_text):
                findings.append(AuditFinding(
                    severity="error",
                    code="UNGROUNDED_LENS_QUOTE",
                    message=(
                        f"source_quote가 해당 문단에 없음: "
                        f"{item.paragraph_id}"
                    ),
                    source_ref=ref,
                ))
            elif _quote_len(quote) < 8:
                findings.append(AuditFinding(
                    severity="warning",
                    code="WEAK_LENS_QUOTE",
                    message=f"source_quote가 너무 짧아 검증력이 약함: {item.paragraph_id}",
                    source_ref=ref,
                ))
            else:
                if is_normalized_match(quote, para_text):
                    findings.append(AuditFinding(
                        severity="info",
                        code="QUOTE_NORMALIZED_MATCH",
                        message=(
                            f"source_quote가 정규화(공백/유니코드) 후에만 일치함: "
                            f"{item.paragraph_id}"
                        ),
                        source_ref=ref,
                    ))
                seen_quotes.setdefault(canon_quote(quote), []).append(ref)

            if len(item.analysis.strip()) < 20:
                findings.append(AuditFinding(
                    severity="warning",
                    code="WEAK_LENS_ANALYSIS",
                    message="finding.analysis가 너무 짧아 해석 품질 판단이 어려움",
                    source_ref=ref,
                ))

        for refs in seen_quotes.values():
            if len(refs) > 1:
                findings.append(AuditFinding(
                    severity="warning",
                    code="DUPLICATE_LENS_QUOTE",
                    message="여러 finding이 동일한 source_quote를 재사용함: " + ", ".join(refs),
                    source_ref=refs[0],
                ))

        for focus_norm, focus_label in configured_norm.items():
            if focus_norm not in observed_focus:
                findings.append(AuditFinding(
                    severity="warning",
                    code="MISSING_FOCUS_COVERAGE",
                    message=f"렌즈 focus_area가 분석 finding으로 직접 다뤄지지 않음: {focus_label}",
                ))

        if not report.limitations:
            findings.append(AuditFinding(
                severity="warning",
                code="MISSING_LIMITATIONS",
                message="렌즈 분석 limitations가 비어 있음",
            ))

        return self._report(findings)

    def verify_critic(
        self,
        report: LensCriticReport,
        target_document: str,
    ) -> AuditReport:
        findings: List[AuditFinding] = []
        _, paragraph_map = assign_paragraph_ids(target_document)
        if not report.summary.strip():
            findings.append(AuditFinding(
                severity="warning",
                code="EMPTY_CRITIC_SUMMARY",
                message="critic summary가 비어 있음",
            ))
        if report.risk_level == "high" and report.passed:
            findings.append(AuditFinding(
                severity="error",
                code="CRITIC_RISK_CONTRADICTION",
                message="risk_level=high인데 critic passed=true로 보고됨",
            ))
        if any(c.severity == "error" for c in report.critiques) and report.passed:
            findings.append(AuditFinding(
                severity="error",
                code="CRITIC_ERROR_MARKED_PASSED",
                message="error critique가 있는데 critic passed=true로 보고됨",
            ))

        for idx, critique in enumerate(report.critiques, 1):
            ref = f"critique[{idx}]"
            if not critique.critique.strip():
                findings.append(AuditFinding(
                    severity="warning",
                    code="EMPTY_CRITIQUE",
                    message="critique 본문이 비어 있음",
                    source_ref=ref,
                ))
            if not critique.recommendation.strip():
                findings.append(AuditFinding(
                    severity="warning",
                    code="EMPTY_CRITIQUE_RECOMMENDATION",
                    message="critique recommendation이 비어 있음",
                    source_ref=ref,
                ))
            if critique.paragraph_id:
                if critique.paragraph_id not in paragraph_map:
                    findings.append(AuditFinding(
                        severity="error",
                        code="UNGROUNDED_CRITIC_PARAGRAPH",
                        message=f"critic이 존재하지 않는 paragraph_id 참조: {critique.paragraph_id}",
                        source_ref=ref,
                    ))
                    continue
                if critique.source_quote and not quote_in(
                    critique.source_quote, paragraph_map[critique.paragraph_id]
                ):
                    findings.append(AuditFinding(
                        severity="error",
                        code="UNGROUNDED_CRITIC_QUOTE",
                        message=f"critic source_quote가 해당 문단에 없음: {critique.paragraph_id}",
                        source_ref=ref,
                    ))
            elif critique.source_quote:
                findings.append(AuditFinding(
                    severity="warning",
                    code="CRITIC_QUOTE_WITHOUT_PARAGRAPH",
                    message="critic source_quote가 있으나 paragraph_id가 없음",
                    source_ref=ref,
                ))

        return self._report(findings)

    @staticmethod
    def _report(findings: List[AuditFinding]) -> AuditReport:
        penalty = sum(
            25 if f.severity == "error" else 10 if f.severity == "warning" else 0
            for f in findings
        )
        return AuditReport(
            passed=not any(f.severity == "error" for f in findings),
            score=max(0, 100 - penalty),
            findings=findings,
            checked_at=datetime.now(timezone.utc),
        )
