"""헌법 §4 동적 자가-동기화 — Dynamic Glossary MVP.

입력 문서의 앞부분을 스캔해 그 텍스트가 실제로 사용하는 핵심 술어와
문체 관찰을 추출하고, 검증된 용어집을 draft/analyze 프롬프트에 주입한다.

정적 사전에 의존하지 않는다(§4): 용어는 반드시 문서 자신의 문단에서
verbatim 인용으로 근거가 잡혀야 하며, 근거가 깨진 용어집은 주입되지
않는다(fail-closed). 외부 용어 필터(TRE 등)는 이 모듈에 넣지 않는다 —
필요하면 사용자가 렌즈로 주입한다.
"""

from datetime import datetime, timezone
from typing import List

from pydantic import BaseModel, Field
from rich.console import Console

from omni_academic.audit.gate import AuditFinding, AuditReport
from omni_academic.text.grounding import quote_in
from omni_academic.text.paragraphs import assign_paragraph_ids

console = Console()

#: 기본 스캔 범위 — 문서 앞부분 문단 수 (§4: "입력 텍스트의 앞부분을 스캔").
DEFAULT_SCAN_PARAGRAPHS = 30


class GlossaryTerm(BaseModel):
    term: str = Field(description="문서가 사용하는 핵심 술어(원문 표기 그대로)")
    definition: str = Field(description="문서 내 용법에 근거한 짧은 작업 정의")
    paragraph_id: str = Field(description="용어가 도입/정의되는 문단 ID")
    source_quote: str = Field(
        description="paragraph_id 문단에서 그대로 복사한 verbatim 근거 인용"
    )


class GlossaryReport(BaseModel):
    terms: List[GlossaryTerm]
    style_notes: List[str] = Field(
        default_factory=list,
        description="문체/어조 관찰 (예: 시제, 인용 관행, 술어 스타일)",
    )


class GlossaryBuilder:
    """문서 앞부분에서 source-bound 동적 용어집을 추출한다."""

    def __init__(self):
        self.console = console
        self.last_attempts: int = 0

    def build(
        self,
        target_document: str,
        llm_provider,
        scan_paragraphs: int = DEFAULT_SCAN_PARAGRAPHS,
        max_attempts: int = 2,
    ) -> GlossaryReport:
        """용어집을 추출하고 grounding 위반 시 교정 재시도한다.

        최대 시도 후에도 깨지면 마지막 리포트를 반환한다 — 호출부는
        `verify()` 결과로 주입 여부를 결정한다(fail-closed).
        """
        _, paragraph_map = assign_paragraph_ids(target_document)
        head_ids = list(paragraph_map)[: max(1, scan_paragraphs)]
        head_annotated = "\n\n".join(f"[{pid}] {paragraph_map[pid]}" for pid in head_ids)

        base_prompt = (
            "Scan the opening of the supplied scholarly text and build a dynamic "
            "glossary of the key technical terms THIS text actually uses.\n"
            "Hard rules:\n"
            "- Extract only terms that recur or carry load in the supplied excerpt. "
            "Do not import outside terminology or standard dictionary definitions.\n"
            "- Every term must cite the paragraph_id where it is introduced/defined, "
            "copied verbatim from a [P_XXXX] marker in the excerpt.\n"
            "- Every source_quote must be an exact verbatim substring of that "
            "paragraph (do not paraphrase, normalize, or translate).\n"
            "- definitions must reflect the text's own usage, not external knowledge.\n"
            "- Record style observations (tense, citation habits, register) in "
            "style_notes.\n\n"
            f"Document opening:\n{head_annotated}"
        )
        prompt = base_prompt
        report = None
        for attempt in range(1, max(1, max_attempts) + 1):
            self.last_attempts = attempt
            report = llm_provider.generate_structured_output(prompt, GlossaryReport)
            audit = self.verify(report, paragraph_map)
            if audit.passed:
                return report
            if attempt >= max_attempts:
                break
            errors = "; ".join(
                f"[{f.code}] {f.message}" for f in audit.findings if f.severity == "error"
            )
            self.console.print(
                f"[yellow]⚠️ Glossary grounding 실패 (시도 {attempt}/{max_attempts}) "
                f"→ 교정 재시도: {errors}[/yellow]"
            )
            prompt = (
                f"{base_prompt}\n\n"
                "## CORRECTION REQUIRED (previous attempt failed grounding)\n"
                f"{errors}\n"
                "Re-emit the FULL glossary. Drop any term you cannot ground in a "
                "real [P_XXXX] paragraph with an exact verbatim source_quote."
            )
        return report

    @staticmethod
    def verify(report: GlossaryReport, paragraph_map: dict) -> AuditReport:
        """결정론적 용어집 감사 — 환각 용어/인용 차단 (LLM 불사용)."""
        findings: List[AuditFinding] = []
        if not report.terms:
            findings.append(AuditFinding(
                severity="warning", code="EMPTY_GLOSSARY",
                message="추출된 용어가 없음 — 주입 효과 없음",
            ))
        for idx, term in enumerate(report.terms, 1):
            ref = f"term[{idx}:{term.term}]"
            if term.paragraph_id not in paragraph_map:
                findings.append(AuditFinding(
                    severity="error", code="UNGROUNDED_GLOSSARY_TERM",
                    message=f"존재하지 않는 paragraph_id 참조: {term.paragraph_id}",
                    source_ref=ref,
                ))
                continue
            if not quote_in(term.source_quote, paragraph_map[term.paragraph_id]):
                findings.append(AuditFinding(
                    severity="error", code="UNGROUNDED_GLOSSARY_QUOTE",
                    message=(
                        f"source_quote가 해당 문단에 없음(환각): {term.paragraph_id}"
                    ),
                    source_ref=ref,
                ))
            if not quote_in(term.term, " ".join(paragraph_map.values())):
                findings.append(AuditFinding(
                    severity="error", code="FOREIGN_GLOSSARY_TERM",
                    message=f"용어가 원문에 등장하지 않음(외부 주입 의심): {term.term}",
                    source_ref=ref,
                ))
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

    @staticmethod
    def render(report: GlossaryReport) -> str:
        """glossary.md 본문 겸 프롬프트 주입 블록."""
        lines = ["# Dynamic Glossary (source-bound)", ""]
        if report.terms:
            for term in report.terms:
                lines.append(f"- **{term.term}** (`{term.paragraph_id}`): {term.definition}")
                lines.append(f'  > "{term.source_quote}"')
        else:
            lines.append("- No terms extracted.")
        lines.append("")
        lines.append("## Style Notes")
        if report.style_notes:
            lines.extend(f"- {note}" for note in report.style_notes)
        else:
            lines.append("- None recorded.")
        return "\n".join(lines)

    @staticmethod
    def injection_block(report: GlossaryReport) -> str:
        """draft/analyze 프롬프트에 부착할 검증된 용어집 블록."""
        lines = [
            "## Verified Dynamic Glossary (extracted from THIS document's opening)",
            "Use these terms exactly as the source text uses them. Do not introduce "
            "competing terminology for the same concepts.",
        ]
        for term in report.terms:
            lines.append(f"- {term.term}: {term.definition} (see {term.paragraph_id})")
        if report.style_notes:
            lines.append("Style guide observed in the source:")
            lines.extend(f"- {note}" for note in report.style_notes)
        return "\n".join(lines)
