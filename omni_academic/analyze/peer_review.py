"""Phase 3 — 에이전트 피어 리뷰 패널 모듈 (PeerReviewPanel).

작성된 학술 초안(DraftReport)을 입력받아 4인 리뷰어 패널(Ella, Miranda, Methodologist,
Devil's Advocate)과 Chief Editor가 다각도로 비평하고 최종 게재 판정(Decision) 및 점수를 부여한다.
비평 자체의 할루시네이션을 차단하기 위해, 리뷰어들의 비평문 내 source_quotes가 실제 초안
텍스트에 실존하는지 접지(grounding) 검증을 수행한다.
"""

import os
from typing import List, Literal

import yaml
from pydantic import BaseModel, Field
from rich.console import Console

from omni_academic.draft.scribe import DraftReport
from omni_academic.text.grounding import canon_quote, quote_in

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


class EditorSynthesis(BaseModel):
    """독립 패널 모드에서 Chief Editor 종합 호출의 단독 출력 스키마."""
    editor_decision: Literal["Accept", "Major Revision", "Reject"]
    editor_summary: str = Field(description="Synthesis of the independent panelist reviews")
    final_score: int = Field(description="Final synthesized score (0-100)")

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
    def _panelist_items(panel_cfg: dict) -> list[dict]:
        panelists = panel_cfg.get("panelists", [])
        if isinstance(panelists, dict):
            return [
                {"id": name, "name": name, **(info or {})}
                for name, info in panelists.items()
            ]
        return list(panelists or [])

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
        """초안에 대해 reviewer 패널 리뷰를 빌드하고 source_quotes grounding 검증을 수행한다."""
        panel_cfg = self._load_panel_config()
        draft_text = self._render_draft_for_review(draft)

        # 렌즈 지침 가져오기
        from omni_academic.config.lens import LensNotFoundError, load_lens
        try:
            lens_cfg = load_lens(lens_name, self.lens_dir)
        except LensNotFoundError:
            lens_cfg = {}

        panelists_info = []
        for info in self._panelist_items(panel_cfg):
            name = info.get("name") or info.get("id")
            panelists_info.append(
                f"- Panelist: {name}\n"
                f"  Role: {info.get('role')}\n"
                f"  Focus: {info.get('focus')}\n"
                f"  Instructions:\n{info.get('prompt')}"
            )
        panelists_str = "\n\n".join(panelists_info)
        chief_editor = panel_cfg.get("chief_editor") or {}
        chief_editor_str = (
            f"- Editor: {chief_editor.get('name', 'Chief Editor')}\n"
            f"  Role: {chief_editor.get('role', 'Synthesis and publication decision')}\n"
            f"  Instructions:\n{chief_editor.get('prompt', '')}\n"
            f"  Decision Rubric: {chief_editor.get('decision_rubric', {})}\n"
            f"  Score Rubric: {chief_editor.get('score_rubric', {})}"
        )

        base_prompt = (
            "You are the Peer Review Panel (comprising Ella, Miranda, Methodologist, and Devil's Advocate, "
            "synthesized by the Editor-in-Chief).\n"
            "Evaluate the provided academic draft report strictly based on the panel rules and domain lens.\n\n"
            "## Panelist Guidelines:\n"
            f"{panelists_str}\n\n"
            "## Chief Editor Guidelines:\n"
            f"{chief_editor_str}\n\n"
            f"## Target Domain Lens: {lens_cfg.get('name', lens_name)}\n"
            f"Lens Focus Areas: {lens_cfg.get('focus_areas', [])}\n"
            f"Lens Analysis Directive:\n{lens_cfg.get('analysis_prompt', '')}\n\n"
            "## Rules for source_quotes:\n"
            "- Every panelist's source_quotes MUST be exact verbatim substrings of the draft content (title, thesis, section bodies, claims, or open tensions).\n"
            "- Do not synthesize or edit the source_quotes.\n\n"
            f"## Draft Report for Review:\n{draft_text}"
        )
        prompt = base_prompt
        last_error = None
        for attempt in range(1, max(1, max_attempts) + 1):
            self.last_attempts = attempt
            report = llm_provider.generate_structured_output(prompt, ReviewReport)
            try:
                self._verify_review_grounding(report, draft)
                return report
            except ValueError as e:
                last_error = e
                self.console.print(f"[yellow]⚠️ Review grounding check failed (Attempt {attempt}/{max_attempts}): {e}[/yellow]")
                prompt = (
                    f"{base_prompt}\n\n"
                    "## CORRECTION REQUIRED (previous attempt failed peer-review quote grounding)\n"
                    f"{e}\n"
                    "Please re-emit the ReviewReport. Ensure every panelist.source_quotes is present "
                    "verbatim in the draft text. Do not invent quotes."
                )
        raise ValueError(
            "Peer review grounding failed after "
            f"{self.last_attempts} attempt(s): {last_error}"
        )

    def build_review_independent(
        self,
        draft: DraftReport,
        lens_name: str,
        llm_provider,
        max_attempts: int = 2,
    ) -> ReviewReport:
        """패널리스트별 독립 LLM 호출(4회) + Chief Editor 종합 호출(1회).

        single-shot 모드는 한 컨텍스트가 모든 페르소나를 쓰므로 관점 간
        상관이 높다 — 이 모드는 각 패널리스트가 타 패널의 지침/리뷰를 보지
        못하게 격리해 앵커링을 차단한다(비용 약 5배, opt-in).

        grounding 검증·재시도는 패널리스트 단위로 격리되며, 한 패널리스트가
        재시도 후에도 실패하면 ValueError로 hard fail한다(현행 semantics 유지).
        `last_attempts`는 이 리뷰에서 수행된 총 LLM 호출 수를 기록한다.
        """
        panel_cfg = self._load_panel_config()
        draft_text = self._render_draft_for_review(draft)

        from omni_academic.config.lens import LensNotFoundError, load_lens
        try:
            lens_cfg = load_lens(lens_name, self.lens_dir)
        except LensNotFoundError:
            lens_cfg = {}

        self.last_attempts = 0
        reviews: List[PanelistReview] = []
        for info in self._panelist_items(panel_cfg):
            name = str(info.get("name") or info.get("id"))
            base_prompt = (
                "You are ONE peer reviewer on an academic panel. You do NOT see "
                "the other panelists' guidelines or reviews — evaluate strictly "
                "from your own perspective.\n"
                f"Panelist Name: {name}\n"
                f"Role: {info.get('role')}\n"
                f"Focus: {info.get('focus')}\n"
                f"Instructions:\n{info.get('prompt')}\n\n"
                f"## Target Domain Lens: {lens_cfg.get('name', lens_name)}\n"
                f"Lens Focus Areas: {lens_cfg.get('focus_areas', [])}\n\n"
                "## Rules:\n"
                f"- The panelist field MUST be exactly: {name}\n"
                "- Every source_quote MUST be an exact verbatim substring of the "
                "draft content (title, thesis, section bodies, claims, or open "
                "tensions). Do not synthesize or edit quotes.\n"
                "- Score 0-100 honestly.\n\n"
                f"## Draft Report for Review:\n{draft_text}"
            )
            prompt = base_prompt
            review = None
            for attempt in range(1, max(1, max_attempts) + 1):
                self.last_attempts += 1
                review = llm_provider.generate_structured_output(prompt, PanelistReview)
                # 패널리스트 정체성은 오케스트레이터가 권위를 갖는다 —
                # 모델이 다른 이름을 주장해도 이 호출은 name의 평가다.
                review.panelist = name
                try:
                    self._verify_panelist_grounding(review, draft)
                    break
                except ValueError as e:
                    if attempt >= max_attempts:
                        raise ValueError(
                            "Independent review grounding failed for panelist "
                            f"'{name}' after {attempt} attempt(s): {e}"
                        )
                    self.console.print(
                        f"[yellow]⚠️ {name} grounding 실패 (시도 {attempt}/"
                        f"{max_attempts}) → 교정 재시도: {e}[/yellow]"
                    )
                    prompt = (
                        f"{base_prompt}\n\n"
                        "## CORRECTION REQUIRED (previous attempt failed quote grounding)\n"
                        f"{e}\n"
                        "Re-emit your review. Every source_quote must be present "
                        "verbatim in the draft text. Do not invent quotes."
                    )
            reviews.append(review)

        chief_editor = panel_cfg.get("chief_editor") or {}
        panel_digest = "\n\n".join(
            f"### {r.panelist} (score: {r.score}/100)\n{r.feedback}\n"
            + "\n".join(f'> "{q}"' for q in r.source_quotes)
            for r in reviews
        )
        editor_prompt = (
            "You are the Editor-in-Chief synthesizing INDEPENDENT panelist "
            "reviews (the panelists did not see each other).\n"
            f"Role: {chief_editor.get('role', 'Synthesis and publication decision')}\n"
            f"Instructions:\n{chief_editor.get('prompt', '')}\n"
            f"Decision Rubric: {chief_editor.get('decision_rubric', {})}\n"
            f"Score Rubric: {chief_editor.get('score_rubric', {})}\n\n"
            f"## Independent Panelist Reviews:\n{panel_digest}\n\n"
            f"## Draft Under Review:\n{draft_text}"
        )
        self.last_attempts += 1
        synthesis = llm_provider.generate_structured_output(editor_prompt, EditorSynthesis)

        report = ReviewReport(
            reviews=reviews,
            editor_decision=synthesis.editor_decision,
            editor_summary=synthesis.editor_summary,
            final_score=synthesis.final_score,
        )
        # 조립 후 전체 결정론 재검증(저렴) — 패널 단위 검증의 회귀 방지선.
        self._verify_review_grounding(report, draft)
        return report

    @staticmethod
    def _draft_corpus(draft: DraftReport) -> list[str]:
        corpus = [draft.title.strip(), draft.thesis.strip()]
        corpus.extend(sec.body.strip() for sec in draft.sections)
        corpus.extend(claim.source_quote.strip() for claim in draft.claims)
        corpus.extend(tension.strip() for tension in draft.open_tensions)
        return corpus

    @classmethod
    def _verify_panelist_grounding(
        cls, review: PanelistReview, draft: DraftReport
    ) -> None:
        draft_corpus = cls._draft_corpus(draft)
        for quote in review.source_quotes:
            if not canon_quote(quote):
                continue
            # 전체 코퍼스 중 하나에 (정규화 기준) 부분문자열로 들어있는지 검증
            if not any(quote_in(quote, corpus_text) for corpus_text in draft_corpus):
                raise ValueError(
                    f"Panelist '{review.panelist}' referenced a source quote that is absent "
                    f"verbatim in the draft: \"{quote}\""
                )

    @classmethod
    def _verify_review_grounding(cls, report: ReviewReport, draft: DraftReport) -> None:
        for rev in report.reviews:
            cls._verify_panelist_grounding(rev, draft)

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
