"""Phase 3 — 에이전트 피어 리뷰 패널 모듈 (PeerReviewPanel).

작성된 학술 초안(DraftReport)을 입력받아 5인 에이전트 패널(Ella, Miranda, Methodologist,
Devil's Advocate, Chief Editor)이 다각도로 비평하고 최종 게재 판정(Decision) 및 점수를 부여한다.
비평 자체의 할루시네이션을 차단하기 위해, 리뷰어들의 비평문 내 source_quotes가 실제 초안
텍스트에 실존하는지 접지(grounding) 검증을 수행한다.
"""

import os
from typing import List, Literal

import yaml
from pydantic import BaseModel, Field
from rich.console import Console

from omni_academic.draft.scribe import DraftReport

console = Console()

class PanelistReview(BaseModel):
    panelist: Literal["Ella", "Miranda", "Methodologist", "Devil's Advocate"]
    score: int = Field(description="Score out of 100")
    feedback: str = Field(description="Detailed critique and suggestions based on focus areas")
    source_quotes: List[str] = Field(
        default_factory=list,
        description="Direct quotes from the draft text that this panelist's feedback is based on"
    )

class ReviewReport(BaseModel):
    reviews: List[PanelistReview]
    editor_decision: Literal["Accept", "Major Revision", "Reject"]
    editor_summary: str = Field(description="Synthesized feedback and final verdict from the Editor-in-Chief")
    final_score: int = Field(description="Synthesized or average final score (0-100)")

class PeerReviewPanel:
    """학술 초안 피어 리뷰 패널 오케스트레이터."""

    def __init__(self, lens_dir: str = "lenses"):
        self.lens_dir = lens_dir
        self.console = console
        self.last_attempts: int = 0

    def _load_panel_config(self) -> dict:
        path = os.path.join(self.lens_dir, "review_panel.yaml")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Review panel configuration not found at: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    @staticmethod
    def _render_draft_for_review(draft: DraftReport) -> str:
        lines = [
            f"Paper Title: {draft.title}",
            f"Thesis: {draft.thesis}",
            "",
            "--- Draft Content ---"
        ]
        for sec in draft.sections:
            lines.append(f"[{sec.heading}]")
            lines.append(sec.body)
            lines.append("")
        lines.append("--- Claims Ledger ---")
        for claim in draft.claims:
            node = f" (Node: {claim.node_id})" if claim.node_id else ""
            lines.append(f"- [{claim.claim_id}] ({claim.paragraph_id}{node}): {claim.source_quote}")
        lines.append("")
        lines.append("--- Open Tensions (Aporia) ---")
        if draft.open_tensions:
            lines.extend(f"- {t}" for t in draft.open_tensions)
        else:
            lines.append("- None recorded.")
        return "\n".join(lines)

    def build_review(
        self,
        draft: DraftReport,
        lens_name: str,
        llm_provider,
        max_attempts: int = 2
    ) -> ReviewReport:
        """초안에 대해 5인 패널 리뷰를 빌드하고 source_quotes에 대한 grounding 검증을 수행한다."""
        panel_cfg = self._load_panel_config()
        draft_text = self._render_draft_for_review(draft)

        # 렌즈 지침 가져오기
        from omni_academic.config.lens import LensNotFoundError, load_lens
        try:
            lens_cfg = load_lens(lens_name, self.lens_dir)
        except LensNotFoundError:
            lens_cfg = {}

        panelists_info = []
        for name, info in panel_cfg.get("panelists", {}).items():
            panelists_info.append(
                f"- Panelist: {name}\n"
                f"  Role: {info.get('role')}\n"
                f"  Focus: {info.get('focus')}\n"
                f"  Instructions:\n{info.get('prompt')}"
            )
        panelists_str = "\n\n".join(panelists_info)

        base_prompt = (
            "You are the Peer Review Panel (comprising Ella, Miranda, Methodologist, and Devil's Advocate, "
            "synthesized by the Editor-in-Chief).\n"
            "Evaluate the provided academic draft report strictly based on the panel rules and domain lens.\n\n"
            "## Panelist Guidelines:\n"
            f"{panelists_str}\n\n"
            f"## Target Domain Lens: {lens_cfg.get('name', lens_name)}\n"
            f"Lens Focus Areas: {lens_cfg.get('focus_areas', [])}\n"
            f"Lens Analysis Directive:\n{lens_cfg.get('analysis_prompt', '')}\n\n"
            "## Rules for source_quotes:\n"
            "- Every panelist's source_quotes MUST be exact verbatim substrings of the draft content (title, thesis, section bodies, claims, or open tensions).\n"
            "- Do not synthesize or edit the source_quotes.\n\n"
            f"## Draft Report for Review:\n{draft_text}"
        )
        prompt = base_prompt
        report = None
        for attempt in range(1, max(1, max_attempts) + 1):
            self.last_attempts = attempt
            report = llm_provider.generate_structured_output(prompt, ReviewReport)
            try:
                self._verify_review_grounding(report, draft)
                return report
            except ValueError as e:
                self.console.print(f"[yellow]⚠️ Review grounding check failed (Attempt {attempt}/{max_attempts}): {e}[/yellow]")
                if attempt >= max_attempts:
                    break
                prompt = (
                    f"{base_prompt}\n\n"
                    "## CORRECTION REQUIRED (previous attempt failed peer-review quote grounding)\n"
                    f"{e}\n"
                    "Please re-emit the ReviewReport. Ensure every panelist.source_quotes is present "
                    "verbatim in the draft text. Do not invent quotes."
                )
        return report

    @staticmethod
    def _verify_review_grounding(report: ReviewReport, draft: DraftReport) -> None:
        # 드래프트의 전체 텍스트 수집 (어디선가 매칭되어야 함)
        draft_corpus = [
            draft.title.strip(),
            draft.thesis.strip()
        ]
        for sec in draft.sections:
            draft_corpus.append(sec.body.strip())
        for claim in draft.claims:
            draft_corpus.append(claim.source_quote.strip())
        for tension in draft.open_tensions:
            draft_corpus.append(tension.strip())

        for rev in report.reviews:
            for quote in rev.source_quotes:
                q = quote.strip()
                if not q:
                    continue
                # 전체 코퍼스 중 하나에 부분문자열로 들어있는지 검증
                found = False
                for corpus_text in draft_corpus:
                    if q in corpus_text:
                        found = True
                        break
                if not found:
                    raise ValueError(
                        f"Panelist '{rev.panelist}' referenced a source quote that is absent "
                        f"verbatim in the draft: \"{quote}\""
                    )

    @staticmethod
    def render_review(report: ReviewReport) -> str:
        lines = [
            "# Academic Peer Review Report",
            "",
            f"## Editor-in-Chief Verdict: **{report.editor_decision}** (Final Score: `{report.final_score}/100`)",
            "",
            "### Editor's Summary Synthesis",
            report.editor_summary,
            "",
            "---",
            "",
            "## Panelists Detailed Evaluations"
        ]
        for rev in report.reviews:
            lines.append(f"### Reviewer: **{rev.panelist}**")
            lines.append(f"- **Score**: `{rev.score}/100`")
            lines.append("")
            lines.append(rev.feedback)
            lines.append("")
            if rev.source_quotes:
                lines.append("**Anchored Quotes from Draft:**")
                for q in rev.source_quotes:
                    lines.append(f'> "{q}"')
                lines.append("")
            lines.append("---")
        return "\n".join(lines)
