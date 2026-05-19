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
        # manifest-aware mock: 프롬프트의 실제 [P_XXXX] 문단을 파싱해
        # 존재하는 paragraph_id와 verbatim source_quote만 사용한다.
        # → AuditGate(grounding + quote-in-paragraph)를 정상 통과해야
        #   README의 clone-즉시 --mock 경로가 깨지지 않는다.
        import re

        if schema.__name__ == "LensAnalysisReport":
            import ast

            blocks = re.findall(r"\[(P_\d+)\]\s*(.+?)(?=\n\[P_\d+\]|\Z)", prompt, re.S)
            lens_match = re.search(r"^Lens ID:\s*(.+)$", prompt, re.M)
            lens = lens_match.group(1).strip() if lens_match else "mock"
            focus_match = re.search(r"^Focus Areas:\s*(.+)$", prompt, re.M)
            try:
                focus_areas = ast.literal_eval(focus_match.group(1)) if focus_match else []
            except (SyntaxError, ValueError):
                focus_areas = []
            findings = []
            for i, (pid, text) in enumerate(blocks[:3], 1):
                quote = text.strip()[:80]
                findings.append({
                    "focus_area": (
                        str(focus_areas[i - 1])
                        if i - 1 < len(focus_areas)
                        else f"Mock Focus {i}"
                    ),
                    "paragraph_id": pid,
                    "source_quote": quote,
                    "analysis": "Mock source-bound analysis for pipeline verification.",
                })
            return schema.model_validate({
                "lens": lens,
                "executive_summary": (
                    "Mock LLM analysis generated from real paragraph anchors."
                ),
                "findings": findings,
                "limitations": ["MockProvider output is not interpretive analysis."],
            })

        if schema.__name__ == "LensCriticReport":
            return schema.model_validate({
                "passed": True,
                "risk_level": "low",
                "summary": (
                    "Mock critic found no blocking issue. This validates the "
                    "critic artifact path, not real analytical quality."
                ),
                "critiques": [],
            })

        from src.ontology.extractor import (
            Edge,
            EntityClass,
            Node,
            OntologyMap,
            RelationPredicate,
        )

        blocks = re.findall(r"\[(P_\d+)\]\s*(.+?)(?=\n\[P_\d+\]|\Z)", prompt, re.S)
        if not blocks:
            # 문단을 못 찾으면 정직하게 빈 그래프(감사에서 NO 노드 → 통과는
            # 하되 내용 0 — 가짜 P_01 환각보다 정직하다).
            return OntologyMap(nodes=[], edges=[])

        nodes, edges = [], []
        for i, (pid, text) in enumerate(blocks[:3], 1):
            quote = " ".join(text.split())[:60]
            nodes.append(Node(
                id=f"n{i}", label=f"Mock Concept {i}",
                entity_class=EntityClass.CONCEPT,
                paragraph_id=pid, source_quote=quote,
            ))
        for i in range(len(nodes) - 1):
            edges.append(Edge(
                source_id=nodes[i].id, target_id=nodes[i + 1].id,
                predicate=RelationPredicate.BUILDS_ON,
                reasoning="Auto-generated mock relation for pipeline test.",
                source_quote=nodes[i].source_quote,
            ))
        return OntologyMap(nodes=nodes, edges=edges)

class OpenAIProvider(BaseLLMProvider):
    """OpenAI API 플러그인 (gpt-4o)"""
    def __init__(self, api_key: str):
        self.api_key = api_key
        
    def generate_structured_output(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        # TODO: openai.beta.chat.completions.parse() 구현
        raise NotImplementedError("OpenAI API 연결은 향후 플러그인에서 활성화됩니다.")

class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude 플러그인.

    강제 tool-use(`tool_choice`)로 Pydantic 스키마를 그대로 반환받고,
    안정적인 하네스 지침(system)에 prompt caching을 건다. 도메인 규칙은
    여기에 하드코딩하지 않는다(헌법 §2) — 입력 문서에서 동적으로 파악한다.
    """

    DEFAULT_MODEL = "claude-opus-4-7"

    SYSTEM_INSTRUCTION = (
        "You are a domain-agnostic academic ontology extractor. "
        "Decompose the supplied scholarly text into a knowledge graph of "
        "universal entity classes and standard relation predicates ONLY. "
        "Hard rules:\n"
        "1. Every node's paragraph_id MUST be copied verbatim from a [P_XXXX] "
        "marker that actually appears in the supplied text. Never invent a "
        "paragraph_id. If a claim has no [P_XXXX] anchor, do not emit a node "
        "for it.\n"
        "2. Do not flatten, summarize, or resolve logical tensions/aporia in "
        "the source. Preserve contradictory poles as separate nodes/edges.\n"
        "3. Do not inject domain-specific terminology or citation rules of "
        "your own; reflect only what the text states.\n"
        "4. Every edge.reasoning must quote or tightly paraphrase the "
        "supporting span from the source.\n"
        "5. Every node AND every edge MUST include a `source_quote`: a "
        "string copied VERBATIM (exact substring, <=200 chars) from the "
        "text of its cited [P_XXXX] paragraph. The mechanical auditor "
        "rejects any quote not literally present in that paragraph — do "
        "not paraphrase, normalize, or translate the source_quote.\n"
        "Return the result solely by calling the provided tool."
    )

    LENS_ANALYSIS_SYSTEM_INSTRUCTION = (
        "You are a domain-agnostic academic lens analyst. "
        "Analyze only the supplied text and lens instructions. Hard rules:\n"
        "1. Every finding must cite a paragraph_id copied verbatim from a "
        "[P_XXXX] marker in the supplied text.\n"
        "2. Every finding.source_quote must be copied verbatim from that "
        "paragraph. Do not paraphrase source_quote.\n"
        "3. Do not add claims, contexts, citations, or domain terminology not "
        "grounded in the supplied text.\n"
        "4. Preserve unresolved tensions and limitations.\n"
        "Return the result solely by calling the provided tool."
    )

    def __init__(self, api_key: str, model: str | None = None):
        if not api_key:
            raise ValueError(
                "AnthropicProvider: ANTHROPIC_API_KEY가 비어 있습니다. "
                "오프라인 실행은 router의 --mock 플래그를 사용하세요."
            )
        try:
            import anthropic
        except ModuleNotFoundError as e:
            raise ValueError(
                "AnthropicProvider: 'anthropic' 패키지가 필요합니다 "
                "(`uv run --extra llm ...` 또는 `uv sync --extra llm`). 또는 --mock 사용."
            ) from e
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model or self.DEFAULT_MODEL

    def generate_structured_output(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        tool_name = "emit_structured_output"
        system_instruction = (
            self.SYSTEM_INSTRUCTION
            if schema.__name__ == "OntologyMap"
            else self.LENS_ANALYSIS_SYSTEM_INSTRUCTION
        )
        tool = {
            "name": tool_name,
            "description": (
                "Return structured academic output strictly conforming to the "
                "input schema. This is the only allowed output channel."
            ),
            "input_schema": schema.model_json_schema(),
        }
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=16000,
                system=[
                    {
                        "type": "text",
                        "text": system_instruction,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=[tool],
                tool_choice={"type": "tool", "name": tool_name},
                messages=[{"role": "user", "content": prompt}],
            )
        except self._anthropic.APIError as e:
            raise RuntimeError(f"Anthropic API 호출 실패: {e}") from e

        tool_block = next(
            (b for b in response.content if b.type == "tool_use"), None
        )
        if tool_block is None:
            raise RuntimeError(
                f"Anthropic 응답에 tool_use 블록이 없습니다 "
                f"(stop_reason={response.stop_reason})."
            )
        # 강제 스키마 검증 — 모델이 schema를 위반하면 여기서 차단된다.
        return schema.model_validate(tool_block.input)
