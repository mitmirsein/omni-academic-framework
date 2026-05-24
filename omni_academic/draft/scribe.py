"""Phase 2 — 에이전트 집필 모듈 (ScribeAgent).

온톨로지 맵 + 원문 문단맵을 입력받아 논문 초안의 섹션별 본문을 생성한다.
헌법 §3(무손실·환각 차단)을 '생성'에 적용하기 위해 **본문(prose)과 주장
원장(claims ledger)을 분리**한다:

- 본문은 자유 서술이되, 모든 사실 주장은 `claims[]`에 등재되고 본문에서
  `[C1]` 앵커로 참조된다.
- 각 claim은 실존 `paragraph_id` + 그 문단의 verbatim `source_quote`에 묶인다
  (선택적으로 온톨로지 `node_id`에도).
- 미해소 긴장/모순은 평탄화하지 않고 `open_tensions`에 보존한다(§3).

grounding이 깨지면 구체 오류를 피드백해 재시도하는 self-correcting 루프는
`LensAnalyzer.build_llm_analysis`의 운용 패턴을 그대로 계승한다.
"""

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field
from rich.console import Console

from omni_academic.config.lens import load_lens
from omni_academic.ontology.extractor import OntologyMap
from omni_academic.text.paragraphs import assign_paragraph_ids

console = Console()

_CLAIM_REF_RE = re.compile(r"\[(C\d+)\]")

SECTION_TYPES = (
    "introduction",
    "related_work",
    "methodology",
    "discussion",
    "conclusion",
)


class DraftClaim(BaseModel):
    claim_id: str = Field(description="본문에서 [C1]처럼 참조되는 고유 식별자")
    paragraph_id: str = Field(description="근거 문단 ID, 예: P_0001")
    source_quote: str = Field(description="paragraph_id 문단에서 그대로 복사한 verbatim 인용")
    node_id: Optional[str] = Field(
        default=None, description="(선택) 이 주장을 뒷받침하는 온톨로지 노드 id"
    )


class DraftSection(BaseModel):
    section_type: Literal[
        "introduction", "related_work", "methodology", "discussion", "conclusion"
    ]
    heading: str
    body: str = Field(description="서술 본문. 사실 주장은 [C1] 앵커로 표기")
    claim_ids: list[str] = Field(
        default_factory=list, description="이 섹션 본문이 사용한 claim_id 목록"
    )


class DraftReport(BaseModel):
    title: str
    thesis: str
    sections: list[DraftSection]
    claims: list[DraftClaim]
    open_tensions: list[str] = Field(
        default_factory=list,
        description="평탄화하지 않고 보존한 원문의 미해소 긴장/모순",
    )


class ScribeAgent:
    """온톨로지-근거 기반 섹션별 초안 생성기."""

    def __init__(self, lens_dir: str = "lenses"):
        self.lens_dir = lens_dir
        self.console = console
        self.last_attempts: int = 0

    @staticmethod
    def _ontology_digest(ontology: OntologyMap) -> str:
        lines = ["Nodes:"]
        for n in ontology.nodes:
            lines.append(
                f"- {n.id} [{n.entity_class.value}] {n.label} "
                f"(paragraph: {n.paragraph_id})"
            )
        lines.append("Edges:")
        for e in ontology.edges:
            lines.append(
                f"- {e.source_id} --({e.predicate.value})--> {e.target_id}: {e.reasoning}"
            )
        return "\n".join(lines)

    def build_draft(
        self,
        target_document: str,
        ontology: OntologyMap,
        lens_name: str,
        llm_provider,
        max_attempts: int = 2,
    ) -> DraftReport:
        """초안을 생성하고 grounding 위반 시 구체 오류를 피드백해 재시도한다.

        최대 시도 후에도 grounding이 깨지면 마지막 리포트를 반환한다 — 크래시
        대신 DraftComplianceAuditor가 결정론적으로 실패를 기록하게 한다.
        """
        lens_config = load_lens(lens_name, self.lens_dir)
        annotated, paragraph_map = assign_paragraph_ids(target_document)
        node_ids = {n.id for n in ontology.nodes}

        base_prompt = (
            "Write a structured academic paper draft grounded ONLY in the supplied "
            "ontology map and source paragraphs.\n"
            "Hard rules:\n"
            "- Decompose the draft into sections (introduction, related_work, "
            "methodology, discussion, conclusion as appropriate).\n"
            "- Prose body is allowed, but EVERY factual claim must be registered "
            "in claims[] and referenced in the body with its [C#] anchor.\n"
            "- Every claim.paragraph_id must be a real [P_XXXX] marker from the "
            "source, and claim.source_quote must be an exact substring of that "
            "paragraph.\n"
            "- If a claim maps to an ontology node, set claim.node_id to a real "
            "node id.\n"
            "- Do NOT introduce facts, citations, or numbers absent from the "
            "source. Do NOT flatten contradictions — record unresolved tensions "
            "in open_tensions.\n\n"
            f"Lens: {lens_config.get('name', lens_name)} ({lens_name})\n"
            f"Focus Areas: {lens_config.get('focus_areas', []) or []}\n"
            f"Lens Prompt:\n{lens_config.get('analysis_prompt', '')}\n\n"
            f"Ontology Map:\n{self._ontology_digest(ontology)}\n\n"
            f"Source Paragraphs:\n{annotated}"
        )
        prompt = base_prompt
        report = None
        for attempt in range(1, max(1, max_attempts) + 1):
            self.last_attempts = attempt
            report = llm_provider.generate_structured_output(prompt, DraftReport)
            try:
                self._verify_grounding(report, paragraph_map, node_ids)
                return report
            except ValueError as e:
                if attempt >= max_attempts:
                    break
                prompt = (
                    f"{base_prompt}\n\n"
                    "## CORRECTION REQUIRED (previous attempt failed grounding)\n"
                    f"{e}\n"
                    "Re-emit the FULL draft. Every claim.source_quote MUST be an "
                    "exact verbatim substring of its cited [P_XXXX] paragraph, and "
                    "every [C#] used in a body MUST exist in claims. Drop any claim "
                    "you cannot ground."
                )
        return report

    @staticmethod
    def _verify_grounding(
        report: DraftReport,
        paragraph_map: dict[str, str],
        node_ids: set[str],
    ) -> None:
        claim_ids = {c.claim_id for c in report.claims}
        for claim in report.claims:
            source = paragraph_map.get(claim.paragraph_id)
            if source is None:
                raise ValueError(
                    f"draft claim {claim.claim_id} used unknown paragraph_id: "
                    f"{claim.paragraph_id}"
                )
            if claim.source_quote not in source:
                raise ValueError(
                    f"draft claim {claim.claim_id} source_quote is not present in "
                    f"paragraph {claim.paragraph_id}: {claim.source_quote}"
                )
            if claim.node_id is not None and claim.node_id not in node_ids:
                raise ValueError(
                    f"draft claim {claim.claim_id} referenced unknown node_id: "
                    f"{claim.node_id}"
                )
        for section in report.sections:
            for ref in _CLAIM_REF_RE.findall(section.body):
                if ref not in claim_ids:
                    raise ValueError(
                        f"section '{section.heading}' body references undeclared "
                        f"claim anchor: [{ref}]"
                    )

    @staticmethod
    def render_draft(report: DraftReport) -> str:
        lines = [f"# {report.title}", "", f"*Thesis*: {report.thesis}", ""]
        for section in report.sections:
            lines.append(f"## {section.heading}")
            lines.append("")
            lines.append(section.body)
            lines.append("")
        lines.append("## Open Tensions (preserved, not flattened)")
        if report.open_tensions:
            lines.extend(f"- {t}" for t in report.open_tensions)
        else:
            lines.append("- None recorded.")
        lines.append("")
        lines.append("## Claims Ledger (source-bound)")
        for claim in report.claims:
            node = f", node `{claim.node_id}`" if claim.node_id else ""
            lines.append(
                f"- `[{claim.claim_id}]` (`{claim.paragraph_id}`{node}): "
                f"\"{claim.source_quote}\""
            )
        return "\n".join(lines)
