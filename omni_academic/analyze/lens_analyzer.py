from typing import Literal, Optional

from pydantic import BaseModel, Field
from rich.console import Console
from rich.panel import Panel

from omni_academic.config.lens import LensNotFoundError, load_lens
from omni_academic.text.grounding import quote_in
from omni_academic.text.paragraphs import assign_paragraph_ids

console = Console()


class LensFinding(BaseModel):
    focus_area: str = Field(description="렌즈 focus area 또는 분석 축")
    paragraph_id: str = Field(description="근거 문단 ID, 예: P_0001")
    source_quote: str = Field(description="근거 문단에서 그대로 복사한 verbatim 인용")
    analysis: str = Field(description="source_quote에 묶인 짧은 분석")


class LensAnalysisReport(BaseModel):
    lens: str
    executive_summary: str
    findings: list[LensFinding]
    limitations: list[str] = []


class LensCritique(BaseModel):
    severity: Literal["error", "warning", "info"]
    issue_type: str = Field(description="예: unsupported_claim, missed_tension, weak_focus_coverage")
    paragraph_id: Optional[str] = Field(default=None, description="근거 문단 ID가 있을 경우")
    source_quote: str = Field(default="", description="비판 근거가 되는 원문 verbatim quote")
    critique: str
    recommendation: str


class LensCriticReport(BaseModel):
    passed: bool
    risk_level: Literal["low", "medium", "high"]
    summary: str
    critiques: list[LensCritique] = []


class LensAnalyzer:
    """렌즈 기반 source-bound briefing 생성기.

    실 LLM 해석 리포트는 아직 제공하지 않는다. 대신 렌즈 설정과 원문 문단을
    기계적으로 묶은 deterministic brief를 생성한다. 가짜 통찰을 만들지 않고,
    사람이 후속 분석할 수 있도록 focus area별 질문과 source paragraph window를
    제시한다.
    """
    def __init__(self, lens_dir: str = "lenses"):
        self.lens_dir = lens_dir
        self.console = console
        self.last_attempts: int = 0

    @staticmethod
    def _excerpt(text: str, limit: int = 280) -> str:
        cleaned = " ".join((text or "").split())
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: max(0, limit - 3)].rstrip() + "..."

    def build_brief(self, target_document: str, lens_name: str) -> str:
        lens_config = load_lens(lens_name, self.lens_dir)
        name = lens_config.get("name", lens_name)
        focus_areas = lens_config.get("focus_areas", []) or []
        prompt = lens_config.get("analysis_prompt", "")
        _, paragraph_map = assign_paragraph_ids(target_document)

        lines = [
            "# Lens Briefing Scaffold",
            "",
            f"- **Lens**: {name} (`{lens_name}`)",
            f"- **Paragraphs**: {len(paragraph_map)}",
            "- **Mode**: deterministic source-bound scaffold, not LLM interpretation",
            "",
            "## Lens Focus",
        ]
        if focus_areas:
            lines.extend(f"- {area}" for area in focus_areas)
        else:
            lines.append("- No focus areas configured.")

        lines.extend(["", "## Lens Prompt", "", prompt or "_No prompt configured._"])

        lines.append("\n## Source Windows")
        if paragraph_map:
            for pid, text in list(paragraph_map.items())[:8]:
                lines.append(f"### {pid}")
                lines.append(self._excerpt(text))
        else:
            lines.append("_No source paragraphs detected._")

        lines.append("\n## Review Questions")
        if focus_areas:
            for area in focus_areas:
                lines.append(
                    f"- Which source paragraphs directly support or complicate "
                    f"`{area}`?"
                )
        else:
            lines.append("- Which paragraphs carry the main claim, method, and limitation?")
        lines.append("- Which tensions should be preserved rather than harmonized?")
        lines.append("- Which claims lack direct textual support in the selected source windows?")
        return "\n".join(lines)

    def build_llm_analysis(
        self,
        target_document: str,
        lens_name: str,
        llm_provider,
        max_attempts: int = 2,
        extra_context: str = "",
    ) -> LensAnalysisReport:
        """source-bound 분석을 생성하고, grounding 위반 시 구체 오류를
        피드백해 재시도하는 self-correcting 루프(운용화).

        시도 횟수는 `self.last_attempts`에 기록된다. 최대 시도 후에도
        grounding이 깨지면 마지막 리포트를 반환한다 — 크래시 대신 Gate 3
        (LensComplianceAuditor)가 결정론적으로 실패를 기록하게 한다.
        """
        lens_config = load_lens(lens_name, self.lens_dir)
        annotated, paragraph_map = assign_paragraph_ids(target_document)
        base_prompt = (
            "Create a concise source-bound lens analysis.\n"
            "Hard rules:\n"
            "- Every finding must cite a real paragraph_id from the supplied [P_XXXX] markers.\n"
            "- Every finding.source_quote must be an exact substring of that paragraph.\n"
            "- Do not add claims that are not supported by the supplied document.\n"
            "- Preserve unresolved tensions rather than harmonizing them.\n\n"
            f"Lens ID: {lens_name}\n"
            f"Lens Name: {lens_config.get('name', lens_name)}\n"
            f"Focus Areas: {lens_config.get('focus_areas', []) or []}\n"
            f"Analysis Prompt:\n{lens_config.get('analysis_prompt', '')}\n\n"
            + (f"{extra_context}\n\n" if extra_context else "")
            + f"Document:\n{annotated}"
        )
        prompt = base_prompt
        report = None
        for attempt in range(1, max(1, max_attempts) + 1):
            self.last_attempts = attempt
            report = llm_provider.generate_structured_output(prompt, LensAnalysisReport)
            try:
                self._verify_analysis_grounding(report, paragraph_map)
                return report
            except ValueError as e:
                if attempt >= max_attempts:
                    break
                prompt = (
                    f"{base_prompt}\n\n"
                    "## CORRECTION REQUIRED (previous attempt failed grounding)\n"
                    f"{e}\n"
                    "Re-emit the FULL analysis. Every finding.source_quote MUST "
                    "be an exact verbatim substring of its cited [P_XXXX] "
                    "paragraph. Drop any finding you cannot ground."
                )
        return report

    def build_llm_critic(
        self,
        target_document: str,
        lens_name: str,
        analysis_report: LensAnalysisReport,
        llm_provider,
    ) -> LensCriticReport:
        lens_config = load_lens(lens_name, self.lens_dir)
        annotated, _ = assign_paragraph_ids(target_document)
        prompt = (
            "Red-team the supplied lens analysis against the source document "
            "and lens instructions.\n"
            "Hard rules:\n"
            "- Judge whether the analysis overclaims, misses tensions, ignores "
            "focus areas, or uses weak support.\n"
            "- Every critique.source_quote, when present, must be an exact "
            "substring from the cited [P_XXXX] paragraph.\n"
            "- Do not introduce outside facts. Critique only against the "
            "supplied document, lens config, and analysis report.\n"
            "- Set passed=false if there is any error-severity critique.\n\n"
            f"Lens ID: {lens_name}\n"
            f"Lens Name: {lens_config.get('name', lens_name)}\n"
            f"Focus Areas: {lens_config.get('focus_areas', []) or []}\n"
            f"Analysis Prompt:\n{lens_config.get('analysis_prompt', '')}\n\n"
            f"Document:\n{annotated}\n\n"
            f"Analysis Report:\n{analysis_report.model_dump_json(indent=2)}"
        )
        return llm_provider.generate_structured_output(prompt, LensCriticReport)

    @staticmethod
    def _verify_analysis_grounding(
        report: LensAnalysisReport,
        paragraph_map: dict[str, str],
    ) -> None:
        for finding in report.findings:
            source = paragraph_map.get(finding.paragraph_id)
            if source is None:
                raise ValueError(
                    f"LLM lens analysis used unknown paragraph_id: {finding.paragraph_id}"
                )
            if not quote_in(finding.source_quote, source):
                raise ValueError(
                    "LLM lens analysis source_quote is not present in paragraph "
                    f"{finding.paragraph_id}: {finding.source_quote}"
                )

    @staticmethod
    def render_analysis(report: LensAnalysisReport) -> str:
        lines = [
            "# Lens LLM Analysis",
            "",
            f"- **Lens**: {report.lens}",
            "",
            "## Executive Summary",
            report.executive_summary,
            "",
            "## Findings",
        ]
        if report.findings:
            for finding in report.findings:
                lines.append(f"### {finding.focus_area} ({finding.paragraph_id})")
                lines.append(f"> {finding.source_quote}")
                lines.append("")
                lines.append(finding.analysis)
        else:
            lines.append("_No findings returned._")

        lines.append("\n## Limitations")
        if report.limitations:
            lines.extend(f"- {item}" for item in report.limitations)
        else:
            lines.append("- No limitations returned.")
        return "\n".join(lines)

    @staticmethod
    def render_critic(report: LensCriticReport) -> str:
        lines = [
            "# Lens LLM Critic",
            "",
            f"- **Passed**: `{report.passed}`",
            f"- **Risk Level**: `{report.risk_level}`",
            "",
            "## Summary",
            report.summary,
            "",
            "## Critiques",
        ]
        if report.critiques:
            for idx, critique in enumerate(report.critiques, 1):
                lines.append(f"### [{idx}] {critique.issue_type} ({critique.severity})")
                if critique.paragraph_id:
                    lines.append(f"- Paragraph: `{critique.paragraph_id}`")
                if critique.source_quote:
                    lines.append(f"> {critique.source_quote}")
                lines.append("")
                lines.append(critique.critique)
                lines.append("")
                lines.append(f"Recommendation: {critique.recommendation}")
        else:
            lines.append("_No critiques returned._")
        return "\n".join(lines)

    def print_brief(self, brief: str) -> None:
        self.console.print(Panel(brief, title="👓 Source-Bound Lens Brief", border_style="blue"))
        self.console.print(
            "\n[bold yellow]⚠️ 실 LLM 해석 리포트가 아니라, 원문 문단에 묶인 "
            "분석 준비용 brief입니다.[/bold yellow]"
        )

    def analyze(self, target_document: str, lens_name: str) -> bool:
        self.console.print(
            f"\n[bold magenta]🎯 [Lens Briefing Scaffold] (렌즈: {lens_name})[/bold magenta]"
        )
        try:
            brief = self.build_brief(target_document, lens_name)
        except LensNotFoundError as e:
            self.console.print(f"[bold red]❌ Error: {e}[/bold red]")
            return False

        self.print_brief(brief)
        return True
