from abc import ABC, abstractmethod
from typing import Dict, Any
from pydantic import BaseModel

class BaseLLMProvider(ABC):
    """
    모든 LLM 플러그인의 추상 기본 클래스입니다.
    어떤 모델(OpenAI, Anthropic, Gemini 등)을 사용하든 동일한 인터페이스로 Pydantic 스키마를 반환해야 합니다.
    """
    @abstractmethod
    def generate_structured_output(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        pass

class MockProvider(BaseLLMProvider):
    """
    안티그래비티 IDE 환경 등 API 키 없이 즉시 가동(엔진 테스트)하기 위한 Mock 플러그인입니다.
    """
    def generate_structured_output(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        # Pydantic 스키마의 더미 데이터를 자동 생성하여 반환 (테스트용)
        # 실제로는 schema.model_construct() 등을 사용하거나 정의된 더미 객체를 반환합니다.
        from src.ontology.extractor import OntologyMap, Node, Edge, EntityClass, RelationPredicate
        
        return OntologyMap(
            nodes=[
                Node(id="n1", label="Mock Artifact", entity_class=EntityClass.ARTIFACT, paragraph_id="P_01"),
                Node(id="n2", label="Mock Concept", entity_class=EntityClass.CONCEPT, paragraph_id="P_02")
            ],
            edges=[
                Edge(source_id="n1", target_id="n2", predicate=RelationPredicate.USES_METHOD, reasoning="Auto-generated mock relation.")
            ]
        )

class OpenAIProvider(BaseLLMProvider):
    """OpenAI API 플러그인 (gpt-4o)"""
    def __init__(self, api_key: str):
        self.api_key = api_key
        
    def generate_structured_output(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        # TODO: openai.beta.chat.completions.parse() 구현
        raise NotImplementedError("OpenAI API 연결은 향후 플러그인에서 활성화됩니다.")

class AnthropicProvider(BaseLLMProvider):
    """Anthropic API 플러그인 (claude-3.5-sonnet)"""
    def __init__(self, api_key: str):
        self.api_key = api_key
        
    def generate_structured_output(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        # TODO: Instructor 라이브러리 등을 통한 Claude Tool calling 연결
        raise NotImplementedError("Anthropic API 연결은 향후 플러그인에서 활성화됩니다.")
