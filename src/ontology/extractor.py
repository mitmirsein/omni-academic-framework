import json
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

class Edge(BaseModel):
    source_id: str
    target_id: str
    predicate: RelationPredicate
    reasoning: str = Field(description="이 엣지(관계)가 성립한다고 판단한 원문의 짧은 근거")

class OntologyMap(BaseModel):
    nodes: List[Node]
    edges: List[Edge]

class OntologyExtractor:
    """
    Omni-Academic Ontology Extractor (Phase C)
    깊은 의미 해석을 배제하고 텍스트를 범용 클래스와 표준 관계어휘(Triples) 기반의 
    JSON 지형도로 구조화하는 모듈입니다.
    """
    def __init__(self):
        self.console = console

    def extract(self, document_text: str) -> OntologyMap:
        self.console.print("[bold magenta]🕸️ 텍스트에서 Ontology Map(RDF Triples)을 추출 중입니다...[/bold magenta]")
        
        # TODO: 실제 LLM (Gemini/Claude) 호출 시 Pydantic Schema(OntologyMap)를 
        # Output Format으로 강제하여 넘겨주는 로직이 들어갈 자리입니다.
        # 현재는 아키텍처 증명을 위해 Hardcoded Mock Data를 반환합니다.
        
        mock_map = OntologyMap(
            nodes=[
                Node(id="n1", label="Transformer", entity_class=EntityClass.ARTIFACT, paragraph_id="P_01"),
                Node(id="n2", label="Long-term Dependency", entity_class=EntityClass.LIMITATION, paragraph_id="P_01"),
                Node(id="n3", label="Self-Attention", entity_class=EntityClass.CONCEPT, paragraph_id="P_02"),
            ],
            edges=[
                Edge(
                    source_id="n1", 
                    target_id="n2", 
                    predicate=RelationPredicate.ADDRESSES,
                    reasoning="The paper states Transformer eliminates long-term dependency problems."
                ),
                Edge(
                    source_id="n1",
                    target_id="n3",
                    predicate=RelationPredicate.USES_METHOD,
                    reasoning="Transformer is entirely built on self-attention mechanism."
                )
            ]
        )
        return mock_map
