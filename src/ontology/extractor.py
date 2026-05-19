from enum import Enum
from typing import List

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

    def extract(self, document_text: str) -> OntologyMap:
        self.console.print(f"[bold magenta]🕸️ 텍스트에서 Ontology Map(RDF Triples)을 추출 중입니다... (Provider: {self.llm_provider.__class__.__name__})[/bold magenta]")
        
        prompt = f"Analyze the following text and return a structured ontology map:\n\n{document_text}"
        
        # LLM Provider에 의존하여 Pydantic 모델을 강제 반환받음
        ontology_map = self.llm_provider.generate_structured_output(prompt, OntologyMap)
        
        return ontology_map
