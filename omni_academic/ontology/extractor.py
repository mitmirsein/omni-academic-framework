from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field
from rich.console import Console

console = Console()

class EntityClass(str, Enum):
    CONCEPT = "Concept"
    ACTOR = "Actor"
    METHOD = "Method"
    CLAIM = "Claim/Data"
    ARTIFACT = "Artifact/System"
    CONTEXT = "Context/Setting"
    LIMITATION = "Limitation/Gap"

class RelationPredicate(str, Enum):
    IS_A = "is_a"
    PART_OF = "part_of"
    BUILDS_ON = "builds_on"
    IS_DERIVED_FROM = "is_derived_from"
    CAUSES = "causes"
    CORRELATES_WITH = "correlates_with"
    SUPPORTS = "supports"
    CONFLICTS_WITH = "conflicts_with"
    # 양극이 *동시에 참으로 긍정되는* 환원 불가 역설(아포리아). CONFLICTS_WITH
    # (경합·배타, 한쪽이 다른 쪽을 무효화)와 구분된다. 헌법 §3: 이런 긴장은
    # 평탄화/해소하지 말고 양 노드를 보존한 채 이 술어로 묶는다. (도메인 무관:
    # 신학의 이중 술어, 물리의 파동-입자 이중성 등)
    IN_TENSION_WITH = "in_tension_with"
    ADDRESSES = "addresses"
    USES_METHOD = "uses_method"

class Node(BaseModel):
    id: str = Field(description="노드의 고유 식별자 (예: node_1)")
    label: str = Field(description="추출된 지식의 이름 (예: Transformer)")
    entity_class: EntityClass = Field(description="7대 범용 클래스 중 하나")
    paragraph_id: str = Field(description="이 지식이 기원한 원문의 문단 ID (Hallucination 방지용)")
    source_quote: str = Field(
        default="",
        description="paragraph_id 문단에서 그대로 복사한 근거 인용(verbatim, 환각 차단용)",
    )

class Edge(BaseModel):
    source_id: str
    target_id: str
    predicate: RelationPredicate
    reasoning: str = Field(description="이 엣지(관계)가 성립한다고 판단한 원문의 짧은 근거")
    source_quote: str = Field(
        default="",
        description="이 관계의 근거가 되는 원문 문단의 verbatim 인용",
    )

class OntologyMap(BaseModel):
    nodes: List[Node]
    edges: List[Edge]

class OntologyExtractor:
    """
    Omni-Academic Ontology Extractor (Phase C)
    깊은 의미 해석을 배제하고 텍스트를 범용 클래스와 표준 관계어휘(Triples) 기반의
    JSON 지형도로 구조화하는 모듈입니다.
    """
    def __init__(self, llm_provider=None):
        if llm_provider is None:
            raise ValueError(
                "OntologyExtractor: LLM provider를 명시적으로 주입해야 합니다. "
                "오프라인/테스트는 MockProvider를 직접 주입하거나 router의 --mock 플래그를 사용하세요."
            )
        self.console = console
        self.llm_provider = llm_provider
        self.last_attempts: int = 0

    def extract(
        self,
        document_text: str,
        directive: str = "",
        paragraph_map: Optional[dict] = None,
        max_attempts: int = 2,
    ) -> OntologyMap:
        """온톨로지를 추출하고, paragraph_map이 주어지면 grounding 위반 시
        구체 오류를 피드백해 재시도한다 (ScribeAgent/LensAnalyzer와 동일 패턴).

        최대 시도 후에도 grounding이 깨지면 마지막 맵을 반환한다 — 크래시
        대신 AuditGate가 결정론적으로 실패를 기록하게 한다.
        """
        self.console.print(f"[bold magenta]🕸️ 텍스트에서 Ontology Map(RDF Triples)을 추출 중입니다... (Provider: {self.llm_provider.__class__.__name__})[/bold magenta]")

        base_prompt = "Analyze the following text and return a structured ontology map."
        # 도메인 지시(렌즈 어댑터에서 주입). 코어는 도메인 용어를 모른다(헌법 §2):
        # 신학 등 분야별 아포리아 보존 강조는 lenses/*.yaml 의 ontology_directive 가 싣는다.
        if directive and directive.strip():
            base_prompt += (
                "\n\nDomain extraction directive (obey; preserve, do not flatten):\n"
                f"{directive.strip()}"
            )
        base_prompt += f"\n\n{document_text}"

        if paragraph_map is None:
            # grounding 검증 기준이 없으면 재시도 근거도 없다 → 1회 추출.
            self.last_attempts = 1
            return self.llm_provider.generate_structured_output(base_prompt, OntologyMap)

        prompt = base_prompt
        ontology_map = None
        for attempt in range(1, max(1, max_attempts) + 1):
            self.last_attempts = attempt
            ontology_map = self.llm_provider.generate_structured_output(prompt, OntologyMap)
            try:
                self._verify_grounding(ontology_map, paragraph_map)
                return ontology_map
            except ValueError as e:
                if attempt >= max_attempts:
                    break
                self.console.print(
                    f"[yellow]⚠️ Ontology grounding 실패 (시도 {attempt}/{max_attempts}) "
                    f"→ 교정 재시도: {e}[/yellow]"
                )
                prompt = (
                    f"{base_prompt}\n\n"
                    "## CORRECTION REQUIRED (previous attempt failed grounding)\n"
                    f"{e}\n"
                    "Re-emit the FULL ontology map. Every node.paragraph_id MUST be a "
                    "real [P_XXXX] marker from the supplied text, and every node/edge "
                    "source_quote MUST be an exact verbatim substring of the source. "
                    "Drop any node or edge you cannot ground."
                )
        return ontology_map

    @staticmethod
    def _verify_grounding(ontology: "OntologyMap", paragraph_map: dict) -> None:
        """재시도 루프용 경량 grounding 검증(공식 게이트는 AuditGate)."""
        from omni_academic.text.grounding import quote_in

        corpus = " ".join(paragraph_map.values())
        for node in ontology.nodes:
            if node.paragraph_id not in paragraph_map:
                raise ValueError(
                    f"ontology node {node.id} used unknown paragraph_id: "
                    f"{node.paragraph_id}"
                )
            if node.source_quote and not quote_in(
                node.source_quote, paragraph_map[node.paragraph_id]
            ):
                raise ValueError(
                    f"ontology node {node.id} source_quote is not present in "
                    f"paragraph {node.paragraph_id}: {node.source_quote}"
                )
        for edge in ontology.edges:
            if edge.source_quote and not quote_in(edge.source_quote, corpus):
                raise ValueError(
                    f"ontology edge {edge.source_id}->{edge.target_id} source_quote "
                    f"is not present in the source: {edge.source_quote}"
                )
